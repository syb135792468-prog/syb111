import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useTaskStore } from '../stores/taskStore'
import { useLearningCenterStore } from '../stores/learningCenter'
import { listResources, generateResource, generateResourceAsync, deleteResource, addToLibrary } from '../api/resource'
import { pollTaskProgress } from '../composables/useSSE'
import AppHeader from '../components/layout/AppHeader'
import ResourceCard from '../components/resource/ResourceCard'
import ResourceDetail from '../components/resource/ResourceDetail'
import ConfirmDialog from '../components/common/ConfirmDialog'
import GenerateModal from '../components/resource/GenerateModal'
import QuizView from '../components/quiz/QuizView'
import ProgressBar from '../components/common/ProgressBar'
import { BookOpen, Plus } from 'lucide-react'

// --- 类型定义 ---
interface Resource {
  id: number | string
  title: string
  content: string
  resource_type: string
  knowledge_points?: string[]
  in_library?: boolean
  [key: string]: unknown
}

interface GeneratePayload {
  topic: string
  type: string
  config?: Record<string, unknown>
}

// --- 组件 ---
const ResourcesView: React.FC = () => {
  const authStore = useAuthStore()
  const appStore = useAppStore()
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)
  const [searchParams, setSearchParams] = useSearchParams()

  // --- 状态 ---
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')
  const [libraryFilter, setLibraryFilter] = useState<'all' | 'library'>('all')
  const [savedIds, setSavedIds] = useState<Set<number | string>>(new Set())
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])
  const [showGenerate, setShowGenerate] = useState(false)
  const [showDetail, setShowDetail] = useState(false)
  const [detailResource, setDetailResource] = useState<Resource | null>(null)
  const [showQuiz, setShowQuiz] = useState(false)
  const [quizResourceId, setQuizResourceId] = useState('')
  const [quizGenTaskId, setQuizGenTaskId] = useState<string | null>(null)

  // --- 删除状态 ---
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [deletingId, setDeletingId] = useState<number | string | null>(null)
  const [deleting, setDeleting] = useState(false)

  // --- 加载资源列表 ---
  const fetchResources = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listResources(authStore.userId, {
        resourceType: typeFilter || undefined,
        inLibrary: libraryFilter === 'library' ? true : undefined,
      })
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { resources: Resource[] }
        setResources(data.resources || [])
      }
    } catch (e) {
      if (!mountedRef.current) return
      console.error('Failed to load resources:', e)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [authStore.userId, typeFilter, libraryFilter])

  // --- 初始加载 ---
  useEffect(() => {
    fetchResources()
  }, [fetchResources])

  // --- URL ?quiz=<id> 自动打开测验弹窗（来自图谱"开始练习"跳转） ---
  useEffect(() => {
    const quizId = searchParams.get('quiz')
    if (quizId) {
      setQuizResourceId(String(quizId))
      setShowQuiz(true)
      // 消费后清掉 query 参数，避免刷新或返回时重复打开
      const next = new URLSearchParams(searchParams)
      next.delete('quiz')
      setSearchParams(next, { replace: true })
    }
  }, [searchParams, setSearchParams])

  // --- 打开详情 ---
  const openDetail = useCallback((r: Resource) => {
    const knowledgePoints = Array.isArray(r.knowledge_points)
      ? r.knowledge_points.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
      : []
    const resourceId = typeof r.id === 'number'
      ? r.id
      : Number.isNaN(Number(r.id))
        ? undefined
        : Number(r.id)

    recordLearningEvent({
      userId: authStore.userId,
      sourcePage: 'resources',
      actionType: 'resource_viewed',
      topic: r.title,
      knowledgePoint: knowledgePoints[0] || undefined,
      knowledgePoints,
      resourceId,
    })

    if (r.resource_type === 'quiz') {
      setQuizResourceId(String(r.id))
      setShowQuiz(true)
    } else if (r.resource_type === 'video' || r.resource_type === 'slides') {
      // video/slides 需要完整渲染，打开全屏弹窗
      setDetailResource(r)
      setShowDetail(true)
    } else {
      // 打开右侧面板
      appStore.openRightPanel('resource-summary', { resource: r })
    }
  }, [appStore, authStore.userId, recordLearningEvent])

  // --- 生成资源 ---
  const handleGenerate = useCallback(async ({ topic, type, config = {} }: GeneratePayload) => {
    // 多题测验走异步进度路径，其他类型走同步
    const questionCount = (config.questionCount as number) || 1
    const useAsync = type === 'quiz' && questionCount > 1

    if (useAsync) {
      try {
        const resp = await generateResourceAsync(authStore.userId, topic, type, config)
        if (resp.code === 200 && resp.data?.task_id) {
          const taskId = resp.data.task_id
          setQuizGenTaskId(taskId)
          setShowGenerate(false)
          useTaskStore.getState().addTask({
            taskId,
            resourceType: type,
            topic,
            status: 'pending',
            createdAt: Date.now(),
            progress: 0,
          })
          pollTaskProgress(
            taskId,
            () => {
              if (!mountedRef.current) return
              setQuizGenTaskId(null)
              appStore.showToast('资源生成成功', 'success')
              fetchResources()
              setTimeout(() => useTaskStore.getState().removeTask(taskId), 2000)
            },
            (error) => {
              if (!mountedRef.current) return
              setQuizGenTaskId(null)
              appStore.showToast('生成失败：' + error, 'error')
              setTimeout(() => useTaskStore.getState().removeTask(taskId), 2000)
            },
          )
        } else {
          appStore.showToast(resp.message || '生成失败', 'error')
        }
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : '网络错误'
        appStore.showToast('生成失败：' + msg, 'error')
      }
      return
    }

    // 同步路径（原有逻辑）
    try {
      const resp = await generateResource(authStore.userId, topic, type, config)
      if (resp.code === 200) {
        appStore.showToast('资源生成成功', 'success')
        setShowGenerate(false)
        fetchResources()
      } else {
        appStore.showToast(resp.message || '生成失败', 'error')
        setShowGenerate(false)
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('生成失败：' + msg, 'error')
      setShowGenerate(false)
    }
  }, [authStore.userId, appStore, fetchResources])

  // --- 筛选变化 ---
  const handleFilterChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
    setTypeFilter(e.target.value)
  }, [])

  // --- 收藏/取消收藏 ---
  const handleSave = useCallback(async (r: Resource) => {
    try {
      const resp = await addToLibrary(r.id, authStore.userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library: boolean })?.in_library
        if (newState) {
          setSavedIds(prev => new Set(prev).add(r.id))
        } else {
          setSavedIds(prev => { const s = new Set(prev); s.delete(r.id); return s })
        }
        appStore.showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
        // 更新列表中该资源的 in_library 状态
        setResources(prev => prev.map(item => item.id === r.id ? { ...item, in_library: newState } : item))
      } else {
        appStore.showToast(resp.message || '操作失败', 'error')
      }
    } catch {
      appStore.showToast('操作失败，请重试', 'error')
    }
  }, [authStore.userId, appStore])

  // --- 删除资源 ---
  const askDelete = useCallback((r: Resource) => {
    setDeletingId(r.id)
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
        setResources(prev => prev.filter(r => r.id !== deletingId))
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
      <AppHeader title="学习资源">
        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-2xl border border-slate-300/80 bg-white/84 p-1 shadow-[inset_0_1px_0_rgba(255,255,255,0.84),0_10px_22px_rgba(148,163,184,0.08)]">
            <button
              onClick={() => setLibraryFilter('all')}
              className={`px-3 py-1.5 text-xs rounded-xl transition-all ${libraryFilter === 'all' ? 'bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(232,240,252,0.92))] text-brand-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.88),0_8px_16px_rgba(148,163,184,0.08)]' : 'text-slate-500 hover:text-slate-700'}`}
            >
              全部
            </button>
            <button
              onClick={() => setLibraryFilter('library')}
              className={`px-3 py-1.5 text-xs rounded-xl transition-all ${libraryFilter === 'library' ? 'bg-[linear-gradient(135deg,rgba(255,255,255,0.96),rgba(232,240,252,0.92))] text-brand-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.88),0_8px_16px_rgba(148,163,184,0.08)]' : 'text-slate-500 hover:text-slate-700'}`}
            >
              已收藏
            </button>
          </div>
          <select
            value={typeFilter}
            onChange={handleFilterChange}
            className="text-sm border border-slate-300/80 bg-white/84 rounded-xl px-3 py-2 text-slate-600 shadow-[inset_0_1px_0_rgba(255,255,255,0.84),0_10px_22px_rgba(148,163,184,0.08)] focus:outline-none focus:ring-2 focus:ring-slate-200"
          >
            <option value="">全部类型</option>
            <option value="quiz">练习题</option>
            <option value="code">代码案例</option>
            <option value="mindmap">思维导图</option>
            <option value="doc">讲解文档</option>
            <option value="video">教学动画</option>
            <option value="slides">幻灯片</option>
          </select>
        </div>
        <button
          onClick={() => setShowGenerate(true)}
          className="btn-primary"
        >
          <Plus className="w-4 h-4" />
          生成资源
        </button>
      </AppHeader>

      <div className="page-scroll-area">
        {quizGenTaskId && (
          <QuizGenProgress taskId={quizGenTaskId} />
        )}
        {/* Loading */}
        {loading ? (
          <div className="page-content flex items-center justify-center h-64">
            <div className="page-panel-soft flex items-center gap-3 px-5 py-4">
              <div className="animate-spin rounded-full h-7 w-7 border-b-2 border-brand-600" />
              <span className="text-sm text-slate-500">正在整理学习资源...</span>
            </div>
          </div>
        ) : resources.length === 0 ? (
          /* Empty */
          <div className="page-content">
            <div className="page-panel flex flex-col items-center justify-center h-72 text-slate-400">
              <BookOpen className="w-12 h-12 mb-3 opacity-40" />
              <p className="text-sm font-medium text-slate-600">暂无学习资源</p>
              <p className="mt-1 text-xs text-slate-400">先生成一份文档、练习题或动画资源</p>
            <button
              onClick={() => setShowGenerate(true)}
                className="mt-4 text-sm text-brand-600 hover:text-brand-700"
            >
              生成第一个资源
            </button>
            </div>
          </div>
        ) : (
          /* Grid */
          <div className="page-content">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 max-w-6xl mx-auto">
            {resources.map(r => (
              <ResourceCard
                key={r.id}
                resource={r}
                onClick={() => openDetail(r)}
                onDelete={() => askDelete(r)}
                onSave={() => handleSave(r)}
                saved={savedIds.has(r.id) || r.in_library}
              />
            ))}
            </div>
          </div>
        )}
      </div>

      {/* Modals */}
      <GenerateModal
        show={showGenerate}
        onClose={() => setShowGenerate(false)}
        onGenerate={handleGenerate}
      />
      {detailResource && (
        <ResourceDetail
          show={showDetail}
          title={detailResource.title}
          content={detailResource.content}
          type={detailResource.resource_type}
          resourceId={String(detailResource.id || '')}
          extraMetadata={detailResource.extra_metadata as Record<string, unknown> | null}
          onClose={() => setShowDetail(false)}
        />
      )}
      {showQuiz && (
        <QuizView
          show={showQuiz}
          resourceId={quizResourceId}
          onClose={() => setShowQuiz(false)}
        />
      )}

      <ConfirmDialog
        show={showDeleteConfirm}
        title="删除学习资源"
        message="确定要删除这个资源吗？此操作不可撤销。"
        confirmText="确认删除"
        dangerLevel="warning"
        isLoading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setShowDeleteConfirm(false)}
      />
    </div>
  )
}

export default ResourcesView

const QuizGenProgress: React.FC<{ taskId: string }> = ({ taskId }) => {
  const task = useTaskStore((state) => state.tasks.find((t) => t.taskId === taskId))
  if (!task) return null
  return (
    <div className="page-content">
      <div className="page-panel-soft" style={{ padding: '14px 18px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-brand-600" />
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink, #1e293b)' }}>
            正在生成练习题：{task.topic}
          </span>
        </div>
        <ProgressBar
          percent={task.progress || 0}
          stage={task.stage}
          message={task.message}
        />
      </div>
    </div>
  )
}
