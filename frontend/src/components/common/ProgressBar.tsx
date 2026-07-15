import React from 'react'

interface ProgressBarProps {
  percent: number
  stage?: string
  message?: string
  height?: number
  showPercent?: boolean
}

const STAGE_LABEL: Record<string, string> = {
  script: '生成脚本',
  audio: '合成语音',
  render: '渲染视频',
  done: '完成',
  gen: '生成中',
  dedup: '去重',
  supplement: '补生成',
  assemble: '组装',
}

const ProgressBar: React.FC<ProgressBarProps> = ({
  percent,
  stage,
  message,
  height = 6,
  showPercent = true,
}) => {
  const clamped = Math.max(0, Math.min(100, percent || 0))
  const stageLabel = (stage && STAGE_LABEL[stage]) || stage || ''
  const displayMessage = message || stageLabel

  return (
    <div style={{ width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            flex: 1,
            height,
            background: 'rgba(48, 105, 152, 0.10)',
            borderRadius: height,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${clamped}%`,
              height: '100%',
              background: 'var(--py-blue, #306699)',
              borderRadius: height,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
        {showPercent && (
          <span
            style={{
              fontSize: 12,
              fontWeight: 600,
              color: 'var(--py-blue-deep, #1e3a5f)',
              minWidth: 36,
              textAlign: 'right',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {clamped}%
          </span>
        )}
      </div>
      {displayMessage && (
        <div style={{ marginTop: 6, fontSize: 11.5, color: 'var(--mute, #64748b)', lineHeight: 1.4 }}>
          {displayMessage}
        </div>
      )}
    </div>
  )
}

export default ProgressBar
