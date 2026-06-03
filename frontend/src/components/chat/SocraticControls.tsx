import React from 'react'
import { Lightbulb, HelpCircle, StopCircle } from 'lucide-react'

interface SocraticControlsProps {
  threadId: string | null
  isStreaming: boolean
  onHint: () => void
  onConfused: () => void
  onEnd: () => void
}

const SocraticControls: React.FC<SocraticControlsProps> = ({
  threadId,
  isStreaming,
  onHint,
  onConfused,
  onEnd,
}) => {
  if (!threadId) return null

  const btnBase: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 4,
    padding: '4px 12px',
    borderRadius: 16,
    fontSize: 12,
    fontWeight: 500,
    border: '1px solid #e5e7eb',
    background: '#fff',
    cursor: isStreaming ? 'not-allowed' : 'pointer',
    opacity: isStreaming ? 0.5 : 1,
    transition: 'all 0.15s',
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 24px', gap: 8 }}>
      <button
        onClick={onHint}
        disabled={isStreaming}
        style={{ ...btnBase, color: '#2563eb', borderColor: '#bfdbfe', background: '#eff6ff' }}
        title="获取提示"
      >
        <Lightbulb style={{ width: 12, height: 12 }} />
        我需要提示
      </button>
      <button
        onClick={onConfused}
        disabled={isStreaming}
        style={{ ...btnBase, color: '#7c3aed', borderColor: '#c4b5fd', background: '#f5f3ff' }}
        title="让 AI 换种方式讲解"
      >
        <HelpCircle style={{ width: 12, height: 12 }} />
        我没听懂
      </button>
      <button
        onClick={onEnd}
        disabled={isStreaming}
        style={{ ...btnBase, color: '#dc2626', borderColor: '#fecaca', background: '#fef2f2' }}
        title="结束本次学习"
      >
        <StopCircle style={{ width: 12, height: 12 }} />
        结束学习
      </button>
    </div>
  )
}

export default SocraticControls
