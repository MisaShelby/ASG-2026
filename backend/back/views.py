import io

from django.core.files.base import ContentFile
from django.http import FileResponse, Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .models import (
    AlignmentRun,
    Dataset,
    FastaConversion,
    KmerAnalysis,
    KmerCount,
    KmerSpectrumBin,
    QualityReport,
)
from .serializers import (
    MAX_READ_LENGTH,
    AlignmentCreateSerializer,
    AlignmentRunSerializer,
    DatasetSerializer,
    DatasetUploadSerializer,
    FastaConversionSerializer,
    KmerAnalysisSerializer,
    KmerCountSerializer,
    KmerSpectrumBinSerializer,
    QualityReportSerializer,
    ReadDetailSerializer,
    ReadPreviewSerializer,
)
from .services import alignment, fasta_converter, kmer, quality, read_access
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

    @action(detail=True, methods=["get"], url_path="reads")
    def reads(self, request, pk=None):
        """Lot 2 — Aperçu paginé des reads du dataset (pour le sélecteur)."""
        dataset = self.get_object()
        try:
            limit = int(request.query_params.get("limit", 50))
            offset = int(request.query_params.get("offset", 0))
        except ValueError:
            raise ValidationError({"detail": "limit et offset doivent être des entiers."})
        if limit <= 0 or offset < 0:
            raise ValidationError({"detail": "limit doit être > 0, offset doit être >= 0."})
        previews = read_access.preview_reads(dataset, limit=limit, offset=offset)
        return Response(ReadPreviewSerializer(previews, many=True).data)

    @action(detail=True, methods=["get"], url_path=r"reads/(?P<index>\d+)")
    def read_at(self, request, pk=None, index=None):
        """Lot 2 — Récupère un read complet par index (relu à la volée)."""
        dataset = self.get_object()
        idx = int(index)
        try:
            read = read_access.get_read_at(dataset, idx)
        except IndexError:
            return Response(
                {"detail": "Aucun read à cet index."}, status=status.HTTP_404_NOT_FOUND
            )
        data = {
            "index": idx,
            "identifier": read.identifier,
            "sequence": read.sequence,
            "length": len(read.sequence),
        }
        return Response(ReadDetailSerializer(data).data)


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


class AlignmentRunViewSet(viewsets.ModelViewSet):
    """Lot 2 — Alignement de chevauchement entre deux reads + historique."""

    queryset = AlignmentRun.objects.all()
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return AlignmentCreateSerializer
        return AlignmentRunSerializer

    def create(self, request, *args, **kwargs):
        serializer = AlignmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        read_a_data = serializer.validated_data["read_a"]
        read_b_data = serializer.validated_data["read_b"]
        cache = self._prefetch_shared_dataset(read_a_data, read_b_data)

        label_a, seq_a, dataset_a, index_a = self._resolve_read(read_a_data, "a", cache)
        label_b, seq_b, dataset_b, index_b = self._resolve_read(read_b_data, "b", cache)

        if len(seq_a) * len(seq_b) > alignment.MAX_CELLS:
            raise ValidationError(
                {
                    "detail": (
                        f"Combinaison trop coûteuse pour ce prototype "
                        f"({len(seq_a)}×{len(seq_b)} nt) — réduisez la longueur "
                        f"d'au moins un des deux reads."
                    )
                }
            )

        result = alignment.overlap_align(seq_a, seq_b)
        run = AlignmentRun.objects.create(
            read_a_label=label_a,
            read_a_sequence=seq_a,
            dataset_a=dataset_a,
            read_a_index=index_a,
            read_b_label=label_b,
            read_b_sequence=seq_b,
            dataset_b=dataset_b,
            read_b_index=index_b,
            score=result["score"],
            read_a_start=result["a_start"],
            read_a_end=result["a_end"],
            read_b_start=result["b_start"],
            read_b_end=result["b_end"],
            aligned_a=result["aligned_a"],
            match_line=result["match_line"],
            aligned_b=result["aligned_b"],
        )
        return Response(
            AlignmentRunSerializer(run).data, status=status.HTTP_201_CREATED
        )

    def _prefetch_shared_dataset(self, read_a_data, read_b_data):
        """Si les deux reads viennent du même dataset, relit le fichier une
        seule fois pour les deux index au lieu de deux passages séparés."""
        dataset_a = read_a_data.get("dataset")
        dataset_b = read_b_data.get("dataset")
        index_a = read_a_data.get("index")
        index_b = read_b_data.get("index")
        if dataset_a is not None and dataset_a == dataset_b:
            return read_access.get_reads_at(dataset_a, [index_a, index_b])
        return None

    def _resolve_read(self, data, letter, cache=None):
        """Construit (label, séquence, dataset, index) depuis dataset+index ou sequence."""
        dataset = data.get("dataset")
        index = data.get("index")
        if dataset is not None and index is not None:
            try:
                if cache is not None and index in cache:
                    read = cache[index]
                else:
                    read = read_access.get_read_at(dataset, index)
            except IndexError as exc:
                raise ValidationError({f"read_{letter}": str(exc)})
            if len(read.sequence) > MAX_READ_LENGTH:
                raise ValidationError(
                    {
                        f"read_{letter}": (
                            f"Read trop long ({len(read.sequence)} nt) — "
                            f"limite {MAX_READ_LENGTH} nt."
                        )
                    }
                )
            return f"{dataset.name} — read #{index}", read.sequence, dataset, index
        return f"Read {letter.upper()} (manuel)", data["sequence"], None, None
