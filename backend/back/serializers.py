from rest_framework import serializers

from .models import (
    AlignmentRun,
    AssemblyRun,
    Contig,
    Dataset,
    FastaConversion,
    KmerAnalysis,
    KmerCount,
    KmerSpectrumBin,
    QualityReport,
)


class QualityReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityReport
        exclude = ["id", "dataset"]


class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "original_filename",
            "file",
            "input_format",
            "total_reads",
            "status",
            "error_message",
            "created_at",
        ]
        read_only_fields = [
            "original_filename", "total_reads", "status", "error_message", "created_at",
        ]


class DatasetUploadSerializer(serializers.ModelSerializer):
    """Upload d'un fichier FASTQ/FASTA."""

    class Meta:
        model = Dataset
        fields = ["id", "name", "file", "input_format", "status", "error_message"]
        read_only_fields = ["status", "error_message"]


class FastaConversionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FastaConversion
        fields = [
            "id",
            "dataset",
            "min_mean_quality",
            "min_length",
            "reads_kept",
            "reads_discarded",
            "output_file",
            "created_at",
        ]
        read_only_fields = [
            "dataset",
            "reads_kept",
            "reads_discarded",
            "output_file",
            "created_at",
        ]


class KmerCountSerializer(serializers.ModelSerializer):
    class Meta:
        model = KmerCount
        fields = ["sequence", "count"]


class KmerSpectrumBinSerializer(serializers.ModelSerializer):
    class Meta:
        model = KmerSpectrumBin
        fields = ["multiplicity", "distinct_count"]


class KmerAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = KmerAnalysis
        fields = [
            "id",
            "dataset",
            "k",
            "source",
            "total_kmers",
            "distinct_kmers",
            "created_at",
        ]
        read_only_fields = ["dataset", "total_kmers", "distinct_kmers", "created_at"]


# =====================================================================
#  Lot 2 — Alignement de chevauchement
# =====================================================================
MAX_READ_LENGTH = 5000


class ReadPreviewSerializer(serializers.Serializer):
    """Aperçu d'un read pour le sélecteur frontend (pas un modèle)."""

    index = serializers.IntegerField()
    identifier = serializers.CharField()
    length = serializers.IntegerField()
    preview = serializers.CharField()


class ReadDetailSerializer(serializers.Serializer):
    """Read complet (identifiant + séquence) récupéré par index."""

    index = serializers.IntegerField()
    identifier = serializers.CharField()
    sequence = serializers.CharField()
    length = serializers.IntegerField()


class ReadInputSerializer(serializers.Serializer):
    """Un read fourni soit par référence (dataset+index), soit en saisie libre."""

    dataset = serializers.PrimaryKeyRelatedField(
        queryset=Dataset.objects.all(), required=False, allow_null=True
    )
    index = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    sequence = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        has_ref = attrs.get("dataset") is not None and attrs.get("index") is not None
        has_sequence = bool(attrs.get("sequence"))
        if has_ref == has_sequence:
            raise serializers.ValidationError(
                "Fournir soit 'dataset' + 'index', soit 'sequence' (l'un des deux, pas les deux)."
            )
        if has_sequence:
            cleaned = "".join(attrs["sequence"].split()).upper()
            if not cleaned:
                raise serializers.ValidationError("La séquence saisie est vide.")
            if len(cleaned) > MAX_READ_LENGTH:
                raise serializers.ValidationError(
                    f"Séquence trop longue ({len(cleaned)} nt) — limite {MAX_READ_LENGTH} nt."
                )
            attrs["sequence"] = cleaned
        return attrs


class AlignmentCreateSerializer(serializers.Serializer):
    """Payload de création d'un alignement : deux reads (A et B)."""

    read_a = ReadInputSerializer()
    read_b = ReadInputSerializer()


class AlignmentRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlignmentRun
        fields = [
            "id",
            "read_a_label",
            "read_a_sequence",
            "dataset_a",
            "read_a_index",
            "read_b_label",
            "read_b_sequence",
            "dataset_b",
            "read_b_index",
            "score",
            "read_a_start",
            "read_a_end",
            "read_b_start",
            "read_b_end",
            "aligned_a",
            "match_line",
            "aligned_b",
            "created_at",
        ]
        read_only_fields = fields


class ContigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contig
        fields = ["index", "sequence", "length", "identity_to_reference"]


class AssemblyRunSerializer(serializers.ModelSerializer):
    contigs = ContigSerializer(many=True, read_only=True)

    class Meta:
        model = AssemblyRun
        fields = [
            "id", "dataset", "source", "k", "solidity_threshold",
            "bloom_bits", "num_hashes", "distinct_kmers", "solid_kmers",
            "bloom_fp_rate", "bloom_bytes", "dict_bytes_estimate",
            "num_contigs", "max_contig_length", "total_contig_length",
            "reference_sequence", "best_identity", "status", "created_at",
            "contigs",
        ]


class AssemblyCreateSerializer(serializers.Serializer):
    dataset = serializers.PrimaryKeyRelatedField(queryset=Dataset.objects.all())
    source = serializers.ChoiceField(
        choices=AssemblyRun.Source.choices, default=AssemblyRun.Source.RAW
    )
    k = serializers.IntegerField(min_value=2, max_value=64)
    solidity_threshold = serializers.IntegerField(min_value=1, default=2)
    bloom_bits = serializers.IntegerField(
        min_value=8, max_value=200_000_000, required=False
    )
    num_hashes = serializers.IntegerField(
        min_value=1, max_value=20, required=False
    )
    reference_sequence = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True
    )

    def validate_reference_sequence(self, value):
        # Normalisation cohérente avec ReadInputSerializer (Lot 2) : on retire
        # tout blanc interne (retours à la ligne d'un FASTA collé) et on met en
        # majuscules, car les contigs sont construits à partir de reads en
        # majuscules (fastq_parser applique .upper()).
        return "".join(value.split()).upper()
