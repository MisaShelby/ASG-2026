# Plan — Lot 2 : Module d'Alignement par Programmation Dynamique (Projet ASG-2026)

> Document de **planification à valider avant codage**, dans la continuité du Lot 1
> (voir [docs/LOT1_PLAN.md](LOT1_PLAN.md)). Mêmes conventions : app Django `back`,
> services métier purs + testés, ViewSets DRF, pages React **MUI (composants interactifs)
> + Tailwind (mise en page/affichage)**.

---

## 0. Rappel du périmètre (cahier des charges, §Lot 2)

> *« Afin de valider localement certains chevauchements complexes, un moteur d'alignement
> est requis :*
> *- **Algorithme** : Implémentation d'une variante de programmation dynamique pour
> trouver la Plus Longue Sous-Séquence Commune entre deux reads.*
> *- **Contrainte** : Le module doit retourner le score d'alignement et la position du
> chevauchement.*
> *- **Livrable** : Une page pour choisir ou uploader deux reads et puis affiche
> l'alignement de façon lisible. »*

Décomposition technique (mise à jour suite à tes précisions) :

| # | Besoin | Détail |
|---|--------|--------|
| **A1** | Algorithme DP | **Alignement de chevauchement** (*overlap alignment*) — variante de programmation dynamique à bords libres (proche de Needleman-Wunsch), scoring **match = +1, mismatch = −1, gap = −2** |
| **A2** | Résultat | score d'alignement (somme pondérée match/mismatch/gap) **+** position du **chevauchement contigu** (suffixe/préfixe) dans chaque read |
| **A3** | Page | choisir deux reads (dataset Lot 1) **ou** les saisir/uploader manuellement, puis affichage lisible de l'alignement |

**Notion clé** : contrairement à une LCS classique (qui autorise des trous n'importe où
dans la séquence), on cherche ici un **chevauchement contigu** — la fin d'un read qui
recouvre le début de l'autre, comme lors d'un assemblage réel, avec un taux d'erreur
toléré (mismatches/gaps pénalisés mais pas interdits). La table DP est initialisée avec
des **bords libres** (`dp[i][0] = 0` pour tout i, `dp[0][j] = 0` pour tout j) afin de ne
pas pénaliser la partie de chaque read qui n'appartient pas au chevauchement. Le meilleur
score est recherché sur la **dernière ligne et la dernière colonne** de la table (c'est
la variante dite *overlap alignment*). Le backtracking depuis cette cellule jusqu'à un
bord (i=0 ou j=0) donne à la fois le score, les positions du chevauchement, et — en
parcourant le même chemin — la représentation alignée à 3 lignes (read A / symboles de
correspondance / read B).

---

## 1. Décisions d'architecture (validées)

1. **Deux façons de fournir un read**, indépendamment pour le read A et le read B :
   - **Choisir** un read existant d'un Dataset du Lot 1, par son **index** (n-ième read
     du fichier) — relu à la volée depuis le fichier (cohérent avec la décision du
     Lot 1 de ne pas stocker les reads individuels en base). ✅
   - **Uploader / coller** une séquence manuellement (texte collé ou petit fichier
     FASTA/texte lu côté client) — aucun stockage serveur de ce fichier, seule la
     séquence textuelle est envoyée à l'API.
2. **Chevauchement = overlap contigu (suffixe/préfixe)**, pas une LCS dispersée avec
   trous. Détecté par un alignement de chevauchement (bords libres) sur la table DP. ✅
3. **Scoring de l'alignement** : ✅
   - ✅ match = **+1**
   - ❌ mismatch = **−1**
   - ➖ gap (insertion/délétion) = **−2**
   (pénalité de gap linéaire, pas de distinction ouverture/extension — suffisant pour
   ce prototype.)
4. **Limite de longueur** par read pour le prototype : **5000 nt** (garde-fou pour garder
   le calcul O(n·m) instantané en cas de saisie manuelle longue — pas une contrainte du
   cahier des charges). ✅
5. **Historique des alignements** : chaque calcul est persisté (`AlignmentRun`) et une
   page de liste (`AlignmentHistoryPage`) fait partie du périmètre. ✅

---

## 2. Modèle de données (PostgreSQL)

Une seule table nécessaire, `back_alignmentrun` :

