import { Line } from 'react-chartjs-2'

// Taux de faux positifs theorique d'un filtre de Bloom :
//   p(m) = (1 - e^{-num_hashes·n/m})^num_hashes
// trace en fonction de m (bits), a n (k-mers solides) et num_hashes donnes.
function fpRate(numBits, numHashes, n) {
  if (n <= 0 || numBits <= 0) return 0
  return (1 - Math.exp((-numHashes * n) / numBits)) ** numHashes
}

export default function BloomAnalysisChart({ n, numHashes }) {
  const points = []
  for (let factor = 2; factor <= 40; factor += 2) {
    const m = n * factor
    points.push({ x: m, y: fpRate(m, numHashes, n) })
  }
  const data = {
    labels: points.map((p) => p.x),
    datasets: [
      {
        label: `Taux de FP (n=${n} k-mers, ${numHashes} hachages)`,
        data: points.map((p) => p.y),
        borderColor: '#2e7d32',
        backgroundColor: '#2e7d32',
        fill: false,
      },
    ],
  }
  const options = {
    responsive: true,
    plugins: {
      legend: { display: true },
      title: {
        display: true,
        text: 'Impact de la taille du filtre (m bits) sur le taux de faux positifs',
      },
    },
    scales: {
      x: { title: { display: true, text: 'm (bits du filtre de Bloom)' } },
      y: {
        title: { display: true, text: 'Taux de faux positifs' },
        beginAtZero: true,
      },
    },
  }
  return <Line data={data} options={options} />
}
