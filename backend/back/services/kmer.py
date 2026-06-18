"""Découpage en k-mers, comptage et construction du spectre.

k est paramétrable (saisi par l'utilisateur).
Le spectre de k-mers (histogramme) associe à chaque multiplicité
(nombre d'occurrences) le nombre de k-mers distincts qui l'atteignent.
"""
from collections import Counter

from .fastq_parser import Read


def iter_kmers(sequence: str, k: int):
    """Génère les k-mers d'une séquence par fenêtre glissante."""
    for i in range(len(sequence) - k + 1):
        yield sequence[i : i + k]


def count_kmers(reads, k: int) -> Counter:
    """Compte tous les k-mers sur un itérable de Reads pour un k donné."""
    if k < 1:
        raise ValueError("k doit être >= 1")
    counter: Counter = Counter()
    for read in reads:
        if len(read.sequence) >= k:
            counter.update(iter_kmers(read.sequence, k))
    return counter


def build_spectrum(counter: Counter) -> dict[int, int]:
    """Spectre : {multiplicité: nb de k-mers distincts ayant cette multiplicité}."""
    spectrum: Counter = Counter()
    for occurrences in counter.values():
        spectrum[occurrences] += 1
    return dict(sorted(spectrum.items()))


def analyze(reads, k: int, top_n: int = 1000) -> dict:
    """Analyse complète : comptage + agrégats + top-N + spectre.

    Retourne un dict :
      total_kmers, distinct_kmers, top (liste (sequence, count)), spectrum (dict).
    """
    counter = count_kmers(reads, k)
    total_kmers = sum(counter.values())
    distinct_kmers = len(counter)
    return {
        "total_kmers": total_kmers,
        "distinct_kmers": distinct_kmers,
        "top": counter.most_common(top_n),
        "spectrum": build_spectrum(counter),
    }
