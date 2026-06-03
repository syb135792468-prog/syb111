import React, { useRef, useState, useEffect, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { X, Pencil } from 'lucide-react'
import { renderMarkdown, highlightCodeBlocks } from '../../utils/markdown'
import MindmapViewer from '../mindmap/MindmapViewer'
import QuizView from '../quiz/QuizView'

// --- 类型定义 ---
interface ResourceDetailProps {
  show?: boolean
  title?: string
  content?: string
  type?: string
  resourceId?: string
  onClose: () => void
}

// --- 组件 ---
const ResourceDetail: React.FC<ResourceDetailProps> = ({
  show = false,
  title = '',
  content = '',
  type = 'doc',
  resourceId = '',
  onClose,
}) => {
  const contentRef = useRef<HTMLDivElement>(null)
  const [showQuiz, setShowQuiz] = useState(false)

  // 渲染 markdown 内容
  useEffect(() => {
    if (!show || !contentRef.current || !content) return
    if (type === 'mindmap') return // 由 MindmapViewer 处理

    contentRef.current.innerHTML = renderMarkdown(content)
    highlightCodeBlocks(contentRef.current)
  }, [show, content, type])

  // ESC 关闭
  useEffect(() => {
    if (!show) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [show, onClose])

  if (!show) return null

  return createPortal(
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      >
        <div
          className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col"
          onClick={e => e.stopPropagation()}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
            <h3 className="text-base font-semibold text-gray-800">{title}</h3>
            <div className="flex items-center gap-2">
              {type === 'quiz' && resourceId && (
                <button
                  onClick={() => setShowQuiz(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
                >
                  <Pencil className="w-4 h-4" />
                  开始练习
                </button>
              )}
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
          {/* Content */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {type === 'mindmap' ? (
              <MindmapViewer content={content} />
            ) : (
              <div ref={contentRef} className="md-content" />
            )}
          </div>
        </div>
      </div>
      {showQuiz && (
        <QuizView
          show={showQuiz}
          resourceId={resourceId}
          onClose={() => setShowQuiz(false)}
        />
      )}
    </>,
    document.body
  )
}

export default ResourceDetail
