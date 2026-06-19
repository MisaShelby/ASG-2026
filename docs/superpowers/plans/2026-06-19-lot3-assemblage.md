# Lot 3 — Moteur d'assemblage « memory-efficient » Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconstruire des contigs à partir des reads d'un dataset en testant la connectivité d'un graphe de de Bruijn implicite via un filtre de Bloom (jamais matérialisé), avec validation d'identité vs référence et analyses (faux positifs, mémoire, complexité).

**Architecture:** Deux services Python purs et testés — `bloom.py` (filtre de Bloom from scratch) et `assembly.py` (sélection des k-mers solides + traversée on-the-fly + identité via `alignment.overlap_align`). Persistance via `AssemblyRun` + `Contig`, exposée par un `AssemblyRunViewSet` DRF. Frontend React (MUI interactif + Tailwind mise en page + chart.js) : page d'assemblage, viewer de contigs, page d'analyse, historique.

**Tech Stack:** Django + DRF + PostgreSQL (app `back`) ; React + Vite + MUI + Tailwind + react-chartjs-2 + axios + react-router-dom.

## Global Constraints

- App Django `back` ; services métier purs dans `backend/back/services/`, testés dans `backend/back/tests.py` (classes `TestCase`/`APIClient`).
- Tests backend lancés avec : `cd backend && python manage.py test back.tests` (DJANGO_SETTINGS_MODULE = `backend.settings`).
- Conventions de nommage des tables : `back_<modele>` ; FK `ON DELETE SET NULL` quand l'objet doit survivre à la suppression de sa source, `CASCADE` pour les enfants.
- Filtre de Bloom **from scratch** (Python pur, pas de dépendance externe).
- Le graphe de de Bruijn n'est **jamais matérialisé** : le test de voisinage passe uniquement par le Bloom.
- Frontend : MUI pour l'interactif (champs, boutons, sélecteurs), Tailwind pour la mise en page et l'affichage typographique, react-chartjs-2 pour les graphiques. Pas de tests unitaires frontend (vérification navigateur, comme Lots 1/2).
- Recette CDC : un dataset de 10 000 reads doit se reconstruire avec identité > 98 %.
- Messages utilisateur en français (cohérent avec l'existant).
- Commits fréquents ; le code review final via `/code-review`.

---

### Task 1 : Service filtre de Bloom (`services/bloom.py`)

**Files:**
- Create: `backend/back/services/bloom.py`
- Test: `backend/back/tests.py` (nouvelle classe `BloomFilterTests`)

**Interfaces:**
- Consumes: rien (module autonome, stdlib `hashlib`/`math` uniquement).
- Produces:
  - `BloomFilter(num_bits: int, num_hashes: int)` avec `add(item: str) -> None`, `__contains__(item: str) -> bool`, `byte_size() -> int`, `estimated_fp_rate(n_inserted: int) -> float`.
  - `optimal_params(n: int, p: float) -> tuple[int, int]` (retourne `(num_bits, num_hashes)`).

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `backend/back/tests.py` :

```python
from .services import bloom


class BloomFilterTests(TestCase):
    def test_no_false_negatives(self):
        bf = bloom.BloomFilter(num_bits=10_000, num_hashes=4)
        items = [f"ACGT{i}" for i in range(500)]
        for it in items:
            bf.add(it)
        for it in items:
            self.assertIn(it, bf)

    def test_membership_false_before_add(self):
        bf = bloom.BloomFilter(num_bits=10_000, num_hashes=4)
        bf.add("AAAA")
        # Un élément non inséré est très probablement absent avec ce dimensionnement.
        self.assertNotIn("TTTT", bf)

    def test_byte_size_matches_bits(self):
        bf = bloom.BloomFilter(num_bits=16, num_hashes=3)
        self.assertEqual(bf.byte_size(), 2)  # 16 bits = 2 octets

    def test_estimated_fp_rate_increases_with_load(self):
        bf = bloom.BloomFilter(num_bits=1_000, num_hashes=3)
        low = bf.estimated_fp_rate(50)
        high = bf.estimated_fp_rate(500)
        self.assertTrue(0.0 <= low < high < 1.0)

    def test_optimal_params(self):
        m, k = bloom.optimal_params(n=1000, p=0.01)
        self.assertGreater(m, 1000)
        self.assertGreaterEqual(k, 1)

    def test_invalid_params_raise(self):
        with self.assertRaises(ValueError):
            bloom.BloomFilter(num_bits=0, num_hashes=1)
        with self.assertRaises(ValueError):
            bloom.BloomFilter(num_bits=10, num_hashes=0)
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `cd backend && python manage.py test back.tests.BloomFilterTests -v 2`
Expected: FAIL (`ModuleNotFoundError`/`ImportError: cannot import name 'bloom'`).

- [ ] **Step 3 : Écrire l'implémentation minimale**

Créer `backend/back/services/bloom.py` :

```python
"""Filtre de Bloom implémenté from scratch (Python pur).

Structure probabiliste à coût mémoire constant : `add` marque `num_hashes`
positions d'un bitset de `num_bits` bits ; `__contains__` teste ces positions.
Aucun faux négatif possible (un élément inséré est toujours « présent »), mais
des faux positifs le sont — c'est l'objet de l'analyse critique du Lot 3.

Les `num_hashes` positions sont dérivées par *double hashing* (Kirsch-Mitzenmacher)
à partir de deux hachages de base extraits d'un unique blake2b : on évite ainsi
de calculer num_hashes hachages indépendants.
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
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `cd backend && python manage.py test back.tests.BloomFilterTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 5 : Commit**

```bash
git add backend/back/services/bloom.py backend/back/tests.py
git commit -m "feat(lot3): filtre de Bloom from scratch + tests"
```

---

### Task 2 : Sélection des k-mers solides + primitives de traversée (`services/assembly.py`)

**Files:**
- Create: `backend/back/services/assembly.py`
- Test: `backend/back/tests.py` (nouvelle classe `AssemblyTraversalTests`)

**Interfaces:**
- Consumes: `BloomFilter` (Task 1) comme oracle de connectivité (toute structure exposant `__contains__(str)` convient pour les tests).
- Produces:
  - `ALPHABET = "ACGT"`
  - `select_solid_kmers(counter, threshold: int) -> set[str]`
  - `successors(kmer: str, oracle) -> list[str]` (extensions 3' présentes dans l'oracle)
  - `predecessors(kmer: str, oracle) -> list[str]` (extensions 5' présentes dans l'oracle)
  - `build_contig(seed: str, oracle, visited: set[str]) -> str`

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `backend/back/tests.py` :

```python
from collections import Counter
from .services import assembly


class AssemblyTraversalTests(TestCase):
    def test_select_solid_kmers(self):
        counter = Counter({"AAA": 5, "AAC": 1, "ACG": 3})
        self.assertEqual(
            assembly.select_solid_kmers(counter, threshold=3),
            {"AAA", "ACG"},
        )

    def test_select_solid_kmers_invalid_threshold(self):
        with self.assertRaises(ValueError):
            assembly.select_solid_kmers(Counter(), threshold=0)

    def test_successors_and_predecessors(self):
        oracle = {"ATG", "TGC", "TGA", "CAT"}  # set = oracle de test
        # successeurs de "CAT" : suffixe "AT" + base -> ATG présent, pas ATA/ATC/ATT
        self.assertEqual(sorted(assembly.successors("CAT", oracle)), ["ATG"])
        # successeurs de "ATG" : "TG"+base -> TGC, TGA présents (embranchement)
        self.assertEqual(sorted(assembly.successors("ATG", oracle)), ["TGA", "TGC"])
        # prédécesseurs de "ATG" : base+"AT" -> CAT présent
        self.assertEqual(sorted(assembly.predecessors("ATG", oracle)), ["CAT"])

    def test_build_contig_linear_path(self):
        # Chaîne linéaire de 3-mers couvrant "ACGTAC"
        oracle = {"ACG", "CGT", "GTA", "TAC"}
        visited = set()
        contig = assembly.build_contig("ACG", oracle, visited)
        self.assertEqual(contig, "ACGTAC")
        # tous les k-mers du chemin sont marqués visités
        self.assertEqual(visited, oracle)

    def test_build_contig_stops_at_branch(self):
        # Après "ACG"->"CGT", "GT" s'étend en GTA et GTC : embranchement -> arrêt
        oracle = {"ACG", "CGT", "GTA", "GTC"}
        visited = set()
        contig = assembly.build_contig("ACG", oracle, visited)
        self.assertEqual(contig, "ACGT")  # s'arrête avant la bifurcation

    def test_build_contig_starts_from_visited_is_seed_only(self):
        oracle = {"ACG", "CGT"}
        visited = {"CGT"}
        contig = assembly.build_contig("ACG", oracle, visited)
        # successeur unique CGT déjà visité -> on ne l'étend pas
        self.assertEqual(contig, "ACG")
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `cd backend && python manage.py test back.tests.AssemblyTraversalTests -v 2`
Expected: FAIL (`ImportError: cannot import name 'assembly'`).

- [ ] **Step 3 : Écrire l'implémentation minimale**

Créer `backend/back/services/assembly.py` :

```python
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
        neighbors = successors(current, oracle) if forward else predecessors(current, oracle)
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
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `cd backend && python manage.py test back.tests.AssemblyTraversalTests -v 2`
Expected: PASS (6 tests).

- [ ] **Step 5 : Commit**

```bash
git add backend/back/services/assembly.py backend/back/tests.py
git commit -m "feat(lot3): k-mers solides + primitives de traversée du graphe implicite"
```

---

### Task 3 : Orchestration `assemble` + identité + recette toy dataset (`services/assembly.py`)

**Files:**
- Modify: `backend/back/services/assembly.py`
- Test: `backend/back/tests.py` (nouvelle classe `AssemblyEngineTests`)

**Interfaces:**
- Consumes: `count_kmers` (services.kmer), `BloomFilter` (Task 1), `build_contig`/`select_solid_kmers` (Task 2), `alignment.overlap_align` (Lot 2).
- Produces:
  - `identity_to_reference(contig: str, reference: str) -> float` (fraction 0–1)
  - `assemble(reads, k, threshold, num_bits, num_hashes, reference=None, min_contig_length=None) -> dict`
    retourne `{"contigs": [{"index", "sequence", "length", "identity"}], "stats": {...}}`.
    `stats` contient : `distinct_kmers`, `solid_kmers`, `bloom_fp_rate`, `bloom_bytes`, `dict_bytes_estimate`, `num_contigs`, `max_contig_length`, `total_contig_length`, `best_identity`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `backend/back/tests.py` :

```python
class AssemblyEngineTests(TestCase):
    @staticmethod
    def _fragment(sequence, read_len, step):
        """Découpe une séquence en reads chevauchants (objets à attribut .sequence)."""
        class _R:
            def __init__(self, s):
                self.sequence = s
        return [
            _R(sequence[i : i + read_len])
            for i in range(0, len(sequence) - read_len + 1, step)
        ]

    def test_identity_perfect(self):
        ref = "ACGTACGTACGTACGT"
        self.assertEqual(assembly.identity_to_reference(ref, ref), 1.0)

    def test_identity_empty(self):
        self.assertEqual(assembly.identity_to_reference("", "ACGT"), 0.0)

    def test_assemble_reconstructs_toy_sequence(self):
        target = (
            "ACGTGACCTGATTACAGGTCAGTTCACGATCCGATTACAGGCATTAGCATGACTTAGCCA"
            "TGCATTGACCATGCATGCATTAGCATGCATTAGGCATGACTTAGCATGCATTGACATGCA"
        )
        reads = self._fragment(target, read_len=20, step=2)
        result = assembly.assemble(
            reads, k=11, threshold=1, num_bits=200_000, num_hashes=4,
            reference=target,
        )
        self.assertGreaterEqual(result["stats"]["best_identity"], 0.98)

    def test_assemble_stats_present(self):
        target = "ACGTGACCTGATTACAGGTCAGTTCACGATCCGATTACAGG"
        reads = self._fragment(target, read_len=15, step=2)
        result = assembly.assemble(
            reads, k=9, threshold=1, num_bits=100_000, num_hashes=4,
        )
        stats = result["stats"]
        for key in (
            "distinct_kmers", "solid_kmers", "bloom_fp_rate", "bloom_bytes",
            "dict_bytes_estimate", "num_contigs", "max_contig_length",
            "total_contig_length", "best_identity",
        ):
            self.assertIn(key, stats)
        self.assertIsNone(stats["best_identity"])  # pas de référence fournie
        self.assertGreater(stats["bloom_bytes"], 0)

    def test_assemble_threshold_filters_errors(self):
        # Un read erroné minoritaire ne doit pas créer de k-mers solides au seuil 2
        target = "ACGTGACCTGATTACAGGTCAGTTCACG"
        reads = self._fragment(target, read_len=12, step=1) * 3  # cible répétée
        reads += [type(reads[0])("TTTTTTTTTTTT")]  # un read bruit unique
        result = assembly.assemble(
            reads, k=9, threshold=2, num_bits=100_000, num_hashes=4,
        )
        # "TTTTTTTTT" n'apparaît qu'une fois -> non solide -> absent des contigs
        self.assertFalse(any("TTTTTTTTT" in c["sequence"] for c in result["contigs"]))

    def test_assemble_invalid_k(self):
        with self.assertRaises(ValueError):
            assembly.assemble([], k=1, threshold=1, num_bits=10, num_hashes=1)
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `cd backend && python manage.py test back.tests.AssemblyEngineTests -v 2`
Expected: FAIL (`AttributeError: module ... has no attribute 'identity_to_reference'`).

- [ ] **Step 3 : Écrire l'implémentation minimale**

Ajouter à la fin de `backend/back/services/assembly.py` :

```python
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
        identity = (
            identity_to_reference(sequence, reference) if reference else None
        )
        if identity is not None:
            best_identity = identity if best_identity is None else max(
                best_identity, identity
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
```

- [ ] **Step 4 : Lancer les tests pour vérifier qu'ils passent**

Run: `cd backend && python manage.py test back.tests.AssemblyEngineTests -v 2`
Expected: PASS (6 tests). Si `test_assemble_reconstructs_toy_sequence` échoue de peu sur l'identité, vérifier `k` (trop grand pour `read_len`) — ne pas baisser le seuil de 0.98.

- [ ] **Step 5 : Commit**

```bash
git add backend/back/services/assembly.py backend/back/tests.py
git commit -m "feat(lot3): moteur assemble + identité vs référence + recette toy dataset"
```

---

### Task 4 : Modèles `AssemblyRun` / `Contig` + migration + base.sql

**Files:**
- Modify: `backend/back/models.py` (ajout en fin de fichier)
- Create: `backend/back/migrations/0003_assemblyrun_contig.py` (généré)
- Modify: `backend/back/admin.py` (enregistrement)
- Modify: `docs/base.sql` (ajout des tables)
- Test: `backend/back/tests.py` (nouvelle classe `AssemblyModelTests`)

**Interfaces:**
- Consumes: `Dataset` (existant).
- Produces: modèles `AssemblyRun` (champs cf. spec §3) et `Contig` (FK `assembly`, `related_name="contigs"`).

- [ ] **Step 1 : Écrire le test qui échoue**

Ajouter à `backend/back/tests.py` :

```python
from .models import AssemblyRun, Contig


class AssemblyModelTests(TestCase):
    def test_create_assembly_with_contigs(self):
        run = AssemblyRun.objects.create(
            source="RAW", k=11, solidity_threshold=2,
            bloom_bits=200_000, num_hashes=4,
            distinct_kmers=100, solid_kmers=80, bloom_fp_rate=0.01,
            bloom_bytes=25_000, dict_bytes_estimate=40_000,
            num_contigs=1, max_contig_length=120, total_contig_length=120,
        )
        Contig.objects.create(
            assembly=run, index=0, sequence="ACGT" * 30, length=120,
        )
        self.assertEqual(run.contigs.count(), 1)
        self.assertEqual(run.contigs.first().index, 0)
```

- [ ] **Step 2 : Lancer le test pour vérifier qu'il échoue**

Run: `cd backend && python manage.py test back.tests.AssemblyModelTests -v 2`
Expected: FAIL (`ImportError: cannot import name 'AssemblyRun'`).

- [ ] **Step 3 : Écrire les modèles**

Ajouter à la fin de `backend/back/models.py` :

```python
# =====================================================================
#  Lot 3 — Assemblage de novo (graphe de de Bruijn implicite + Bloom)
# =====================================================================
class AssemblyRun(models.Model):
    """Un run d'assemblage : paramètres, statistiques et contigs produits."""

    class Source(models.TextChoices):
        RAW = "RAW", "Reads bruts"
        FILTERED = "FILTERED", "Reads filtrés"

    class Status(models.TextChoices):
        DONE = "DONE", "Terminé"
        ERROR = "ERROR", "Erreur"

    dataset = models.ForeignKey(
        Dataset, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assemblies",
    )
    source = models.CharField(
        max_length=10, choices=Source.choices, default=Source.RAW
    )
    k = models.IntegerField()
    solidity_threshold = models.IntegerField()
    bloom_bits = models.BigIntegerField()
    num_hashes = models.IntegerField()

    distinct_kmers = models.BigIntegerField(default=0)
    solid_kmers = models.BigIntegerField(default=0)
    bloom_fp_rate = models.FloatField(default=0.0)
    bloom_bytes = models.BigIntegerField(default=0)
    dict_bytes_estimate = models.BigIntegerField(default=0)

    num_contigs = models.IntegerField(default=0)
    max_contig_length = models.IntegerField(default=0)
    total_contig_length = models.BigIntegerField(default=0)

    reference_sequence = models.TextField(blank=True)
    best_identity = models.FloatField(null=True, blank=True)
    contigs_file = models.FileField(upload_to="assemblies/", null=True, blank=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.DONE
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Assemblage k={self.k} ({self.num_contigs} contigs)"


class Contig(models.Model):
    """Un contig produit par un AssemblyRun."""

    assembly = models.ForeignKey(
        AssemblyRun, on_delete=models.CASCADE, related_name="contigs"
    )
    index = models.IntegerField()
    sequence = models.TextField()
    length = models.IntegerField()
    identity_to_reference = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["index"]

    def __str__(self):
        return f"Contig #{self.index} ({self.length} nt)"
```

- [ ] **Step 4 : Générer la migration**

Run: `cd backend && python manage.py makemigrations back`
Expected: création de `back/migrations/0003_assemblyrun_contig.py`.

- [ ] **Step 5 : Enregistrer dans l'admin**

Ajouter à `backend/back/admin.py` (après les imports/enregistrements existants) :

```python
from .models import AssemblyRun, Contig


class ContigInline(admin.TabularInline):
    model = Contig
    extra = 0


@admin.register(AssemblyRun)
class AssemblyRunAdmin(admin.ModelAdmin):
    list_display = ("id", "k", "solidity_threshold", "num_contigs",
                    "best_identity", "created_at")
    inlines = [ContigInline]
```

(Adapter l'import `admin` si le fichier ne l'importe pas déjà : `from django.contrib import admin`.)

- [ ] **Step 6 : Compléter `docs/base.sql`**

Ajouter à la fin de `docs/base.sql` :

```sql
-- =====================================================================
--  Lot 3 — Assemblage de novo
-- =====================================================================
CREATE TABLE back_assemblyrun (
    id BIGSERIAL PRIMARY KEY,
    dataset_id BIGINT NULL REFERENCES back_dataset(id) ON DELETE SET NULL,
    source VARCHAR(10) NOT NULL DEFAULT 'RAW',
    k INTEGER NOT NULL,
    solidity_threshold INTEGER NOT NULL,
    bloom_bits BIGINT NOT NULL,
    num_hashes INTEGER NOT NULL,
    distinct_kmers BIGINT NOT NULL DEFAULT 0,
    solid_kmers BIGINT NOT NULL DEFAULT 0,
    bloom_fp_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    bloom_bytes BIGINT NOT NULL DEFAULT 0,
    dict_bytes_estimate BIGINT NOT NULL DEFAULT 0,
    num_contigs INTEGER NOT NULL DEFAULT 0,
    max_contig_length INTEGER NOT NULL DEFAULT 0,
    total_contig_length BIGINT NOT NULL DEFAULT 0,
    reference_sequence TEXT NOT NULL DEFAULT '',
    best_identity DOUBLE PRECISION NULL,
    contigs_file VARCHAR(100) NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'DONE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE back_contig (
    id BIGSERIAL PRIMARY KEY,
    assembly_id BIGINT NOT NULL REFERENCES back_assemblyrun(id) ON DELETE CASCADE,
    index INTEGER NOT NULL,
    sequence TEXT NOT NULL,
    length INTEGER NOT NULL,
    identity_to_reference DOUBLE PRECISION NULL
);
```

- [ ] **Step 7 : Lancer le test pour vérifier qu'il passe**

Run: `cd backend && python manage.py test back.tests.AssemblyModelTests -v 2`
Expected: PASS.

- [ ] **Step 8 : Commit**

```bash
git add backend/back/models.py backend/back/migrations/0003_assemblyrun_contig.py backend/back/admin.py docs/base.sql backend/back/tests.py
git commit -m "feat(lot3): modèles AssemblyRun/Contig + migration + base.sql + admin"
```

---

### Task 5 : Chargement des reads + Serializers + ViewSet + endpoints

**Files:**
- Modify: `backend/back/services/read_access.py` (ajout `load_reads`)
- Modify: `backend/back/serializers.py` (ajout serializers)
- Modify: `backend/back/views.py` (ajout `AssemblyRunViewSet`)
- Modify: `backend/back/urls.py` (route `assemblies`)
- Test: `backend/back/tests.py` (nouvelle classe `AssemblyApiTests`)

**Interfaces:**
- Consumes: `assembly.assemble` (Task 3), `read_access` (existant + `load_reads`), modèles (Task 4).
- Produces:
  - `read_access.load_reads(dataset) -> list[Read]`
  - `AssemblyCreateSerializer` (entrée : `dataset`, `source`, `k`, `solidity_threshold`, `bloom_bits` (optionnel), `num_hashes` (optionnel), `reference_sequence` (optionnel)), `ContigSerializer`, `AssemblyRunSerializer` (sortie imbriquant `contigs` + `stats`).
  - Endpoints `POST/GET /api/assemblies/`, `GET /api/assemblies/{id}/`, `GET /api/assemblies/{id}/contigs.fasta`.

- [ ] **Step 1 : Écrire les tests qui échouent**

Ajouter à `backend/back/tests.py` :

```python
class AssemblyApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        target = (
            "ACGTGACCTGATTACAGGTCAGTTCACGATCCGATTACAGGCATTAGCATGACTTAGCCA"
            "TGCATTGACCATGCATGCATTAGCATGCATTAGGCATGACTTAGCATGCATTGACATGCA"
        )
        # Reads chevauchants au format FASTQ
        reads = [target[i : i + 20] for i in range(0, len(target) - 20 + 1, 2)]
        fastq = "".join(
            f"@r{i}\n{seq}\n+\n{'I' * len(seq)}\n" for i, seq in enumerate(reads)
        )
        self.dataset = Dataset.objects.create(
            name="toy", original_filename="toy.fastq",
            file=SimpleUploadedFile("toy.fastq", fastq.encode()),
            input_format="FASTQ",
        )
        self.target = target

    def test_create_assembly(self):
        resp = self.client.post(
            "/api/assemblies/",
            {
                "dataset": self.dataset.id, "source": "RAW", "k": 11,
                "solidity_threshold": 1, "bloom_bits": 200000, "num_hashes": 4,
                "reference_sequence": self.target,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        data = resp.json()
        self.assertGreaterEqual(data["best_identity"], 0.98)
        self.assertGreaterEqual(len(data["contigs"]), 1)
        self.assertIn("bloom_bytes", data)

    def test_list_assemblies(self):
        self.client.post(
            "/api/assemblies/",
            {"dataset": self.dataset.id, "k": 11, "solidity_threshold": 1},
            format="json",
        )
        resp = self.client.get("/api/assemblies/")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_invalid_k_rejected(self):
        resp = self.client.post(
            "/api/assemblies/",
            {"dataset": self.dataset.id, "k": 1, "solidity_threshold": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `cd backend && python manage.py test back.tests.AssemblyApiTests -v 2`
Expected: FAIL (404 sur `/api/assemblies/`).

- [ ] **Step 3 : Ajouter `load_reads` à `read_access.py`**

Ajouter à `backend/back/services/read_access.py` :

```python
def load_reads(dataset) -> list:
    """Charge tous les `Read` d'un dataset en mémoire (un seul passage du
    fichier). Utilisé par l'assemblage, qui a besoin de l'ensemble des reads."""
    with dataset.file.open("rt") as handle:
        return list(parse(handle, dataset.input_format))
```

- [ ] **Step 4 : Ajouter les serializers**

Ajouter à `backend/back/serializers.py` :

```python
from .models import AssemblyRun, Contig, Dataset  # Dataset peut déjà être importé


class ContigSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contig
        fields = ["index", "sequence", "length", "identity_to_reference"]


class AssemblyRunSerializer(serializers.ModelSerializer):
    contigs = ContigSerializer(many=True, read_only=True)

    class Meta:
        model = AssemblyRun
        fields = [
            "id", "dataset", "source", "k", "solidity_threshold",
            "bloom_bits", "num_hashes", "distinct_kmers", "solid_kmers",
            "bloom_fp_rate", "bloom_bytes", "dict_bytes_estimate",
            "num_contigs", "max_contig_length", "total_contig_length",
            "reference_sequence", "best_identity", "status", "created_at",
            "contigs",
        ]


class AssemblyCreateSerializer(serializers.Serializer):
    dataset = serializers.PrimaryKeyRelatedField(queryset=Dataset.objects.all())
    source = serializers.ChoiceField(
        choices=AssemblyRun.Source.choices, default=AssemblyRun.Source.RAW
    )
    k = serializers.IntegerField(min_value=2, max_value=64)
    solidity_threshold = serializers.IntegerField(min_value=1, default=2)
    bloom_bits = serializers.IntegerField(
        min_value=8, max_value=200_000_000, required=False
    )
    num_hashes = serializers.IntegerField(
        min_value=1, max_value=20, required=False
    )
    reference_sequence = serializers.CharField(
        required=False, allow_blank=True, trim_whitespace=True
    )
```

(`serializers` et le module sont déjà importés en tête du fichier — réutiliser l'import existant ; ne pas dupliquer.)

- [ ] **Step 5 : Ajouter le ViewSet**

Ajouter à `backend/back/views.py` (et compléter les imports `from .models import ...` / `from .serializers import ...` / `from .services import ...`) :

```python
import math

from django.http import HttpResponse

from .models import AssemblyRun, Contig
from .serializers import AssemblyCreateSerializer, AssemblyRunSerializer
from .services import assembly, bloom


class AssemblyRunViewSet(viewsets.ModelViewSet):
    """Lot 3 — Assemblage de novo via graphe de de Bruijn implicite + Bloom."""

    queryset = AssemblyRun.objects.all()
    http_method_names = ["get", "post", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return AssemblyCreateSerializer
        return AssemblyRunSerializer

    def create(self, request, *args, **kwargs):
        serializer = AssemblyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        dataset = data["dataset"]
        k = data["k"]
        threshold = data["solidity_threshold"]
        reference = data.get("reference_sequence", "") or ""

        reads = read_access.load_reads(dataset)

        # Dimensionnement par défaut du Bloom si non fourni : ~1% de FP sur une
        # borne haute du nombre de k-mers distincts.
        num_bits = data.get("bloom_bits")
        num_hashes = data.get("num_hashes")
        if num_bits is None or num_hashes is None:
            upper = max(1, sum(max(0, len(r.sequence) - k + 1) for r in reads))
            opt_bits, opt_hashes = bloom.optimal_params(upper, 0.01)
            num_bits = num_bits or opt_bits
            num_hashes = num_hashes or opt_hashes

        result = assembly.assemble(
            reads, k=k, threshold=threshold,
            num_bits=num_bits, num_hashes=num_hashes,
            reference=reference or None,
        )
        stats = result["stats"]

        run = AssemblyRun.objects.create(
            dataset=dataset, source=data["source"], k=k,
            solidity_threshold=threshold, bloom_bits=num_bits,
            num_hashes=num_hashes, reference_sequence=reference,
            distinct_kmers=stats["distinct_kmers"],
            solid_kmers=stats["solid_kmers"],
            bloom_fp_rate=stats["bloom_fp_rate"],
            bloom_bytes=stats["bloom_bytes"],
            dict_bytes_estimate=stats["dict_bytes_estimate"],
            num_contigs=stats["num_contigs"],
            max_contig_length=stats["max_contig_length"],
            total_contig_length=stats["total_contig_length"],
            best_identity=stats["best_identity"],
        )
        Contig.objects.bulk_create(
            Contig(
                assembly=run, index=c["index"], sequence=c["sequence"],
                length=c["length"], identity_to_reference=c["identity"],
            )
            for c in result["contigs"]
        )
        return Response(
            AssemblyRunSerializer(run).data, status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=["get"], url_path="contigs.fasta")
    def contigs_fasta(self, request, pk=None):
        run = self.get_object()
        lines = []
        for c in run.contigs.all():
            lines.append(f">contig_{c.index} len={c.length}")
            lines.append(c.sequence)
        content = "\n".join(lines) + "\n"
        resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
        resp["Content-Disposition"] = (
            f'attachment; filename="assembly_{run.id}_contigs.fasta"'
        )
        return resp
```

(Vérifier que `action`, `viewsets`, `status`, `Response`, `read_access` sont déjà importés — ils le sont pour les ViewSets existants. N'ajouter que ce qui manque.)

- [ ] **Step 6 : Déclarer la route**

Modifier `backend/back/urls.py` : importer `AssemblyRunViewSet` et l'enregistrer :

```python
from .views import (
    AlignmentRunViewSet,
    AssemblyRunViewSet,
    DatasetViewSet,
    FastaConversionViewSet,
    KmerAnalysisViewSet,
)

router.register(r"assemblies", AssemblyRunViewSet, basename="assemblyrun")
```

- [ ] **Step 7 : Lancer les tests pour vérifier qu'ils passent**

Run: `cd backend && python manage.py test back.tests.AssemblyApiTests -v 2`
Expected: PASS (3 tests).

- [ ] **Step 8 : Lancer toute la suite backend (non-régression)**

Run: `cd backend && python manage.py test back.tests -v 1`
Expected: PASS (toutes classes, y compris Lots 1/2).

- [ ] **Step 9 : Commit**

```bash
git add backend/back/services/read_access.py backend/back/serializers.py backend/back/views.py backend/back/urls.py backend/back/tests.py
git commit -m "feat(lot3): endpoints assemblies (create/list/retrieve + FASTA)"
```

---

### Task 6 : Frontend — API + page d'assemblage + viewer de contigs

**Files:**
- Modify: `frontend/src/api/api.js`
- Create: `frontend/src/components/ContigViewer.jsx`
- Create: `frontend/src/pages/AssemblyPage.jsx`
- Modify: `frontend/src/App.jsx` (route + nav, complété en Task 7)

**Interfaces:**
- Consumes: endpoints Task 5 ; `AlignmentViewer.jsx` (Lot 2) pour l'alignement du meilleur contig.
- Produces: `createAssembly`, `listAssemblies`, `getAssembly`, `assemblyContigsUrl` dans `api.js` ; composants `ContigViewer`, page `AssemblyPage`.

- [ ] **Step 1 : Ajouter les appels API**

Ajouter à `frontend/src/api/api.js` (suivre le style des fonctions existantes — même instance axios) :

```javascript
export const createAssembly = (payload) =>
  api.post("/assemblies/", payload).then((r) => r.data);

export const listAssemblies = () =>
  api.get("/assemblies/").then((r) => r.data);

export const getAssembly = (id) =>
  api.get(`/assemblies/${id}/`).then((r) => r.data);

export const assemblyContigsUrl = (id) =>
  `${api.defaults.baseURL}/assemblies/${id}/contigs.fasta`;
```

(Adapter aux noms réels : si l'export de l'instance axios s'appelle autrement que `api`, utiliser le même symbole que les fonctions existantes du fichier.)

- [ ] **Step 2 : Créer `ContigViewer.jsx`**

Créer `frontend/src/components/ContigViewer.jsx` — liste des contigs en `font-mono`, repli/dépli, et alignement du meilleur contig vs référence via `AlignmentViewer` :

```jsx
import { Button } from "@mui/material";
import AlignmentViewer from "./AlignmentViewer";

export default function ContigViewer({ contigs, downloadUrl }) {
  if (!contigs?.length) {
    return <p className="text-gray-500">Aucun contig produit.</p>;
  }
  return (
    <div className="space-y-4">
      {downloadUrl && (
        <Button variant="outlined" href={downloadUrl} component="a">
          Télécharger les contigs (FASTA)
        </Button>
      )}
      {contigs.map((c) => (
        <div key={c.index} className="rounded border border-gray-200 p-3">
          <div className="mb-1 flex justify-between text-sm text-gray-600">
            <span>Contig #{c.index} — {c.length} nt</span>
            {c.identity_to_reference != null && (
              <span>
                identité : {(c.identity_to_reference * 100).toFixed(2)} %
              </span>
            )}
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs">
            {c.sequence}
          </pre>
        </div>
      ))}
    </div>
  );
}
```

(Vérifier le chemin d'import d'`AlignmentViewer` et son export — réutiliser tel quel pour un éventuel affichage d'alignement détaillé si déjà alimenté côté API ; sinon laisser l'affichage `pre` ci-dessus, suffisant pour les contigs.)

- [ ] **Step 3 : Créer `AssemblyPage.jsx`**

Créer `frontend/src/pages/AssemblyPage.jsx` — formulaire MUI (sélecteur de dataset, k, seuil, bloom_bits, num_hashes, référence) + cartes de stats Tailwind + `ContigViewer`. Suivre le style de `AlignmentPage.jsx` (récupération de la liste des datasets, gestion `loading`/`error`). Champs :

```jsx
import { useEffect, useState } from "react";
import {
  Button, MenuItem, TextField, CircularProgress,
} from "@mui/material";
import { listDatasets } from "../api/api"; // nom réel à vérifier
import { createAssembly, assemblyContigsUrl } from "../api/api";
import ContigViewer from "../components/ContigViewer";

export default function AssemblyPage() {
  const [datasets, setDatasets] = useState([]);
  const [form, setForm] = useState({
    dataset: "", source: "RAW", k: 21, solidity_threshold: 2,
    bloom_bits: "", num_hashes: "", reference_sequence: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    listDatasets().then(setDatasets).catch(() => setDatasets([]));
  }, []);

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = {
        dataset: form.dataset, source: form.source,
        k: Number(form.k), solidity_threshold: Number(form.solidity_threshold),
        reference_sequence: form.reference_sequence,
      };
      if (form.bloom_bits) payload.bloom_bits = Number(form.bloom_bits);
      if (form.num_hashes) payload.num_hashes = Number(form.num_hashes);
      setResult(await createAssembly(payload));
    } catch (e) {
      setError(e?.response?.data?.detail || "Échec de l'assemblage.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Assemblage de novo</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <TextField select label="Dataset" value={form.dataset}
          onChange={set("dataset")}>
          {datasets.map((d) => (
            <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>
          ))}
        </TextField>
        <TextField select label="Source" value={form.source}
          onChange={set("source")}>
          <MenuItem value="RAW">Reads bruts</MenuItem>
          <MenuItem value="FILTERED">Reads filtrés</MenuItem>
        </TextField>
        <TextField label="k" type="number" value={form.k} onChange={set("k")} />
        <TextField label="Seuil de solidité" type="number"
          value={form.solidity_threshold} onChange={set("solidity_threshold")} />
        <TextField label="Bloom : m bits (auto si vide)" type="number"
          value={form.bloom_bits} onChange={set("bloom_bits")} />
        <TextField label="Nb de hachages (auto si vide)" type="number"
          value={form.num_hashes} onChange={set("num_hashes")} />
      </div>
      <TextField label="Séquence de référence (optionnelle)" multiline minRows={2}
        fullWidth value={form.reference_sequence}
        onChange={set("reference_sequence")} />
      <Button variant="contained" onClick={submit} disabled={!form.dataset || loading}>
        {loading ? <CircularProgress size={22} /> : "Assembler"}
      </Button>
      {error && <p className="text-red-600">{error}</p>}
      {result && (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Contigs" value={result.num_contigs} />
            <Stat label="Plus long contig" value={`${result.max_contig_length} nt`} />
            <Stat label="K-mers solides" value={result.solid_kmers} />
            <Stat label="Taux FP (théorique)"
              value={`${(result.bloom_fp_rate * 100).toFixed(3)} %`} />
            <Stat label="Mémoire Bloom" value={`${result.bloom_bytes} o`} />
            <Stat label="Mémoire dict (est.)"
              value={`${result.dict_bytes_estimate} o`} />
            {result.best_identity != null && (
              <Stat label="Meilleure identité"
                value={`${(result.best_identity * 100).toFixed(2)} %`} />
            )}
          </div>
          <ContigViewer contigs={result.contigs}
            downloadUrl={assemblyContigsUrl(result.id)} />
        </>
      )}
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div className="rounded border border-gray-200 p-3">
      <div className="text-xs text-gray-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  );
}
```

(Vérifier le nom réel de la fonction qui liste les datasets dans `api.js` — l'utiliser ; ne pas en inventer une nouvelle.)

- [ ] **Step 4 : Vérification navigateur**

Run: `cd frontend && npm run dev` (et le backend `python manage.py runserver` dans un autre terminal).
Vérifier : la page `/assembly` charge la liste des datasets, un assemblage sur un dataset existant retourne des contigs et des stats, et le téléchargement FASTA fonctionne. (La route `/assembly` est ajoutée en Task 7 ; pour tester avant, ajouter temporairement la route ou tester via Task 7.)

- [ ] **Step 5 : Commit**

```bash
git add frontend/src/api/api.js frontend/src/components/ContigViewer.jsx frontend/src/pages/AssemblyPage.jsx
git commit -m "feat(lot3): page d'assemblage + viewer de contigs (frontend)"
```

---

### Task 7 : Frontend — page d'analyse, historique, navigation

**Files:**
- Create: `frontend/src/components/BloomAnalysisChart.jsx`
- Create: `frontend/src/pages/AssemblyAnalysisPage.jsx`
- Create: `frontend/src/pages/AssemblyHistoryPage.jsx`
- Modify: `frontend/src/App.jsx` (nav + routes)

**Interfaces:**
- Consumes: `listAssemblies`, `getAssembly` (Task 6) ; `bloom.estimated_fp_rate` reproduite côté client pour les courbes paramétriques (formule pure, pas d'appel API).
- Produces: composant `BloomAnalysisChart`, pages `AssemblyAnalysisPage`/`AssemblyHistoryPage`, routes `/assembly`, `/assembly/analysis`, `/assemblies`.

- [ ] **Step 1 : Créer `BloomAnalysisChart.jsx`**

Créer `frontend/src/components/BloomAnalysisChart.jsx` — courbe du taux de FP en fonction de `m` (à `n` et `num_hashes` donnés), via react-chartjs-2 (déjà utilisé par `KmerHistogram`/`SpectrumPage` — réutiliser les mêmes imports/enregistrements chart.js) :

```jsx
import { Line } from "react-chartjs-2";

// p(m) = (1 - e^{-num_hashes·n/m})^num_hashes
function fpRate(numBits, numHashes, n) {
  if (n <= 0) return 0;
  return (1 - Math.exp((-numHashes * n) / numBits)) ** numHashes;
}

export default function BloomAnalysisChart({ n, numHashes }) {
  const points = [];
  for (let factor = 2; factor <= 40; factor += 2) {
    const m = n * factor;
    points.push({ x: m, y: fpRate(m, numHashes, n) });
  }
  const data = {
    labels: points.map((p) => p.x),
    datasets: [
      {
        label: `Taux de FP (n=${n}, k_hash=${numHashes})`,
        data: points.map((p) => p.y),
        borderColor: "rgb(37,99,235)",
        fill: false,
      },
    ],
  };
  return <Line data={data} />;
}
```

(Reprendre l'enregistrement `ChartJS.register(...)` tel qu'il est fait dans les composants chart existants pour éviter l'erreur « category scale not registered ».)

- [ ] **Step 2 : Créer `AssemblyAnalysisPage.jsx`**

Créer `frontend/src/pages/AssemblyAnalysisPage.jsx` — récupère un run via `getAssembly` (id en query/param) et affiche : `BloomAnalysisChart` (avec `n = solid_kmers`, `numHashes = num_hashes`), une comparaison mémoire Bloom vs dict (barres), et un texte expliquant l'impact des faux positifs. Suivre le style de `SpectrumPage.jsx`.

```jsx
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { getAssembly } from "../api/api";
import BloomAnalysisChart from "../components/BloomAnalysisChart";

export default function AssemblyAnalysisPage() {
  const { id } = useParams();
  const [run, setRun] = useState(null);
  useEffect(() => { getAssembly(id).then(setRun); }, [id]);
  if (!run) return <p className="p-6">Chargement…</p>;
  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Analyse du filtre de Bloom</h1>
      <BloomAnalysisChart n={run.solid_kmers} numHashes={run.num_hashes} />
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded border p-3">
          <div className="text-sm text-gray-500">Mémoire Bloom</div>
          <div className="text-xl font-semibold">{run.bloom_bytes} o</div>
        </div>
        <div className="rounded border p-3">
          <div className="text-sm text-gray-500">Mémoire dictionnaire (est.)</div>
          <div className="text-xl font-semibold">{run.dict_bytes_estimate} o</div>
        </div>
      </div>
      <p className="text-sm text-gray-700">
        Un faux positif du filtre fait croire qu'un k-mer non solide est présent :
        la traversée peut alors suivre un chemin fantôme (sur-extension) ou marquer
        un faux embranchement. Augmenter m (bits) réduit le taux de FP ; voir la
        courbe ci-dessus. Le détail figure dans docs/LOT3_ANALYSE.md.
      </p>
    </div>
  );
}
```

- [ ] **Step 3 : Créer `AssemblyHistoryPage.jsx`**

Créer `frontend/src/pages/AssemblyHistoryPage.jsx` — liste des runs (style `AlignmentHistoryPage.jsx`), chaque ligne liant vers l'analyse `/assemblies/:id/analysis` (ou détail).

```jsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { listAssemblies } from "../api/api";

export default function AssemblyHistoryPage() {
  const [runs, setRuns] = useState([]);
  useEffect(() => { listAssemblies().then(setRuns); }, []);
  return (
    <div className="mx-auto max-w-4xl space-y-3 p-6">
      <h1 className="text-2xl font-bold">Historique des assemblages</h1>
      {runs.map((r) => (
        <Link key={r.id} to={`/assemblies/${r.id}/analysis`}
          className="block rounded border border-gray-200 p-3 hover:bg-gray-50">
          k={r.k}, seuil={r.solidity_threshold} — {r.num_contigs} contigs
          {r.best_identity != null &&
            ` — identité ${(r.best_identity * 100).toFixed(2)} %`}
        </Link>
      ))}
    </div>
  );
}
```

- [ ] **Step 4 : Brancher la navigation et les routes dans `App.jsx`**

Modifier `frontend/src/App.jsx` : ajouter un lien de nav « Assemblage » et les routes (suivre exactement le pattern des routes/liens existants `/alignment`, `/alignments/:id`) :

```jsx
// imports
import AssemblyPage from "./pages/AssemblyPage";
import AssemblyHistoryPage from "./pages/AssemblyHistoryPage";
import AssemblyAnalysisPage from "./pages/AssemblyAnalysisPage";

// dans la navigation (même composant de lien que les autres entrées) :
// <NavLink to="/assembly">Assemblage</NavLink>
// <NavLink to="/assemblies">Historique assemblages</NavLink>

// dans <Routes> :
// <Route path="/assembly" element={<AssemblyPage />} />
// <Route path="/assemblies" element={<AssemblyHistoryPage />} />
// <Route path="/assemblies/:id/analysis" element={<AssemblyAnalysisPage />} />
```

- [ ] **Step 5 : Vérification navigateur**

Run: backend `python manage.py runserver` + `cd frontend && npm run dev`.
Vérifier le flux complet : nav « Assemblage » → lancer un assemblage (avec et sans référence) → stats + contigs + téléchargement FASTA → page d'analyse (courbe FP + comparaison mémoire) → historique → re-clic ouvre l'analyse.

- [ ] **Step 6 : Commit**

```bash
git add frontend/src/components/BloomAnalysisChart.jsx frontend/src/pages/AssemblyAnalysisPage.jsx frontend/src/pages/AssemblyHistoryPage.jsx frontend/src/App.jsx
git commit -m "feat(lot3): analyse Bloom + historique + navigation (frontend)"
```

---

### Task 8 : Rapport d'analyse, mise à jour CLAUDE.md, revue de code

**Files:**
- Create: `docs/LOT3_ANALYSE.md`
- Modify: `CLAUDE.md` (section « État d'avancement »)

**Interfaces:** aucun code exécutable ; livrables documentaires + revue.

- [ ] **Step 1 : Rédiger `docs/LOT3_ANALYSE.md`**

Contenu (sections rédigées, pas de placeholder) :
1. **Impact des faux positifs** : un FP crée un k-mer fantôme → chemin fantôme (sur-extension du contig) ou faux embranchement (arrêt prématuré). Formule du taux de FP `p = (1 - e^{-k_hash·n/m})^k_hash` ; effet de `m` (↑ m ⇒ ↓ p) et de `k_hash` (optimum `k_hash = (m/n)·ln 2`). Donner un tableau chiffré de `p` pour plusieurs `m/n` (ex. m/n = 8, 10, 16) en réutilisant `bloom.optimal_params`/`estimated_fp_rate`.
2. **Mémoire Bloom vs dictionnaire** : comparer `bloom_bytes` (≈ m/8 octets, indépendant de la longueur des k-mers) vs `dict_bytes_estimate` (`sys.getsizeof` du set + chaque k-mer). Donner les ordres de grandeur observés sur un run réel.
3. **Complexité O(n²) (alignement Lot 2) vs traversée par graphe** : alignement DP = O(n·m) temps et espace ; traversée = O(nb k-mers solides · k_hash) en temps, mémoire = O(m bits) constante côté oracle. Conclure sur le gain de scalabilité.

- [ ] **Step 2 : Mettre à jour `CLAUDE.md`**

Modifier la ligne « **Lot 3** : non démarré. » de la section « État d'avancement » pour refléter l'achèvement (backend + frontend + tests + analyses + revue), avec renvoi vers `docs/LOT3.md` et `docs/LOT3_ANALYSE.md`.

- [ ] **Step 3 : Lancer toute la suite de tests (vérification finale)**

Run: `cd backend && python manage.py test back.tests -v 1`
Expected: PASS (toutes les classes).

- [ ] **Step 4 : Commit**

```bash
git add docs/LOT3_ANALYSE.md CLAUDE.md
git commit -m "docs(lot3): rapport d'analyse (FP, mémoire, complexité) + état d'avancement"
```

- [ ] **Step 5 : Revue de code**

Lancer `/code-review` sur le diff complet du Lot 3, traiter les retours (via la skill receiving-code-review), puis corriger et re-commiter si nécessaire.

---

## Notes de réutilisation

- `services/kmer.count_kmers(reads, k)` : comptage des k-mers (Lot 1) — réutilisé tel quel.
- `services/alignment.overlap_align(a, b)` : alignement de chevauchement (Lot 2) — réutilisé pour l'identité contig/référence. Attention au garde-fou `alignment.MAX_CELLS` (rejet si `len(contig)·len(reference)` trop grand) ; pour le toy dataset court, sans risque.
- `services/read_access` : ajout de `load_reads(dataset)` ; `preview_reads`/`get_read_at` existants inchangés.
- `components/AlignmentViewer.jsx` : disponible pour un affichage d'alignement détaillé si souhaité.
