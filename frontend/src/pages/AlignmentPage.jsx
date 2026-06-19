import { useState } from 'react'
import { Box, Typography, Button, Alert } from '@mui/material'
import CompareArrowsIcon from '@mui/icons-material/CompareArrows'
import ReadPicker from '../components/ReadPicker'
import AlignmentViewer from '../components/AlignmentViewer'
import { createAlignment } from '../api/api'

export default function AlignmentPage() {
  const [readA, setReadA] = useState(null)
  const [readB, setReadB] = useState(null)
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  const canRun = Boolean(readA && readB)

  const handleRun = async () => {
    setRunning(true); setError(null); setResult(null)
    try {
      const res = await createAlignment({ read_a: readA, read_b: readB })
      setResult(res.data)
    } catch (err) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : "Échec de l'alignement.")
    } finally {
      setRunning(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Alignement de chevauchement</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Choisissez ou saisissez deux reads. L'algorithme cherche le meilleur chevauchement
        contigu (suffixe/préfixe) entre les deux, avec un score pondéré
        (match&nbsp;=&nbsp;+1, mismatch&nbsp;=&nbsp;−1, gap&nbsp;=&nbsp;−2).
      </Typography>

      <div className="mb-6 grid grid-cols-1 gap-6 md:grid-cols-2">
        <ReadPicker label="Read A" onChange={setReadA} />
        <ReadPicker label="Read B" onChange={setReadB} />
      </div>

      <Button variant="contained" startIcon={<CompareArrowsIcon />}
        disabled={!canRun || running} onClick={handleRun} sx={{ mb: 3 }}>
        {running ? 'Alignement…' : 'Aligner'}
      </Button>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {result && <AlignmentViewer result={result} />}
    </Box>
  )
}
