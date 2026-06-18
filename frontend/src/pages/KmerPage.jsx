import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Box, Typography, Paper, TextField, MenuItem, Button, Stack, Alert,
  Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material'
import BarChartIcon from '@mui/icons-material/BarChart'
import { runKmerAnalysis, getTopKmers } from '../api/api'

// Carte de statistique en Tailwind (affichage)
function StatCard({ label, value }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-xl font-semibold text-slate-800">{value}</p>
    </div>
  )
}

export default function KmerPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [k, setK] = useState(21)
  const [source, setSource] = useState('RAW')
  const [analysis, setAnalysis] = useState(null)
  const [top, setTop] = useState([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  const handleRun = async () => {
    setRunning(true); setError(null)
    try {
      const res = await runKmerAnalysis(id, { k: Number(k), source })
      setAnalysis(res.data)
      const topRes = await getTopKmers(res.data.id)
      setTop(topRes.data.slice(0, 20))
    } catch (err) {
      setError(err?.response?.data ? JSON.stringify(err.response.data) : "Échec de l'analyse.")
    } finally {
      setRunning(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Analyse k-mers</Typography>
      <Paper sx={{ p: 3, mb: 3 }}>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Choisissez la taille <strong>k</strong> du k-mer (paramétrable par vous).
        </Typography>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          <TextField type="number" label="Taille k" value={k}
            onChange={(e) => setK(e.target.value)} inputProps={{ min: 1, max: 64 }} />
          <TextField select label="Source" value={source}
            onChange={(e) => setSource(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="RAW">Reads bruts</MenuItem>
            <MenuItem value="FILTERED">Reads filtrés</MenuItem>
          </TextField>
          <Button variant="contained" onClick={handleRun} disabled={running}>
            {running ? 'Découpage…' : 'Lancer le découpage'}
          </Button>
        </Stack>
      </Paper>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {analysis && (
        <>
          <div className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label="k" value={analysis.k} />
            <StatCard label="k-mers totaux" value={analysis.total_kmers} />
            <StatCard label="k-mers distincts" value={analysis.distinct_kmers} />
          </div>

          <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
            <Typography variant="h6">Top k-mers</Typography>
            <Button variant="contained" startIcon={<BarChartIcon />}
              onClick={() => navigate(`/kmer-analyses/${analysis.id}/spectrum`)}>
              Voir l'histogramme
            </Button>
          </Box>
          <Paper>
            <Table size="small">
              <TableHead>
                <TableRow><TableCell>k-mer</TableCell><TableCell align="right">Occurrences</TableCell></TableRow>
              </TableHead>
              <TableBody>
                {top.map((row) => (
                  <TableRow key={row.sequence}>
                    <TableCell sx={{ fontFamily: 'monospace' }}>{row.sequence}</TableCell>
                    <TableCell align="right">{row.count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </>
      )}
    </Box>
  )
}
