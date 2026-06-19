"""Assemblage de novo « memory-efficient » (approche Minia 2).

Le graphe de de Bruijn n'est jamais matérialisé : la connectivité entre k-mers
est testée à la volée via un filtre de Bloom (services.bloom) servant d'oracle.
On conserve séparément l'ensemble des k-mers solides uniquement pour énumérer
les seeds et marquer les k-mers déjà parcourus (anti-boucle), ainsi que comme
baseline mémoire pour la comparaison avec un dictionnaire (CDC §3).
"""
import sys

from . import alignment, bloom
from .kmer import count_kmers

ALPHABET = "ACGT"


def select_solid_kmers(counter, threshold: int) -> set[str]:
    """K-mers « solides » = ceux dont la multiplicité atteint le seuil."""
    if threshold < 1:
        raise ValueError("threshold doit être >= 1")
    return {kmer for kmer, count in counter.items() if count >= threshold}


def successors(kmer: str, oracle) -> list[str]:
    """Extensions 3' (A/C/G/T) du k-mer présentes dans l'oracle."""
    suffix = kmer[1:]
    return [suffix + base for base in ALPHABET if (suffix + base) in oracle]


def predecessors(kmer: str, oracle) -> list[str]:
    """Extensions 5' (A/C/G/T) du k-mer présentes dans l'oracle."""
    prefix = kmer[:-1]
    return [base + prefix for base in ALPHABET if (base + prefix) in oracle]


def _walk(start: str, oracle, visited: set[str], forward: bool) -> list[str]:
    """Étend un chemin depuis `start` tant qu'il y a exactement un voisin non
    visité. Retourne la liste des bases ajoutées (dans l'ordre d'extension).
    Arrêt sur cul-de-sac (0 voisin) ou embranchement (>= 2 voisins)."""
    added = []
    current = start
    while True:
        neighbors = (
            successors(current, oracle) if forward
            else predecessors(current, oracle)
        )
        if len(neighbors) != 1:
            break  # 0 = cul-de-sac, >= 2 = embranchement
        nxt = neighbors[0]
        if nxt in visited:
            break  # convergence sur un contig existant / boucle
        visited.add(nxt)
        added.append(nxt[-1] if forward else nxt[0])
        current = nxt
    return added


def build_contig(seed: str, oracle, visited: set[str]) -> str:
    """Construit un contig autour de `seed` en étendant en 3' puis en 5'."""
    visited.add(seed)
    forward = _walk(seed, oracle, visited, forward=True)
    backward = _walk(seed, oracle, visited, forward=False)
    return "".join(reversed(backward)) + seed + "".join(forward)
