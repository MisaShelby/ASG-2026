import { useEffect, useState } from 'react'
import {
  Box,
  Typography,
  Button,
  Alert,
  TextField,
  MenuItem,
} from '@mui/material'
import HubIcon from '@mui/icons-material/Hub'
import { Link as RouterLink } from 'react-router-dom'
import { listDatasets, createAssembly, assemblyContigsUrl } from '../api/api'
import ContigViewer from '../components/ContigViewer'

function Stat({ label, value }) {
  return (
    <div className="rounded border border-slate-200 bg-white p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  )
}

export default function AssemblyPage() {
  const [datasets, setDatasets] = useState([])
  const [form, setForm] = useState({
    dataset: '',
    source: 'RAW',
    k: 21,
    solidity_threshold: 2,
    bloom_bits: '',
    num_hashes: '',
    reference_sequence: '',
  })
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    listDatasets()
      .then((res) => setDatasets(res.data))
      .catch(() => setDatasets([]))
  }, [])

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const handleRun = async () => {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const payload = {
        dataset: form.dataset,
        source: form.source,
        k: Number(form.k),
        solidity_threshold: Number(form.solidity_threshold),
        reference_sequence: form.reference_sequence,
      }
      if (form.bloom_bits) payload.bloom_bits = Number(form.bloom_bits)
      if (form.num_hashes) payload.num_hashes = Number(form.num_hashes)
      const res = await createAssembly(payload)
      setResult(res.data)
    } catch (err) {
      setError(
        err?.response?.data
          ? JSON.stringify(err.response.data)
          : "Échec de l'assemblage."
      )
    } finally {
      setRunning(false)
    }
  }

  return (
    <Box>
      <Typography variant="h4" gutterBottom>Assemblage de novo</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Reconstruction de contigs via un graphe de de Bruijn implicite&nbsp;: la
        connectivité des k-mers est testée à la volée par un filtre de Bloom (jamais
        construit en mémoire). Fournissez une séquence de référence pour mesurer
        l'identité du meilleur contig.
      </Typography>

      <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
        <TextField select label="Dataset" value={form.dataset} onChange={set('dataset')}>
          {datasets.map((d) => (
            <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>
          ))}
        </TextField>
        <TextField select label="Source" value={form.source} onChange={set('source')}>
          <MenuItem value="RAW">Reads bruts</MenuItem>
          <MenuItem value="FILTERED">Reads filtrés</MenuItem>
        </TextField>
        <TextField label="k (taille des k-mers)" type="number" value={form.k}
          onChange={set('k')} />
        <TextField label="Seuil de solidité" type="number"
          value={form.solidity_threshold} onChange={set('solidity_threshold')} />
        <TextField label="Bloom : m bits (auto si vide)" type="number"
          value={form.bloom_bits} onChange={set('bloom_bits')} />
        <TextField label="Nb de hachages (auto si vide)" type="number"
          value={form.num_hashes} onChange={set('num_hashes')} />
      </div>

      <TextField label="Séquence de référence (optionnelle)" multiline minRows={2}
        fullWidth value={form.reference_sequence} onChange={set('reference_sequence')}
        sx={{ mb: 3 }} />

      <Button variant="contained" startIcon={<HubIcon />}
        disabled={!form.dataset || running} onClick={handleRun} sx={{ mb: 3 }}>
        {running ? 'Assemblage…' : 'Assembler'}
      </Button>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {result && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Contigs" value={result.num_contigs} />
            <Stat label="Plus long contig" value={`${result.max_contig_length} nt`} />
            <Stat label="K-mers solides" value={result.solid_kmers} />
            <Stat label="Taux FP (théorique)"
              value={`${(result.bloom_fp_rate * 100).toFixed(3)} %`} />
            <Stat label="Mémoire Bloom" value={`${result.bloom_bytes} o`} />
            <Stat label="Mémoire dict (est.)"
              value={`${result.dict_bytes_estimate} o`} />
            {result.best_identity != null && (
              <Stat label="Meilleure identité"
                value={`${(result.best_identity * 100).toFixed(2)} %`} />
            )}
          </div>

          <Button variant="text" component={RouterLink}
            to={`/assemblies/${result.id}/analysis`}>
            Voir l'analyse du filtre de Bloom →
          </Button>

          <ContigViewer contigs={result.contigs}
            downloadUrl={assemblyContigsUrl(result.id)} />
        </div>
      )}
    </Box>
  )
}
