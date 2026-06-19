import { Routes, Route, Link as RouterLink } from 'react-router-dom'
import {
  AppBar,
  Toolbar,
  Typography,
  Button,
} from '@mui/material'
import ScienceIcon from '@mui/icons-material/Science'
import DatasetListPage from './pages/DatasetListPage'
import UploadPage from './pages/UploadPage'
import DatasetDetailPage from './pages/DatasetDetailPage'
import KmerPage from './pages/KmerPage'
import SpectrumPage from './pages/SpectrumPage'
import AlignmentPage from './pages/AlignmentPage'
import AlignmentHistoryPage from './pages/AlignmentHistoryPage'
import AlignmentDetailPage from './pages/AlignmentDetailPage'
import AssemblyPage from './pages/AssemblyPage'
import AssemblyHistoryPage from './pages/AssemblyHistoryPage'
import AssemblyAnalysisPage from './pages/AssemblyAnalysisPage'

function App() {
  return (
    <div className="min-h-screen bg-slate-50">
      <AppBar position="static">
        <Toolbar>
          <ScienceIcon sx={{ mr: 1 }} />
          <Typography variant="h6" component={RouterLink} to="/"
            sx={{ flexGrow: 1, color: 'inherit', textDecoration: 'none' }}>
            ASG-2026 — Pipeline d'assemblage
          </Typography>
          <Button color="inherit" component={RouterLink} to="/">Datasets</Button>
          <Button color="inherit" component={RouterLink} to="/upload">Importer</Button>
          <Button color="inherit" component={RouterLink} to="/alignment">Alignement</Button>
          <Button color="inherit" component={RouterLink} to="/alignments">Historique</Button>
          <Button color="inherit" component={RouterLink} to="/assembly">Assemblage</Button>
          <Button color="inherit" component={RouterLink} to="/assemblies">Assemblages</Button>
        </Toolbar>
      </AppBar>

      <main className="mx-auto max-w-6xl px-4 py-8">
        <Routes>
          <Route path="/" element={<DatasetListPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/datasets/:id" element={<DatasetDetailPage />} />
          <Route path="/datasets/:id/kmers" element={<KmerPage />} />
          <Route path="/kmer-analyses/:id/spectrum" element={<SpectrumPage />} />
          <Route path="/alignment" element={<AlignmentPage />} />
          <Route path="/alignments" element={<AlignmentHistoryPage />} />
          <Route path="/alignments/:id" element={<AlignmentDetailPage />} />
          <Route path="/assembly" element={<AssemblyPage />} />
          <Route path="/assemblies" element={<AssemblyHistoryPage />} />
          <Route path="/assemblies/:id/analysis" element={<AssemblyAnalysisPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
