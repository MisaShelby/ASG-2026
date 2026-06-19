# Dialog d'erreur import FASTQ / conversion FASTA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quand l'import d'un fichier FASTQ échoue (caractère invalide dans un
read, longueur séquence/qualité différente, structure 4-lignes invalide), ou
quand l'action "Convertir" (FASTQ→FASTA) échoue, l'utilisateur voit une dialog
d'erreur claire expliquant la cause — au lieu d'un JSON brut ou d'un statut
"ERROR" silencieux.

**Architecture:** Le parseur FASTQ/FASTA (`fastq_parser.py`) valide désormais
l'alphabet des séquences (A, C, G, T, N) en plus des contrôles déjà en place.
Le message d'erreur, auparavant perdu, est stocké sur le `Dataset`
(`error_message`) et renvoyé directement dans la réponse d'upload (puisque
l'ingestion est synchrone). Côté frontend, un composant `ErrorDialog` MUI
réutilisable affiche ce message sur la page d'import et sur l'action de
conversion.

**Tech Stack:** Django + DRF (backend/back), React + Vite + MUI (frontend/src).

## Global Constraints

- Alphabet de séquence accepté : **A, C, G, T, N** uniquement (pas de codes
  IUPAC étendus). Tout autre caractère (ex: `/`, `X`, `9`, `%`, `@`) est rejeté.
