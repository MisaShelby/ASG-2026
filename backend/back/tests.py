import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AlignmentRun, Dataset
from .services import alignment, fasta_converter, kmer, quality, read_access
from .services.fastq_parser import decode_quality, parse_fasta, parse_fastq

FASTQ_SAMPLE = """@read1
ATGCATGC
+
IIIIIIII
@read2
GGGGCCCC
+
!!!!!!!!
@read3
ATGCATGC
+
IIIIIIII
"""


class FastqParserTests(TestCase):
    def test_decode_quality(self):
        # 'I' = 73 -> 73-33 = 40 ; '!' = 33 -> 0
        self.assertEqual(decode_quality("I!"), [40, 0])

    def test_parse_fastq(self):
        reads = list(parse_fastq(io.StringIO(FASTQ_SAMPLE)))
        self.assertEqual(len(reads), 3)
        self.assertEqual(reads[0].identifier, "read1")
        self.assertEqual(reads[0].sequence, "ATGCATGC")
        self.assertEqual(reads[0].qualities, [40] * 8)

    def test_parse_fastq_length_mismatch(self):
        bad = "@r\nATGC\n+\nII\n"
        with self.assertRaises(ValueError):
            list(parse_fastq(io.StringIO(bad)))

    def test_parse_fasta(self):
        fasta = ">r1\nATGC\nATGC\n>r2\nGGCC\n"
        reads = list(parse_fasta(io.StringIO(fasta)))
        self.assertEqual(len(reads), 2)
        self.assertEqual(reads[0].sequence, "ATGCATGC")


class QualityTests(TestCase):
    def test_quality_report(self):
        reads = list(parse_fastq(io.StringIO(FASTQ_SAMPLE)))
        report = quality.compute_quality_report(reads)
        self.assertEqual(report["total_reads"], 3)
        self.assertEqual(report["min_length"], 8)
        self.assertEqual(report["max_length"], 8)
        # read2 a une qualité 0, les autres 40 -> moyenne globale = (40+40+0)/3
        self.assertAlmostEqual(report["mean_quality"], round((40 + 40 + 0) / 3, 2))
        self.assertEqual(len(report["per_position_quality"]), 8)


class FastaConverterTests(TestCase):
    def test_selective_conversion_by_quality(self):
        out = io.StringIO()
        # seuil 30 -> read2 (qualité 0) rejeté, read1 & read3 conservés
        kept, discarded = fasta_converter.convert_fastq_to_fasta(
            io.StringIO(FASTQ_SAMPLE), out, min_mean_quality=30
        )
        self.assertEqual(kept, 2)
        self.assertEqual(discarded, 1)
        self.assertIn(">read1", out.getvalue())
        self.assertNotIn(">read2", out.getvalue())

    def test_min_length_filter(self):
        out = io.StringIO()
        kept, discarded = fasta_converter.convert_fastq_to_fasta(
            io.StringIO(FASTQ_SAMPLE), out, min_mean_quality=0, min_length=100
        )
        self.assertEqual(kept, 0)
        self.assertEqual(discarded, 3)


class KmerTests(TestCase):
    def test_count_and_spectrum(self):
        reads = list(parse_fastq(io.StringIO(FASTQ_SAMPLE)))
        result = kmer.analyze(reads, k=4)
        # ATGCATGC (x2) et GGGGCCCC : k=4 -> 5 kmers chacun = 15 au total
        self.assertEqual(result["total_kmers"], 15)
        # spectre : somme des distinct_count = nb de kmers distincts
        self.assertEqual(
            sum(result["spectrum"].values()), result["distinct_kmers"]
        )

    def test_invalid_k(self):
        with self.assertRaises(ValueError):
            kmer.count_kmers([], 0)


class OverlapAlignTests(TestCase):
    """Lot 2 — alignement de chevauchement (overlap, bords libres)."""

    def test_clean_overlap_no_error(self):
        # suffixe de A "CCCC" == préfixe de B "CCCC" : chevauchement net
        result = alignment.overlap_align("AAAACCCC", "CCCCGGGG")
        self.assertEqual(result["score"], 4)
        self.assertEqual((result["a_start"], result["a_end"]), (5, 8))
        self.assertEqual((result["b_start"], result["b_end"]), (1, 4))
        self.assertEqual(result["match_line"], "||||")

    def test_overlap_with_one_mismatch(self):
        # suffixe de A "CCCT" vs préfixe de B "CCCC" : 1 erreur tolérée
        result = alignment.overlap_align("AAAACCCT", "CCCCGGGG")
        # 3 matches (+1) + 1 mismatch (-1) = 2
        self.assertEqual(result["score"], 2)
        self.assertEqual(result["match_line"], "|||.")

    def test_no_overlap(self):
        result = alignment.overlap_align("AAAA", "GGGG")
        self.assertEqual(result["score"], 0)
        self.assertIsNone(result["a_start"])
        self.assertEqual(result["aligned_a"], "")

    def test_full_containment(self):
        # A entièrement contenu au milieu de B (pas seulement à un bord)
        result = alignment.overlap_align("CCCC", "AACCCCGG")
        self.assertEqual(result["score"], 4)
        self.assertEqual((result["a_start"], result["a_end"]), (1, 4))
        self.assertEqual((result["b_start"], result["b_end"]), (3, 6))


