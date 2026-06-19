import { Button, Typography } from '@mui/material'
import DownloadIcon from '@mui/icons-material/Download'

export default function ContigViewer({ contigs, downloadUrl }) {
  if (!contigs?.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        Aucun contig produit.
      </Typography>
    )
  }
  return (
    <div className="space-y-4">
      {downloadUrl && (
        <Button variant="outlined" startIcon={<DownloadIcon />}
          href={downloadUrl} component="a">
          Télécharger les contigs (FASTA)
        </Button>
      )}
      {contigs.map((c) => (
        <div key={c.index} className="rounded border border-slate-200 bg-white p-3">
          <div className="mb-1 flex justify-between text-sm text-slate-600">
            <span>Contig #{c.index} — {c.length} nt</span>
            {c.identity_to_reference != null && (
              <span>
                identité&nbsp;: {(c.identity_to_reference * 100).toFixed(2)}&nbsp;%
              </span>
            )}
          </div>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs">
            {c.sequence}
          </pre>
        </div>
      ))}
    </div>
  )
}
