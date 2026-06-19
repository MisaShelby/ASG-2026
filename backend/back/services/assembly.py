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


def identity_to_reference(contig: str, reference: str) -> float:
    """Identité (0–1) du contig vs référence via l'alignement de chevauchement
    du Lot 2 : fraction de positions « match » sur la zone alignée."""
    if not contig or not reference:
        return 0.0
    result = alignment.overlap_align(contig, reference)
    match_line = result["match_line"]
    if not match_line:
        return 0.0
    return match_line.count("|") / len(match_line)


def _set_bytes(solid: set[str]) -> int:
    """Mémoire réelle (octets) du set de k-mers solides — baseline pour la
    comparaison avec le filtre de Bloom (CDC §3 Scalabilité)."""
    return sys.getsizeof(solid) + sum(sys.getsizeof(s) for s in solid)


def assemble(
    reads,
    k: int,
    threshold: int,
    num_bits: int,
    num_hashes: int,
    reference: str | None = None,
    min_contig_length: int | None = None,
) -> dict:
    """Assemble des contigs à partir des reads via un graphe de de Bruijn
    implicite testé par filtre de Bloom. Retourne contigs + statistiques."""
    if k < 2:
        raise ValueError("k doit être >= 2")

    counter = count_kmers(reads, k)
    distinct_kmers = len(counter)
    solid = select_solid_kmers(counter, threshold)

    oracle = bloom.BloomFilter(num_bits, num_hashes)
    for kmer in solid:
        oracle.add(kmer)

    visited: set[str] = set()
    min_len = min_contig_length if min_contig_length is not None else k
    raw_contigs = []
    for seed in sorted(solid):  # ordre déterministe
        if seed in visited:
            continue
        contig = build_contig(seed, oracle, visited)
        if len(contig) >= min_len:
            raw_contigs.append(contig)
    raw_contigs.sort(key=len, reverse=True)

    best_identity = None
    contigs = []
    for index, sequence in enumerate(raw_contigs):
        # Garde-fou identique à celui du Lot 2 (vue d'alignement) : la table DP
        # de overlap_align est en O(n·m) pur Python. Au-delà de MAX_CELLS on
        # saute le calcul d'identité pour ce contig (identity=None) plutôt que
        # de bloquer la requête synchrone.
        if reference and len(sequence) * len(reference) <= alignment.MAX_CELLS:
            identity = identity_to_reference(sequence, reference)
        else:
            identity = None
        if identity is not None:
            best_identity = (
                identity if best_identity is None
                else max(best_identity, identity)
            )
        contigs.append(
            {
                "index": index,
                "sequence": sequence,
                "length": len(sequence),
                "identity": identity,
            }
        )

    stats = {
        "distinct_kmers": distinct_kmers,
        "solid_kmers": len(solid),
        "bloom_fp_rate": oracle.estimated_fp_rate(len(solid)),
        "bloom_bytes": oracle.byte_size(),
        "dict_bytes_estimate": _set_bytes(solid),
        "num_contigs": len(contigs),
        "max_contig_length": max((c["length"] for c in contigs), default=0),
        "total_contig_length": sum(c["length"] for c in contigs),
        "best_identity": best_identity,
    }
    return {"contigs": contigs, "stats": stats}
