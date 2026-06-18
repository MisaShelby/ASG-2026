import io

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import (
    Dataset,
    FastaConversion,
    KmerAnalysis,
    KmerCount,
    KmerSpectrumBin,
    QualityReport,
)
from .serializers import (
    DatasetSerializer,
    DatasetUploadSerializer,
    FastaConversionSerializer,
    KmerAnalysisSerializer,
    KmerCountSerializer,
    KmerSpectrumBinSerializer,
    QualityReportSerializer,
)
from .services import fasta_converter, kmer, quality
from .services.fastq_parser import parse

TOP_N = 1000


class DatasetViewSet(viewsets.ModelViewSet):
    """Q1 — Ingestion : upload d'un FASTQ/FASTA + rapport qualité + conversion."""

    queryset = Dataset.objects.all()

    def get_serializer_class(self):
        if self.action == "create":
            return DatasetUploadSerializer
        return DatasetSerializer

    def perform_create(self, serializer):
        dataset = serializer.save(
            original_filename=serializer.validated_data["file"].name,
            status=Dataset.Status.PROCESSING,
        )
        self._ingest(dataset)

    def _ingest(self, dataset):
        """Calcule le rapport qualité et le nombre de reads après upload.

        Un fichier mal formé (ValueError) marque le dataset en ERROR sans
        faire échouer l'upload ; les autres erreurs (serveur) remontent.
        """
        try:
            with dataset.file.open("rt") as handle:
                report = quality.compute_quality_report(
                    parse(handle, dataset.input_format)
                )
            dataset.total_reads = report.pop("total_reads", 0)
            QualityReport.objects.update_or_create(
                dataset=dataset, defaults=report
            )
            dataset.status = Dataset.Status.DONE
        except ValueError:
            # Fichier invalide / format incorrect : erreur côté utilisateur.
            dataset.status = Dataset.Status.ERROR
        except Exception:
            dataset.status = Dataset.Status.ERROR
            raise
        finally:
            dataset.save()

    @action(detail=True, methods=["get"])
    def quality(self, request, pk=None):
        dataset = self.get_object()
        report = getattr(dataset, "quality_report", None)
        if report is None:
            return Response(
                {"detail": "Aucun rapport qualité disponible."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(QualityReportSerializer(report).data)

    @action(detail=True, methods=["post"])
    def convert(self, request, pk=None):
        """Conversion sélective FASTQ -> FASTA avec filtres utilisateur."""
        dataset = self.get_object()
        if dataset.input_format != Dataset.Format.FASTQ:
            return Response(
                {"detail": "La conversion sélective nécessite un fichier FASTQ."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FastaConversionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        min_mean_quality = serializer.validated_data["min_mean_quality"]
        min_length = serializer.validated_data.get("min_length")

        out_buffer = io.StringIO()
        with dataset.file.open("rt") as handle:
            kept, discarded = fasta_converter.convert_fastq_to_fasta(
                handle, out_buffer, min_mean_quality, min_length
            )

        conversion = FastaConversion(
            dataset=dataset,
            min_mean_quality=min_mean_quality,
            min_length=min_length,
            reads_kept=kept,
            reads_discarded=discarded,
        )
        filename = f"{dataset.id}_q{min_mean_quality}.fasta"
        conversion.output_file.save(
            filename, ContentFile(out_buffer.getvalue().encode()), save=False
        )
        conversion.save()
        return Response(
            FastaConversionSerializer(conversion).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def kmers(self, request, pk=None):
        """Q2 — Lance un découpage en k-mers (k saisi par l'utilisateur)."""
        dataset = self.get_object()
        serializer = KmerAnalysisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        k = serializer.validated_data["k"]
        source = serializer.validated_data.get("source", KmerAnalysis.Source.RAW)

        if k < 1:
            return Response(
                {"detail": "k doit être >= 1."}, status=status.HTTP_400_BAD_REQUEST
            )

        with dataset.file.open("rt") as handle:
            result = kmer.analyze(parse(handle, dataset.input_format), k, top_n=TOP_N)

        analysis, _ = KmerAnalysis.objects.update_or_create(
            dataset=dataset,
            k=k,
            source=source,
            defaults={
                "total_kmers": result["total_kmers"],
                "distinct_kmers": result["distinct_kmers"],
            },
        )
        # On reconstruit les comptages et le spectre liés à ce run
        analysis.counts.all().delete()
        analysis.spectrum.all().delete()
        KmerCount.objects.bulk_create(
            [
                KmerCount(analysis=analysis, sequence=seq, count=cnt)
                for seq, cnt in result["top"]
            ]
        )
        KmerSpectrumBin.objects.bulk_create(
            [
                KmerSpectrumBin(
                    analysis=analysis, multiplicity=mult, distinct_count=dc
                )
                for mult, dc in result["spectrum"].items()
            ]
        )
        return Response(
            KmerAnalysisSerializer(analysis).data, status=status.HTTP_201_CREATED
        )


class FastaConversionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = FastaConversion.objects.all()
    serializer_class = FastaConversionSerializer

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        conversion = self.get_object()
        if not conversion.output_file:
            raise Http404("Aucun fichier FASTA généré.")
        return FileResponse(
            conversion.output_file.open("rb"),
            as_attachment=True,
            filename=conversion.output_file.name.split("/")[-1],
        )


class KmerAnalysisViewSet(viewsets.ReadOnlyModelViewSet):
    """Q2/Q3 — Consultation des runs k-mers, top k-mers et spectre."""

    queryset = KmerAnalysis.objects.all()
    serializer_class = KmerAnalysisSerializer

    @action(detail=True, methods=["get"])
    def top(self, request, pk=None):
        analysis = self.get_object()
        return Response(KmerCountSerializer(analysis.counts.all(), many=True).data)

    @action(detail=True, methods=["get"])
    def spectrum(self, request, pk=None):
        analysis = self.get_object()
        return Response(
            KmerSpectrumBinSerializer(analysis.spectrum.all(), many=True).data
        )