- Comportement **fail-fast** : on s'arrête à la première erreur trouvée dans le
  fichier (pas d'accumulation de toutes les erreurs).
- La dialog d'erreur s'affiche sur **2 surfaces** : la page d'import (upload)
  et l'action "Convertir" (FASTQ→FASTA) de la page détail dataset. Pas sur la
  page k-mers.
- Sur la page d'import, si l'import échoue, l'utilisateur **reste sur la page
  d'import** (pas de navigation vers la page détail).
- Tous les textes UI sont en français, cohérent avec le reste de l'app.
- Le frontend n'a pas de framework de test (pas de Jest/Vitest configuré) :
  la vérification se fait via `npm run build` + test manuel navigateur.
- Commande de test backend : `cd backend && ./venv/bin/python manage.py test back -v 1`
  (53 tests passent actuellement, doit rester vert après chaque tâche).

---

### Task 1: Validation de l'alphabet de séquence (FASTQ + FASTA)

**Files:**
- Modify: `backend/back/services/fastq_parser.py`
- Test: `backend/back/tests.py` (classe `FastqParserTests`)

**Interfaces:**
- Produces: `_validate_bases(seq: str, header: str) -> None` (lève
  `ValueError` si `seq` contient un caractère hors de `ACGTN`). Utilisée par
  Task 2 et Task 3 indirectement (toute erreur de caractère remonte comme
  `ValueError` standard, déjà géré par l'existant).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `backend/back/tests.py`, classe `FastqParserTests`, ajouter ces méthodes
juste après `test_parse_fasta` (vers la ligne 50) :

```python
    def test_parse_fastq_invalid_character(self):
        bad = "@r\nATGX\n+\nIIII\n"
        with self.assertRaises(ValueError):
            list(parse_fastq(io.StringIO(bad)))

    def test_parse_fastq_accepts_n_base(self):
        ok = "@r\nATGN\n+\nIIII\n"
        reads = list(parse_fastq(io.StringIO(ok)))
        self.assertEqual(reads[0].sequence, "ATGN")

    def test_parse_fasta_invalid_character(self):
        bad = ">r1\nATG/CGT\n"
        with self.assertRaises(ValueError):
            list(parse_fasta(io.StringIO(bad)))
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd backend && ./venv/bin/python manage.py test back.tests.FastqParserTests -v 2`

Expected: `test_parse_fastq_invalid_character` et `test_parse_fasta_invalid_character`
échouent avec un message du type `ValueError not raised` (le code actuel
n'a pas encore de validation des caractères). `test_parse_fastq_accepts_n_base`
passe déjà (rien n'empêche `N` aujourd'hui).

- [ ] **Step 3: Implémenter la validation**

Remplacer le contenu de `backend/back/services/fastq_parser.py` en entier par :

```python
"""Parsing FASTQ / FASTA en Python pur.

FASTQ : 4 lignes par read
    @identifiant
    SEQUENCE
    +
    SCORES_QUALITE (ASCII Phred+33)

FASTA : 2 lignes par read
    >identifiant
    SEQUENCE
"""
from dataclasses import dataclass

PHRED_OFFSET = 33
ALLOWED_BASES = frozenset("ACGTN")


@dataclass
class Read:
    """Un read de séquençage."""

    identifier: str
    sequence: str
    qualities: list[int]  # scores Phred décodés (vide pour le FASTA)


def decode_quality(quality_line: str) -> list[int]:
    """Décode une ligne de qualité ASCII (Phred+33) en scores entiers."""
    return [ord(c) - PHRED_OFFSET for c in quality_line]


def _validate_bases(seq: str, header: str) -> None:
    """Vérifie que la séquence ne contient que des bases ACGTN.

    Lève ValueError listant les caractères rejetés (ex: '/', 'X', '9', '%').
    `seq` doit déjà être en majuscules.
    """
    invalid = sorted(set(seq) - ALLOWED_BASES)
    if invalid:
        raise ValueError(
            f"Read invalide {header!r} : caractère(s) non autorisé(s) dans la "
            f"séquence : {', '.join(invalid)} (bases acceptées : A, C, G, T, N)"
        )


def parse_fastq(handle):
    """Itère sur les reads d'un fichier FASTQ.

    `handle` est un itérable de lignes (fichier texte ouvert).
    Lève ValueError si la structure 4-lignes est invalide, si la longueur
    séquence/qualité diffère, ou si la séquence contient des caractères hors
    de l'alphabet ACGTN.
    """
    while True:
        header = handle.readline()
        if not header:
            break  # fin de fichier
        header = header.rstrip("\n")
        if header == "":
            continue  # ligne vide tolérée entre les reads
        if not header.startswith("@"):
            raise ValueError(f"En-tête FASTQ invalide : {header!r}")

        seq = handle.readline().rstrip("\n")
        plus = handle.readline().rstrip("\n")
        qual = handle.readline().rstrip("\n")

        if not plus.startswith("+"):
            raise ValueError(f"Ligne séparateur '+' attendue, reçu : {plus!r}")
        if len(seq) != len(qual):
            raise ValueError(
                f"Séquence ({len(seq)}) et qualité ({len(qual)}) de longueurs différentes "
                f"pour le read {header!r}"
            )
        seq = seq.upper()
        _validate_bases(seq, header)

        yield Read(
            identifier=header[1:],
            sequence=seq,
            qualities=decode_quality(qual),
        )


def parse_fasta(handle):
    """Itère sur les reads d'un fichier FASTA (sans qualité).

    Lève ValueError si une séquence contient des caractères hors de
    l'alphabet ACGTN.
    """
    header = None
    identifier = None
    seq_parts: list[str] = []
    for line in handle:
        line = line.rstrip("\n")
        if line.startswith(">"):
            if identifier is not None:
                seq = "".join(seq_parts).upper()
                _validate_bases(seq, header)
                yield Read(identifier, seq, [])
            header = line
            identifier = line[1:]
            seq_parts = []
        elif line:
            seq_parts.append(line)
    if identifier is not None:
        seq = "".join(seq_parts).upper()
        _validate_bases(seq, header)
        yield Read(identifier, seq, [])


def parse(handle, input_format: str):
    """Dispatch selon le format ('FASTQ' ou 'FASTA')."""
    fmt = input_format.upper()
    if fmt == "FASTQ":
        return parse_fastq(handle)
    if fmt == "FASTA":
        return parse_fasta(handle)
    raise ValueError(f"Format non supporté : {input_format!r}")
```

- [ ] **Step 4: Lancer tous les tests, vérifier qu'ils passent**

Run: `cd backend && ./venv/bin/python manage.py test back -v 1`

Expected: `OK` — 56 tests (53 existants + 3 nouveaux), aucune régression sur
les tests existants (`test_parse_fastq`, `test_parse_fasta`, k-mers, qualité,
conversion, alignement, assemblage utilisent tous des séquences déjà en
ACGT/ACGTN).

- [ ] **Step 5: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add backend/back/services/fastq_parser.py backend/back/tests.py
git commit -m "feat(lot1): valider l'alphabet ACGTN des séquences FASTQ/FASTA"
```

---

### Task 2: Persister et exposer le message d'erreur d'import

**Files:**
- Modify: `backend/back/models.py:7-37` (classe `Dataset`)
- Create: migration via `makemigrations` (nom auto-généré, ex.
  `backend/back/migrations/0004_dataset_error_message.py`)
- Modify: `backend/back/views.py:68-91` (méthode `_ingest`)
- Modify: `backend/back/serializers.py:22-43` (`DatasetSerializer`,
  `DatasetUploadSerializer`)
- Test: `backend/back/tests.py` (nouvelle classe `DatasetIngestApiTests`)

**Interfaces:**
- Consumes: `parse()` de Task 1 (lève `ValueError` avec un message explicite
  en cas de read invalide).
- Produces: `Dataset.error_message` (champ modèle, string). Réponse JSON de
  `POST /api/datasets/` contient désormais `"status"` et `"error_message"`.
  Réponse JSON de `GET /api/datasets/{id}/` contient aussi `"error_message"`.

- [ ] **Step 1: Écrire le test API qui échoue**

Dans `backend/back/tests.py`, ajouter cette classe après `FastaConverterTests`
(vers la ligne 81, avant `class KmerTests`) :

```python
class DatasetIngestApiTests(TestCase):
    """Vérifie que l'API d'upload renvoie le statut et le message d'erreur."""

    def setUp(self):
        self.client = APIClient()

    def test_upload_invalid_read_returns_error_message(self):
        bad_file = SimpleUploadedFile(
            "bad.fastq", b"@r1\nATGX\n+\nIIII\n", content_type="text/plain"
        )
        response = self.client.post(
            "/api/datasets/",
            {"name": "bad", "input_format": "FASTQ", "file": bad_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "ERROR")
        self.assertIn("X", response.data["error_message"])

    def test_upload_valid_file_has_empty_error_message(self):
        good_file = SimpleUploadedFile(
            "good.fastq", b"@r1\nATGC\n+\nIIII\n", content_type="text/plain"
        )
        response = self.client.post(
            "/api/datasets/",
            {"name": "good", "input_format": "FASTQ", "file": good_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "DONE")
        self.assertEqual(response.data["error_message"], "")
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd backend && ./venv/bin/python manage.py test back.tests.DatasetIngestApiTests -v 2`

Expected: échec avec `KeyError: 'error_message'` (le champ n'existe pas
encore dans `DatasetUploadSerializer`).

- [ ] **Step 3: Ajouter le champ au modèle**

Dans `backend/back/models.py`, dans la classe `Dataset`, remplacer :

```python
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPLOADED
    )
    created_at = models.DateTimeField(auto_now_add=True)
```

par :

```python
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.UPLOADED
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
```

- [ ] **Step 4: Générer et appliquer la migration**

Run:
```bash
cd backend && ./venv/bin/python manage.py makemigrations back
```
Expected: crée un fichier `back/migrations/000X_dataset_error_message.py`
(ou nom similaire auto-généré) ajoutant le champ `error_message`.

Run:
```bash
./venv/bin/python manage.py migrate back
```
Expected: `Applying back.000X_dataset_error_message... OK`.

- [ ] **Step 5: Mettre à jour `_ingest()` pour stocker le message**

Dans `backend/back/views.py`, remplacer la méthode `_ingest` (actuellement
lignes 68-91) :

```python
    def _ingest(self, dataset):
        """Calcule le rapport qualité et le nombre de reads après upload.

        Un fichier mal formé (ValueError) marque le dataset en ERROR sans
        faire échouer l'upload ; les autres erreurs (serveur) remontent.
        """
        try:
            with dataset.file.open("rt") as handle:
                report = quality.compute_quality_report(
                    parse(handle, dataset.input_format)
                )
            dataset.total_reads = report.pop("total_reads", 0)
            QualityReport.objects.update_or_create(
                dataset=dataset, defaults=report
            )
            dataset.status = Dataset.Status.DONE
        except ValueError:
            # Fichier invalide / format incorrect : erreur côté utilisateur.
            dataset.status = Dataset.Status.ERROR
        except Exception:
            dataset.status = Dataset.Status.ERROR
            raise
        finally:
            dataset.save()
```

par :

```python
    def _ingest(self, dataset):
        """Calcule le rapport qualité et le nombre de reads après upload.

        Un fichier mal formé (ValueError) marque le dataset en ERROR sans
        faire échouer l'upload ; les autres erreurs (serveur) remontent.
        Le message d'erreur est conservé pour affichage côté frontend.
        """
        try:
            with dataset.file.open("rt") as handle:
                report = quality.compute_quality_report(
                    parse(handle, dataset.input_format)
                )
            dataset.total_reads = report.pop("total_reads", 0)
            QualityReport.objects.update_or_create(
                dataset=dataset, defaults=report
            )
            dataset.status = Dataset.Status.DONE
            dataset.error_message = ""
        except ValueError as exc:
            # Fichier invalide / format incorrect : erreur côté utilisateur.
            dataset.status = Dataset.Status.ERROR
            dataset.error_message = str(exc)
        except Exception:
            dataset.status = Dataset.Status.ERROR
            dataset.error_message = "Erreur interne lors du traitement du fichier."
            raise
        finally:
            dataset.save()
```

- [ ] **Step 6: Exposer le champ dans les serializers**

Dans `backend/back/serializers.py`, remplacer `DatasetSerializer` (lignes
22-35) :

```python
class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "original_filename",
            "file",
            "input_format",
            "total_reads",
            "status",
            "created_at",
        ]
        read_only_fields = ["original_filename", "total_reads", "status", "created_at"]
```

par :

```python
class DatasetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dataset
        fields = [
            "id",
            "name",
            "original_filename",
            "file",
            "input_format",
            "total_reads",
            "status",
            "error_message",
            "created_at",
        ]
        read_only_fields = [
            "original_filename", "total_reads", "status", "error_message", "created_at",
        ]
```

Et remplacer `DatasetUploadSerializer` (lignes 38-43) :

```python
class DatasetUploadSerializer(serializers.ModelSerializer):
    """Upload d'un fichier FASTQ/FASTA."""

    class Meta:
        model = Dataset
        fields = ["id", "name", "file", "input_format"]
```

par :

```python
class DatasetUploadSerializer(serializers.ModelSerializer):
    """Upload d'un fichier FASTQ/FASTA."""

    class Meta:
        model = Dataset
        fields = ["id", "name", "file", "input_format", "status", "error_message"]
        read_only_fields = ["status", "error_message"]
```

- [ ] **Step 7: Lancer tous les tests, vérifier qu'ils passent**

Run: `cd backend && ./venv/bin/python manage.py test back -v 1`

Expected: `OK` — 58 tests (56 de Task 1 + 2 nouveaux), aucune régression.

- [ ] **Step 8: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add backend/back/models.py backend/back/views.py backend/back/serializers.py backend/back/tests.py backend/back/migrations/
git commit -m "feat(lot1): exposer le message d'erreur d'ingestion FASTQ via l'API"
```

---

### Task 3: Rendre l'action de conversion FASTQ→FASTA robuste aux fichiers invalides

**Files:**
- Modify: `backend/back/views.py:104-140` (action `convert`)
- Test: `backend/back/tests.py` (nouvelle classe `ConvertApiTests`)

**Interfaces:**
- Consumes: `fasta_converter.convert_fastq_to_fasta()` (inchangé, lève déjà
  `ValueError` via `parse_fastq` de Task 1).
- Produces: `POST /api/datasets/{id}/convert/` renvoie désormais `400` avec
  `{"detail": "..."}` au lieu d'un 500 non géré, quand le fichier contient un
  read invalide.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `backend/back/tests.py`, ajouter cette classe après `DatasetIngestApiTests` :

```python
class ConvertApiTests(TestCase):
    """Vérifie que la conversion FASTQ->FASTA échoue proprement (400) sur un
    fichier invalide, au lieu de planter en 500."""

    def setUp(self):
        self.client = APIClient()

    def test_convert_invalid_file_returns_400(self):
        # Dataset créé directement (sans passer par l'upload/_ingest) pour
        # simuler un fichier devenu invalide sur disque.
        dataset = Dataset.objects.create(
            name="bad",
            original_filename="bad.fastq",
            file=SimpleUploadedFile("bad.fastq", b"@r1\nATGX\n+\nIIII\n"),
            input_format=Dataset.Format.FASTQ,
        )
        response = self.client.post(
            f"/api/datasets/{dataset.id}/convert/",
            {"min_mean_quality": 0},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("X", response.data["detail"])
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd backend && ./venv/bin/python manage.py test back.tests.ConvertApiTests -v 2`

Expected: échec — la requête lève une `ValueError` non interceptée, Django
renvoie une erreur 500 (ou une exception non gérée dans le test runner), pas
un `400`.

- [ ] **Step 3: Intercepter l'erreur dans l'action `convert`**

Dans `backend/back/views.py`, remplacer ce bloc (action `convert`, vers la
ligne 119) :

```python
        out_buffer = io.StringIO()
        with dataset.file.open("rt") as handle:
            kept, discarded = fasta_converter.convert_fastq_to_fasta(
                handle, out_buffer, min_mean_quality, min_length
            )
```

par :

```python
        out_buffer = io.StringIO()
        try:
            with dataset.file.open("rt") as handle:
                kept, discarded = fasta_converter.convert_fastq_to_fasta(
                    handle, out_buffer, min_mean_quality, min_length
                )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
```

- [ ] **Step 4: Lancer tous les tests, vérifier qu'ils passent**

Run: `cd backend && ./venv/bin/python manage.py test back -v 1`

Expected: `OK` — 59 tests, aucune régression.

- [ ] **Step 5: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add backend/back/views.py backend/back/tests.py
git commit -m "fix(lot1): renvoyer 400 (au lieu de 500) si le FASTQ est invalide lors de la conversion"
```

---

### Task 4: Composant `ErrorDialog` et utilitaire d'extraction de message

**Files:**
- Create: `frontend/src/components/ErrorDialog.jsx`
- Modify: `frontend/src/api/api.js`

**Interfaces:**
- Produces: `export default function ErrorDialog({ open, onClose, title, message })`
  (composant React, props : `open: boolean`, `onClose: () => void`,
  `title?: string` défaut `"Erreur d'import"`, `message: string | null`).
- Produces: `export function extractErrorMessage(err, fallback): string` dans
  `frontend/src/api/api.js`. Utilisée par Task 5 et Task 6.

- [ ] **Step 1: Créer le composant `ErrorDialog`**

Créer `frontend/src/components/ErrorDialog.jsx` :

```jsx
import {
  Dialog, DialogTitle, DialogContent, DialogContentText, DialogActions, Button,
} from '@mui/material'

export default function ErrorDialog({ open, onClose, title = "Erreur d'import", message }) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ whiteSpace: 'pre-wrap' }}>{message}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} autoFocus>Fermer</Button>
      </DialogActions>
    </Dialog>
  )
}
```

- [ ] **Step 2: Ajouter `extractErrorMessage` dans `api.js`**

Dans `frontend/src/api/api.js`, ajouter après la création de l'instance axios
(après la ligne `});` qui suit `axios.create`) :

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

- [ ] **Step 3: Vérifier que le build frontend passe**

Run: `cd frontend && npm run build`

Expected: build réussit (exit code 0), aucune erreur de syntaxe/import sur
les deux nouveaux fichiers (le composant n'est encore importé nulle part,
donc aucun changement visuel à ce stade).

- [ ] **Step 4: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add frontend/src/components/ErrorDialog.jsx frontend/src/api/api.js
git commit -m "feat(lot1): composant ErrorDialog + extraction de message d'erreur API"
```

