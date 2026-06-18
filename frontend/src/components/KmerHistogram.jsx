import { Bar } from 'react-chartjs-2'

// Histogramme de fréquence des k-mers / spectre (Q3)
// X = multiplicité (nb d'occurrences), Y = nb de k-mers distincts.
export default function KmerHistogram({ spectrum, maxMultiplicity = 50 }) {
  const bins = spectrum.filter((b) => b.multiplicity <= maxMultiplicity)
  const data = {
    labels: bins.map((b) => b.multiplicity),
    datasets: [{
      label: 'Nombre de k-mers distincts',
      data: bins.map((b) => b.distinct_count),
      backgroundColor: '#2e7d32',
    }],
  }
  const options = {
    responsive: true,
    plugins: {
      legend: { display: true },
      title: {
        display: true,
        text: 'Spectre de k-mers — le pic à gauche (multiplicité 1-2) traduit les erreurs de séquençage',
      },
    },
    scales: {
      x: { title: { display: true, text: 'Multiplicité (nombre d\'occurrences)' } },
      y: { title: { display: true, text: 'k-mers distincts' }, beginAtZero: true },
    },
  }
  return <Bar data={data} options={options} />
}