FASTQ_TWO_READS = """@r1
AAAACCCC
+
IIIIIIII
@r2
CCCCGGGG
+
IIIIIIII
"""


class ReadAccessTests(TestCase):
    def setUp(self):
        self.dataset = Dataset.objects.create(
            name="ds",
            original_filename="ds.fastq",
            file=SimpleUploadedFile("ds.fastq", FASTQ_TWO_READS.encode()),
            input_format=Dataset.Format.FASTQ,
        )

    def test_get_read_at(self):
        read = read_access.get_read_at(self.dataset, 1)
        self.assertEqual(read.identifier, "r2")
        self.assertEqual(read.sequence, "CCCCGGGG")

    def test_get_read_at_out_of_range(self):
        with self.assertRaises(IndexError):
            read_access.get_read_at(self.dataset, 5)

    def test_preview_reads(self):
        previews = read_access.preview_reads(self.dataset, limit=10, offset=0)
        self.assertEqual(len(previews), 2)
        self.assertEqual(previews[0]["identifier"], "r1")
        self.assertEqual(previews[0]["length"], 8)

    def test_get_reads_at_batch_single_pass(self):
        reads = read_access.get_reads_at(self.dataset, [1, 0])
        self.assertEqual(reads[0].identifier, "r1")
        self.assertEqual(reads[1].identifier, "r2")


