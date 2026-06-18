from rest_framework import serializers

from .models import (
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
            "created_at",
        ]
        read_only_fields = ["original_filename", "total_reads", "status", "created_at"]


class DatasetUploadSerializer(serializers.ModelSerializer):
    """Upload d'un fichier FASTQ/FASTA."""

    class Meta:
        model = Dataset
        fields = ["id", "name", "file", "input_format"]


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