---

### Task 5: Brancher la dialog d'erreur sur la page d'import

**Files:**
- Modify: `frontend/src/pages/UploadPage.jsx`

**Interfaces:**
- Consumes: `ErrorDialog` et `extractErrorMessage` de Task 4 ; réponse
  `POST /api/datasets/` contenant `status`/`error_message` de Task 2.

- [ ] **Step 1: Remplacer le contenu de `UploadPage.jsx`**

Remplacer le fichier `frontend/src/pages/UploadPage.jsx` en entier par :

```jsx
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Paper, Typography, TextField, MenuItem, Button, Box, Stack, Alert,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { uploadDataset, extractErrorMessage } from '../api/api'
import ErrorDialog from '../components/ErrorDialog'

export default function UploadPage() {
  const [name, setName] = useState('')
  const [format, setFormat] = useState('FASTQ')
  const [file, setFile] = useState(null)
  const [error, setError] = useState(null)
  const [errorDialog, setErrorDialog] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    setErrorDialog(null)
    if (!file) { setError('Sélectionnez un fichier.'); return }
    const formData = new FormData()
    formData.append('name', name)
    formData.append('input_format', format)
    formData.append('file', file)
    setSubmitting(true)
    try {
      const res = await uploadDataset(formData)
      if (res.data.status === 'ERROR') {
        setErrorDialog(res.data.error_message || "Échec de l'import : fichier invalide.")
      } else {
        navigate(`/datasets/${res.data.id}`)
      }
    } catch (err) {
      setErrorDialog(extractErrorMessage(err, "Échec de l'import."))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Box maxWidth={560} mx="auto">
      <Typography variant="h4" gutterBottom>Importer un fichier de séquençage</Typography>
      <Paper sx={{ p: 3 }}>
        <form onSubmit={handleSubmit}>
          <Stack spacing={2}>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField label="Nom du dataset" value={name} required
              onChange={(e) => setName(e.target.value)} fullWidth />
            <TextField select label="Format" value={format}
              onChange={(e) => setFormat(e.target.value)} fullWidth>
              <MenuItem value="FASTQ">FASTQ (avec scores qualité)</MenuItem>
              <MenuItem value="FASTA">FASTA</MenuItem>
            </TextField>
            <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
              {file ? file.name : 'Choisir un fichier'}
              <input type="file" hidden accept=".fastq,.fq,.fasta,.fa,.txt"
                onChange={(e) => setFile(e.target.files[0])} />
            </Button>
            <Button type="submit" variant="contained" disabled={submitting}>
              {submitting ? 'Import en cours…' : 'Importer et analyser'}
            </Button>
          </Stack>
        </form>
      </Paper>
      <ErrorDialog
        open={!!errorDialog}
        onClose={() => setErrorDialog(null)}
        title="Erreur d'import"
        message={errorDialog}
      />
    </Box>
  )
}
```

