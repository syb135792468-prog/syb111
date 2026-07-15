import React, { useMemo, useState, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { useAuthStore } from '../../stores/auth'
import { renderVideo } from '../../api/resource'
import { Eye, Download, Trash2, Video, Loader2, ChevronDown, ChevronRight, Copy, Check, Clock3 } from 'lucide-react'

interface AnimationItem {
  id: number
  title?: string
  content?: string
  status?: string
  resource_type?: string
  created_at?: string
  extra_metadata?: {
    duration?: number
    style?: string
    [key: string]: unknown
  }
}

function formatTime(dateStr?: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function extractKeyPoints(html: string): string[] {
  if (!html) return []
  try {
    const parser = new DOMParser()
    const doc = parser.parseFromString(html, 'text/html')
    const points: string[] = []
    // Extract from <li> elements
    const lis = doc.querySelectorAll('li')
    lis.forEach((li) => {
      const text = li.textContent?.trim()
      if (text && text.length > 2 && text.length < 100) {
        points.push(text.length > 15 ? text.slice(0, 15) + '...' : text)
      }
    })
    // Extract from headings if not enough <li>
    if (points.length < 3) {
      const headings = doc.querySelectorAll('h3, h4, h5')
      headings.forEach((h) => {
        const text = h.textContent?.trim()
        if (text && text.length > 2) {
          points.push(text.length > 15 ? text.slice(0, 15) + '...' : text)
        }
      })
    }
    return points.slice(0, 5)
  } catch {
    return []
  }
}

const STYLE_LABELS: Record<string, string> = {
  tutorial: '教程风格',
  code_demo: '代码演示',
  visualization: '可视化',
  story: '故事化',
}

const AnimationDetailPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const appStore = useAppStore()
  const authStore = useAuthStore()
  const item = (data?.item as AnimationItem | undefined) || undefined
  const onPreview = data?.onPreview as (() => void) | undefined
  const onDownload = data?.onDownload as (() => void) | undefined
  const onDelete = data?.onDelete as (() => void) | undefined

  const [rendering, setRendering] = useState(false)
  const [videoResult, setVideoResult] = useState<{ video_url?: string; mp4_url?: string } | null>(null)
  const [codeExpanded, setCodeExpanded] = useState(false)
  const [infoExpanded, setInfoExpanded] = useState(false)
  const [codeCopied, setCodeCopied] = useState(false)

  const handleRenderVideo = useCallback(async () => {
    if (!item?.id || rendering) return
    setRendering(true)
    setVideoResult(null)
    try {
      const resp = await renderVideo(item.id, authStore.userId)
      if (resp.code === 200 && resp.data) {
        setVideoResult(resp.data as { video_url?: string; mp4_url?: string })
        appStore.showToast('视频渲染成功', 'success')
      } else {
        appStore.showToast(resp.message || '渲染失败', 'error')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('渲染失败：' + msg, 'error')
    } finally {
      setRendering(false)
    }
  }, [item?.id, rendering, authStore.userId, appStore])

  const keyPoints = useMemo(() => extractKeyPoints(item?.content || ''), [item?.content])

  const handleCopyCode = useCallback(() => {
    if (!item?.content) return
    const content = item.content
    const done = () => { setCodeCopied(true); setTimeout(() => setCodeCopied(false), 1500) }
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(content).then(done).catch(() => fallbackCopy(content))
    } else {
      fallbackCopy(content)
    }
    function fallbackCopy(text: string) {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.cssText = 'position:fixed;left:-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      done()
    }
  }, [item?.content])

  if (!item) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-slate-400 px-6">
        <p className="text-xs text-center">点击动画卡片查看详情</p>
      </div>
    )
  }

  const duration = item.extra_metadata?.duration
  const style = typeof item.extra_metadata?.style === 'string' ? item.extra_metadata.style : ''
  const styleLabel = STYLE_LABELS[style] || style || '教程风格'
  const charCount = (item.content || '').length

  return (
    <div className="h-full flex flex-col">
      {/* Module A: Basic info */}
      <div style={{ padding: '0 16px 16px 16px' }}>
        <h3 className="text-base font-medium text-slate-800 leading-6 break-words mb-2">
          {item.title || '未命名动画'}
        </h3>
        <div className="flex items-center gap-2 flex-wrap">
          {duration && (
            <span className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-600">
              <Clock3 className="w-3 h-3" />
              {duration} 秒
            </span>
          )}
          <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-600">
            {styleLabel}
          </span>
          {item.created_at && (
            <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-600">
              {formatTime(item.created_at)} 生成
            </span>
          )}
        </div>
      </div>

      {/* Module B: Core actions - fixed */}
      <div
        className="flex-shrink-0"
        style={{ padding: '0 16px 16px 16px' }}
      >
        <div className="flex items-center gap-2">
          <button
            onClick={onPreview}
            disabled={!onPreview}
            className="flex-1 flex items-center justify-center gap-1.5 h-9 text-xs font-medium text-white bg-brand-600 rounded-md hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Eye className="w-3.5 h-3.5" />
            预览
          </button>
          <button
            onClick={onDownload}
            disabled={!onDownload}
            className="flex-1 flex items-center justify-center gap-1.5 h-9 text-xs font-medium text-slate-700 border border-slate-300 rounded-md hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            下载 HTML
          </button>
        </div>
        <div className="flex items-center gap-2 mt-2">
          <button
            onClick={handleRenderVideo}
            disabled={rendering}
            className="flex-1 flex items-center justify-center gap-1.5 h-9 text-xs text-slate-500 hover:text-slate-700 hover:bg-slate-50 rounded-md disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {rendering ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                渲染中...
              </>
            ) : (
              <>
                <Video className="w-3.5 h-3.5" />
                导出视频
              </>
            )}
          </button>
          <button
            onClick={onDelete}
            disabled={!onDelete}
            className="flex-1 flex items-center justify-center gap-1.5 h-9 text-xs text-red-500 hover:text-red-700 hover:bg-red-50 rounded-md disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
            删除
          </button>
        </div>

        {/* Video result */}
        {videoResult && (
          <div className="flex gap-2 mt-2">
            {videoResult.video_url && (
              <a
                href={videoResult.video_url}
                download
                className="flex-1 flex items-center justify-center gap-1.5 h-8 text-xs font-medium text-white bg-green-600 rounded-md hover:bg-green-700 transition-colors"
              >
                <Download className="w-3 h-3" />
                WebM
              </a>
            )}
            {videoResult.mp4_url && (
              <a
                href={videoResult.mp4_url}
                download
                className="flex-1 flex items-center justify-center gap-1.5 h-8 text-xs font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 transition-colors"
              >
                <Download className="w-3 h-3" />
                MP4
              </a>
            )}
          </div>
        )}
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-slate-200/60" />

      {/* Module C: Key knowledge points */}
      <div style={{ padding: '12px 16px' }}>
        <h4 className="text-[13px] font-medium text-slate-700 mb-2">核心知识点</h4>
        {keyPoints.length > 0 ? (
          <ul className="space-y-1.5">
            {keyPoints.map((point, i) => (
              <li key={i} className="text-[13px] text-slate-600 leading-relaxed flex items-start gap-2">
                <span className="w-1 h-1 rounded-full bg-slate-400 mt-2 flex-shrink-0" />
                {point}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-slate-400">生成完成后可查看核心知识点</p>
        )}
      </div>

      {/* Divider */}
      <div className="mx-4 border-t border-slate-200/60" />

      {/* Module D: Collapsible panels */}
      <div className="flex-1 overflow-y-auto">
        {/* HTML Code snippet */}
        <button
          onClick={() => setCodeExpanded(!codeExpanded)}
          className="w-full flex items-center justify-between h-10 px-4 text-xs text-slate-600 hover:bg-slate-50/60 transition-colors border-b border-slate-200/40"
        >
          <span className="font-medium">HTML 代码片段</span>
          <div className="flex items-center gap-2">
            {codeExpanded && (
              <button
                onClick={(e) => { e.stopPropagation(); handleCopyCode() }}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-brand-600 transition-colors"
              >
                {codeCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                {codeCopied ? '已复制' : '复制代码'}
              </button>
            )}
            {codeExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </div>
        </button>
        {codeExpanded && (
          <div className="px-4 py-2">
            <pre
              className="text-[11px] bg-slate-900 text-slate-300 rounded-lg p-3 overflow-auto leading-relaxed font-mono"
              style={{ height: 240 }}
            >
              {(item.content || '').slice(0, 3000)}
              {(item.content || '').length > 3000 ? '\n...' : ''}
            </pre>
          </div>
        )}

        {/* More info */}
        <button
          onClick={() => setInfoExpanded(!infoExpanded)}
          className="w-full flex items-center justify-between h-10 px-4 text-xs text-slate-600 hover:bg-slate-50/60 transition-colors border-b border-slate-200/40"
        >
          <span className="font-medium">更多信息</span>
          {infoExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </button>
        {infoExpanded && (
          <div className="px-4 py-2 space-y-0">
            <InfoRow label="资源 ID" value={String(item.id)} />
            <InfoRow label="字符数" value={`${charCount} 字符`} />
            <InfoRow label="资源类型" value={item.resource_type || 'video'} />
            <InfoRow label="风格" value={styleLabel} />
          </div>
        )}
      </div>
    </div>
  )
}

const InfoRow: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
    <span className="text-xs text-slate-400">{label}</span>
    <span className="text-xs text-slate-700 text-right break-all">{value}</span>
  </div>
)

export default AnimationDetailPanel
