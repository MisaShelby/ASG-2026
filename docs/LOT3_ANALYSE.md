# Lot 3 — Rapport d'analyse technique

> Analyses exigées par le cahier des charges (CDC §2 Lot 3 « Analyse critique »,
> §3 « Scalabilité », §4 « Analyse de Complexité »). Les chiffres ci-dessous sont
> reproductibles via les services `back/services/bloom.py` et `back/services/assembly.py`.

---

## 1. Impact des faux positifs (chemins fantômes)

Le filtre de Bloom ne produit **jamais de faux négatif** : tout k-mer solide inséré est
toujours reconnu présent. En revanche il produit des **faux positifs** : un k-mer jamais
inséré peut être déclaré « présent ». Dans le moteur d'assemblage, l'oracle est interrogé
pour décider si une extension (A/C/G/T) prolonge un contig. Un faux positif a donc deux
effets néfastes :

- **Chemin fantôme / sur-extension** : une extension qui n'existe pas réellement est
  validée, et le contig se prolonge sur une base erronée (ou continue au-delà de la fin
  réelle de la séquence).
- **Faux embranchement** : à un nœud qui n'a qu'un seul vrai successeur, un faux positif
  ajoute un second successeur apparent. La traversée voit alors `len(neighbors) >= 2` et
  **s'arrête prématurément** (cf. `_walk` dans `assembly.py`), fragmentant l'assemblage en
  contigs plus courts.

### Loi du taux de faux positifs

Pour un filtre de `m` bits, `num_hashes` fonctions de hachage et `n` k-mers solides
insérés :

$$p = \left(1 - e^{-\,\text{num\_hashes}\cdot n / m}\right)^{\text{num\_hashes}}$$

Le nombre optimal de hachages pour un `m/n` donné est `num_hashes = (m/n)·ln 2`. Valeurs
calculées (via `bloom.estimated_fp_rate`, n = 10 000) :

| m / n | num_hashes optimal | Taux de FP théorique |
|------:|-------------------:|---------------------:|
|     4 |                  3 |             14.6892 % |
|     8 |                  6 |              2.1577 % |
|    10 |                  7 |              0.8194 % |
|    16 |                 11 |              0.0459 % |
|    20 |                 14 |              0.0067 % |

**Lecture** : augmenter `m` (bits du filtre) fait chuter le taux de FP de façon
quasi-exponentielle ; à `m/n ≥ 10` le taux passe sous 1 %, ce qui suffit pour que les
chemins fantômes restent rares devant les vrais chemins. Le choix de `num_hashes` est un
compromis : trop peu de hachages sature mal le bitset, trop de hachages le remplit trop
vite ; l'optimum `(m/n)·ln 2` minimise `p`. La page d'analyse in-app
(`AssemblyAnalysisPage`) trace cette courbe `p = f(m)` pour le run consulté.

### Atténuation dans ce prototype

Le **seuil de solidité** (`solidity_threshold`) écarte en amont les k-mers rares (issus
des erreurs de séquençage, ~1 % du CDC §3) avant même l'insertion : moins de k-mers
insérés ⇒ `n` plus petit ⇒ `p` plus faible à `m` constant. C'est la première ligne de
défense contre les chemins fantômes, complémentaire du dimensionnement du filtre.

---

## 2. Mémoire : filtre de Bloom vs dictionnaire

Cas mesuré (via `assembly._set_bytes` et `BloomFilter.byte_size`) pour **n = 10 000
k-mers distincts de longueur k = 21**, filtre dimensionné pour ~1 % de FP
(`optimal_params` → m = 95 851 bits, 7 hachages) :

| Structure | Mémoire | Détail |
|-----------|--------:|--------|
| **Filtre de Bloom** | **11 982 o (≈ 11.7 Kio)** | bitset `m/8` octets, **indépendant de la longueur k** |
| **`set` Python (baseline dict)** | **1 144 504 o (≈ 1117.7 Kio)** | `sys.getsizeof(set)` + chaque chaîne k-mer |
| **Ratio** | **0.0105** | gain mémoire **≈ ×95** |

