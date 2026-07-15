import React, { useState, useEffect, useCallback, useRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { generateResource, addToLibrary } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import SlidesViewer from '../components/slides/SlidesViewer'
import { SLIDE_STYLES, type SlideStyle } from '../components/slides/slideStyles'
import { Presentation, Bookmark } from 'lucide-react'

// --- 常量 ---
const STORAGE_KEY = 'slides_cache'

const PRESETS = [
  { label: '变量与数据类型', icon: '📦' },
  { label: '控制流', icon: '🔀' },
  { label: '函数', icon: '⚡' },
  { label: '面向对象', icon: '🏗️' },
  { label: '文件操作', icon: '📁' },
  { label: '异常处理', icon: '🛡️' },
  { label: '列表推导式', icon: '📋' },
  { label: '装饰器', icon: '🎨' },
]

interface CacheData {
  content: string
  lastTitle: string
  topic: string
  resourceId?: number
  style?: SlideStyle
}

// --- 组件 ---
const SlidesView: React.FC = () => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  const [topic, setTopic] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastTitle, setLastTitle] = useState('')
  const [resourceId, setResourceId] = useState<number | undefined>()
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showFullscreen, setShowFullscreen] = useState(false)
  const [slideStyle, setSlideStyle] = useState<SlideStyle>('python-blue')
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // 从 localStorage 恢复缓存
  useEffect(() => {
    try {
      const cached: CacheData | null = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
      if (cached && cached.content) {
        setContent(cached.content)
        setLastTitle(cached.lastTitle || '')
        setTopic(cached.topic || '')
        setResourceId(cached.resourceId)
        if (cached.style) setSlideStyle(cached.style)
      }
    } catch {
      // ignore
    }
  }, [])

  // 生成幻灯片
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
    setSaved(false)
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }

    try {
      const resp = await generateResource(authStore.userId, target, 'slides')
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { content?: string; title?: string; id?: number }
        const newContent = data.content || ''
        const newTitle = data.title || target
        const newResourceId = data.id
        setContent(newContent)
        setLastTitle(newTitle)
        setResourceId(newResourceId)
        try {
          localStorage.setItem(STORAGE_KEY, JSON.stringify({
            content: newContent,
            lastTitle: newTitle,
            topic: target,
            resourceId: newResourceId,
            style: slideStyle,
          }))
        } catch { /* ignore */ }
        appStore.showToast('幻灯片生成成功', 'success')
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
  }, [topic, authStore.userId, appStore, slideStyle])

  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if (e.nativeEvent.isComposing) return
    if (e.key === 'Enter') generate()
  }, [generate])

  // 切换风格时同步缓存
  const handleStyleChange = useCallback((s: SlideStyle) => {
    setSlideStyle(s)
    try {
      const cached: CacheData | null = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
      if (cached) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...cached, style: s }))
      }
    } catch { /* ignore */ }
  }, [])

  // 收藏
  const handleBookmark = useCallback(async () => {
    if (!resourceId || !authStore.userId || saving) return
    setSaving(true)
    try {
      const resp = await addToLibrary(resourceId, authStore.userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library?: boolean })?.in_library
        setSaved(!!newState)
        appStore.showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
      }
    } catch {
      appStore.showToast('操作失败', 'error')
    } finally {
      setSaving(false)
    }
  }, [resourceId, authStore.userId, saving, appStore])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', background: '#f8fafc' }}>
      <AppHeader title="演示幻灯片" />

      <div style={{ flex: 1, padding: '20px 24px', overflow: 'auto' }}>
        {/* 输入区域 */}
        <div style={{
          background: '#fff', borderRadius: 16, padding: '20px 24px', marginBottom: 20,
          border: '1px solid rgba(203,213,225,0.8)',
          boxShadow: '0 2px 12px rgba(148,163,184,0.08)',
        }}>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <input
              value={topic}
              onChange={e => setTopic(e.target.value)}
              onKeyDown={handleKeydown}
              placeholder="输入知识点主题，如：Python函数"
              style={{
                flex: 1, padding: '10px 16px', borderRadius: 10, fontSize: 14,
                border: '1px solid #e2e8f0', outline: 'none',
                background: '#f8fafc', color: '#0f172a',
              }}
            />
            <button
              onClick={() => generate()}
              disabled={loading || !topic.trim()}
              style={{
                padding: '10px 24px', borderRadius: 10, fontSize: 14, fontWeight: 600,
                background: loading ? '#94a3b8' : 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
                color: '#fff', border: 'none', cursor: loading ? 'not-allowed' : 'pointer',
                boxShadow: '0 4px 12px rgba(37,99,235,0.25)',
                display: 'flex', alignItems: 'center', gap: 8,
              }}
            >
              {loading ? (
                <>
                  <div style={{
                    width: 16, height: 16, border: '2px solid rgba(255,255,255,0.3)',
                    borderTopColor: '#fff', borderRadius: '50%',
                    animation: 'spin 0.8s linear infinite',
                  }} />
                  生成中...
                </>
              ) : '生成幻灯片'}
            </button>
            {content && (
              <button
                onClick={handleBookmark}
                disabled={saving}
                title={saved ? '取消收藏' : '收藏到资源库'}
                style={{
                  padding: '10px 14px', borderRadius: 10,
                  background: saved ? 'rgba(37,99,235,0.1)' : '#f1f5f9',
                  border: saved ? '1px solid rgba(37,99,235,0.3)' : '1px solid #e2e8f0',
                  cursor: 'pointer', display: 'flex', alignItems: 'center',
                }}
              >
                <Bookmark size={18} color={saved ? '#2563eb' : '#94a3b8'} fill={saved ? '#2563eb' : 'none'} />
              </button>
            )}
          </div>

          {/* 预设按钮 */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {PRESETS.map(p => (
              <button
                key={p.label}
                onClick={() => generate(p.label)}
                disabled={loading}
                style={{
                  padding: '6px 14px', borderRadius: 20, fontSize: 13,
                  background: topic === p.label ? 'rgba(37,99,235,0.1)' : '#f1f5f9',
                  border: topic === p.label ? '1px solid rgba(37,99,235,0.3)' : '1px solid #e2e8f0',
                  color: topic === p.label ? '#2563eb' : '#475569',
                  cursor: loading ? 'not-allowed' : 'pointer',
                  fontWeight: topic === p.label ? 600 : 400,
                  transition: 'all 0.15s ease',
                }}
              >
                {p.icon} {p.label}
              </button>
            ))}
          </div>
        </div>

        {/* 幻灯片预览 */}
        {content && (
          <div style={{
            background: '#fff', borderRadius: 16, padding: 20,
            border: '1px solid rgba(203,213,225,0.8)',
            boxShadow: '0 2px 12px rgba(148,163,184,0.08)',
          }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 16, gap: 16, flexWrap: 'wrap',
            }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: '#0f172a' }}>
                {lastTitle || topic}
              </h3>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                {/* 风格选择器 */}
                <div style={{ display: 'flex', gap: 4, background: '#f1f5f9', padding: 3, borderRadius: 8 }}>
                  {SLIDE_STYLES.map(s => (
                    <button
                      key={s.value}
                      onClick={() => handleStyleChange(s.value)}
                      title={s.desc}
                      style={{
                        padding: '5px 12px', borderRadius: 6, fontSize: 12, fontWeight: 500,
                        background: slideStyle === s.value ? '#fff' : 'transparent',
                        color: slideStyle === s.value ? '#2563eb' : '#64748b',
                        border: 'none', cursor: 'pointer',
                        boxShadow: slideStyle === s.value ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => setShowFullscreen(true)}
                  style={{
                    padding: '6px 16px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                    background: 'rgba(37,99,235,0.1)', color: '#2563eb',
                    border: '1px solid rgba(37,99,235,0.3)', cursor: 'pointer',
                  }}
                >
                  全屏播放
                </button>
              </div>
            </div>
            <SlidesViewer content={content} style={slideStyle} />
          </div>
        )}

        {/* 空状态 */}
        {!content && !loading && (
          <div style={{
            textAlign: 'center', padding: '60px 20px', color: '#94a3b8',
          }}>
            <Presentation size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
            <p style={{ fontSize: 15, margin: 0 }}>输入知识点主题，生成交互式教学幻灯片</p>
            <p style={{ fontSize: 13, margin: '8px 0 0' }}>支持键盘左右翻页、代码高亮、全屏播放</p>
          </div>
        )}
      </div>

      {/* 全屏播放模态 */}
      {showFullscreen && content && (
        <div style={{
          position: 'fixed', inset: 0, zIndex: 1000, background: '#fff',
          display: 'flex', flexDirection: 'column',
        }}>
          <SlidesViewer
            content={content}
            fullscreen
            style={slideStyle}
            onClose={() => setShowFullscreen(false)}
          />
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  )
}

export default SlidesView