| Champ | Type | Description |
|-------|------|--------------|
| `id` | BigAuto (PK) | |
| `read_a_label` | CharField | nom affiché (ex. `"Dataset X — read #12"` ou `"Read A (manuel)"`) |
| `read_a_sequence` | TextField | séquence de A (toujours stockée, qu'elle vienne d'un dataset ou d'une saisie) |
| `dataset_a` | FK → Dataset (null, `SET NULL`) | traçabilité si A vient d'un dataset Lot 1 |
| `read_a_index` | IntegerField (null) | position du read dans le fichier dataset, si applicable |
| `read_b_label` | CharField | idem pour B |
| `read_b_sequence` | TextField | |
| `dataset_b` | FK → Dataset (null, `SET NULL`) | |
| `read_b_index` | IntegerField (null) | |
| `score` | IntegerField | score d'alignement pondéré (match +1 / mismatch −1 / gap −2) |
| `read_a_start` / `read_a_end` | IntegerField (null) | position du chevauchement contigu dans A (1-based, inclusif) |
| `read_b_start` / `read_b_end` | IntegerField (null) | position du chevauchement contigu dans B |
| `aligned_a` | TextField | ligne A avec gaps `-` pour l'affichage |
| `match_line` | TextField | ligne de symboles : `\|` match, `.` mismatch, espace sous un gap |
| `aligned_b` | TextField | ligne B avec gaps `-` pour l'affichage |
| `created_at` | DateTimeField (auto) | |

`docs/base.sql` sera complété avec cette table (même convention de nommage
`back_<modele>`, `FOREIGN KEY ... ON DELETE SET NULL` pour `dataset_a`/`dataset_b` —
l'alignement doit survivre à la suppression du dataset source, seule la traçabilité
est perdue).

---

## 3. Backend — fichiers & endpoints (DRF)

### Nouveaux fichiers
- `backend/back/services/alignment.py` — algorithme pur :
  - `overlap_align(a: str, b: str) -> dict` : construit la table DP à bords libres
    (scoring match=+1/mismatch=−1/gap=−2), cherche le meilleur score sur la dernière
    ligne/colonne, backtrack jusqu'à un bord, retourne `score`, `a_start/a_end`,
    `b_start/b_end`, `aligned_a`, `match_line`, `aligned_b`. Si aucun chevauchement
    positif n'existe (score ≤ 0), retourne `score=0` et positions `None`.
- `backend/back/services/read_access.py` — lecture d'un read par index dans un fichier
  Dataset existant (réutilise `services/fastq_parser.parse`), + aperçu paginé des reads
  d'un dataset (identifiant, longueur, début de séquence) pour le sélecteur frontend.

### Fichiers modifiés
- `models.py` — ajout `AlignmentRun`.
- `serializers.py` — `AlignmentRunSerializer`, `ReadPreviewSerializer`.
- `views.py` :
  - `DatasetViewSet` : actions `@action(detail=True) reads` (liste paginée d'aperçus)
    et `read_at` (récupère un read complet par index).
  - `AlignmentRunViewSet` (`ModelViewSet` restreint à `create`/`list`/`retrieve`) :
    construit les séquences (depuis dataset+index ou texte fourni), valide la limite
    de 5000 nt, appelle `alignment.overlap_align`, persiste le résultat.
- `urls.py` — déclaration des nouvelles routes.
- `admin.py` — enregistrement de `AlignmentRun`.
- `tests.py` — tests de `alignment.overlap_align` :
  - chevauchement net avec quelques erreurs (suffixe de A ≈ préfixe de B),
  - aucun chevauchement (score ≤ 0 → résultat vide),
  - chevauchement total (un read entièrement contenu dans l'autre),
  - vérification du score (somme exacte match/mismatch/gap) et des positions ;
  - tests d'intégration des endpoints (lecture par index, création d'un alignement).

### Endpoints proposés (préfixe `/api/`)
| Méthode | URL | Rôle |
|---------|-----|------|
| `GET` | `/api/datasets/{id}/reads/?limit=50&offset=0` | Aperçu paginé des reads d'un dataset (pour le sélecteur) |
| `GET` | `/api/datasets/{id}/reads/{index}/` | Récupère un read complet (id + séquence) par index |
| `POST` | `/api/alignments/` | Lance un alignement (payload : pour A et B, soit `dataset` + `index`, soit `sequence`) |
| `GET` | `/api/alignments/` | Historique des alignements |
| `GET` | `/api/alignments/{id}/` | Détail d'un alignement (pour ré-affichage) |

---

## 4. Frontend — pages & composants

- `api/api.js` — ajout : `listDatasetReads`, `getDatasetRead`, `createAlignment`,
  `listAlignments`, `getAlignment`.
- `components/ReadPicker.jsx` — sélecteur réutilisable (mode « Depuis un dataset »
  avec liste déroulante dataset + index, ou mode « Saisie manuelle » avec zone de texte
  + bouton d'upload de fichier lu côté client). Mise en page en **Tailwind**
  (`grid`, `gap`, bascule d'onglets simple), champs de saisie en **MUI** (`TextField`,
  `ToggleButtonGroup`).
- `components/AlignmentViewer.jsx` — affichage à 3 lignes en **Tailwind**
  (`font-mono`, `whitespace-pre`, `overflow-x-auto`, surlignage vert pour les matches,
  rouge/orangé pour les mismatches) — zone d'affichage typographique pure, cas d'usage
  naturel pour Tailwind plutôt que MUI.
- `pages/AlignmentPage.jsx` — deux `ReadPicker` côte à côte (Tailwind `grid grid-cols-1
  md:grid-cols-2 gap-6`), bouton « Aligner » (MUI), puis cartes de résultat (score,
  positions) + `AlignmentViewer`.
- `pages/AlignmentHistoryPage.jsx` — liste des alignements passés (cohérence avec
  `DatasetListPage`), clic → ré-affichage en lecture seule via `AlignmentViewer`.
- `App.jsx` — ajout d'un lien de navigation « Alignement » + routes `/alignment` et
  `/alignments/:id`.

---

## 5. Déroulé chronologique (checklist d'implémentation)

- [ ] Modèle `AlignmentRun` + migration ; mise à jour de `docs/base.sql`.
- [ ] Service `alignment.overlap_align` (DP bords libres + backtracking) + tests
      unitaires (chevauchement net avec erreurs, aucun chevauchement, chevauchement
      total, vérification exacte du score).
- [ ] Service `read_access` (aperçu paginé + lecture par index) + tests.
- [ ] Serializers + endpoints `reads`/`read_at`/`alignments` + tests d'intégration.
- [ ] Frontend : `ReadPicker`, `AlignmentViewer`, `AlignmentPage` (Tailwind pour la
      mise en page/l'affichage typographique, MUI pour les champs et boutons).
- [ ] Frontend : `AlignmentHistoryPage`.
- [ ] Vérification manuelle dans le navigateur (`npm run dev`) : un cas avec
      chevauchement net (avec quelques erreurs), un cas sans rien en commun.
- [ ] Revue **`/code-review`** sur le diff complet du Lot 2, puis corrections.

---

## 6. Utilisation des skills / outils

- **Design front-end** : Tailwind pour la mise en page (grilles, espacement) et
  l'affichage typographique (`AlignmentViewer`), MUI conservé pour les composants
  interactifs (boutons, champs, listes) — même répartition que validée pour le Lot 1.
- **`/code-review`** : exécuté sur le diff complet du Lot 2 une fois le module
  fonctionnel (backend + frontend), avant de considérer le lot terminé.
- **CLAUDE.md** : sert de référence d'énoncé (cf. §0 ci-dessus, citation directe) ;
  la section « État d'avancement » est tenue à jour (Lot 1 terminé, Lot 2 en cours).
- **« superpowers »** : ce nom ne correspond à aucun skill disponible dans cet
  environnement — non utilisé. Si tu fais référence à un plugin/skill précis,
  dis-m'en plus et je l'intégrerai.

---

## 7. Détail d'implémentation à noter (pas une question, juste pour info)

La DP à bords libres gère **automatiquement les deux orientations** du chevauchement
(suffixe de A / préfixe de B, **ou** suffixe de B / préfixe de A) en une seule passe —
pas besoin de demander à l'utilisateur dans quel sens comparer les deux reads, ni de
lancer l'algorithme deux fois.

➡️ Plan figé sur ces bases. Je démarre l'implémentation à partir du modèle
`AlignmentRun` et du service `overlap_align`, sauf remarque de ta part.