- [ ] **Step 2: Vérifier que le build frontend passe**

Run: `cd frontend && npm run build`

Expected: build réussit (exit code 0).

- [ ] **Step 3: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add frontend/src/pages/UploadPage.jsx
git commit -m "feat(lot1): afficher une dialog d'erreur sur la page d'import FASTQ"
```

---

### Task 6: Brancher la dialog d'erreur sur la conversion FASTQ→FASTA

**Files:**
- Modify: `frontend/src/pages/DatasetDetailPage.jsx`

**Interfaces:**
- Consumes: `ErrorDialog` et `extractErrorMessage` de Task 4 ; réponse
  `400 {"detail": "..."}` de Task 3 sur `convertToFasta()` ; champ
  `dataset.error_message` de Task 2.

- [ ] **Step 1: Mettre à jour les imports et l'état**

Dans `frontend/src/pages/DatasetDetailPage.jsx`, remplacer :

```jsx
import { getDataset, getQualityReport, convertToFasta } from '../api/api'
import QualityChart from '../components/QualityChart'
```

par :

```jsx
import { getDataset, getQualityReport, convertToFasta, extractErrorMessage } from '../api/api'
import QualityChart from '../components/QualityChart'
import ErrorDialog from '../components/ErrorDialog'
```

Puis remplacer :

```jsx
  const [conversion, setConversion] = useState(null)
  const [converting, setConverting] = useState(false)
