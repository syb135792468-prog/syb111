import React, { useRef, useEffect } from 'react'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

// --- 类型定义 ---
interface StyleData {
  visual?: number
  auditory?: number
  kinesthetic?: number
  mixed?: number
  dominant?: string
}

interface StyleChartProps {
  styleData?: StyleData
}

// --- 常量 ---
const STYLE_LABELS = ['视觉型', '听觉型', '动手型', '混合型']
const STYLE_KEYS = ['visual', 'auditory', 'kinesthetic', 'mixed'] as const
const COLORS = [
  'rgba(59, 130, 246, 0.8)',
  'rgba(139, 92, 246, 0.8)',
  'rgba(16, 185, 129, 0.8)',
  'rgba(245, 158, 11, 0.8)',
]

// --- 组件 ---
const StyleChart: React.FC<StyleChartProps> = ({
  styleData = { visual: 25, auditory: 25, kinesthetic: 25, mixed: 25, dominant: '混合型' },
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!canvasRef.current) return

    // 销毁旧图表
    if (chartRef.current) {
      chartRef.current.destroy()
      chartRef.current = null
    }

    const data = STYLE_KEYS.map(k => styleData[k] ?? 0)

    chartRef.current = new Chart(canvasRef.current, {
      type: 'doughnut',
      data: {
        labels: STYLE_LABELS,
        datasets: [{
          data,
          backgroundColor: COLORS,
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '60%',
        animation: { duration: 800, easing: 'easeOutQuart' },
        plugins: {
          legend: {
            position: 'bottom',
            labels: { padding: 16, usePointStyle: true, pointStyleWidth: 8, font: { size: 12 } },
          },
          tooltip: {
            callbacks: {
              label(item) {
                return `${item.label}：${item.raw}%`
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
  }, [styleData])

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
      <h3 className="text-sm font-semibold text-gray-700 mb-4">学习风格分析</h3>
      <div style={{ height: 280 }}>
        <canvas ref={canvasRef} />
      </div>
    </div>
  )
}

export default StyleChart
