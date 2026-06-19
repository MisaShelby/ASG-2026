import { Alert, Chip } from '@mui/material'
import EastIcon from '@mui/icons-material/East'

function symbolType(c) {
  if (c === '|') return 'match'
  if (c === '.') return 'mismatch'
  return 'gap'
}

function buildSegments(matchLine) {
  if (!matchLine) return []
  const segments = []
  let start = 0
  for (let i = 1; i <= matchLine.length; i++) {
    if (i === matchLine.length || symbolType(matchLine[i]) !== symbolType(matchLine[start])) {
      segments.push({ type: symbolType(matchLine[start]), start, end: i })
      start = i
    }
  }
  return segments
}

const SEGMENT_CLASS = {
  match: 'bg-emerald-900/40 text-emerald-300',
  mismatch: 'bg-rose-900/40 text-rose-300',
  gap: 'text-slate-500',
}

const LEGEND = [
  { type: 'match', label: 'Match', dot: 'bg-emerald-400' },
  { type: 'mismatch', label: 'Mismatch', dot: 'bg-rose-400' },
  { type: 'gap', label: 'Gap', dot: 'bg-slate-400' },
]

function AlignedLine({ sequence, segments }) {
  return (
    <div>
      {segments.map((s, i) => (
        <span key={i} className={SEGMENT_CLASS[s.type]}>{sequence.slice(s.start, s.end)}</span>
      ))}
    </div>
  )
}

function ReadBadge({ label, start, end }) {
  return (
    <div className="flex flex-col gap-0.5 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <span className="truncate text-xs font-medium uppercase tracking-wide text-slate-400">{label}</span>
      <span className="font-mono text-sm text-slate-700">positions {start}–{end}</span>
    </div>
  )
}

export default function AlignmentViewer({ result }) {
  if (!result || !result.score || result.score <= 0) {
    return <Alert severity="info">Aucun chevauchement significatif détecté entre ces deux reads.</Alert>
  }

  const {
    aligned_a, match_line, aligned_b, score,
    read_a_label, read_b_label,
    read_a_start, read_a_end, read_b_start, read_b_end,
  } = result
  const segments = buildSegments(match_line)
  const matches = [...match_line].filter((c) => c === '|').length
  const identity = match_line.length ? Math.round((matches / match_line.length) * 100) : 0

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Chip color="success" label={`Score ${score}`} sx={{ fontWeight: 600 }} />
          {/* <Chip variant="outlined" label={`${identity}% identité sur ${match_line.length} nt`} /> */}
        </div>
        <div className="flex flex-wrap gap-3 text-xs text-slate-500">
          {LEGEND.map((l) => (
            <span key={l.type} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${l.dot}`} />{l.label}
            </span>
          ))}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <ReadBadge label={read_a_label} start={read_a_start} end={read_a_end} />
        <EastIcon className="shrink-0 text-slate-400" fontSize="small" />
        <ReadBadge label={read_b_label} start={read_b_start} end={read_b_end} />
      </div>

      <div className="overflow-x-auto whitespace-pre rounded-lg bg-slate-900 p-4 font-mono text-sm leading-6 text-slate-100 shadow-inner">
        <AlignedLine sequence={aligned_a} segments={segments} />
        <div className="text-slate-500">{match_line}</div>
        <AlignedLine sequence={aligned_b} segments={segments} />
      </div>
    </div>
  )
}
