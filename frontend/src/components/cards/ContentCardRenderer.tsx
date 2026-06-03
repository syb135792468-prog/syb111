import React, { useState, useCallback } from 'react'
import { ContentCardRef } from '../../stores/chat'
import { useAppStore } from '../../stores/app'
import QuizCard from './QuizCard'
import CodeCard from './CodeCard'
import CardShell from './CardShell'
import FullscreenModal from './FullscreenModal'
import FullscreenQuiz from './FullscreenQuiz'
import FullscreenCode from './FullscreenCode'

interface ContentCardRendererProps {
  card: ContentCardRef
}

const TYPE_CONFIG: Record<string, { icon: string; gradient: string; label: string }> = {
  quiz: { icon: '📝', gradient: 'linear-gradient(135deg, #8b5cf6, #6d28d9)', label: '互动测验' },
  code: { icon: '💻', gradient: 'linear-gradient(135deg, #3b82f6, #1d4ed8)', label: '代码示例' },
  mindmap: { icon: '🧠', gradient: 'linear-gradient(135deg, #f59e0b, #d97706)', label: '思维导图' },
  doc: { icon: '📖', gradient: 'linear-gradient(135deg, #10b981, #059669)', label: '学习文档' },
  video: { icon: '🎬', gradient: 'linear-gradient(135deg, #ef4444, #dc2626)', label: '教学动画' },
}

const ContentCardRenderer: React.FC<ContentCardRendererProps> = ({ card }) => {
  const [collapsed, setCollapsed] = useState(card.collapsed || false)
  const [saved, setSaved] = useState(false)
  const [fullscreen, setFullscreen] = useState(false)
  const config = TYPE_CONFIG[card.type] || TYPE_CONFIG.doc
  const showToast = useAppStore(s => s.showToast)

  const handleSave = useCallback(() => {
    setSaved(true)
    showToast('已保存到资源库', 'success')
  }, [showToast])

  const handleFullscreen = useCallback(() => {
    setFullscreen(true)
  }, [])

  const hasFullscreen = card.type === 'quiz' || card.type === 'code'

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
      case 'video':
        return <div style={{ color: '#6b7280', fontSize: 13, textAlign: 'center', padding: 16 }}>
          教学动画将在资源库中可预览播放
        </div>
      case 'document':
        return <div style={{ color: '#374151', fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
          {typeof card.data === 'string' ? card.data : card.data?.markdown || JSON.stringify(card.data, null, 2)}
        </div>
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
        onSave={saved ? undefined : handleSave}
        onFullscreen={hasFullscreen ? handleFullscreen : undefined}
        footer={renderFooter()}
      >
        {renderContent()}
      </CardShell>

      {hasFullscreen && (
        <FullscreenModal
          open={fullscreen}
          onClose={() => setFullscreen(false)}
          title={card.title}
        >
          {renderFullscreenContent()}
        </FullscreenModal>
      )}
    </>
  )
}

export default ContentCardRenderer
