"""Calcul des statistiques qualité d'un jeu de reads FASTQ."""
from collections import defaultdict

from .fastq_parser import Read


def mean_quality(read: Read) -> float:
    """Qualité Phred moyenne d'un read (0.0 si pas de scores)."""
    if not read.qualities:
        return 0.0
    return sum(read.qualities) / len(read.qualities)


def compute_quality_report(reads) -> dict:
    """Agrège les statistiques qualité sur un itérable de Reads.

    Retourne un dict prêt à alimenter le modèle QualityReport :
    mean_quality, min/max/mean_length, gc_content,
    per_position_quality (liste) et length_distribution (dict).
    """
    total_reads = 0
    total_bases = 0
    total_quality = 0.0
    gc_count = 0
    min_length = None
    max_length = 0
    length_distribution: dict[int, int] = defaultdict(int)

    # qualité par position : somme et compte pour faire la moyenne ensuite
    pos_sum: dict[int, int] = defaultdict(int)
    pos_count: dict[int, int] = defaultdict(int)

    for read in reads:
        total_reads += 1
        length = len(read.sequence)
        total_bases += length
        max_length = max(max_length, length)
        min_length = length if min_length is None else min(min_length, length)
        length_distribution[length] += 1
        gc_count += read.sequence.count("G") + read.sequence.count("C")

        for i, q in enumerate(read.qualities):
            total_quality += q
            pos_sum[i] += q
            pos_count[i] += 1

    if total_reads == 0:
        return {
            "mean_quality": 0.0,
            "min_length": 0,
            "max_length": 0,
            "mean_length": 0.0,
            "gc_content": 0.0,
            "per_position_quality": [],
            "length_distribution": {},
        }

    total_quality_bases = sum(pos_count.values())
    per_position_quality = [
        round(pos_sum[i] / pos_count[i], 2) for i in sorted(pos_sum)
    ]

    return {
        "mean_quality": round(total_quality / total_quality_bases, 2)
        if total_quality_bases
        else 0.0,
        "min_length": min_length or 0,
        "max_length": max_length,
        "mean_length": round(total_bases / total_reads, 2),
        "gc_content": round(100 * gc_count / total_bases, 2) if total_bases else 0.0,
        "per_position_quality": per_position_quality,
        # clés en str pour la sérialisation JSON
        "length_distribution": {str(k): v for k, v in sorted(length_distribution.items())},
        "total_reads": total_reads,
    }
