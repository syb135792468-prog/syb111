import React, { useState, useCallback } from 'react'
import { ContentCardRef } from '../../stores/chat'
import { useAppStore } from '../../stores/app'
import { useAuthStore } from '../../stores/auth'
import { addToLibrary } from '../../api/resource'
import QuizCard from './QuizCard'
import CodeCard from './CodeCard'
import CardShell from './CardShell'
import FullscreenModal from './FullscreenModal'
import FullscreenQuiz from './FullscreenQuiz'
import FullscreenCode from './FullscreenCode'
import SlidesViewer from '../slides/SlidesViewer'

interface ContentCardRendererProps {
  card: ContentCardRef
}

const TYPE_CONFIG: Record<string, { icon: string; gradient: string; label: string }> = {
  quiz: { icon: '📝', gradient: '#7c3aed', label: '互动测验' },
  code: { icon: '💻', gradient: '#2563eb', label: '代码示例' },
  mindmap: { icon: '🧠', gradient: '#d97706', label: '思维导图' },
  doc: { icon: '📖', gradient: '#059669', label: '学习文档' },
  video: { icon: '🎬', gradient: '#dc2626', label: '教学动画' },
  slides: { icon: '📊', gradient: '#2563eb', label: '演示幻灯片' },
}

const ContentCardRenderer: React.FC<ContentCardRendererProps> = ({ card }) => {
  const [collapsed, setCollapsed] = useState(card.collapsed || false)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const config = TYPE_CONFIG[card.type] || TYPE_CONFIG.doc
  const showToast = useAppStore(s => s.showToast)
  const userId = useAuthStore(s => s.userId)

  const handleSave = useCallback(async () => {
    if (saving) return
    setSaving(true)
    try {
      const resp = await addToLibrary(card.id, userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library: boolean })?.in_library
        setSaved(newState)
        showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
      } else {
        showToast(resp.message || '操作失败', 'error')
      }
    } catch {
      showToast('操作失败，请重试', 'error')
    } finally {
      setSaving(false)
    }
  }, [card.id, userId, saving, showToast])

  const handleFullscreen = useCallback(() => {
    setFullscreen(true)
  }, [])

  const handleCloseFullscreen = useCallback(() => {
    try { window.speechSynthesis?.cancel() } catch {}
    setFullscreen(false)
  }, [])

  const hasFullscreen = card.type === 'quiz' || card.type === 'code' || card.type === 'video' || card.type === 'slides'

  const renderContent = () => {
    switch (card.type) {
      case 'quiz':
        return <QuizCard data={card.data} />
      case 'code':
        return <CodeCard data={card.data} />
      case 'mindmap':
        return <div style={{ color: '#6b7280', fontSize: 13, textAlign: 'center', padding: 16 }}>
          思维导图将在资源库中可交互查看
        </div>
      case 'video': {
        const html = typeof card.data === 'string' ? card.data : card.data?.content || ''
        const handlePlay = () => {
          if (!html) return
          const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
          const url = URL.createObjectURL(blob)
          const win = window.open(url, '_blank')
          if (win) {
            win.addEventListener('load', () => URL.revokeObjectURL(url))
          } else {
            URL.revokeObjectURL(url)
            showToast('弹窗被拦截，请允许弹窗后重试', 'error')
          }
        }
        return (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>🎬</div>
            <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 12 }}>
              {card.title || '教学动画'}
            </div>
            {html ? (
              <button
                onClick={handlePlay}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 20px', borderRadius: 8,
                  background: '#dc2626',
                  color: '#fff', fontSize: 14, border: 'none', cursor: 'pointer',
                }}
              >
                ▶ 播放动画
              </button>
            ) : (
              <div style={{ color: '#9ca3af', fontSize: 12 }}>动画内容将在资源库中可预览</div>
            )}
          </div>
        )
      }
      case 'document':
        return <div style={{ color: '#374151', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
          {typeof card.data === 'string' ? card.data : card.data?.markdown || JSON.stringify(card.data, null, 2)}
        </div>
      case 'slides': {
        const md = typeof card.data === 'string' ? card.data : card.data?.content || ''
        return md ? (
          <div style={{ textAlign: 'center', padding: 20 }}>
            <div style={{ fontSize: 40, marginBottom: 8 }}>📊</div>
            <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 12 }}>
              {card.title || '教学幻灯片'}
            </div>
            <div style={{ color: '#9ca3af', fontSize: 12 }}>点击全屏播放幻灯片</div>
          </div>
        ) : (
          <div style={{ color: '#9ca3af', fontSize: 12, textAlign: 'center', padding: 16 }}>无幻灯片内容</div>
        )
      }
      default:
        return null
    }
  }

  const renderFullscreenContent = () => {
    switch (card.type) {
      case 'quiz':
        return <FullscreenQuiz data={card.data} />
      case 'code':
        return <FullscreenCode data={card.data} />
      case 'video': {
        const html = typeof card.data === 'string' ? card.data : card.data?.content || ''
        return html ? (
          <iframe
            srcDoc={html}
            style={{ width: '100%', height: '70vh', border: 'none', borderRadius: 8 }}
            sandbox="allow-scripts allow-same-origin allow-speech-synthesis"
            title={card.title}
          />
        ) : (
          <div style={{ color: '#9ca3af', textAlign: 'center', padding: 40 }}>无动画内容</div>
        )
      }
      case 'slides': {
        const md = typeof card.data === 'string' ? card.data : card.data?.content || ''
        return md ? (
          <SlidesViewer content={md} fullscreen />
        ) : (
          <div style={{ color: '#9ca3af', textAlign: 'center', padding: 40 }}>无幻灯片内容</div>
        )
      }
      default:
        return null
    }
  }

  const renderFooter = () => {
    const parts: string[] = []
    if (card.type === 'quiz' && card.data?.questions) {
      parts.push(`${card.data.questions.length} 道题目`)
    }
    if (card.data?.metadata?.difficulty) {
      const diffMap: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
      const diff = diffMap[card.data.metadata.difficulty as string] || card.data.metadata.difficulty
      parts.push(diff)
    }
    if (card.data?.metadata?.duration) {
      parts.push(`约 ${card.data.metadata.duration} 分钟`)
    }
    return parts.length > 0 ? <span>{parts.join(' · ')}</span> : null
  }

  return (
    <>
      <CardShell
        icon={<span>{config.icon}</span>}
        title={card.title}
        typeLabel={config.label}
        gradient={config.gradient}
        collapsed={collapsed}
        onToggleCollapse={() => setCollapsed(!collapsed)}
        onSave={handleSave}
        onFullscreen={hasFullscreen ? handleFullscreen : undefined}
        saved={saved}
        footer={renderFooter()}
      >
        {renderContent()}
      </CardShell>

      {hasFullscreen && (
        <FullscreenModal
          open={fullscreen}
          onClose={handleCloseFullscreen}
          title={card.title}
        >
          {renderFullscreenContent()}
        </FullscreenModal>
      )}
    </>
  )
}

export default ContentCardRenderer
