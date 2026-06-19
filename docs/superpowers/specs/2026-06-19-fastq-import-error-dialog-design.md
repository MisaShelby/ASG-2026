# Design : Dialog d'erreur pour l'import FASTQ et la conversion FASTQ→FASTA

## Contexte

Lot 1 (ingestion) valide déjà la structure FASTQ (en-tête `@`, séparateur `+`,
longueur séquence == longueur qualité) dans
`backend/back/services/fastq_parser.py`. Mais :

1. **Aucune validation des caractères de la séquence** : un read contenant des
   caractères comme `/`, `X`, `9`, `%`, `@` est accepté tel quel.
2. **Le message d'erreur est perdu** : quand `_ingest()` (dans
   `backend/back/views.py`) intercepte une `ValueError` levée par le parseur,
   le dataset passe en statut `ERROR` mais le message d'erreur n'est stocké
   nulle part. Le frontend ne voit qu'un statut `ERROR` sans explication.
3. **Pas de dialog d'erreur côté frontend** : les erreurs d'import et de
   conversion s'affichent (quand elles s'affichent) comme du JSON brut dans un
   `Alert` MUI.
4. **La conversion FASTQ→FASTA peut planter en 500** : l'action `convert` de
   `DatasetViewSet` appelle `fasta_converter.convert_fastq_to_fasta()`, qui
   relit le fichier via `parse_fastq()`, sans intercepter les `ValueError`.

## Décisions validées avec l'utilisateur

- Alphabet de séquence autorisé : **A, C, G, T, N** (N = base indéterminée,
  cas réel en séquençage). Tout autre caractère déclenche une erreur "read
  invalide".
- Comportement en présence de plusieurs reads invalides : **fail-fast**, on
  s'arrête à la première erreur trouvée (cohérent avec la validation
  structurelle déjà en place : en-tête, séparateur `+`, longueur).
- Portée UI : la dialog d'erreur apparaît sur la page d'**import** (upload)
  et sur l'action **Convertir** (FASTQ→FASTA) de la page détail dataset.
- Flux d'import : si l'import échoue (reads invalides), on **reste sur la
  page d'import** (pas de navigation vers la page détail).

## Backend

### 1. Validation des caractères (`backend/back/services/fastq_parser.py`)

```python
ALLOWED_BASES = frozenset("ACGTN")


def _validate_bases(seq: str, header: str) -> None:
    invalid = sorted(set(seq.upper()) - ALLOWED_BASES)
    if invalid:
        raise ValueError(
            f"Read invalide {header!r} : caractère(s) non autorisé(s) dans la "
            f"séquence : {', '.join(invalid)} (bases acceptées : A, C, G, T, N)"
        )
```

- Appelée dans `parse_fastq()` juste après la vérification de longueur
  existante (avant le `yield`).
- Appelée aussi dans `parse_fasta()` (même alphabet, pour cohérence — un
  FASTA corrompu doit être détecté de la même façon). Nécessite de garder la
  ligne d'en-tête brute (`>...`) pour le message d'erreur, en plus de
  `identifier`.

### 2. Mémoriser le message d'erreur

- `backend/back/models.py` : nouveau champ sur `Dataset` :
  `error_message = models.TextField(blank=True, default="")`.
- Migration Django associée.
- `backend/back/views.py`, `DatasetViewSet._ingest()` :
  - branche `except ValueError as exc:` → `dataset.error_message = str(exc)`
    (en plus de `dataset.status = Dataset.Status.ERROR`).
  - branche succès → `dataset.error_message = ""`.
  - branche `except Exception:` (erreur serveur inattendue) →
    `dataset.error_message = "Erreur interne lors du traitement du fichier."`
    avant le `raise` existant (le `finally: dataset.save()` reste inchangé).

### 3. Exposer l'erreur via l'API (`backend/back/serializers.py`)

- `DatasetSerializer` : ajoute `"error_message"` aux `fields` et aux
  `read_only_fields`.
