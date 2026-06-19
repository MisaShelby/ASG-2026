from django.db import models


# =====================================================================
#  Q1 — Ingestion & Qualité
# =====================================================================
class Dataset(models.Model):
    """Un fichier de séquençage importé (FASTQ ou FASTA)."""

    class Format(models.TextChoices):
        FASTQ = "FASTQ", "FASTQ"
        FASTA = "FASTA", "FASTA"

    class Status(models.TextChoices):
        UPLOADED = "UPLOADED", "Importé"
        PROCESSING = "PROCESSING", "En traitement"
        DONE = "DONE", "Terminé"
        ERROR = "ERROR", "Erreur"

    name = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to="uploads/")
    input_format = models.CharField(
        max_length=10, choices=Format.choices, default=Format.FASTQ
    )
    total_reads = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPLOADED
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.input_format})"


class QualityReport(models.Model):
    """Statistiques qualité agrégées d'un dataset (relation 1-1)."""

    dataset = models.OneToOneField(
        Dataset, on_delete=models.CASCADE, related_name="quality_report"
    )
    mean_quality = models.FloatField()
    min_length = models.IntegerField()
    max_length = models.IntegerField()
    mean_length = models.FloatField()
    gc_content = models.FloatField()
    per_position_quality = models.JSONField(default=list)
    length_distribution = models.JSONField(default=dict)

    def __str__(self):
        return f"Qualité de {self.dataset.name}"


class FastaConversion(models.Model):
    """Conversion sélective FASTQ -> FASTA avec filtres définis par l'utilisateur."""

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="conversions"
    )
    # Filtre principal : qualité moyenne minimale choisie par l'utilisateur
    min_mean_quality = models.IntegerField()
    # Filtre secondaire optionnel
    min_length = models.IntegerField(null=True, blank=True)
    reads_kept = models.IntegerField(default=0)
    reads_discarded = models.IntegerField(default=0)
    output_file = models.FileField(upload_to="fasta/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Conversion {self.dataset.name} (Q>={self.min_mean_quality})"


# =====================================================================
#  Q2 — Découpage en k-mers
# =====================================================================
class KmerAnalysis(models.Model):
    """Un run de découpage en k-mers pour une valeur de k (saisie par l'utilisateur)."""

    class Source(models.TextChoices):
        RAW = "RAW", "Reads bruts"
        FILTERED = "FILTERED", "Reads filtrés"

    dataset = models.ForeignKey(
        Dataset, on_delete=models.CASCADE, related_name="kmer_analyses"
    )
    k = models.IntegerField()
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.RAW
    )
    total_kmers = models.BigIntegerField(default=0)
    distinct_kmers = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["dataset", "k", "source"], name="unique_kmer_run"
            )
        ]

    def __str__(self):
        return f"k={self.k} sur {self.dataset.name} ({self.source})"


class KmerCount(models.Model):
    """Occurrences des k-mers (top-N) d'un run."""

    analysis = models.ForeignKey(
        KmerAnalysis, on_delete=models.CASCADE, related_name="counts"
    )
    sequence = models.CharField(max_length=64)
    count = models.IntegerField()

    class Meta:
        ordering = ["-count"]
        indexes = [models.Index(fields=["analysis", "-count"])]

    def __str__(self):
        return f"{self.sequence}: {self.count}"


# =====================================================================
#  Q3 — Histogramme / spectre de k-mers
# =====================================================================
class KmerSpectrumBin(models.Model):
    """Une barre du spectre : X = multiplicité, Y = nb de k-mers distincts."""

    analysis = models.ForeignKey(
        KmerAnalysis, on_delete=models.CASCADE, related_name="spectrum"
    )
    multiplicity = models.IntegerField()
    distinct_count = models.BigIntegerField()

    class Meta:
        ordering = ["multiplicity"]
        constraints = [
            models.UniqueConstraint(
                fields=["analysis", "multiplicity"], name="unique_spectrum_bin"
            )
        ]

    def __str__(self):
        return f"mult={self.multiplicity} -> {self.distinct_count}"


# =====================================================================
#  Lot 2 — Alignement par programmation dynamique (overlap alignment)
# =====================================================================
class AlignmentRun(models.Model):
    """Un calcul d'alignement de chevauchement entre deux reads (A et B)."""

    read_a_label = models.CharField(max_length=255)
    read_a_sequence = models.TextField()
    dataset_a = models.ForeignKey(
        Dataset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="alignments_as_a",
    )
    read_a_index = models.IntegerField(null=True, blank=True)

    read_b_label = models.CharField(max_length=255)
    read_b_sequence = models.TextField()
    dataset_b = models.ForeignKey(
        Dataset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="alignments_as_b",
    )
    read_b_index = models.IntegerField(null=True, blank=True)

    # Score pondéré : match=+1, mismatch=-1, gap=-2
    score = models.IntegerField()
    read_a_start = models.IntegerField(null=True, blank=True)
    read_a_end = models.IntegerField(null=True, blank=True)
    read_b_start = models.IntegerField(null=True, blank=True)
    read_b_end = models.IntegerField(null=True, blank=True)

    aligned_a = models.TextField()
    match_line = models.TextField()
    aligned_b = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.read_a_label} x {self.read_b_label} (score={self.score})"