**Pourquoi le dictionnaire/`set` explose** : chaque k-mer y est stocké comme un objet
`str` Python complet (en-tête d'objet + buffer de caractères), et la table de hachage du
`set` réserve des emplacements de pointeurs avec un facteur de charge < 1. Le coût croît
donc avec `n` **et** avec la longueur `k`. Le filtre de Bloom, lui, n'occupe que `m/8`
octets quelle que soit la longueur des k-mers : sa mémoire est **constante** pour un `m`
donné. C'est exactement la propriété recherchée par l'approche Minia : tester la
connectivité du graphe de de Bruijn « à coût mémoire constant » sans jamais matérialiser
les sommets ni les arêtes.

**Contrepartie assumée** : le filtre n'autorise que le test d'appartenance (pas
d'énumération, pas de suppression) et introduit le taux de FP analysé en §1. Dans ce
prototype on conserve volontairement un `set` des k-mers solides pour l'amorçage des seeds
et l'anti-boucle ; le gain mémoire ci-dessus illustre ce que coûterait une approche
*entièrement* basée sur un dictionnaire pour le test de connectivité, que l'oracle de
Bloom remplace.

---

## 3. Complexité : alignement O(n²) vs traversée par graphe

### Alignement par programmation dynamique (Lot 2)

L'alignement de chevauchement remplit une table DP de taille `(n+1)·(m+1)` pour deux
séquences de longueurs `n` et `m` :

- **Temps** : `O(n·m)` — quadratique (`O(n²)` pour `n ≈ m`).
- **Espace** : `O(n·m)` pour la table complète (nécessaire ici au backtracking qui
  reconstruit l'alignement à 3 lignes).

C'est la raison pour laquelle le CDC qualifie l'alignement global de « trop coûteux »
pour des millions de reads : comparer toutes les paires de reads serait
`O(R²·L²)` (R reads de longueur L).

### Traversée par graphe de de Bruijn implicite (Lot 3)

- **Construction** : comptage des k-mers `O(R·L)` (linéaire dans la taille totale des
  données) ; insertion des `n` k-mers solides dans le filtre `O(n·num_hashes)`.
- **Test de voisinage** : à chaque pas, 4 extensions testées dans le filtre, chacune en
  `O(num_hashes)` — soit `O(1)` par rapport à `n` et à la longueur des séquences.
- **Traversée complète** : chaque k-mer solide est visité au plus une fois ⇒
  `O(n·num_hashes)` au total.
- **Espace** : `O(m)` bits pour l'oracle (constant, cf. §2), indépendant de la longueur
  des reads et des contigs.

### Synthèse

| | Alignement DP (Lot 2) | Traversée Bloom (Lot 3) |
|---|---|---|
| Temps | `O(n·m)` (quadratique) | `O(n·num_hashes)` (linéaire en k-mers) |
| Espace | `O(n·m)` | `O(m bits)` constant |
| Passage à l'échelle | comparaison de paires : explose | adapté aux millions de reads |

L'alignement reste utile **localement** (valider un chevauchement précis, mesurer
l'identité d'un contig vs référence — c'est d'ailleurs son rôle dans la validation de
recette du Lot 3). Mais la reconstruction globale repose sur la traversée du graphe
implicite, dont le coût mémoire constant et le temps linéaire en nombre de k-mers
justifient le choix du filtre de Bloom pour l'objectif de scalabilité du projet.

---

## 4. Recette

Le test `AssemblyEngineTests.test_assemble_reconstructs_toy_sequence` (et son pendant
d'intégration `AssemblyApiTests.test_create_assembly`) valident le critère CDC §5 :
à partir de reads chevauchants d'une séquence cible connue, le meilleur contig atteint
une **identité ≥ 98 %** vs la référence, identité calculée en réutilisant l'alignement de
chevauchement du Lot 2 (`alignment.overlap_align`).
