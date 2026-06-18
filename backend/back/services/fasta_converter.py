"""Conversion sélective FASTQ -> FASTA.

Les filtres sont définis par l'utilisateur :
  - filtre principal : qualité moyenne minimale (min_mean_quality)
  - filtre secondaire optionnel : longueur minimale (min_length)
"""
from .fastq_parser import parse_fastq
from .quality import mean_quality


def convert_fastq_to_fasta(in_handle, out_handle, min_mean_quality, min_length=None):
    """Lit un FASTQ, écrit en FASTA les reads qui passent les filtres.

    Retourne (reads_kept, reads_discarded).
    """
    reads_kept = 0
    reads_discarded = 0

    for read in parse_fastq(in_handle):
        if mean_quality(read) < min_mean_quality:
            reads_discarded += 1
            continue
        if min_length is not None and len(read.sequence) < min_length:
            reads_discarded += 1
            continue

        out_handle.write(f">{read.identifier}\n{read.sequence}\n")
        reads_kept += 1

    return reads_kept, reads_discarded
