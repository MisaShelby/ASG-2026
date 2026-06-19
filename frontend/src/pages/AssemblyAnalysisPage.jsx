import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Box, Typography, CircularProgress, Alert } from '@mui/material'
import { getAssembly } from '../api/api'
import BloomAnalysisChart from '../components/BloomAnalysisChart'
import ContigViewer from '../components/ContigViewer'
import { assemblyContigsUrl } from '../api/api'

function Stat({ label, value }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  )
}

export default function AssemblyAnalysisPage() {
  const { id } = useParams()
  const [run, setRun] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    getAssembly(id)
      .then((res) => setRun(res.data))
      .catch(() => setError("Impossible de charger cet assemblage."))
  }, [id])

  if (error) return <Alert severity="error">{error}</Alert>
  if (!run) return <Box textAlign="center" mt={4}><CircularProgress /></Box>

  const ratio =
    run.dict_bytes_estimate > 0
      ? (run.bloom_bytes / run.dict_bytes_estimate).toFixed(3)
      : '—'

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Analyse du filtre de Bloom (assemblage #{run.id})
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        k&nbsp;=&nbsp;{run.k}, seuil de solidité&nbsp;=&nbsp;{run.solidity_threshold},
        m&nbsp;=&nbsp;{run.bloom_bits} bits, {run.num_hashes} fonctions de hachage.
      </Typography>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="K-mers distincts" value={run.distinct_kmers} />
        <Stat label="K-mers solides" value={run.solid_kmers} />
        <Stat label="Mémoire Bloom" value={`${run.bloom_bytes} o`} />
        <Stat label="Mémoire dict (est.)" value={`${run.dict_bytes_estimate} o`} />
        <Stat label="Ratio Bloom / dict" value={ratio} />
        <Stat label="Taux FP (théorique)"
          value={`${(run.bloom_fp_rate * 100).toFixed(3)} %`} />
        <Stat label="Contigs" value={run.num_contigs} />
        {run.best_identity != null && (
          <Stat label="Meilleure identité"
            value={`${(run.best_identity * 100).toFixed(2)} %`} />
        )}
      </div>

      <div className="mb-6">
        <BloomAnalysisChart n={run.solid_kmers} numHashes={run.num_hashes} />
      </div>

      <Alert severity="info" sx={{ mb: 4 }}>
        Un faux positif du filtre fait croire qu'un k-mer non solide est présent&nbsp;:
        la traversée peut alors suivre un chemin fantôme (sur-extension d'un contig) ou
        marquer un faux embranchement (arrêt prématuré). Augmenter m (bits) réduit le
        taux de faux positifs — voir la courbe ci-dessus. Le détail figure dans
        docs/LOT3_ANALYSE.md.
      </Alert>

      <Typography variant="h6" gutterBottom>Contigs produits</Typography>
      <ContigViewer contigs={run.contigs}
        downloadUrl={assemblyContigsUrl(run.id)} />
    </Box>
  )
}
