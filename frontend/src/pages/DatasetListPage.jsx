import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Paper, Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Typography, Chip, Button, Box, CircularProgress, Alert,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { listDatasets } from '../api/api'

const STATUS_COLOR = {
  UPLOADED: 'default', PROCESSING: 'warning', DONE: 'success', ERROR: 'error',
}

export default function DatasetListPage() {
  const [datasets, setDatasets] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const navigate = useNavigate()

  useEffect(() => {
    listDatasets()
      .then((res) => setDatasets(res.data))
      .catch(() => setError("Impossible de charger les datasets."))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">Jeux de séquençage</Typography>
        <Button variant="contained" startIcon={<UploadFileIcon />}
          onClick={() => navigate('/upload')}>
          Importer un FASTQ / FASTA
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {datasets.length === 0 ? (
        <Alert severity="info">Aucun dataset. Commencez par en importer un.</Alert>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Nom</TableCell>
                <TableCell>Format</TableCell>
                <TableCell align="right">Reads</TableCell>
                <TableCell>Statut</TableCell>
                <TableCell>Importé le</TableCell>
                <TableCell align="right">Action</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {datasets.map((d) => (
                <TableRow key={d.id} hover>
                  <TableCell>{d.name}</TableCell>
                  <TableCell>{d.input_format}</TableCell>
                  <TableCell align="right">{d.total_reads ?? '—'}</TableCell>
                  <TableCell>
                    <Chip size="small" label={d.status} color={STATUS_COLOR[d.status]} />
                  </TableCell>
                  <TableCell>{new Date(d.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => navigate(`/datasets/${d.id}`)}>
                      Ouvrir
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
