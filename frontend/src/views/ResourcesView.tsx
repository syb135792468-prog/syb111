import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { listResources, generateResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import ResourceCard from '../components/resource/ResourceCard'
import ResourceDetail from '../components/resource/ResourceDetail'
import GenerateModal from '../components/resource/GenerateModal'
import QuizView from '../components/quiz/QuizView'
import { BookOpen, Plus } from 'lucide-react'

// --- 类型定义 ---
interface Resource {
  id: number | string
  title: string
  content: string
  resource_type: string
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

  // --- 状态 ---
  const [resources, setResources] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [typeFilter, setTypeFilter] = useState('')
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

  // --- 加载资源列表 ---
  const fetchResources = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listResources(authStore.userId, {
        resourceType: typeFilter || undefined,
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
  }, [authStore.userId, typeFilter])

  // --- 初始加载 ---
  useEffect(() => {
    fetchResources()
  }, [fetchResources])

  // --- 打开详情 ---
  const openDetail = useCallback((r: Resource) => {
    if (r.resource_type === 'quiz') {
      setQuizResourceId(String(r.id))
      setShowQuiz(true)
    } else {
      setDetailResource(r)
      setShowDetail(true)
    }
  }, [])

  // --- 生成资源 ---
  const handleGenerate = useCallback(async ({ topic, type, config = {} }: GeneratePayload) => {
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

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="学习资源">
        <select
          value={typeFilter}
          onChange={handleFilterChange}
          className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">全部类型</option>
          <option value="quiz">练习题</option>
          <option value="code">代码案例</option>
          <option value="mindmap">思维导图</option>
          <option value="doc">讲解文档</option>
          <option value="video">教学动画</option>
        </select>
        <button
          onClick={() => setShowGenerate(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          生成资源
        </button>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* Loading */}
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
          </div>
        ) : resources.length === 0 ? (
          /* Empty */
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <BookOpen className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-sm">暂无学习资源</p>
            <button
              onClick={() => setShowGenerate(true)}
              className="mt-3 text-sm text-brand-600 hover:text-brand-700"
            >
              生成第一个资源
            </button>
          </div>
        ) : (
          /* Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
            {resources.map(r => (
              <ResourceCard key={r.id} resource={r} onClick={() => openDetail(r)} />
            ))}
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
    </div>
  )
}

export default ResourcesView
