import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Paper, TextField, Button,
  Stack, Alert, CircularProgress, Divider, Chip, Link,
} from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'
import ScatterPlotIcon from '@mui/icons-material/ScatterPlot'
import { getDataset, getQualityReport, convertToFasta, extractErrorMessage } from '../api/api'
import QualityChart from '../components/QualityChart'
import ErrorDialog from '../components/ErrorDialog'

// Carte de statistique en Tailwind (affichage)
function StatCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-800">{value}</p>
    </div>
  )
}

export default function DatasetDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [dataset, setDataset] = useState(null)
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Filtres de conversion définis par l'utilisateur
  const [minQuality, setMinQuality] = useState(30)
  const [minLength, setMinLength] = useState('')
  const [conversion, setConversion] = useState(null)
  const [converting, setConverting] = useState(false)
  const [convertErrorDialog, setConvertErrorDialog] = useState(null)

  useEffect(() => {
    Promise.all([getDataset(id), getQualityReport(id).catch(() => null)])
      .then(([ds, qr]) => { setDataset(ds.data); setReport(qr?.data ?? null) })
      .catch(() => setError('Dataset introuvable.'))
      .finally(() => setLoading(false))
  }, [id])

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

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>
  if (!dataset) return <Alert severity="error">{error || 'Introuvable'}</Alert>

  const apiUrl = import.meta.env.VITE_API_URL

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="h4">{dataset.name}</Typography>
        <Button variant="contained" startIcon={<ScatterPlotIcon />}
          onClick={() => navigate(`/datasets/${id}/kmers`)}>
          Analyse k-mers
        </Button>
      </Box>
      <Stack direction="row" spacing={1} mb={3}>
        <Chip label={dataset.input_format} color="primary" />
        <Chip label={dataset.status} />
        <Chip label={`${dataset.total_reads ?? '—'} reads`} variant="outlined" />
      </Stack>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {dataset.status === 'ERROR' && dataset.error_message && (
        <Alert severity="error" sx={{ mb: 2 }}>{dataset.error_message}</Alert>
      )}

      {/* --- Rapport qualité (Q1) --- */}
      <Typography variant="h6" gutterBottom>Rapport qualité</Typography>
      {report ? (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard label="Qualité moyenne" value={report.mean_quality} />
            <StatCard label="Longueur moyenne" value={report.mean_length} />
            <StatCard label="Long. min / max" value={`${report.min_length} / ${report.max_length}`} />
            <StatCard label="% GC" value={`${report.gc_content} %`} />
          </div>
          {report.per_position_quality?.length > 0 && (
            <Paper sx={{ p: 2, mb: 4 }}>
              <QualityChart perPosition={report.per_position_quality} />
            </Paper>
          )}
        </>
      ) : (
        <Alert severity="info" sx={{ mb: 3 }}>Aucun rapport qualité disponible.</Alert>
      )}

      <Divider sx={{ my: 3 }} />

      {/* --- Conversion sélective FASTQ -> FASTA (Q1) --- */}
      <Typography variant="h6" gutterBottom>Conversion sélective → FASTA</Typography>
      {dataset.input_format !== 'FASTQ' ? (
        <Alert severity="info">La conversion sélective nécessite un fichier FASTQ.</Alert>
      ) : (
        <Paper sx={{ p: 3 }}>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Définissez les filtres. Le filtre principal est la <strong>qualité moyenne minimale</strong> ;
            la longueur minimale est optionnelle.
          </Typography>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
            <TextField type="number" label="Qualité moyenne min" value={minQuality}
              onChange={(e) => setMinQuality(e.target.value)}
              inputProps={{ min: 0, max: 60 }} />
            <TextField type="number" label="Longueur min (optionnel)" value={minLength}
              onChange={(e) => setMinLength(e.target.value)}
              inputProps={{ min: 0 }} />
            <Button variant="contained" onClick={handleConvert} disabled={converting}>
              {converting ? 'Conversion…' : 'Convertir'}
            </Button>
          </Stack>

          {conversion && (
            <Alert severity="success" sx={{ mt: 3 }}>
              {conversion.reads_kept} reads conservés, {conversion.reads_discarded} rejetés.{' '}
              <Link href={`${apiUrl}/conversions/${conversion.id}/download/`} target="_blank">
                <DownloadIcon fontSize="small" sx={{ verticalAlign: 'middle' }} /> Télécharger le FASTA
              </Link>
            </Alert>
          )}
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
