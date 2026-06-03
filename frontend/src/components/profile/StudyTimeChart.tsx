import React, { useRef, useEffect } from 'react'
import { Chart, registerables } from 'chart.js'

Chart.register(...registerables)

// --- 类型定义 ---
export interface DailyStudyTime {
  date: string
  label: string
  minutes: number
}

interface StudyTimeChartProps {
  data?: DailyStudyTime[]
  totalHours?: number
}

// --- 组件 ---
const StudyTimeChart: React.FC<StudyTimeChartProps> = ({ data = [], totalHours = 0 }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const chartRef = useRef<Chart | null>(null)

  useEffect(() => {
    if (!canvasRef.current || data.length === 0) return

    // 销毁旧图表
    if (chartRef.current) {
      chartRef.current.destroy()
      chartRef.current = null
    }

    const ctx = canvasRef.current.getContext('2d')
    if (!ctx) return

    const maxMinutes = Math.max(...data.map((d) => d.minutes), 1)

    chartRef.current = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: data.map((d) => d.date),
        datasets: [
          {
            label: '学习时长(分钟)',
            data: data.map((d) => d.minutes),
            backgroundColor: data.map((d) =>
              d.minutes > 0
                ? 'rgba(99, 102, 241, 0.7)'
                : 'rgba(229, 231, 235, 0.5)'
            ),
            borderColor: data.map((d) =>
              d.minutes > 0
                ? 'rgba(99, 102, 241, 1)'
                : 'rgba(209, 213, 219, 0.8)'
            ),
            borderWidth: 1,
            borderRadius: 6,
            maxBarThickness: 40,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => {
                const idx = items[0]?.dataIndex ?? 0
                return data[idx] ? `${data[idx].date} ${data[idx].label}` : ''
              },
              label: (item) => {
                const m = item.raw as number
                if (m >= 60) return ` ${Math.floor(m / 60)}小时${m % 60}分钟`
                return ` ${m}分钟`
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { size: 11 },
              callback: (_val, idx) => {
                const d = data[idx]
                return d ? `${d.date}\n${d.label}` : ''
              },
            },
          },
          y: {
            beginAtZero: true,
            suggestedMax: Math.max(maxMinutes, 30),
            grid: { color: 'rgba(0,0,0,0.04)' },
            ticks: {
              font: { size: 11 },
              callback: (val) => {
                const m = val as number
                if (m >= 60) return `${Math.round(m / 60)}h`
                return `${m}m`
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
  }, [data])

  const todayMinutes = data.length > 0 ? data[data.length - 1].minutes : 0
  const todayHours = todayMinutes >= 60
    ? `${Math.floor(todayMinutes / 60)}小时${todayMinutes % 60 > 0 ? todayMinutes % 60 + '分钟' : ''}`
    : `${todayMinutes}分钟`

  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-gray-700">学习时间</h3>
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span>今日 <b className="text-gray-600">{todayHours}</b></span>
          <span>累计 <b className="text-gray-600">{totalHours}小时</b></span>
        </div>
      </div>

      {data.length > 0 && data.some((d) => d.minutes > 0) ? (
        <div className="h-[200px]">
          <canvas ref={canvasRef} />
        </div>
      ) : (
        <div className="h-[200px] flex items-center justify-center text-gray-300 text-sm">
          暂无学习时间记录
        </div>
      )}
    </div>
  )
}

export default StudyTimeChart
