# Plan — Lot 1 : Module d'Ingestion et de Qualité (Projet ASG-2026)

> Document de **planification à valider avant codage**.
> Stack détectée : **Django 6 + DRF + django-cors-headers + PostgreSQL** (`asg_2026`) côté backend ;
> **React 19 + Vite 8 + MUI 9 + chart.js / react-chartjs-2 + axios + react-router-dom 7** côté frontend.

---

## 0. Rappel du périmètre (les 3 « questions » du Lot 1)

| # | Sous-module | Entrée | Sortie attendue |
|---|-------------|--------|-----------------|
| **Q1** | Ingestion & Qualité | Fichier **FASTQ** (séquences + scores qualité) | Conversion **sélective** en FASTA (filtrage par qualité) + rapport qualité |
| **Q2** | Granularité / k-mers | Séquences ingérées + paramètre **k** | Découpage paramétrable en k-mers + comptage |
| **Q3** | Livrable visuel | Comptage de k-mers (Q2) | **Histogramme de fréquence des k-mers** (spectre) pour estimer le taux d'erreur |

**Notion biologique clé** : un FASTQ = 4 lignes/read (`@id`, séquence, `+`, qualité ASCII Phred+33). Les erreurs de séquençage créent des k-mers rares (multiplicité 1–2). Le **spectre de k-mers** (histogramme « nombre de k-mers distincts » en fonction de « leur nombre d'occurrences ») permet de repérer ce pic d'erreurs → c'est l'objectif de Q3.

---

## 1. Décisions d'architecture à valider

1. **On ne stocke PAS les millions de reads dans PostgreSQL.**
   Le fichier brut est sauvegardé sur disque (`MEDIA_ROOT`), seuls les **agrégats** (stats, comptages, histogramme) + un **échantillon** de reads vont en base. → performant et suffisant pour le prototype.
2. **Parsing en Python pur** (pas de Biopython au départ) pour rester léger et lisible ; Biopython reste une option si besoin plus tard.
3. **Traitement synchrone** au début (fichiers de test petits/moyens). Si on passe à de très gros fichiers, on ajoutera Celery + Redis (hors Lot 1).
4. Comptage de k-mers via `collections.Counter` ; on ne matérialise que les k-mers **observés** (pas les 4^k possibles).

> ⚠️ À confirmer : ces 4 choix te conviennent-ils ? (notamment le point 1 : reads sur disque + agrégats en base).

---

## 2. Modèle de données (tables PostgreSQL)

Application Django : `back`. Tables proposées (modèles dans `backend/back/models.py`).

### Q1 — Ingestion & Qualité

**`Dataset`** — un fichier de séquençage importé
| Champ | Type | Description |
|-------|------|-------------|
| `id` | BigAuto (PK) | |
| `name` | CharField | nom donné par l'utilisateur |
| `original_filename` | CharField | nom du fichier source |
| `file` | FileField | fichier brut stocké (`uploads/`) |
| `input_format` | CharField (choices: `FASTQ`, `FASTA`) | format détecté |
| `total_reads` | IntegerField (null) | nb de reads (calculé) |
| `status` | CharField (choices: `UPLOADED`, `PROCESSING`, `DONE`, `ERROR`) | |
| `created_at` | DateTimeField (auto) | |

**`QualityReport`** — rapport qualité d'un Dataset (relation 1–1)
| Champ | Type | Description |
|-------|------|-------------|
| `dataset` | OneToOne → Dataset | |
| `mean_quality` | FloatField | score Phred moyen |
| `min_length` / `max_length` / `mean_length` | Integer/Float | distribution des longueurs |
| `gc_content` | FloatField | % GC |
| `per_position_quality` | JSONField | qualité moyenne par position (courbe) |
| `length_distribution` | JSONField | histogramme des longueurs |

**`FastaConversion`** — résultat d'une conversion sélective FASTQ→FASTA
| Champ | Type | Description |
|-------|------|-------------|
| `dataset` | FK → Dataset | |
| `min_mean_quality` | IntegerField | **seuil de qualité moyenne choisi par l'utilisateur** (filtre principal) |
| `min_length` | IntegerField (null) | longueur min conservée (filtre secondaire optionnel) |
| `reads_kept` / `reads_discarded` | IntegerField | bilan du filtrage |
| `output_file` | FileField | FASTA généré |
| `created_at` | DateTimeField | |

### Q2 — Granularité / k-mers

**`KmerAnalysis`** — un run de découpage pour un k donné
| Champ | Type | Description |
|-------|------|-------------|
| `dataset` | FK → Dataset | |
| `k` | IntegerField | taille du k-mer (paramétrable) |
| `source` | CharField (choices: `RAW`, `FILTERED`) | sur reads bruts ou filtrés |
| `total_kmers` | BigIntegerField | nb total de k-mers générés |
| `distinct_kmers` | BigIntegerField | nb de k-mers distincts |
| `created_at` | DateTimeField | |
| *contrainte* | `unique_together (dataset, k, source)` | évite les doublons de run |

**`KmerCount`** — comptage par k-mer (top-N stocké, ou tous selon volume)
| Champ | Type | Description |
|-------|------|-------------|
| `analysis` | FK → KmerAnalysis | |
| `sequence` | CharField(length=k) | le k-mer (ex. `ATGGC`) |
| `count` | IntegerField | nb d'occurrences |
| *index* | sur (`analysis`, `count`) | tri rapide |

> Pour limiter le volume : on stocke par défaut les **k-mers les plus fréquents (top 1000)** + on garde toujours le spectre complet (table ci-dessous) qui suffit pour l'histogramme.

### Q3 — Histogramme / spectre de k-mers

**`KmerSpectrumBin`** — une barre de l'histogramme
| Champ | Type | Description |
|-------|------|-------------|
| `analysis` | FK → KmerAnalysis | |
| `multiplicity` | IntegerField | nb d'occurrences (axe X) |
| `distinct_count` | BigIntegerField | nb de k-mers distincts ayant cette multiplicité (axe Y) |
| *contrainte* | `unique_together (analysis, multiplicity)` | |

> L'histogramme Q3 = `KmerSpectrumBin` tracé en barres (X = multiplicité, Y = distinct_count). Le pic à gauche (multiplicité 1–2) = erreurs de séquençage.

### Schéma relationnel
```
Dataset 1─1 QualityReport
Dataset 1─* FastaConversion
Dataset 1─* KmerAnalysis 1─* KmerCount
                        1─* KmerSpectrumBin
```

---

## 3. Backend — fichiers & endpoints (DRF)

Fichiers à créer / modifier dans `backend/back/` :
- `models.py` — les 6 modèles ci-dessus
- `serializers.py` *(nouveau)* — un serializer par modèle + serializers d'action (upload, conversion params, kmer params)
- `services/` *(nouveau package)* — logique métier pure (testable hors HTTP) :
  - `fastq_parser.py` — parsing FASTQ/FASTA, décodage qualité Phred
  - `quality.py` — calcul des stats qualité
  - `fasta_converter.py` — conversion sélective avec seuils
  - `kmer.py` — découpage k-mers + comptage + construction du spectre
- `views.py` — ViewSets DRF
- `urls.py` — routage (DRF router)
- `admin.py` — enregistrement des modèles
- `tests.py` — tests unitaires des services + endpoints

### Endpoints REST proposés (préfixe `/api/`)
| Méthode | URL | Rôle |
|---------|-----|------|
| `POST` | `/api/datasets/` | Upload d'un FASTQ/FASTA (Q1) |
| `GET` | `/api/datasets/` | Liste des datasets |
| `GET` | `/api/datasets/{id}/` | Détail + statut |
| `GET` | `/api/datasets/{id}/quality/` | Rapport qualité (Q1) |
| `POST` | `/api/datasets/{id}/convert/` | Conversion sélective → FASTA (Q1) |
| `GET` | `/api/conversions/{id}/download/` | Télécharger le FASTA généré |
| `POST` | `/api/datasets/{id}/kmers/` | Lancer un découpage k-mers (param `k`, `source`) (Q2) |
| `GET` | `/api/kmer-analyses/{id}/` | Détail d'un run (total/distinct) (Q2) |
| `GET` | `/api/kmer-analyses/{id}/top/` | Top k-mers (Q2) |
| `GET` | `/api/kmer-analyses/{id}/spectrum/` | Données de l'histogramme (Q3) |

---

## 4. Frontend — pages & composants (React + MUI + chart.js)

Arborescence à créer sous `frontend/src/` :
- `api/api.js` — déjà présent (axios). On ajoutera les fonctions d'appel par module.
- `routes/` ou config router dans `App.jsx` (react-router-dom) :
  - `/` — Accueil / liste des datasets
  - `/upload` — Import d'un FASTQ (Q1)
  - `/datasets/:id` — Détail : rapport qualité + conversion FASTA (Q1)
  - `/datasets/:id/kmers` — Lancer & visualiser le découpage k-mers (Q2)
  - `/kmer-analyses/:id/spectrum` — Histogramme de fréquence (Q3)
- `components/`
  - `UploadForm.jsx` (Q1)
  - `QualityReportCard.jsx` + courbe qualité par position (Q1)
  - `ConversionForm.jsx` — **filtres définis par l'utilisateur** : champ/slider **qualité moyenne minimale** (filtre principal) + longueur min optionnelle (Q1)
  - `KmerForm.jsx` — **valeur de `k` saisie par l'utilisateur** (input numérique paramétrable) (Q2)
  - `KmerTopTable.jsx` (Q2)
  - `KmerHistogram.jsx` — `<Bar>` de react-chartjs-2 (Q3)
- `pages/` — assemblage des composants par route
- Mise en page MUI : `AppBar` + navigation, thème commun.

> Les pages reprendront un **design cohérent (MUI)** ; l'étape de design est détaillée en §6.

---

## 5. Déroulé chronologique (checklist d'implémentation)

**Étape 0 — Préparation**
- [ ] Vérifier la connexion PostgreSQL (`asg_2026`) ; sinon proposer un fallback SQLite.
- [ ] Ajouter `MEDIA_ROOT` / `MEDIA_URL` dans `settings.py` + DRF `DEFAULT_*` config.
- [ ] Geler les dépendances backend dans `requirements.txt`.

**Étape 1 — Q1 Ingestion & Qualité**
- [ ] Modèles `Dataset`, `QualityReport`, `FastaConversion` + migration.
- [ ] Services `fastq_parser`, `quality`, `fasta_converter` + tests.
- [ ] Endpoints upload / quality / convert / download.
- [ ] Frontend : pages Upload + Détail (rapport qualité + conversion).

**Étape 2 — Q2 K-mers**
- [ ] Modèles `KmerAnalysis`, `KmerCount` + migration.
- [ ] Service `kmer` (découpage paramétrable + comptage) + tests.
- [ ] Endpoints kmers / top.
- [ ] Frontend : page paramétrage `k` + table top k-mers.

**Étape 3 — Q3 Histogramme**
- [ ] Modèle `KmerSpectrumBin` + migration.
- [ ] Construction du spectre dans le service `kmer`.
- [ ] Endpoint `/spectrum/`.
- [ ] Frontend : `KmerHistogram` (barres chart.js) + lecture du pic d'erreurs.

**Étape 4 — Qualité du code (plugins/skills)** *(voir §6)*
- [ ] Passage du skill **/code-review** sur le diff.
- [ ] Revue **design front-end** des pages.
- [ ] Corrections.

---

## 6. Utilisation des skills / plugins (design front-end + code review)

- **Design front-end** : une fois les pages React posées, on harmonise la mise en page MUI (thème, espacements, composants `Card`/`Table`/`Bar`), responsive, états de chargement/erreur. (Skill de design front-end si disponible, sinon revue manuelle MUI.)
- **Revue de code** : exécution du skill **`/code-review`** sur le diff de chaque étape pour détecter bugs et simplifications, puis application des correctifs. (Optionnel : `/code-review high` pour une couverture plus large.)

> Ces deux passes interviennent **après** que le code d'un module fonctionne, pas avant.

---

## 7. Points à confirmer avant de démarrer

1. Stockage reads **sur disque + agrégats en base** (pas tous les reads en SQL) — OK ?
2. PostgreSQL bien disponible en local (`asg_2026`, user `postgres`) — ou je prévois un fallback SQLite ?
3. Traitement **synchrone** d'abord (Celery plus tard si gros volumes) — OK ?
4. On commence par **Q1**, puis Q2, puis Q3 (dépendances naturelles) — OK ?
5. Top **1000** k-mers stockés par run + spectre complet — la limite te convient ?

➡️ Dis-moi ce que tu valides / modifies, et je commence l'implémentation à partir de l'Étape 0.