```

par :

```jsx
  const [conversion, setConversion] = useState(null)
  const [converting, setConverting] = useState(false)
  const [convertErrorDialog, setConvertErrorDialog] = useState(null)
```

- [ ] **Step 2: Mettre à jour `handleConvert`**

Remplacer :

```jsx
  const handleConvert = async () => {
    setConverting(true); setError(null); setConversion(null)
    try {
      const params = { min_mean_quality: Number(minQuality) }
      if (minLength !== '') params.min_length = Number(minLength)
      const res = await convertToFasta(id, params)
      setConversion(res.data)
    } catch (err) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : 'Échec de la conversion.')
    } finally {
      setConverting(false)
    }
  }
```

par :

```jsx
  const handleConvert = async () => {
    setConverting(true); setConvertErrorDialog(null); setConversion(null)
    try {
      const params = { min_mean_quality: Number(minQuality) }
      if (minLength !== '') params.min_length = Number(minLength)
      const res = await convertToFasta(id, params)
      setConversion(res.data)
    } catch (err) {
      setConvertErrorDialog(extractErrorMessage(err, 'Échec de la conversion.'))
    } finally {
      setConverting(false)
    }
  }
```

- [ ] **Step 3: Afficher le message d'erreur d'un dataset déjà en ERROR + la dialog**

Remplacer :

```jsx
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {/* --- Rapport qualité (Q1) --- */}
```

par :

```jsx
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {dataset.status === 'ERROR' && dataset.error_message && (
        <Alert severity="error" sx={{ mb: 2 }}>{dataset.error_message}</Alert>
      )}

      {/* --- Rapport qualité (Q1) --- */}
