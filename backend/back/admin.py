from django.contrib import admin

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


@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "input_format", "total_reads", "status", "created_at")
    list_filter = ("input_format", "status")
    search_fields = ("name", "original_filename")


@admin.register(QualityReport)
class QualityReportAdmin(admin.ModelAdmin):
    list_display = ("dataset", "mean_quality", "mean_length", "gc_content")


@admin.register(FastaConversion)
class FastaConversionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "dataset",
        "min_mean_quality",
        "min_length",
        "reads_kept",
        "reads_discarded",
        "created_at",
    )


@admin.register(KmerAnalysis)
class KmerAnalysisAdmin(admin.ModelAdmin):
    list_display = ("id", "dataset", "k", "source", "total_kmers", "distinct_kmers")
    list_filter = ("source", "k")


@admin.register(KmerCount)
class KmerCountAdmin(admin.ModelAdmin):
    list_display = ("analysis", "sequence", "count")


@admin.register(KmerSpectrumBin)
class KmerSpectrumBinAdmin(admin.ModelAdmin):
    list_display = ("analysis", "multiplicity", "distinct_count")


@admin.register(AlignmentRun)
class AlignmentRunAdmin(admin.ModelAdmin):
    list_display = ("id", "read_a_label", "read_b_label", "score", "created_at")
    search_fields = ("read_a_label", "read_b_label")


class ContigInline(admin.TabularInline):
    model = Contig
    extra = 0


@admin.register(AssemblyRun)
class AssemblyRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "k", "solidity_threshold", "num_contigs",
        "best_identity", "created_at",
    )
    inlines = [ContigInline]
