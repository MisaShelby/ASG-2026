import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Box, Typography, CircularProgress, Alert } from '@mui/material'
import AlignmentViewer from '../components/AlignmentViewer'
import { getAlignment } from '../api/api'

export default function AlignmentDetailPage() {
  const { id } = useParams()
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getAlignment(id)
      .then((res) => setResult(res.data))
      .catch(() => setError('Alignement introuvable.'))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return <Box textAlign="center" mt={4}><CircularProgress /></Box>
  if (!result) return <Alert severity="error">{error}</Alert>

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Alignement #{id}</Typography>
      <AlignmentViewer result={result} />
    </Box>
  )
}
