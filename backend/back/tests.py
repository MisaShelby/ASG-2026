import io

from django.test import TestCase

from .services import fasta_converter, kmer, quality
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
