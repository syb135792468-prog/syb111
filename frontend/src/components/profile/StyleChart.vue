<script setup>
import { ref, onMounted, watch } from 'vue'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

const props = defineProps({
  style: { type: String, default: 'mixed' },
})

const canvasRef = ref(null)
let chartInstance = null

const styleMap = {
  visual: '视觉型',
  auditory: '听觉型',
  kinesthetic: '动手型',
  mixed: '混合型',
}

const allStyles = ['visual', 'auditory', 'kinesthetic', 'mixed']
const colors = [
  'rgba(59, 130, 246, 0.8)',
  'rgba(139, 92, 246, 0.8)',
  'rgba(16, 185, 129, 0.8)',
  'rgba(245, 158, 11, 0.8)',
]

function renderChart() {
  if (chartInstance) chartInstance.destroy()
  if (!canvasRef.value) return

  const data = allStyles.map(s => s === props.style ? 100 : Math.floor(Math.random() * 20) + 30)

  chartInstance = new Chart(canvasRef.value, {
    type: 'doughnut',
    data: {
      labels: allStyles.map(s => styleMap[s]),
      datasets: [{
        data,
        backgroundColor: colors,
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '60%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { padding: 16, usePointStyle: true, pointStyleWidth: 8, font: { size: 12 } },
        },
      },
    },
  })
}

onMounted(renderChart)
watch(() => props.style, renderChart)
</script>

<template>
  <div class="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
    <h3 class="text-sm font-semibold text-gray-700 mb-4">学习风格分析</h3>
    <div style="height: 280px">
      <canvas ref="canvasRef"></canvas>
    </div>
  </div>
</template>
