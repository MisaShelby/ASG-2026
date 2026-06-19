# Plan — Lot 3 : Moteur d'Assemblage « Memory-Efficient » (Approche Minia 2)

> Document de **planification à valider avant codage**, dans la continuité des Lots 1 et 2
> (voir [docs/LOT1_PLAN.md](LOT1_PLAN.md) et [docs/LOT2.md](LOT2.md)). Mêmes conventions :
> app Django `back`, services métier purs + testés, ViewSets DRF, pages React
> **MUI (composants interactifs) + Tailwind (mise en page/affichage)**, chart.js pour les
> graphiques.

---

## 0. Rappel du périmètre (cahier des charges, §Lot 3)

> *« L'objectif est de reconstruire les contigs sans jamais construire explicitement le
> Graphe de de Bruijn en mémoire, en utilisant une structure probabiliste pour tester la
> connectivité.*
>
> ***Structure Oracle (Filtre de Bloom)*** *: implémenter un Filtre de Bloom où seront
> insérés tous les k-mers distincts considérés comme « solides » (apparaissant au-delà d'un
> seuil de fréquence). Ce filtre servira d'outil de test d'appartenance à coût mémoire
> constant.*
>
> ***Algorithme de Traversée « On-the-fly »*** *: à partir d'un k-mer de départ (seed), le
> système doit explorer les voisins potentiels en générant les 4 extensions possibles
> (A, C, G, T) en 3'. Chaque extension est soumise au Filtre de Bloom : si le test est
> positif, la progression continue dans cette direction. Le Graphe de de Bruijn est donc ici
> conceptuel. Il n'est jamais construit entièrement ni stocké quelque part.*
>
> ***Sortie*** *: l'algorithme doit s'arrêter ou marquer un embranchement lorsque plusieurs
> extensions sont validées par le filtre (bifurcation dans le graphe implicite). Plusieurs
> contigs peuvent sortir du parcours.*
>
> ***Analyse critique*** *: étude de l'impact des faux positifs inhérents au Filtre de Bloom
> (création de chemins fantômes) et comment les paramètres du filtre (m bits, k fonctions de
> hachage) influencent la qualité de l'assemblage. »*

Critère de recette (CDC §5) : à partir d'un fichier de **10 000 reads**, reconstruire la
séquence cible avec une **identité > 98 %**.

Décomposition technique :

| # | Besoin | Détail |
|---|--------|--------|
| **A1** | K-mers solides | Comptage des k-mers (réutilise `services/kmer`), filtrage par **seuil de fréquence** paramétrable → ensemble des k-mers « solides ». |
| **A2** | Filtre de Bloom | Implémenté **from scratch** (Python pur) : bitset de `m` bits, `num_hashes` fonctions de hachage. Insertion de tous les k-mers solides. Test d'appartenance O(num_hashes). |
| **A3** | Traversée on-the-fly | Depuis un seed solide, extensions 3' **et** 5' (A/C/G/T) testées via le Bloom. 1 extension → on avance ; 0 → cul-de-sac ; ≥2 → embranchement (arrêt + marquage). |
| **A4** | Plusieurs contigs | Itération sur tous les k-mers solides comme seeds (en sautant les k-mers déjà parcourus) → plusieurs contigs en sortie. |
| **A5** | Validation identité | Référence optionnelle fournie par l'utilisateur ; identité du meilleur contig calculée en **réutilisant `alignment.overlap_align`** (Lot 2). |
| **A6** | Analyses CDC | Impact des faux positifs (chemins fantômes), mémoire Bloom vs dictionnaire, complexité O(n²) vs graphe — exposées **in-app** (pages + graphiques) **et** dans un rapport markdown. |

---

## 1. Décisions d'architecture (validées)

1. **Filtre de Bloom from scratch** (Python pur), pas de bibliothèque externe : on doit
   pouvoir justifier le fonctionnement interne et la consommation mémoire (CDC §3
   Scalabilité). ✅
2. **Oracle Bloom + ensemble de k-mers solides séparé** pour le seeding et l'anti-boucle
   (« visited »). Le **test de voisinage passe uniquement par le filtre de Bloom** ; le
   graphe de de Bruijn n'est **jamais matérialisé** (aucune liste d'arêtes/nœuds stockée).
   L'ensemble solide ne sert qu'à (1) énumérer les seeds et (2) marquer les k-mers déjà
   parcourus. Il fournit aussi la **baseline mémoire** (dictionnaire) pour la comparaison
   exigée par le CDC. ✅
