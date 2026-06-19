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