- `DatasetUploadSerializer` : ajoute `"status"` et `"error_message"` aux
  `fields`, listés dans `read_only_fields`. Comme `_ingest()` s'exécute de
  façon synchrone dans `perform_create()` avant que la vue ne sérialise la
  réponse, le POST `/datasets/` peut directement renvoyer le statut final
  (`DONE` ou `ERROR`) et le message d'erreur, sans round-trip supplémentaire
  côté frontend.

### 4. Conversion FASTQ→FASTA robuste (`backend/back/views.py`, action `convert`)

```python
try:
    with dataset.file.open("rt") as handle:
        kept, discarded = fasta_converter.convert_fastq_to_fasta(
            handle, out_buffer, min_mean_quality, min_length
        )
except ValueError as exc:
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

## Frontend

### 1. Composant `frontend/src/components/ErrorDialog.jsx`

Dialog MUI réutilisable : props `open`, `onClose`, `title` (défaut "Erreur
d'import"), `message`. Affiche le message avec retours à la ligne préservés
(`whiteSpace: 'pre-wrap'`) et un bouton "Fermer".

### 2. Extraction de message lisible

Petite fonction utilitaire (ajoutée dans `frontend/src/api/api.js`) :

```js
export function extractErrorMessage(err, fallback) {
  const data = err?.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  if (data.error_message) return data.error_message
  const firstKey = Object.keys(data)[0]
  if (firstKey && Array.isArray(data[firstKey])) return data[firstKey][0]
  return fallback
}
```

Remplace les `JSON.stringify(err.response.data)` actuels.

### 3. `frontend/src/pages/UploadPage.jsx`

- Nouvel état `errorDialog` (string | null).
- Après upload réussi en HTTP : si `res.data.status === 'ERROR'`, ouvrir la
  dialog avec `res.data.error_message` et **ne pas naviguer**. Sinon,
  navigation vers `/datasets/{id}` comme avant.
- En cas d'échec HTTP (400/500), ouvrir la dialog via `extractErrorMessage`.
- L'`Alert` existant pour "Sélectionnez un fichier" (validation cliente
  simple, avant tout appel réseau) reste inline, inchangé.

### 4. `frontend/src/pages/DatasetDetailPage.jsx`

- Nouvel état dédié `convertErrorDialog` (string | null) pour ne plus
  partager l'état `error` (actuellement utilisé à la fois pour "dataset
  introuvable" et pour les erreurs de conversion — ce qui est le bug source
  de confusion). `handleConvert()` utilise désormais ce nouvel état + la
  `ErrorDialog`.
- Si le dataset chargé a `status === 'ERROR'`, un `Alert` (pas une dialog,
  car pas d'action utilisateur déclenchante) affiche `dataset.error_message`
  en haut de page — utile pour les datasets en erreur consultés depuis la
  liste (`DatasetListPage`).

## Tests

- `backend/back/tests.py`, `FastqParserTests` :
  - séquence avec caractère invalide (`/`, `X`, `9`, `%`, `@`) en FASTQ →
    `ValueError`.
  - même chose en FASTA.
  - séquence avec `N` → acceptée (pas d'erreur).
- Nouveau test API (`APIClient`) :
  - upload d'un FASTQ contenant un read invalide → réponse 201 avec
    `status == "ERROR"` et `error_message` non vide.
  - action `convert` sur un dataset dont le fichier contient un read invalide
    → réponse `400` avec `detail` non vide (au lieu d'un 500).

## Hors-scope (explicitement exclu par les réponses de l'utilisateur)

- Accumulation de toutes les erreurs d'un fichier (on garde le comportement
  fail-fast existant).
- Dialog sur la page k-mers (reste un `Alert` JSON, inchangé).
- Codes IUPAC d'ambiguïté étendus (R, Y, S, W, K, M, B, D, H, V) — uniquement
  `A, C, G, T, N`.
