"""Filtre de Bloom implémenté from scratch (Python pur).

Structure probabiliste à coût mémoire constant : `add` marque `num_hashes`
positions d'un bitset de `num_bits` bits ; `__contains__` teste ces positions.
Aucun faux négatif possible (un élément inséré est toujours « présent »), mais
des faux positifs le sont — c'est l'objet de l'analyse critique du Lot 3.

Les `num_hashes` positions sont dérivées par *double hashing*
(Kirsch-Mitzenmacher) à partir de deux hachages de base extraits d'un unique
blake2b : on évite ainsi de calculer num_hashes hachages indépendants.
"""
import hashlib
import math


class BloomFilter:
    def __init__(self, num_bits: int, num_hashes: int):
        if num_bits < 1:
            raise ValueError("num_bits doit être >= 1")
        if num_hashes < 1:
            raise ValueError("num_hashes doit être >= 1")
        self.num_bits = num_bits
        self.num_hashes = num_hashes
        self._bits = bytearray((num_bits + 7) // 8)

    def _indices(self, item: str):
        digest = hashlib.blake2b(item.encode("ascii"), digest_size=16).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:], "big")
        for i in range(self.num_hashes):
            yield (h1 + i * h2) % self.num_bits

    def add(self, item: str) -> None:
        for idx in self._indices(item):
            self._bits[idx >> 3] |= 1 << (idx & 7)

    def __contains__(self, item: str) -> bool:
        return all(
            self._bits[idx >> 3] & (1 << (idx & 7))
            for idx in self._indices(item)
        )

    def byte_size(self) -> int:
        """Mémoire réelle du bitset, en octets."""
        return len(self._bits)

    def estimated_fp_rate(self, n_inserted: int) -> float:
        """Taux de faux positifs théorique pour n éléments insérés :
        (1 - e^{-num_hashes·n/num_bits})^num_hashes."""
        if n_inserted <= 0:
            return 0.0
        exponent = -self.num_hashes * n_inserted / self.num_bits
        return (1 - math.exp(exponent)) ** self.num_hashes


def optimal_params(n: int, p: float) -> tuple[int, int]:
    """Paramètres (num_bits, num_hashes) optimaux pour n éléments et un taux
    de faux positifs cible p : m = -n·ln p / (ln 2)², k = (m/n)·ln 2."""
    if n < 1 or not (0 < p < 1):
        raise ValueError("n>=1 et 0<p<1 requis")
    num_bits = math.ceil(-n * math.log(p) / (math.log(2) ** 2))
    num_hashes = max(1, round((num_bits / n) * math.log(2)))
    return num_bits, num_hashes
