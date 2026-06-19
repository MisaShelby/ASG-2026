import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography, Box, CircularProgress, Alert, Chip, Button,
} from '@mui/material'
import { listAlignments } from '../api/api'

export default function AlignmentHistoryPage() {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    listAlignments()
      .then((res) => setRuns(res.data))
      .catch(() => setError("Impossible de charger l'historique."))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Historique des alignements</Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {runs.length === 0 ? (
        <Alert severity="info">Aucun alignement calculé pour l'instant.</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Read A</TableCell>
                <TableCell>Read B</TableCell>
                <TableCell align="right">Score</TableCell>
                <TableCell>Calculé le</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {runs.map((r) => (
                <TableRow key={r.id} hover>
                  <TableCell>{r.read_a_label}</TableCell>
                  <TableCell>{r.read_b_label}</TableCell>
                  <TableCell align="right">
                    <Chip size="small" label={r.score} color={r.score > 0 ? 'success' : 'default'} />
                  </TableCell>
                  <TableCell>{new Date(r.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => navigate(`/alignments/${r.id}`)}>Voir</Button>
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