3. **K-mers solides issus d'un Dataset du Lot 1** avec **(re)comptage à la volée** pour le
   `k` choisi (réutilise `services/kmer.count_kmers`), filtrés par seuil. Source `RAW`
   (reads bruts) ou `FILTERED` (reads d'une conversion FASTA), comme `KmerAnalysis`. ✅
4. **Validation de la recette intégrée** : l'utilisateur peut coller une **séquence de
   référence** (toy dataset / séquence cible) ; le backend calcule le **% d'identité** du
   meilleur contig vs référence en réutilisant l'alignement du Lot 2. ✅
5. **Analyses CDC exposées in-app** (pages + graphiques chart.js : FP vs paramètres, mémoire
   Bloom vs dict, longueurs de contigs) **et** consignées dans `docs/LOT3_ANALYSE.md`. ✅
6. **Historique des assemblages** persisté (`AssemblyRun`) + page de liste, cohérent avec
   `DatasetListPage` / `AlignmentHistoryPage`. ✅

---

## 2. Algorithme détaillé

### 2.1 Filtre de Bloom (`services/bloom.py`)

- Bitset : `bytearray(ceil(m / 8))`, accès bit par `byte_index, bit_mask`.
- `num_hashes` hachages dérivés par **double hashing** : deux hachages de base `h1`, `h2`
  (ex. `blake2b` du k-mer encodé en bytes, découpé en deux entiers), puis
  `g_i = (h1 + i · h2) mod m` pour `i` dans `[0, num_hashes)`. Évite de calculer
  `num_hashes` hachages cryptographiques indépendants.
- API : `add(item: str)`, `__contains__(item: str)`, `estimated_fp_rate(n_inserted)` (formule
  `(1 - e^{-num_hashes·n/m})^{num_hashes}`), `byte_size()` (mémoire réelle du bitset).
- Helper module-level `optimal_params(n, p)` → `(m, num_hashes)` optimaux pour `n` éléments et
  un taux de FP cible `p` (`m = -n·ln p / (ln 2)²`, `num_hashes = (m/n)·ln 2`), utilisé pour
  proposer des valeurs par défaut et pour l'analyse.
- **Garantie** : aucun faux négatif (un k-mer inséré est toujours « présent »). Les faux
  positifs sont possibles et constituent l'objet de l'analyse critique.

### 2.2 Traversée (`services/assembly.py`)

- `select_solid_kmers(counter, threshold) -> set[str]` : k-mers avec `count >= threshold`.
- `extend(kmer_suffix, direction, bloom, alphabet="ACGT")` : génère les 4 candidats
  (concat en 3' du suffixe (k−1), ou en 5' du préfixe (k−1)), retourne ceux présents dans le
  Bloom.
- `build_contig(seed, bloom, solid, visited)` : étend en 3' puis en 5'.
  - À chaque pas : si **exactement 1** extension validée et non-`visited` → on l'ajoute,
    on marque `visited`. Si **0** → cul-de-sac (fin). Si **≥ 2** → embranchement : on
    s'arrête et on note la bifurcation.
  - `visited` = `set` de k-mers déjà intégrés à un contig (anti-boucle, et évite de
    re-seeder au milieu d'un contig existant).
- `assemble(reads, k, threshold, m, num_hashes, reference=None) -> dict` :
  1. `counter = kmer.count_kmers(reads, k)` ; `solid = select_solid_kmers(...)`.
  2. Construire le Bloom, insérer tous les `solid`.
  3. Pour chaque k-mer solide non `visited` (ordre déterministe) : `build_contig(...)`.
  4. Filtrer les contigs trop courts (< k, ou un seuil de longueur min paramétrable par
     défaut) ; trier par longueur décroissante.
  5. Si `reference` fournie : `identity_to_reference(contig, reference)` pour chaque contig,
     `best_identity` = max.
  6. Retourner `contigs` + `stats` (distinct_kmers, solid_kmers, bloom_fp_rate, bloom_bytes,
     dict_bytes_estimate, num_contigs, longueurs, best_identity).
- `identity_to_reference(contig, ref)` : `res = alignment.overlap_align(contig, ref)` ;
  identité = `res["match_line"].count("|") / len(res["match_line"])` (0 si vide). On
  documente le garde-fou `MAX_CELLS` de `overlap_align` (toy dataset court → sans risque ;
  contig très long vs référence longue → rejet explicite plutôt que blocage).

### 2.3 Note « faux positifs / chemins fantômes »

Un faux positif du Bloom fait croire qu'un k-mer non solide est présent → la traversée peut
suivre un **chemin fantôme** (sur-extension, contig erroné) ou créer un **faux embranchement**
(arrêt prématuré). L'analyse (`docs/LOT3_ANALYSE.md` + page in-app) montre comment le taux de
FP `(1 - e^{-num_hashes·n/m})^{num_hashes}` décroît avec `m` et dépend de `num_hashes`, et son
effet observé sur le nombre/longueur des contigs et l'identité.

---

## 3. Modèle de données (PostgreSQL)

### `back_assemblyrun`

| Champ | Type | Description |
|-------|------|-------------|
| `id` | BigAuto (PK) | |
| `dataset` | FK → Dataset (null, `SET NULL`) | source des reads (traçabilité ; l'assemblage survit à la suppression du dataset) |
| `source` | CharField (`RAW`/`FILTERED`) | reads bruts ou reads filtrés (FASTA) |
| `k` | IntegerField | taille des k-mers |
| `solidity_threshold` | IntegerField | seuil de fréquence pour « solide » |
| `bloom_bits` | BigIntegerField | `m` (taille du bitset en bits) |
| `num_hashes` | IntegerField | nombre de fonctions de hachage |
| `distinct_kmers` | BigIntegerField | nb de k-mers distincts comptés |
| `solid_kmers` | BigIntegerField | nb de k-mers solides insérés dans le Bloom |
| `bloom_fp_rate` | FloatField | taux de FP théorique estimé |
| `bloom_bytes` | BigIntegerField | mémoire réelle du bitset |
| `dict_bytes_estimate` | BigIntegerField | mémoire estimée d'un dict/set équivalent (baseline) |
| `num_contigs` | IntegerField | nb de contigs produits |
| `max_contig_length` | IntegerField | longueur du plus long contig |
| `total_contig_length` | BigIntegerField | somme des longueurs |
| `reference_sequence` | TextField (blank) | séquence de référence optionnelle |
| `best_identity` | FloatField (null) | meilleure identité contig vs référence (0–1) |
| `contigs_file` | FileField (`assemblies/`, null) | FASTA des contigs téléchargeable |
| `status` | CharField | `DONE` / `ERROR` (cohérent avec `Dataset.Status`) |
| `created_at` | DateTimeField (auto) | |

### `back_contig`

| Champ | Type | Description |
|-------|------|-------------|
| `id` | BigAuto (PK) | |
| `assembly` | FK → AssemblyRun (`CASCADE`, `related_name="contigs"`) | |
| `index` | IntegerField | rang (0 = plus long) |
| `sequence` | TextField | séquence assemblée |
| `length` | IntegerField | longueur |
| `identity_to_reference` | FloatField (null) | identité vs référence (0–1) si référence fournie |

`docs/base.sql` complété (`back_assemblyrun`, `back_contig`, `FOREIGN KEY ... ON DELETE
SET NULL` pour `dataset`, `ON DELETE CASCADE` pour `assembly`).

---

## 4. Backend — fichiers & endpoints (DRF)

### Nouveaux fichiers
- `backend/back/services/bloom.py` — filtre de Bloom from scratch (cf. §2.1).
- `backend/back/services/assembly.py` — sélection des k-mers solides, traversée on-the-fly,
  calcul d'identité (cf. §2.2).

### Fichiers modifiés
- `models.py` — `AssemblyRun`, `Contig`.
- `serializers.py` — `AssemblyRunSerializer` (imbrique les `Contig` en lecture, accepte les
  paramètres en écriture), `ContigSerializer`.
- `views.py` — `AssemblyRunViewSet` (`create`/`list`/`retrieve`) : lit les reads du dataset
  (réutilise `services/read_access` / `fastq_parser`), valide les paramètres (k ≥ 2,
  seuil ≥ 1, m > 0, num_hashes ≥ 1, garde-fous de taille), appelle `assembly.assemble`,
  persiste `AssemblyRun` + `Contig`, génère le FASTA. Action `@action(detail=True)
  contigs.fasta` pour le téléchargement.
- `urls.py` — route `assemblies`.
- `admin.py` — enregistrement de `AssemblyRun` (+ inline `Contig`).
- `tests.py` — tests (cf. §6).

### Endpoints proposés (préfixe `/api/`)
| Méthode | URL | Rôle |
|---------|-----|------|
| `POST` | `/api/assemblies/` | Lance un assemblage (dataset, source, k, seuil, m, num_hashes, référence optionnelle) |
| `GET` | `/api/assemblies/` | Historique des assemblages |
| `GET` | `/api/assemblies/{id}/` | Détail (contigs + stats + analyse) |
| `GET` | `/api/assemblies/{id}/contigs.fasta` | Téléchargement FASTA des contigs |

---

## 5. Frontend — pages & composants

- `api/api.js` — ajout : `createAssembly`, `listAssemblies`, `getAssembly`,
  `downloadAssemblyContigs`.
- `pages/AssemblyPage.jsx` — formulaire de configuration (MUI : sélecteur de dataset,
  `source`, `k`, `solidity_threshold`, `bloom_bits`, `num_hashes`, zone de texte référence
  optionnelle ; bouton « Assembler »). Résultats : cartes de stats (mémoire, FP, nb contigs,
  identité) en Tailwind (`grid`, `gap`), liste des contigs via `ContigViewer`.
- `components/ContigViewer.jsx` — affichage des contigs (`font-mono`, `whitespace-pre`,
  `overflow-x-auto`, bouton de téléchargement FASTA) ; pour le meilleur contig, réutilise
  `AlignmentViewer.jsx` pour montrer l'alignement vs référence.
- `pages/AssemblyAnalysisPage.jsx` + `components/BloomAnalysisChart.jsx` — graphiques
  chart.js : taux de FP vs `m` (et vs `num_hashes`), mémoire Bloom vs dictionnaire,
  distribution des longueurs de contigs. Mise en page Tailwind, `Chart`/`Bar`/`Line` via
  react-chartjs-2 (déjà dans la stack).
- `pages/AssemblyHistoryPage.jsx` — liste des runs (cohérent avec `AlignmentHistoryPage`),
  clic → ré-affichage du détail.
- `App.jsx` — lien de navigation « Assemblage » + routes `/assembly`, `/assemblies/:id`,
  `/assembly/analysis` (ou analyse intégrée à la page de détail, à trancher en
  implémentation selon la lisibilité).

---

## 6. Tests

- `services/bloom` :
  - aucun faux négatif (tout k-mer inséré est « présent ») ;
  - taux de FP empirique cohérent avec la formule théorique (ordre de grandeur) ;
  - `optimal_params` retourne des valeurs sensées ; `byte_size` correct.
- `services/assembly` :
  - **toy dataset** : séquence connue fragmentée en reads (avec ~1 % d'erreurs) →
    reconstruction avec **identité ≥ 98 %** (recette CDC §5) ;
  - détection d'**embranchement** (≥ 2 extensions) et de **cul-de-sac** (0 extension) ;
  - **anti-boucle** (séquence répétée) ;
  - sélection des k-mers solides selon le seuil ;
  - cohérence des stats mémoire (bloom_bytes vs dict_bytes_estimate).
- Tests d'intégration des endpoints (`POST /assemblies/`, `GET /assemblies/{id}/`,
  téléchargement FASTA).

---

## 7. Déroulé chronologique (checklist d'implémentation)

- [ ] `services/bloom.py` (from scratch) + tests unitaires.
- [ ] `services/assembly.py` (k-mers solides + traversée on-the-fly + identité) + tests
      (toy dataset ≥ 98 %, embranchement, cul-de-sac, anti-boucle).
- [ ] Modèles `AssemblyRun` + `Contig` + migration ; mise à jour de `docs/base.sql`.
- [ ] Serializers + `AssemblyRunViewSet` + endpoints + génération FASTA + tests d'intégration.
- [ ] Frontend : `api.js`, `AssemblyPage`, `ContigViewer`.
- [ ] Frontend : `AssemblyAnalysisPage` + `BloomAnalysisChart`, `AssemblyHistoryPage`,
      navigation `App.jsx`.
- [ ] Vérification manuelle dans le navigateur (`npm run dev`) : un assemblage sur un dataset
      réel, un cas avec référence (identité affichée), téléchargement FASTA.
- [ ] `docs/LOT3_ANALYSE.md` : impact des faux positifs, mémoire Bloom vs dict (chiffré),
      complexité O(n²) alignement vs traversée par graphe.
- [ ] Revue **`/code-review`** sur le diff complet du Lot 3, puis corrections.
- [ ] Mise à jour de la section « État d'avancement » de `CLAUDE.md`.

---

## 8. Utilisation des skills / outils

- **superpowers** : brainstorming (ce plan) → writing-plans (plan d'implémentation détaillé) →
  test-driven-development pour les services `bloom`/`assembly` → requesting-code-review.
- **Frontend design** : Tailwind pour la mise en page (grilles, cartes de stats, affichage
  typographique des contigs), MUI pour les composants interactifs (champs, boutons, sélecteurs),
  chart.js/react-chartjs-2 pour les graphiques d'analyse — même répartition que Lots 1 et 2.
- **`/code-review`** : exécuté sur le diff complet du Lot 3 une fois le module fonctionnel
  (backend + frontend), avant de considérer le lot terminé.
- **CLAUDE.md** : référence d'énoncé (cf. §0, citation directe) ; section « État d'avancement »
  tenue à jour (Lot 3 en cours).

---

➡️ Plan à valider. Une fois relu, je passe au plan d'implémentation détaillé (writing-plans)
puis au code en TDD, en démarrant par `services/bloom.py`.
