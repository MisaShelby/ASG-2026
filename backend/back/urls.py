from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AlignmentRunViewSet,
    DatasetViewSet,
    FastaConversionViewSet,
    KmerAnalysisViewSet,
)

router = DefaultRouter()
router.register(r"datasets", DatasetViewSet, basename="dataset")
router.register(r"conversions", FastaConversionViewSet, basename="conversion")
router.register(r"kmer-analyses", KmerAnalysisViewSet, basename="kmeranalysis")
router.register(r"alignments", AlignmentRunViewSet, basename="alignmentrun")

urlpatterns = [
    path("", include(router.urls)),
]
