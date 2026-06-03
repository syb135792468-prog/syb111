import React, { useRef, useEffect } from 'react'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

// --- 类型定义 ---
interface RadarPoint {
  id: string
  name: string
  mastery: number
  category?: string
}

interface RadarChartProps {
  radarData?: RadarPoint[]
}

// --- 组件 ---
const RadarChart: React.FC<RadarChartProps> = ({ radarData = [] }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    // 销毁旧图表
    if (chartRef.current) {
      chartRef.current.destroy()
      chartRef.current = null
    }

    // 直接使用 radarData 的 name 和 mastery，不再依赖 PYTHON_KNOWLEDGE_POINTS
    const labels = radarData.map(p =>
      p.name.length > 6 ? p.name.slice(0, 6) + '...' : p.name
    )
    const data = radarData.map(p => p.mastery)

    chartRef.current = new Chart(canvasRef.current, {
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
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 800, easing: 'easeOutQuart' },
        scales: {
          r: {
            beginAtZero: true,
            max: 100,
            ticks: { display: false, stepSize: 25 },
            grid: { color: 'rgba(0,0,0,0.05)' },
            pointLabels: { font: { size: 11 }, color: '#6b7280' },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title(items) {
                const idx = items[0]?.dataIndex
                return idx !== undefined && radarData[idx] ? radarData[idx].name : ''
              },
              label(item) {
                return `掌握程度：${item.raw}%`
              },
            },
          },
        },
      },
    })

    return () => {
      if (chartRef.current) {
        chartRef.current.destroy()
        chartRef.current = null
      }
    }
  }, [radarData])

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">知识掌握雷达图</h3>
      <div style={{ height: 280 }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  )
}

export default RadarChart
