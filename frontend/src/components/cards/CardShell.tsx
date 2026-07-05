import React, { useRef, useEffect, useState } from 'react'
import { ChevronDown, ChevronUp, Bookmark, Maximize2 } from 'lucide-react'

interface CardShellProps {
  icon: React.ReactNode
  title: string
  typeLabel: string
  gradient: string
  collapsed: boolean
  onToggleCollapse: () => void
  onSave?: () => void
  onFullscreen?: () => void
  saved?: boolean
  children: React.ReactNode
  footer?: React.ReactNode
}

const CardShell: React.FC<CardShellProps> = ({
  icon,
  title,
  typeLabel,
  gradient,
  collapsed,
  onToggleCollapse,
  onSave,
  onFullscreen,
  saved,
  children,
  footer,
}) => {
  const bodyRef = useRef<HTMLDivElement>(null)
  const [bodyHeight, setBodyHeight] = useState<number | undefined>(undefined)
  const [animating, setAnimating] = useState(false)

  useEffect(() => {
    if (!bodyRef.current) return
    const el = bodyRef.current
    const updateHeight = () => {
      if (collapsed) {
        setBodyHeight(0)
      } else {
        setBodyHeight(el.scrollHeight)
      }
    }
    updateHeight()
    const ro = new ResizeObserver(updateHeight)
    ro.observe(el)
    return () => ro.disconnect()
  }, [collapsed])

  const handleToggle = () => {
    setAnimating(true)
    onToggleCollapse()
    setTimeout(() => setAnimating(false), 300)
  }

  return (
    <div style={{
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      overflow: 'hidden',
      background: '#fff',
      boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    }}>
      {/* Header */}
      <div
        onClick={handleToggle}
        style={{
          background: '#f9fafb',
          borderBottom: `3px solid ${gradient}`,
          padding: '10px 14px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          cursor: 'pointer',
          userSelect: 'none',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
          <span style={{ fontSize: 18, flexShrink: 0 }}>{icon}</span>
          <div style={{ minWidth: 0 }}>
            <div style={{ color: '#1f2937', fontWeight: 600, fontSize: 14, wordBreak: 'break-word' }}>{title}</div>
            <div style={{ color: '#6b7280', fontSize: 11, marginTop: 1 }}>{typeLabel}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          {onFullscreen && (
            <button
              onClick={(e) => { e.stopPropagation(); onFullscreen() }}
              style={{
                background: '#e5e7eb',
                border: 'none',
                borderRadius: 6,
                padding: '6px 8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                color: '#4b5563',
                minHeight: 32, minWidth: 32,
              }}
              title="全屏交互"
            >
              <Maximize2 size={14} />
            </button>
          )}
          {onSave && (
            <button
              onClick={(e) => { e.stopPropagation(); onSave() }}
              style={{
                background: saved ? '#d1fae5' : '#e5e7eb',
                border: 'none',
                borderRadius: 6,
                padding: '6px 8px',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                color: saved ? '#059669' : '#4b5563',
                minHeight: 32, minWidth: 32,
              }}
              title={saved ? '取消收藏' : '收藏到资源库'}
            >
              <Bookmark size={14} fill={saved ? 'currentColor' : 'none'} />
            </button>
          )}
          {collapsed ? <ChevronDown size={16} color="#6b7280" /> : <ChevronUp size={16} color="#6b7280" />}
        </div>
      </div>

      {/* Body with animation */}
      <div
        ref={bodyRef}
        style={{
          maxHeight: bodyHeight !== undefined ? bodyHeight : (collapsed ? 0 : 2000),
          overflow: 'hidden',
          transition: animating ? 'max-height 0.3s ease-in-out, opacity 0.3s ease-in-out' : 'none',
          opacity: collapsed ? 0 : 1,
        }}
      >
        <div style={{ padding: '14px' }}>
          {children}
        </div>
      </div>

      {/* Footer */}
      {footer && (
        <div style={{
          padding: '8px 14px',
          borderTop: '1px solid #f3f4f6',
          background: '#fafafa',
          fontSize: 12,
          color: '#9ca3af',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          {footer}
        </div>
      )}
    </div>
  )
}

export default CardShell
