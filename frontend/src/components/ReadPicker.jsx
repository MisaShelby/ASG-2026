import { useEffect, useState } from 'react'
import {
  ToggleButtonGroup, ToggleButton, TextField, MenuItem, Button,
  Typography, Alert, CircularProgress,
} from '@mui/material'
import UploadFileIcon from '@mui/icons-material/UploadFile'
import { listDatasets, listDatasetReads } from '../api/api'

const MAX_LENGTH = 5000

// Sélecteur de read réutilisable : depuis un dataset (Lot 1) ou saisie manuelle.
// `onChange` reçoit directement le payload à envoyer à l'API
// ({ dataset, index } ou { sequence }), ou null si rien n'est sélectionné.
export default function ReadPicker({ label, onChange }) {
  const [mode, setMode] = useState('dataset')
  const [datasets, setDatasets] = useState([])
  const [datasetId, setDatasetId] = useState('')
  const [reads, setReads] = useState([])
  const [readIndex, setReadIndex] = useState('')
  const [manualSequence, setManualSequence] = useState('')
  const [loadingReads, setLoadingReads] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    listDatasets().then((res) => setDatasets(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    if (datasetId === '') return
    let active = true
    listDatasetReads(datasetId, { limit: 200, offset: 0 })
      .then((res) => { if (active) setReads(res.data) })
      .catch(() => { if (active) setError('Impossible de charger les reads de ce dataset.') })
      .finally(() => { if (active) setLoadingReads(false) })
    return () => { active = false }
  }, [datasetId])

  useEffect(() => {
    if (mode === 'dataset') {
      if (datasetId !== '' && readIndex !== '') {
        onChange({ dataset: Number(datasetId), index: Number(readIndex) })
      } else {
        onChange(null)
      }
    } else {
      const cleaned = manualSequence.replace(/\s+/g, '').toUpperCase()
      onChange(cleaned ? { sequence: cleaned } : null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, datasetId, readIndex, manualSequence])

  const handleSelectRead = (index) => {
    setReadIndex(index)
    setError(null)
  }

  const selectedPreview = reads.find((r) => r.index === readIndex)?.preview ?? ''

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result)
      const lines = text.split('\n').filter((l) => !l.startsWith('>'))
      setManualSequence(lines.join('').trim())
    }
    reader.readAsText(file)
  }

  const manualLength = manualSequence.replace(/\s+/g, '').length

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <Typography variant="subtitle1" fontWeight={600} mb={1}>{label}</Typography>

      <ToggleButtonGroup size="small" exclusive value={mode}
        onChange={(_, v) => { if (v) { setMode(v); setError(null) } }} sx={{ mb: 2 }}>
        <ToggleButton value="dataset">Depuis un dataset</ToggleButton>
        <ToggleButton value="manual">Saisie manuelle</ToggleButton>
      </ToggleButtonGroup>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {mode === 'dataset' ? (
        <div className="flex flex-col gap-3">
          <TextField select size="small" label="Dataset" value={datasetId}
            onChange={(e) => {
              setDatasetId(e.target.value)
              setReadIndex('')
              setLoadingReads(true)
            }}>
            {datasets.map((d) => (
              <MenuItem key={d.id} value={d.id}>
                {d.name} ({d.total_reads ?? '—'} reads)
              </MenuItem>
            ))}
          </TextField>

          {loadingReads && <CircularProgress size={20} />}

          {!loadingReads && datasetId !== '' && (
            <TextField select size="small" label="Read (index)" value={readIndex}
              onChange={(e) => handleSelectRead(e.target.value)}>
              {reads.map((r) => (
                <MenuItem key={r.index} value={r.index}>
                  #{r.index} — {r.identifier} ({r.length} nt) — {r.preview}…
                </MenuItem>
              ))}
            </TextField>
          )}

          {selectedPreview && (
            <p className="break-all font-mono text-xs text-slate-500">
              {selectedPreview}…
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <TextField multiline minRows={4} placeholder="Collez une séquence (ACGT...)"
            value={manualSequence} onChange={(e) => setManualSequence(e.target.value)} />
          <Button size="small" variant="outlined" component="label" startIcon={<UploadFileIcon />}>
            Importer un fichier
            <input type="file" hidden accept=".fasta,.fa,.txt" onChange={handleFileUpload} />
          </Button>
          <p className={`text-xs ${manualLength > MAX_LENGTH ? 'text-red-600' : 'text-slate-500'}`}>
            {manualLength} / {MAX_LENGTH} nt
          </p>
        </div>
      )}
    </div>
  )
}
