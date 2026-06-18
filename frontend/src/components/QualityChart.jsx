import { Line } from 'react-chartjs-2'

// Courbe de la qualité moyenne par position dans les reads (Q1)
export default function QualityChart({ perPosition }) {
  const data = {
    labels: perPosition.map((_, i) => i + 1),
    datasets: [{
      label: 'Qualité Phred moyenne',
      data: perPosition,
      borderColor: '#1565c0',
      backgroundColor: 'rgba(21,101,192,0.2)',
      tension: 0.2,
      pointRadius: 0,
    }],
  }
  const options = {
    responsive: true,
    plugins: { legend: { display: true } },
    scales: {
      x: { title: { display: true, text: 'Position dans le read' } },
      y: { title: { display: true, text: 'Score Phred' }, beginAtZero: true },
    },
  }
  return <Line data={data} options={options} />
}
