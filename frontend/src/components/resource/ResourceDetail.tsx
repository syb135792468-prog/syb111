import React, { useRef, useState, useEffect, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { X, Pencil, Download, ExternalLink, Play, User } from 'lucide-react'
import { renderMarkdown, highlightCodeBlocks } from '../../utils/markdown'
import MindmapViewer from '../mindmap/MindmapViewer'
import SlidesViewer from '../slides/SlidesViewer'
import QuizView from '../quiz/QuizView'

// --- 类型定义 ---
interface ResourceDetailProps {
  show?: boolean
  title?: string
  content?: string
  type?: string
  resourceId?: string
  extraMetadata?: Record<string, unknown> | null
  onClose: () => void
}

// --- 组件 ---
const ResourceDetail: React.FC<ResourceDetailProps> = ({
  show = false,
  title = '',
  content = '',
  type = 'doc',
  resourceId = '',
  extraMetadata = null,
  onClose,
}) => {
  const contentRef = useRef<HTMLDivElement>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [showQuiz, setShowQuiz] = useState(false)

  // 渲染 markdown 内容（video/mindmap 不走 markdown）
  useEffect(() => {
    if (!show || !contentRef.current || !content) return
    if (type === 'mindmap' || type === 'video') return

    contentRef.current.innerHTML = renderMarkdown(content)
    highlightCodeBlocks(contentRef.current)
  }, [show, content, type])

  // video：iframe 加载完成后注入内容（仅AI生成的HTML动画）
  useEffect(() => {
    if (!show || type !== 'video' || !iframeRef.current || !content) return
    if (isExternalUrl) return // 外部链接不走iframe
    const iframe = iframeRef.current
    const handleLoad = () => {
      try {
        const doc = iframe.contentDocument
        if (doc) {
          doc.open()
          doc.write(content)
          doc.close()
        }
      } catch { /* 跨域等情况静默失败 */ }
    }
    iframe.addEventListener('load', handleLoad)
    handleLoad()
    return () => {
      iframe.removeEventListener('load', handleLoad)
      // 关闭模态框时停止 iframe 内的语音合成
      try { iframe.contentWindow?.speechSynthesis?.cancel() } catch { /* ignore */ }
    }
  }, [show, content, type])

  // 判断是否为外部视频链接
  const isExternalUrl = type === 'video' && /^https?:\/\//.test(content.trim())

  // 外部视频元数据
  const externalMeta = useMemo(() => {
    if (!isExternalUrl || !extraMetadata) return null
    return {
      thumbnail: (extraMetadata.thumbnail as string) || '',
      author: (extraMetadata.author as string) || '',
      source: (extraMetadata.source as string) || '',
    }
  }, [isExternalUrl, extraMetadata])

  // 下载视频 HTML
  const handleDownload = useCallback(() => {
    if (!content) return
    const blob = new Blob([content], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title || '教学动画'}.html`
    a.click()
    URL.revokeObjectURL(url)
  }, [content, title])

  // 关闭时停止所有语音合成
  const handleClose = useCallback(() => {
    try { window.speechSynthesis?.cancel() } catch { /* ignore */ }
    onClose()
  }, [onClose])

  // ESC 关闭
  useEffect(() => {
    if (!show) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [show, onClose])

  if (!show) return null

  return createPortal(
    <>
      <div
        className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
        onClick={handleClose}
      >
        <div
          className={`bg-white rounded-2xl shadow-2xl w-full mx-4 max-h-[85vh] flex flex-col ${type === 'video' || type === 'slides' ? 'max-w-5xl' : 'max-w-2xl'}`}
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
              {type === 'video' && !isExternalUrl && (
                <button
                  onClick={handleDownload}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
                >
                  <Download className="w-4 h-4" />
                  下载
                </button>
              )}
              {type === 'video' && isExternalUrl && (
                <a
                  href={content}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 transition-colors"
                >
                  <ExternalLink className="w-4 h-4" />
                  打开视频
                </a>
              )}
              <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>
          {/* Content */}
          <div className="flex-1 overflow-hidden px-6 py-4">
            {type === 'mindmap' ? (
              <MindmapViewer content={content} />
            ) : type === 'slides' ? (
              <SlidesViewer content={content} />
            ) : type === 'video' && isExternalUrl ? (
              <div className="flex flex-col items-center justify-center min-h-[40vh] gap-5">
                {/* 缩略图 */}
                {externalMeta?.thumbnail ? (
                  <a href={content} target="_blank" rel="noopener noreferrer" className="block w-full max-w-md rounded-xl overflow-hidden shadow-md hover:shadow-lg transition-shadow">
                    <div className="relative aspect-video bg-gray-100">
                      <img
                        src={externalMeta.thumbnail}
                        alt={title}
                        className="w-full h-full object-cover"
                        referrerPolicy="no-referrer"
                      />
                      <div className="absolute inset-0 flex items-center justify-center bg-black/20 hover:bg-black/30 transition-colors">
                        <Play className="w-14 h-14 text-white drop-shadow-lg" />
                      </div>
                    </div>
                  </a>
                ) : (
                  <div className="w-20 h-20 rounded-full bg-red-50 flex items-center justify-center">
                    <Play className="w-9 h-9 text-red-500" />
                  </div>
                )}
                <div className="text-center">
                  <h4 className="text-base font-medium text-gray-800 mb-1">{title}</h4>
                  {externalMeta?.author && (
                    <p className="text-xs text-gray-500 flex items-center justify-center gap-1">
                      <User className="w-3 h-3" />
                      {externalMeta.author}
                    </p>
                  )}
                  <p className="text-xs text-gray-300 mt-2 break-all max-w-md">{content}</p>
                </div>
                {externalMeta?.source && (
                  <span className="text-xs text-gray-300 bg-gray-50 px-3 py-1 rounded-full">
                    来源：{externalMeta.source === 'bilibili' ? '哔哩哔哩' : externalMeta.source}
                  </span>
                )}
              </div>
            ) : type === 'video' ? (
              <iframe
                ref={iframeRef}
                className="w-full h-full min-h-[60vh] rounded-lg border-0"
                sandbox="allow-scripts allow-same-origin allow-speech-synthesis"
                title={title}
              />
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