class AlignmentApiTests(TestCase):
    """Tests d'intégration des endpoints Lot 2 (lecture par index, création)."""

    def setUp(self):
        self.client = APIClient()
        self.dataset = Dataset.objects.create(
            name="ds",
            original_filename="ds.fastq",
            file=SimpleUploadedFile("ds.fastq", FASTQ_TWO_READS.encode()),
            input_format=Dataset.Format.FASTQ,
        )

    def test_list_reads_preview(self):
        res = self.client.get(f"/api/datasets/{self.dataset.id}/reads/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 2)

    def test_read_at_index(self):
        res = self.client.get(f"/api/datasets/{self.dataset.id}/reads/1/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["identifier"], "r2")
        self.assertEqual(res.data["sequence"], "CCCCGGGG")

    def test_read_at_index_out_of_range(self):
        res = self.client.get(f"/api/datasets/{self.dataset.id}/reads/9/")
        self.assertEqual(res.status_code, 404)

    def test_list_reads_rejects_non_numeric_limit(self):
        res = self.client.get(f"/api/datasets/{self.dataset.id}/reads/?limit=abc")
        self.assertEqual(res.status_code, 400)

    def test_list_reads_rejects_negative_offset(self):
        res = self.client.get(f"/api/datasets/{self.dataset.id}/reads/?offset=-1")
        self.assertEqual(res.status_code, 400)

    def test_create_alignment_from_dataset_reads(self):
        payload = {
            "read_a": {"dataset": self.dataset.id, "index": 0},
            "read_b": {"dataset": self.dataset.id, "index": 1},
        }
        res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["score"], 4)
        self.assertEqual(AlignmentRun.objects.count(), 1)

    def test_create_alignment_from_manual_sequences(self):
        payload = {
            "read_a": {"sequence": "AAAACCCC"},
            "read_b": {"sequence": "CCCCGGGG"},
        }
        res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["score"], 4)
        self.assertIsNone(res.data["dataset_a"])

    def test_create_alignment_rejects_both_modes(self):
        payload = {
            "read_a": {"dataset": self.dataset.id, "index": 0, "sequence": "ACGT"},
            "read_b": {"sequence": "CCCCGGGG"},
        }
        res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_create_alignment_rejects_too_long_sequence(self):
        payload = {
            "read_a": {"sequence": "A" * 5001},
            "read_b": {"sequence": "CCCCGGGG"},
        }
        res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_create_alignment_rejects_combined_size_too_costly(self):
        # chaque read est sous la limite individuelle (5000 nt) mais le
        # produit des deux longueurs dépasse alignment.MAX_CELLS
        payload = {
            "read_a": {"sequence": "A" * 3000},
            "read_b": {"sequence": "A" * 3000},
        }
        res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 400)

    def test_create_alignment_same_dataset_reads_file_once(self):
        payload = {
            "read_a": {"dataset": self.dataset.id, "index": 0},
            "read_b": {"dataset": self.dataset.id, "index": 1},
        }
        with patch(
            "back.views.read_access.get_reads_at", wraps=read_access.get_reads_at
        ) as batch, patch("back.views.read_access.get_read_at") as single:
            res = self.client.post("/api/alignments/", payload, format="json")
        self.assertEqual(res.status_code, 201)
        batch.assert_called_once()
        single.assert_not_called()

    def test_list_alignment_history(self):
        AlignmentRun.objects.create(
            read_a_label="A", read_a_sequence="AAAA",
            read_b_label="B", read_b_sequence="AAAA",
            score=4, aligned_a="AAAA", match_line="||||", aligned_b="AAAA",
        )
        res = self.client.get("/api/alignments/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)


from .services import bloom


class BloomFilterTests(TestCase):
    def test_no_false_negatives(self):
        bf = bloom.BloomFilter(num_bits=10_000, num_hashes=4)
        items = [f"ACGT{i}" for i in range(500)]
        for it in items:
            bf.add(it)
        for it in items:
            self.assertIn(it, bf)

    def test_membership_false_before_add(self):
        bf = bloom.BloomFilter(num_bits=10_000, num_hashes=4)
        bf.add("AAAA")
        # Un element non insere est tres probablement absent avec ce dimensionnement.
        self.assertNotIn("TTTT", bf)

    def test_byte_size_matches_bits(self):
        bf = bloom.BloomFilter(num_bits=16, num_hashes=3)
        self.assertEqual(bf.byte_size(), 2)  # 16 bits = 2 octets

    def test_estimated_fp_rate_increases_with_load(self):
        bf = bloom.BloomFilter(num_bits=1_000, num_hashes=3)
        low = bf.estimated_fp_rate(50)
        high = bf.estimated_fp_rate(500)
        self.assertTrue(0.0 <= low < high < 1.0)

    def test_optimal_params(self):
        m, k = bloom.optimal_params(n=1000, p=0.01)
        self.assertGreater(m, 1000)
        self.assertGreaterEqual(k, 1)

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            bloom.BloomFilter(num_bits=0, num_hashes=1)
        with self.assertRaises(ValueError):
            bloom.BloomFilter(num_bits=10, num_hashes=0)


from collections import Counter

from .services import assembly


class AssemblyTraversalTests(TestCase):
    def test_select_solid_kmers(self):
        counter = Counter({"AAA": 5, "AAC": 1, "ACG": 3})
        self.assertEqual(
            assembly.select_solid_kmers(counter, threshold=3),
            {"AAA", "ACG"},
        )

    def test_select_solid_kmers_invalid_threshold(self):
        with self.assertRaises(ValueError):
            assembly.select_solid_kmers(Counter(), threshold=0)

    def test_successors_and_predecessors(self):
        oracle = {"ATG", "TGC", "TGA", "CAT"}  # set = oracle de test
        # successeurs de "CAT" : suffixe "AT" + base -> ATG present, pas ATA/ATC/ATT
        self.assertEqual(sorted(assembly.successors("CAT", oracle)), ["ATG"])
        # successeurs de "ATG" : "TG"+base -> TGC, TGA presents (embranchement)
        self.assertEqual(sorted(assembly.successors("ATG", oracle)), ["TGA", "TGC"])
        # predecesseurs de "ATG" : base+"AT" -> CAT present
        self.assertEqual(sorted(assembly.predecessors("ATG", oracle)), ["CAT"])

    def test_build_contig_linear_path(self):
        # Chaine lineaire de 3-mers couvrant "ACGTAC"
        oracle = {"ACG", "CGT", "GTA", "TAC"}
        visited = set()
        contig = assembly.build_contig("ACG", oracle, visited)
        self.assertEqual(contig, "ACGTAC")
        # tous les k-mers du chemin sont marques visites
        self.assertEqual(visited, oracle)

    def test_build_contig_stops_at_branch(self):
        # Apres "ACG"->"CGT", "GT" s'etend en GTA et GTC : embranchement -> arret
        oracle = {"ACG", "CGT", "GTA", "GTC"}
        visited = set()
        contig = assembly.build_contig("ACG", oracle, visited)
        self.assertEqual(contig, "ACGT")  # s'arrete avant la bifurcation

    def test_build_contig_starts_from_visited_is_seed_only(self):
        oracle = {"ACG", "CGT"}
        visited = {"CGT"}
        contig = assembly.build_contig("ACG", oracle, visited)
        # successeur unique CGT deja visite -> on ne l'etend pas
        self.assertEqual(contig, "ACG")
