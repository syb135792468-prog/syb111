<script setup>
import { ref, onMounted, watch } from 'vue'
import { Chart, registerables } from 'chart.js'
import { PYTHON_KNOWLEDGE_POINTS } from '../../utils/constants'

Chart.register(...registerables)

const props = defineProps({
  mastered: { type: Array, default: () => [] },
  weak: { type: Array, default: () => [] },
})

const canvasRef = ref(null)
let chartInstance = null

function getScore(point) {
  if (props.mastered.includes(point)) return 100
  if (props.weak.includes(point)) return 30
  return 50
}

function renderChart() {
  if (chartInstance) chartInstance.destroy()
  if (!canvasRef.value) return

  const labels = PYTHON_KNOWLEDGE_POINTS.map(p =>
    p.length > 6 ? p.slice(0, 6) + '...' : p
  )
  const data = PYTHON_KNOWLEDGE_POINTS.map(getScore)

  chartInstance = new Chart(canvasRef.value, {
    type: 'radar',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: 'rgba(59, 130, 246, 0.15)',
        borderColor: 'rgba(59, 130, 246, 0.8)',
        borderWidth: 2,
        pointBackgroundColor: 'rgba(59, 130, 246, 1)',
        pointRadius: 3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          beginAtZero: true,
          max: 100,
          ticks: { display: false, stepSize: 25 },
          grid: { color: 'rgba(0,0,0,0.05)' },
          pointLabels: { font: { size: 11 }, color: '#6b7280' },
        },
      },
      plugins: { legend: { display: false } },
    },
  })
}

onMounted(renderChart)
watch(() => [props.mastered, props.weak], renderChart, { deep: true })
</script>

<template>
  <div class="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
    <h3 class="text-sm font-semibold text-gray-700 mb-4">知识掌握雷达图</h3>
    <div style="height: 280px">
      <canvas ref="canvasRef"></canvas>
    </div>
  </div>
</template>
