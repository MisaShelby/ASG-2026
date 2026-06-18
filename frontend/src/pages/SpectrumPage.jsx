import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  Box, Typography, Paper, CircularProgress, Alert, TextField, Stack,
} from '@mui/material'
import { getKmerAnalysis, getKmerSpectrum } from '../api/api'
import KmerHistogram from '../components/KmerHistogram'

export default function SpectrumPage() {
  const { id } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [spectrum, setSpectrum] = useState([])
  const [maxMult, setMaxMult] = useState(50)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([getKmerAnalysis(id), getKmerSpectrum(id)])
      .then(([a, s]) => { setAnalysis(a.data); setSpectrum(s.data) })
      .catch(() => setError('Analyse introuvable.'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>
  if (error) return <Alert severity="error">{error}</Alert>

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Histogramme de fréquence des k-mers
      </Typography>
      {analysis && (
        <Typography variant="body2" color="text.secondary" mb={2}>
          k = {analysis.k} · {analysis.distinct_kmers} k-mers distincts · {analysis.total_kmers} k-mers au total
        </Typography>
      )}

      <Stack direction="row" spacing={2} mb={2} alignItems="center">
        <TextField type="number" label="Multiplicité max affichée" value={maxMult}
          onChange={(e) => setMaxMult(Number(e.target.value) || 1)}
          inputProps={{ min: 1 }} size="small" />
      </Stack>

      {spectrum.length === 0 ? (
        <Alert severity="info">Aucune donnée de spectre.</Alert>
      ) : (
        <Paper sx={{ p: 2 }}>
          <KmerHistogram spectrum={spectrum} maxMultiplicity={maxMult} />
        </Paper>
      )}
    </Box>
  )
}
