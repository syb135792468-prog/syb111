import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { generateResource, addToLibrary, getResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import MindmapViewer from '../components/mindmap/MindmapViewer'
import type { NodeObj } from 'mind-elixir'
import { Search, GitBranch, Bookmark } from 'lucide-react'

// --- 常量 ---
const STORAGE_KEY_PREFIX = 'mindmap_cache'

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
  saved?: boolean
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
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const mountedRef = useRef(true)
  const storageKey = useMemo(
    () => (authStore.userId ? `${STORAGE_KEY_PREFIX}_${authStore.userId}` : ''),
    [authStore.userId],
  )

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const resetViewState = useCallback(() => {
    setTopic('')
    setContent('')
    setLastTitle('')
    setResourceId(undefined)
    setSaved(false)
  }, [])

  const persistCache = useCallback((cache: CacheData) => {
    if (!storageKey) return
    localStorage.setItem(storageKey, JSON.stringify(cache))
  }, [storageKey])

  const clearCache = useCallback(() => {
    if (!storageKey) return
    localStorage.removeItem(storageKey)
  }, [storageKey])

  // --- 从 localStorage 恢复缓存 ---
  useEffect(() => {
    let cancelled = false

    async function restoreCache() {
      if (!authStore.userId || !storageKey) {
        resetViewState()
        return
      }

      try {
        const cached: CacheData | null = JSON.parse(localStorage.getItem(storageKey) || 'null')
        if (!cached?.content) {
          resetViewState()
          return
        }

        if (cancelled || !mountedRef.current) return
        setContent(cached.content)
        setLastTitle(cached.lastTitle || '')
        setTopic(cached.topic || '')
        setResourceId(cached.resourceId)
        setSaved(!!cached.saved)

        if (!cached.resourceId) return

        const resp = await getResource(cached.resourceId, authStore.userId)
        if (cancelled || !mountedRef.current) return

        if (resp.code !== 200 || !resp.data) {
          clearCache()
          resetViewState()
          return
        }

        const resource = resp.data as {
          id?: number
          title?: string
          content?: string
          in_library?: boolean
        }
        const nextCache: CacheData = {
          content: resource.content || cached.content,
          lastTitle: resource.title || cached.lastTitle || '',
          topic: cached.topic || '',
          resourceId: resource.id ?? cached.resourceId,
          saved: !!resource.in_library,
        }

        setContent(nextCache.content)
        setLastTitle(nextCache.lastTitle)
        setTopic(nextCache.topic)
        setResourceId(nextCache.resourceId)
        setSaved(!!nextCache.saved)
        persistCache(nextCache)
      } catch {
        if (!cancelled && mountedRef.current) {
          resetViewState()
        }
      }
    }

    restoreCache()
    return () => {
      cancelled = true
    }
  }, [authStore.userId, clearCache, persistCache, resetViewState, storageKey])

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
    setResourceId(undefined)
    setSaved(false)
    // 清除旧缓存
    try { clearCache() } catch { /* ignore */ }

    try {
      const resp = await generateResource(authStore.userId, target, 'mindmap')
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { content?: string; title?: string; id?: number; in_library?: boolean }
        const newContent = data.content || ''
        const newTitle = data.title || target
        const newResourceId = data.id
        const isSaved = !!data.in_library
        setContent(newContent)
        setLastTitle(newTitle)
        setResourceId(newResourceId)
        setSaved(isSaved)
        // 持久化到 localStorage
        try {
          persistCache({
            content: newContent,
            lastTitle: newTitle,
            topic: target,
            resourceId: newResourceId,
            saved: isSaved,
          })
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
  }, [topic, authStore.userId, appStore, clearCache, persistCache])

  // --- 键盘事件 ---
  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter') generate()
  }, [generate])

  // --- 节点点击 → 打开右侧面板 ---
  const handleNodeSelect = useCallback((nodeObj: NodeObj) => {
    const meta = (nodeObj.metadata as Record<string, unknown>) || {}
    const parentTopic = (meta.parentTopic as string) || ''
    const childTopics = (meta.childTopics as string[]) || []
    const ancestorTopics = (meta.ancestorTopics as string[]) || []
    useAppStore.getState().openRightPanel('mindmap-detail', {
      nodeId: String(nodeObj.id || ''),
      resourceId,
      topic: nodeObj.topic,
      definition: (meta.definition as string) || '',
      syntax: (meta.syntax as string) || '',
      examples: (meta.examples as string[]) || [],
      pitfalls: (meta.pitfalls as string[]) || [],
      advice: (meta.advice as string) || '',
      depth: (meta.depth as number) || 0,
      parentTopic,
      childTopics,
      ancestorTopics,
    })
  }, [resourceId])

  // --- 收藏/取消收藏 ---
  const handleBookmark = useCallback(async () => {
    if (saving || !resourceId || !authStore.userId) return
    setSaving(true)
    try {
      const resp = await addToLibrary(resourceId, authStore.userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library: boolean })?.in_library
        setSaved(newState)
        persistCache({
          content,
          lastTitle,
          topic,
          resourceId,
          saved: !!newState,
        })
        appStore.showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
      } else {
        appStore.showToast(resp.message || '操作失败', 'error')
      }
    } catch {
      appStore.showToast('操作失败，请重试', 'error')
    } finally {
      setSaving(false)
    }
  }, [saving, resourceId, authStore.userId, appStore, content, lastTitle, topic, persistCache])

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
              <div className="flex items-center gap-2">
                {resourceId && (
                  <button
                    onClick={handleBookmark}
                    disabled={saving}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors ${
                      saved
                        ? 'bg-green-50 text-green-600 border border-green-200 hover:bg-green-100'
                        : 'bg-amber-50 text-amber-600 border border-amber-200 hover:bg-amber-100'
                    } disabled:opacity-70`}
                    title={saved ? '取消收藏' : '收藏到资源库'}
                  >
                    <Bookmark className={`w-4 h-4 ${saved ? 'fill-current' : ''}`} />
                    {saved ? '已收藏' : '收藏'}
                  </button>
                )}
                <button
                  onClick={() => generate()}
                  disabled={loading}
                  className="text-sm text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
                >
                  重新生成
                </button>
              </div>
            </div>
          )}

          {/* Mindmap viewer */}
          <div style={{ height: 600 }}>
            <MindmapViewer content={content} loading={loading} resourceId={resourceId} userId={authStore.userId} onSelect={handleNodeSelect} />
          </div>
        </div>
      </div>
    </div>
  )
}

export default MindmapView
