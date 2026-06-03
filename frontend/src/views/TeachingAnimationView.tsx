import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { generateResource, listResources, deleteResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import ConfirmDialog from '../components/common/ConfirmDialog'
import {
  PlayCircle, Plus, Trash2, Eye, Download, Loader2,
  Film, Clock
} from 'lucide-react'

// --- 类型定义 ---
interface AnimationItem {
  id: number
  title: string
  content: string
  status: string
  resource_type: string
  extra_metadata?: {
    duration?: number
    [key: string]: unknown
  }
  created_at?: string
}

interface DurationOption {
  value: number
  label: string
}

interface StyleOption {
  value: string
  label: string
}

// --- 常量 ---
const PAGE_SIZE = 12

const DURATION_OPTIONS: DurationOption[] = [
  { value: 30, label: '30 秒' },
  { value: 60, label: '1 分钟' },
  { value: 120, label: '2 分钟' },
  { value: 180, label: '3 分钟' },
]

const STYLE_OPTIONS: StyleOption[] = [
  { value: 'tutorial', label: '教程风格' },
  { value: 'code_demo', label: '代码演示' },
  { value: 'visualization', label: '可视化' },
  { value: 'story', label: '故事化' },
]

// --- 工具函数 ---
function formatTime(dateStr?: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// --- 组件 ---
const TeachingAnimationView: React.FC = () => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // --- 表单状态 ---
  const [formTopic, setFormTopic] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formDuration, setFormDuration] = useState(60)
  const [formStyle, setFormStyle] = useState('tutorial')
  const [generating, setGenerating] = useState(false)

  // --- 列表状态 ---
  const [animations, setAnimations] = useState<AnimationItem[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)

  // --- 删除确认状态 ---
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deletingId, setDeletingId] = useState<number | null>(null)
  const [deleting, setDeleting] = useState(false)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // --- 派生状态 ---
  const isLoggedIn = useMemo(() => !!authStore.userId, [authStore.userId])
  const hasMore = useMemo(() => animations.length < total, [animations.length, total])

  // --- 加载列表 ---
  const fetchAnimations = useCallback(async (reset: boolean = false) => {
    if (!authStore.userId) return

    if (reset) {
      setAnimations([])
      setOffset(0)
    }

    if (reset) setListLoading(true)
    else setLoadingMore(true)

    try {
      // Use functional update to get current offset without stale closure
      let currentOffset = 0
      if (!reset) {
        setOffset(prev => { currentOffset = prev; return prev })
      }

      const resp = await listResources(authStore.userId, {
        resourceType: 'video',
        limit: PAGE_SIZE,
        offset: currentOffset,
      })

      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { resources?: AnimationItem[]; total?: number }
        const items: AnimationItem[] = data.resources || []
        if (reset) {
          setAnimations(items)
        } else {
          setAnimations(prev => [...prev, ...items])
        }
        setTotal(data.total || 0)
        setOffset(currentOffset + items.length)
      }
    } catch {
      if (!mountedRef.current) return
      appStore.showToast('加载列表失败', 'error')
    } finally {
      if (mountedRef.current) {
        setListLoading(false)
        setLoadingMore(false)
      }
    }
  }, [authStore.userId, appStore])

  // --- 初始加载 ---
  useEffect(() => {
    if (isLoggedIn) fetchAnimations(true)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // --- 生成动画 ---
  const handleGenerate = useCallback(async () => {
    if (!formTopic.trim() || generating) return
    setGenerating(true)

    try {
      const config: Record<string, unknown> = {
        duration: formDuration,
        style: formStyle,
      }
      if (formContent.trim()) {
        config.customPrompt = formContent.trim()
      }

      const resp = await generateResource(
        authStore.userId,
        formTopic.trim(),
        'video',
        config
      )

      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        appStore.showToast('教学动画生成成功', 'success')
        setFormTopic('')
        setFormContent('')
        setAnimations(prev => [resp.data as AnimationItem, ...prev])
        setTotal(prev => prev + 1)
      } else {
        appStore.showToast(resp.message || '生成失败', 'error')
      }
    } catch (e: unknown) {
      if (!mountedRef.current) return
      const msg = e instanceof Error ? e.message : '网络错误，请稍后重试'
      appStore.showToast('生成失败：' + msg, 'error')
    } finally {
      if (mountedRef.current) setGenerating(false)
    }
  }, [formTopic, formContent, formDuration, formStyle, generating, authStore.userId, appStore])

  // --- 加载更多 ---
  const loadMore = useCallback(() => {
    if (loadingMore || !hasMore) return
    fetchAnimations(false)
  }, [loadingMore, hasMore, fetchAnimations])

  // --- 预览：新标签页打开 ---
  const openPreview = useCallback((item: AnimationItem) => {
    const html = item.content || ''
    const title = item.title || '教学动画'
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const win = window.open(url, '_blank')
    if (win) {
      win.document.title = title
      // 页面加载完成后释放 Blob URL
      win.addEventListener('load', () => URL.revokeObjectURL(url))
    } else {
      URL.revokeObjectURL(url)
    }
  }, [])

  // --- 下载 ---
  const handleDownload = useCallback((item: { title?: string; content?: string }) => {
    const html = item.content || ''
    const title = (item.title || '教学动画').replace(/[\\/:*?"<>|]/g, '_')
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${title}.html`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    appStore.showToast('下载成功', 'success')
  }, [appStore])

  // --- 删除 ---
  const askDelete = useCallback((item: AnimationItem) => {
    setDeletingId(item.id)
    setShowDeleteConfirm(true)
  }, [])

  const confirmDelete = useCallback(async () => {
    if (deleting || deletingId === null) return
    setDeleting(true)

    try {
      const resp = await deleteResource(deletingId, authStore.userId)
      if (!mountedRef.current) return
      if (resp.code === 200) {
        appStore.showToast('已删除', 'success')
        setAnimations(prev => prev.filter(a => a.id !== deletingId))
        setTotal(prev => Math.max(0, prev - 1))
      } else {
        appStore.showToast(resp.message || '删除失败', 'error')
      }
    } catch (e: unknown) {
      if (!mountedRef.current) return
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('删除失败：' + msg, 'error')
    } finally {
      if (mountedRef.current) {
        setDeleting(false)
        setShowDeleteConfirm(false)
        setDeletingId(null)
      }
    }
  }, [deleting, deletingId, authStore.userId, appStore])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="教学动画">
        <span className="text-xs text-gray-400">共 {total} 个动画</span>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* 未登录提示 */}
        {!isLoggedIn ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <PlayCircle className="w-10 h-10 mb-3 text-gray-300" />
            <p className="text-sm">请先登录后使用教学动画功能</p>
          </div>
        ) : (
          <div className="max-w-6xl mx-auto">
            {/* 桌面端：左侧表单 + 右侧列表 */}
            <div className="flex flex-col lg:flex-row gap-6">

              {/* 左侧：生成表单 */}
              <div className="w-full lg:w-80 flex-shrink-0">
                <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm sticky top-0">
                  <div className="flex items-center gap-2 mb-4">
                    <Plus className="w-4 h-4 text-brand-600" />
                    <h3 className="text-sm font-semibold text-gray-700">生成教学动画</h3>
                  </div>

                  {/* 知识点主题 */}
                  <div className="mb-3">
                    <label className="text-xs text-gray-500 mb-1 block">
                      知识点主题 <span className="text-red-400">*</span>
                    </label>
                    <input
                      type="text"
                      value={formTopic}
                      onChange={e => setFormTopic(e.target.value)}
                      placeholder="例如：Python列表推导式"
                      disabled={generating}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    />
                  </div>

                  {/* 详细要求 */}
                  <div className="mb-3">
                    <label className="text-xs text-gray-500 mb-1 block">详细要求（可选）</label>
                    <textarea
                      value={formContent}
                      onChange={e => setFormContent(e.target.value)}
                      rows={3}
                      placeholder="对动画的特殊要求..."
                      disabled={generating}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    />
                  </div>

                  {/* 时长选择 */}
                  <div className="mb-3">
                    <label className="text-xs text-gray-500 mb-1 block">动画时长</label>
                    <select
                      value={formDuration}
                      onChange={e => setFormDuration(Number(e.target.value))}
                      disabled={generating}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    >
                      {DURATION_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* 风格选择 */}
                  <div className="mb-4">
                    <label className="text-xs text-gray-500 mb-1 block">动画风格</label>
                    <select
                      value={formStyle}
                      onChange={e => setFormStyle(e.target.value)}
                      disabled={generating}
                      className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-brand-500 disabled:opacity-50"
                    >
                      {STYLE_OPTIONS.map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                    </select>
                  </div>

                  {/* 生成按钮 */}
                  <button
                    onClick={handleGenerate}
                    disabled={!formTopic.trim() || generating}
                    className={`w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium rounded-lg transition-all ${
                      generating
                        ? 'bg-amber-500 text-white cursor-not-allowed'
                        : 'bg-brand-600 text-white hover:bg-brand-700 disabled:opacity-40 disabled:cursor-not-allowed'
                    }`}
                  >
                    {generating ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      <Film className="w-4 h-4" />
                    )}
                    {generating ? 'AI 正在生成中...' : '生成动画'}
                  </button>
                </div>
              </div>

              {/* 右侧：动画列表 */}
              <div className="flex-1 min-w-0">
                {/* 加载中 */}
                {listLoading ? (
                  <div className="flex items-center justify-center h-64">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
                  </div>
                ) : animations.length === 0 ? (
                  /* 空状态 */
                  <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                    <PlayCircle className="w-12 h-12 mb-3 opacity-40" />
                    <p className="text-sm">暂无教学动画</p>
                    <p className="text-xs text-gray-300 mt-1">在左侧填写知识点主题后生成</p>
                  </div>
                ) : (
                  <>
                    {/* 动画卡片列表 */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {animations.map(item => (
                        <div
                          key={item.id}
                          className="bg-white rounded-xl border border-gray-100 overflow-hidden shadow-sm hover:shadow-md transition-shadow"
                        >
                          {/* 卡片头部 */}
                          <div className="h-14 bg-gradient-to-r from-red-500 to-red-600 flex items-center justify-center">
                            <PlayCircle className="w-7 h-7 text-white/90" />
                          </div>

                          {/* 卡片内容 */}
                          <div className="p-4">
                            <h4 className="text-sm font-medium text-gray-800 line-clamp-2">{item.title}</h4>
                            <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                              <span className="flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                {formatTime(item.created_at)}
                              </span>
                              {item.extra_metadata?.duration && (
                                <span>{item.extra_metadata.duration}秒</span>
                              )}
                            </div>

                            {/* 操作按钮 */}
                            <div className="flex items-center gap-2 mt-3 pt-3 border-t border-gray-50">
                              <button
                                onClick={e => { e.stopPropagation(); openPreview(item) }}
                                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-brand-700 bg-brand-50 rounded-md hover:bg-brand-100 transition-colors"
                              >
                                <Eye className="w-3 h-3" />
                                预览
                              </button>
                              <button
                                onClick={e => { e.stopPropagation(); handleDownload(item) }}
                                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-gray-600 bg-gray-50 rounded-md hover:bg-gray-100 transition-colors"
                              >
                                <Download className="w-3 h-3" />
                                下载
                              </button>
                              <button
                                onClick={e => { e.stopPropagation(); askDelete(item) }}
                                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-red-600 bg-red-50 rounded-md hover:bg-red-100 transition-colors ml-auto"
                              >
                                <Trash2 className="w-3 h-3" />
                                删除
                              </button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>

                    {/* 加载更多 */}
                    {hasMore && (
                      <div className="flex justify-center mt-6">
                        <button
                          onClick={loadMore}
                          disabled={loadingMore}
                          className="flex items-center gap-1.5 px-5 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
                        >
                          {loadingMore && <Loader2 className="w-4 h-4 animate-spin" />}
                          {loadingMore ? '加载中...' : '加载更多'}
                        </button>
                      </div>
                    )}

                    {/* 列表底部分页信息 */}
                    <div className="text-center mt-4 text-xs text-gray-300">
                      {animations.length} / {total}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 删除确认弹窗 */}
      <ConfirmDialog
        show={showDeleteConfirm}
        title="删除教学动画"
        message="确定要删除这个教学动画吗？此操作不可撤销。"
        confirmText="确认删除"
        dangerLevel="warning"
        isLoading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  )
}

export default TeachingAnimationView