```

Puis, juste avant la fermeture finale du composant, remplacer :

```jsx
        </Paper>
      )}
    </Box>
  )
}
```

par :

```jsx
        </Paper>
      )}

      <ErrorDialog
        open={!!convertErrorDialog}
        onClose={() => setConvertErrorDialog(null)}
        title="Erreur de conversion"
        message={convertErrorDialog}
      />
    </Box>
  )
}
```

- [ ] **Step 4: Vérifier que le build frontend passe**

Run: `cd frontend && npm run build`

Expected: build réussit (exit code 0).

- [ ] **Step 5: Commit**

```bash
cd /home/misashelby/Documents/PPC/ASG-2026
git add frontend/src/pages/DatasetDetailPage.jsx
git commit -m "feat(lot1): afficher une dialog d'erreur sur l'action de conversion FASTQ->FASTA"
```

---

### Task 7: Vérification complète (suite de tests + navigateur)

**Files:** aucun fichier modifié — vérification uniquement.

- [ ] **Step 1: Suite de tests backend complète**

Run: `cd backend && ./venv/bin/python manage.py test back -v 1`

Expected: `OK` — 59 tests, 0 échec.

- [ ] **Step 2: Build frontend complet**

Run: `cd frontend && npm run build`

Expected: exit code 0.

- [ ] **Step 3: Préparer un fichier FASTQ invalide pour le test manuel**

Run:
```bash
printf '@read_invalide\nATGXCGTA\n+\nIIIIIIII\n' > /tmp/invalide.fastq
```

- [ ] **Step 4: Démarrer les serveurs de dev**

Run (deux processus, ou `npm run dev` depuis `frontend/` qui lance les deux) :
```bash
cd backend && ./venv/bin/python manage.py runserver 8000
```
```bash
cd frontend && npm run dev:react
```

- [ ] **Step 5: Vérification manuelle dans le navigateur — import invalide**

Ouvrir la page d'import (`/upload`), donner un nom, sélectionner
`/tmp/invalide.fastq` en format FASTQ, cliquer "Importer et analyser".

Expected : une dialog s'ouvre avec un message mentionnant le read invalide et
le caractère `X` rejeté (ex: "Read invalide '@read_invalide' : caractère(s)
non autorisé(s) dans la séquence : X (bases acceptées : A, C, G, T, N)").
**La page reste sur `/upload`** (pas de navigation vers une page détail).

- [ ] **Step 6: Vérification manuelle dans le navigateur — import valide**

Importer un fichier FASTQ valide (ex. un des fichiers déjà présents dans
`backend/media/uploads/`, ou un petit fichier `@r1\nATGC\n+\nIIII\n`).

Expected : pas de dialog, navigation automatique vers `/datasets/{id}`, statut
affiché `DONE`.

- [ ] **Step 7: Note sur la couverture de la conversion invalide**

Le chemin "conversion FASTQ→FASTA sur fichier invalide" (Task 3) ne peut pas
être déclenché depuis l'UI dans des conditions normales : un dataset dont le
fichier contient un read invalide est désormais bloqué dès l'upload (statut
`ERROR`), donc on n'atteint jamais un dataset `DONE` avec un fichier invalide
sur lequel cliquer "Convertir". Ce chemin reste couvert par le test API
automatisé de Task 3 (`ConvertApiTests`) — c'est un filet de sécurité pour un
fichier corrompu après coup sur le disque, pas un flux utilisateur normal.
Aucune action manuelle supplémentaire n'est nécessaire ici.

- [ ] **Step 8: Arrêter les serveurs de dev**

Interrompre les deux process (Ctrl+C) lancés au Step 4.
