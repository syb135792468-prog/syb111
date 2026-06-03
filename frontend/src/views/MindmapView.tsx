import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { generateResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import MindmapViewer from '../components/mindmap/MindmapViewer'
import { Search, GitBranch } from 'lucide-react'

// --- 常量 ---
const STORAGE_KEY = 'mindmap_cache'

interface Preset {
  label: string
  icon: string
}

const PRESETS: Preset[] = [
  { label: '变量与数据类型', icon: '📦' },
  { label: '控制流', icon: '🔀' },
  { label: '函数', icon: '⚡' },
  { label: '面向对象', icon: '🏗️' },
  { label: '文件操作', icon: '📁' },
  { label: '异常处理', icon: '🛡️' },
]

interface CacheData {
  content: string
  lastTitle: string
  topic: string
  resourceId?: number
}

// --- 组件 ---
const MindmapView: React.FC = () => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // --- 状态 ---
  const [topic, setTopic] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastTitle, setLastTitle] = useState('')
  const [resourceId, setResourceId] = useState<number | undefined>()
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // --- 从 localStorage 恢复缓存 ---
  useEffect(() => {
    try {
      const cached: CacheData | null = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
      if (cached && cached.content) {
        setContent(cached.content)
        setLastTitle(cached.lastTitle || '')
        setTopic(cached.topic || '')
        setResourceId(cached.resourceId)
      }
    } catch {
      // ignore
    }
  }, [])

  // --- 生成思维导图 ---
  const generate = useCallback(async (t?: string) => {
    const target = t || topic.trim()
    if (!target) {
      appStore.showToast('请输入知识点主题', 'warning')
      return
    }
    if (!authStore.userId) {
      appStore.showToast('请先登录', 'warning')
      return
    }
    setTopic(target)
    setLoading(true)
    setContent('')
    setLastTitle('')
    // 清除旧缓存
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }

    try {
      const resp = await generateResource(authStore.userId, target, 'mindmap')
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { content?: string; title?: string; id?: number }
        const newContent = data.content || ''
        const newTitle = data.title || target
        const newResourceId = data.id
        setContent(newContent)
        setLastTitle(newTitle)
        setResourceId(newResourceId)
        // 持久化到 localStorage
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify({
            content: newContent,
            lastTitle: newTitle,
            topic: target,
            resourceId: newResourceId,
          }))
        } catch { /* ignore */ }
        appStore.showToast('思维导图生成成功', 'success')
      } else {
        appStore.showToast(resp.message || '生成失败', 'error')
      }
    } catch (e: unknown) {
      if (!mountedRef.current) return
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('生成失败：' + msg, 'error')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [topic, authStore.userId, appStore])

  // --- 键盘事件 ---
  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') generate()
  }, [generate])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="思维导图">
        <div className="flex items-center gap-2">
          <div className="relative">
            <input
              type="text"
              value={topic}
              onChange={e => setTopic(e.target.value)}
              onKeyDown={handleKeydown}
              placeholder="输入知识点名称..."
              className="w-64 px-3 py-1.5 pr-9 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent bg-white"
            />
            <Search className="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
          <button
            onClick={() => generate()}
            disabled={loading || !topic.trim()}
            className="flex items-center gap-1.5 px-4 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            <GitBranch className="w-4 h-4" />
            {loading ? '生成中...' : '生成导图'}
          </button>
        </div>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="max-w-5xl mx-auto">
          {/* Preset buttons (shown when no content) */}
          {!content && !loading && (
            <div className="mb-6">
              <p className="text-sm text-gray-500 mb-3">快速选择知识点：</p>
              <div className="flex flex-wrap gap-2">
                {PRESETS.map(p => (
                  <button
                    key={p.label}
                    onClick={() => generate(p.label)}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-full text-sm text-gray-700 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 transition-all shadow-sm"
                  >
                    <span>{p.icon}</span>
                    <span>{p.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Title bar (shown when content exists) */}
          {lastTitle && !loading && (
            <div className="mb-4 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <GitBranch className="w-5 h-5 text-brand-600" />
                <h2 className="text-lg font-semibold text-gray-800">{lastTitle}</h2>
              </div>
              <button
                onClick={() => generate()}
                disabled={loading}
                className="text-sm text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
              >
                重新生成
              </button>
            </div>
          )}

          {/* Mindmap viewer */}
          <div style={{ height: 600 }}>
            <MindmapViewer content={content} loading={loading} resourceId={resourceId} userId={authStore.userId} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default MindmapView
