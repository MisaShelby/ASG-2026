import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography, Box, CircularProgress, Alert, Chip, Button,
} from '@mui/material'
import { listAssemblies } from '../api/api'

export default function AssemblyHistoryPage() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    listAssemblies()
      .then((res) => setRuns(res.data))
      .catch(() => setError("Impossible de charger l'historique."))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Historique des assemblages</Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {runs.length === 0 ? (
        <Alert severity="info">Aucun assemblage lancé pour l'instant.</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell align="right">k</TableCell>
                <TableCell align="right">Seuil</TableCell>
                <TableCell align="right">Contigs</TableCell>
                <TableCell align="right">Identité</TableCell>
                <TableCell>Lancé le</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell align="right">{r.k}</TableCell>
                  <TableCell align="right">{r.solidity_threshold}</TableCell>
                  <TableCell align="right">{r.num_contigs}</TableCell>
                  <TableCell align="right">
                    {r.best_identity != null ? (
                      <Chip size="small"
                        label={`${(r.best_identity * 100).toFixed(1)} %`}
                        color={r.best_identity >= 0.98 ? 'success' : 'default'} />
                    ) : '—'}
                  </TableCell>
                  <TableCell>{new Date(r.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
                    <Button size="small"
                      onClick={() => navigate(`/assemblies/${r.id}/analysis`)}>
                      Analyse
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  )
}
