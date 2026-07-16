import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useLearningCenterStore } from '../stores/learningCenter'
import { useTaskStore } from '../stores/taskStore'
import { listErrorBook, listDueReviews, recordReview, markMastered, deleteErrorBook, generateTutorVideo } from '../api/errorBook'
import { pollTaskProgress } from '../composables/useSSE'
import AppHeader from '../components/layout/AppHeader'
import {
  BookOpen, CheckCircle2, XCircle, Trash2,
  Trophy, Clock, Brain, RotateCcw, Sparkles, Calendar, Video, Loader2
} from 'lucide-react'

// --- 类型定义 ---
interface ErrorBookItem {
  id: number | string
  question_type: string
  question_text: string
  difficulty: string
  knowledge_point: string
  mastered: boolean
  error_count: number
  last_wrong_at: string
  user_answer: string
  correct_answer: string
  explanation: string
  next_review_at: string | null
  review_interval_days: number
  easiness_factor: number
  repetition_count: number
}

// --- 常量 ---
const KP_OPTIONS = [
  '变量与数据类型', '运算符与表达式', '条件判断（if/elif/else）',
  '循环（for/while）', '函数定义与调用', '函数参数与返回值',
  '列表与元组', '字典与集合', '字符串操作',
  '面向对象基础', '类与对象', '继承与多态',
  '异常处理', '文件操作', '模块与包',
]

const DIFFICULTY_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'bg-green-100 text-green-700',
  medium: 'bg-amber-100 text-amber-700',
  hard: 'bg-red-100 text-red-700',
}
const TYPE_LABELS: Record<string, string> = { choice: '选择题', fill: '填空题', code: '编程题' }

const QUALITY_OPTIONS = [
  { value: 1, label: '完全忘记', color: 'bg-red-100 text-red-700 border-red-200', icon: XCircle },
  { value: 2, label: '很模糊', color: 'bg-orange-100 text-orange-700 border-orange-200', icon: RotateCcw },
  { value: 3, label: '想了一会', color: 'bg-amber-100 text-amber-700 border-amber-200', icon: Clock },
  { value: 4, label: '基本记得', color: 'bg-blue-100 text-blue-700 border-blue-200', icon: Brain },
  { value: 5, label: '完全记得', color: 'bg-green-100 text-green-700 border-green-200', icon: Sparkles },
]

function formatReviewDate(iso: string | null): string {
  if (!iso) return '待安排'
  const d = new Date(iso)
  const now = new Date()
  const diffMs = d.getTime() - now.getTime()
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24))
  if (diffDays <= 0) return '今天'
  if (diffDays === 1) return '明天'
  if (diffDays <= 7) return `${diffDays}天后`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function getReviewStatus(item: ErrorBookItem): 'overdue' | 'due' | 'upcoming' | 'mastered' {
  if (item.mastered) return 'mastered'
  if (!item.next_review_at) return 'due'
  const d = new Date(item.next_review_at)
  const now = new Date()
  if (d <= now) return 'due'
  const diffDays = (d.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
  if (diffDays <= 1) return 'overdue'
  return 'upcoming'
}

// --- 组件 ---
const ErrorBookView: React.FC = () => {
  const navigate = useNavigate()
  const authStore = useAuthStore()
  const appStore = useAppStore()
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)

  // --- 状态 ---
  const [items, setItems] = useState<ErrorBookItem[]>([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const mountedRef = useRef(true)

  // 模式切换：list=错题列表, review=复习模式
  const [mode, setMode] = useState<'list' | 'review'>('list')

  // 辅导视频生成中的错题 id 集合
  const [tutorGeneratingIds, setTutorGeneratingIds] = useState<Set<string | number>>(new Set())

  // 复习模式状态
  const [dueItems, setDueItems] = useState<ErrorBookItem[]>([])
  const [dueCount, setDueCount] = useState(0)
  const [reviewIndex, setReviewIndex] = useState(0)
  const [showAnswer, setShowAnswer] = useState(false)
  const [reviewLoading, setReviewLoading] = useState(false)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // 筛选
  const [filterKP, setFilterKP] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterMastered, setFilterMastered] = useState('')

  // --- 派生状态 ---
  const unmasteredCount = useMemo(() => items.filter(i => !i.mastered).length, [items])

  const currentReviewItem = dueItems[reviewIndex] || null

  // --- 加载数据 ---
  const fetchItems = useCallback(async () => {
    setLoading(true)
    try {
      const params: Record<string, unknown> = {}
      if (filterKP) params.knowledge_point = filterKP
      if (filterDifficulty) params.difficulty = filterDifficulty
      if (filterMastered !== '') params.mastered = filterMastered === 'true'
      const resp = await listErrorBook(authStore.userId, params)
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { items: ErrorBookItem[]; total: number }
        setItems(data.items || [])
        setTotal(data.total || 0)
      }
    } catch (e) {
      if (!mountedRef.current) return
      console.error('Failed to load error book:', e)
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [authStore.userId, filterKP, filterDifficulty, filterMastered])

  const fetchDueItems = useCallback(async () => {
    setReviewLoading(true)
    try {
      const resp = await listDueReviews(authStore.userId)
      if (!mountedRef.current) return
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { items: ErrorBookItem[]; due_count: number }
        setDueItems(data.items || [])
        setDueCount(data.due_count || 0)
        setReviewIndex(0)
        setShowAnswer(false)
      }
    } catch (e) {
      if (!mountedRef.current) return
      console.error('Failed to load due reviews:', e)
    } finally {
      if (mountedRef.current) setReviewLoading(false)
    }
  }, [authStore.userId])

  // --- 初始加载 ---
  useEffect(() => {
    fetchItems()
  }, [fetchItems])

  // 切换到复习模式时加载待复习
  useEffect(() => {
    if (mode === 'review') {
      fetchDueItems()
    }
  }, [mode, fetchDueItems])

  // --- 展开/折叠（改为右侧面板） ---
  const toggleExpand = useCallback((item: ErrorBookItem) => {
    useAppStore.getState().openRightPanel('error-detail', {
      item,
      onMastered: () => fetchItems(),
    })
  }, [fetchItems])

  // --- 标记已掌握 ---
  const handleMastered = useCallback(async (id: string | number) => {
    const targetItem = items.find(item => item.id === id)
    try {
      const resp = await markMastered(id)
      if (resp.code === 200) {
        if (targetItem?.knowledge_point) {
          recordLearningEvent({
            userId: authStore.userId,
            sourcePage: 'error-book',
            actionType: 'error_reviewed',
            topic: targetItem.knowledge_point,
            knowledgePoint: targetItem.knowledge_point,
            score: 100,
          })
        }
        appStore.showToast('已标记为掌握', 'success')
        fetchItems()
        if (mode === 'review') fetchDueItems()
      }
    } catch {
      appStore.showToast('操作失败', 'error')
    }
  }, [appStore, fetchItems, fetchDueItems, mode, items, recordLearningEvent, authStore.userId])

  // --- 生成辅导短视频 ---
  const handleGenerateTutor = useCallback(async (item: ErrorBookItem) => {
    if (tutorGeneratingIds.has(item.id)) return
    setTutorGeneratingIds(prev => new Set(prev).add(item.id))
    try {
      const resp = await generateTutorVideo(item.id)
      if (resp.code !== 200 || !resp.data?.task_id) {
        appStore.showToast(resp.message || '提交失败', 'error')
        setTutorGeneratingIds(prev => { const n = new Set(prev); n.delete(item.id); return n })
        return
      }
      const taskId = resp.data.task_id
      useTaskStore.getState().addTask({
        taskId,
        resourceType: 'tutor_video',
        topic: item.knowledge_point || '错题辅导',
        status: 'pending',
        createdAt: Date.now(),
        progress: 0,
      })
      appStore.showToast('辅导视频生成中，完成后将跳转', 'success')
      pollTaskProgress(
        taskId,
        () => {
          setTutorGeneratingIds(prev => { const n = new Set(prev); n.delete(item.id); return n })
          appStore.showToast('辅导视频已生成', 'success')
          navigate('/teaching')
        },
        (err) => {
          setTutorGeneratingIds(prev => { const n = new Set(prev); n.delete(item.id); return n })
          appStore.showToast(`生成失败：${err}`, 'error')
        }
      )
    } catch (e) {
      setTutorGeneratingIds(prev => { const n = new Set(prev); n.delete(item.id); return n })
      appStore.showToast('提交失败，请稍后重试', 'error')
      console.error('生成辅导视频失败:', e)
    }
  }, [tutorGeneratingIds, appStore, navigate])

  // --- 删除 ---
  const handleDelete = useCallback(async (id: string | number) => {
    try {
      const resp = await deleteErrorBook(id)
      if (resp.code === 200) {
        appStore.showToast('已删除', 'success')
        fetchItems()
        if (mode === 'review') fetchDueItems()
      }
    } catch {
      appStore.showToast('删除失败', 'error')
    }
  }, [appStore, fetchItems, fetchDueItems, mode])

  // --- 复习评分 ---
  const handleReviewRate = useCallback(async (quality: number) => {
    if (!currentReviewItem) return
    try {
      const resp = await recordReview(currentReviewItem.id, quality)
      if (resp.code === 200) {
        const updated = resp.data as ErrorBookItem
        recordLearningEvent({
          userId: authStore.userId,
          sourcePage: 'error-book',
          actionType: 'error_reviewed',
          topic: currentReviewItem.knowledge_point,
          knowledgePoint: currentReviewItem.knowledge_point,
          score: quality * 20,
        })
        const label = quality >= 4 ? '掌握良好' : quality >= 3 ? '继续加油' : '需要加强'
        appStore.showToast(`${label}，下次复习：${formatReviewDate(updated.next_review_at)}`, 'success')

        // 移动到下一题或结束
        if (reviewIndex < dueItems.length - 1) {
          setReviewIndex(prev => prev + 1)
          setShowAnswer(false)
        } else {
          // 复习完成，刷新
          fetchDueItems()
          appStore.showToast('本轮复习完成！', 'success')
        }
      }
    } catch {
      appStore.showToast('记录失败', 'error')
    }
  }, [currentReviewItem, reviewIndex, dueItems.length, appStore, fetchDueItems, recordLearningEvent, authStore.userId])

  // --- 复习进度 ---
  const reviewProgress = dueItems.length > 0 ? ((reviewIndex) / dueItems.length * 100) : 0

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="错题本">
        <div className="flex items-center gap-2">
          {mode === 'list' && (
            <span className="text-sm text-gray-500">{unmasteredCount} 题待掌握</span>
          )}
          <button
            onClick={() => setMode(mode === 'list' ? 'review' : 'list')}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              mode === 'review'
                ? 'bg-brand-100 text-brand-700'
                : 'bg-brand-600 text-white hover:bg-brand-700'
            }`}
          >
            {mode === 'review' ? (
              <>
                <BookOpen className="w-4 h-4" />
                返回列表
              </>
            ) : (
              <>
                <Brain className="w-4 h-4" />
                开始复习
                {dueCount > 0 && (
                  <span className="ml-1 px-1.5 py-0.5 bg-white/20 rounded-full text-xs">
                    {dueCount}
                  </span>
                )}
              </>
            )}
          </button>
        </div>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* ========== 复习模式 ========== */}
        {mode === 'review' ? (
          reviewLoading ? (
            <div className="flex items-center justify-center h-64">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
            </div>
          ) : dueItems.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-gray-400">
              <Trophy className="w-12 h-12 mb-3 opacity-40" />
              <p className="text-sm">暂无待复习题目，继续保持！</p>
              <p className="text-xs mt-1">答错的题目会自动安排复习计划</p>
            </div>
          ) : (
            <div className="max-w-2xl mx-auto">
              {/* 进度条 */}
              <div className="mb-6">
                <div className="flex items-center justify-between text-sm text-gray-500 mb-2">
                  <span>复习进度</span>
                  <span>{reviewIndex + 1} / {dueItems.length}</span>
                </div>
                <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-brand-500 rounded-full transition-all duration-300"
                    style={{ width: `${reviewProgress}%` }}
                  />
                </div>
              </div>

              {/* 当前复习卡片 */}
              {currentReviewItem && (
                <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                  {/* 题目头部 */}
                  <div className="px-5 py-4 border-b border-gray-100">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        TYPE_LABELS[currentReviewItem.question_type] ? 'bg-violet-100 text-violet-700' : 'bg-gray-100 text-gray-600'
                      }`}>
                        {TYPE_LABELS[currentReviewItem.question_type] || currentReviewItem.question_type}
                      </span>
                      {currentReviewItem.difficulty && (
                        <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[currentReviewItem.difficulty] || 'bg-gray-100 text-gray-600'}`}>
                          {DIFFICULTY_LABELS[currentReviewItem.difficulty] || currentReviewItem.difficulty}
                        </span>
                      )}
                      {currentReviewItem.knowledge_point && (
                        <span className="text-xs text-gray-400">{currentReviewItem.knowledge_point}</span>
                      )}
                      <span className="text-xs text-gray-400 ml-auto">
                        已复习 {currentReviewItem.repetition_count} 次 · 间隔 {currentReviewItem.review_interval_days < 1
                          ? `${Math.round(currentReviewItem.review_interval_days * 24)}小时`
                          : `${Math.round(currentReviewItem.review_interval_days)}天`
                        }
                      </span>
                    </div>
                    <p className="text-base text-gray-800 leading-relaxed">
                      {currentReviewItem.question_text}
                    </p>
                  </div>

                  {/* 回忆提示区 */}
                  {!showAnswer && (
                    <div className="px-5 py-8 flex flex-col items-center">
                      <p className="text-sm text-gray-400 mb-4">先在脑中回忆答案，然后点击下方查看</p>
                      <button
                        onClick={() => setShowAnswer(true)}
                        className="px-6 py-2.5 bg-brand-600 text-white rounded-lg font-medium hover:bg-brand-700 transition-colors"
                      >
                        显示答案
                      </button>
                    </div>
                  )}

                  {/* 答案详情 */}
                  {showAnswer && (
                    <div className="px-5 py-4 space-y-3">
                      <div>
                        <p className="text-xs text-gray-400 mb-1">你的答案</p>
                        <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700 flex items-start gap-2">
                          <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                          <pre className="whitespace-pre-wrap font-mono text-xs">{currentReviewItem.user_answer || '(未作答)'}</pre>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-gray-400 mb-1">正确答案</p>
                        <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-sm text-green-700 flex items-start gap-2">
                          <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5" />
                          <pre className="whitespace-pre-wrap font-mono text-xs">{currentReviewItem.correct_answer}</pre>
                        </div>
                      </div>
                      {currentReviewItem.explanation && (
                        <div>
                          <p className="text-xs text-gray-400 mb-1">解析</p>
                          <div className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700">
                            <p className="whitespace-pre-wrap text-xs">{currentReviewItem.explanation}</p>
                          </div>
                        </div>
                      )}

                      {/* 生成辅导短视频 */}
                      <div className="pt-3 border-t border-gray-100">
                        <button
                          onClick={() => handleGenerateTutor(currentReviewItem)}
                          disabled={tutorGeneratingIds.has(currentReviewItem.id)}
                          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700 transition-colors disabled:opacity-60 disabled:cursor-wait"
                        >
                          {tutorGeneratingIds.has(currentReviewItem.id)
                            ? <Loader2 className="w-4 h-4 animate-spin" />
                            : <Video className="w-4 h-4" />}
                          {tutorGeneratingIds.has(currentReviewItem.id) ? '辅导视频生成中...' : '看辅导短视频'}
                        </button>
                      </div>

                      {/* 评分按钮 */}
                      <div className="pt-3 border-t border-gray-100">
                        <p className="text-sm text-gray-500 mb-3 text-center">你觉得这道题掌握得怎么样？</p>
                        <div className="flex gap-2">
                          {QUALITY_OPTIONS.map(opt => {
                            const Icon = opt.icon
                            return (
                              <button
                                key={opt.value}
                                onClick={() => handleReviewRate(opt.value)}
                                className={`flex-1 flex flex-col items-center gap-1.5 px-2 py-3 rounded-xl border-2 transition-all hover:scale-105 ${opt.color}`}
                              >
                                <Icon className="w-5 h-5" />
                                <span className="text-xs font-medium">{opt.label}</span>
                              </button>
                            )
                          })}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 跳过按钮 */}
              {currentReviewItem && (
                <div className="mt-4 flex justify-center">
                  <button
                    onClick={() => {
                      if (reviewIndex < dueItems.length - 1) {
                        setReviewIndex(prev => prev + 1)
                        setShowAnswer(false)
                      } else {
                        appStore.showToast('本轮复习完成', 'success')
                        fetchDueItems()
                      }
                    }}
                    className="text-sm text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    跳过此题 →
                  </button>
                </div>
              )}
            </div>
          )
        ) : (
          /* ========== 列表模式 ========== */
          <>
            {/* 筛选栏 */}
            <div className="flex flex-wrap gap-3 mb-6">
              <select
                value={filterKP}
                onChange={e => setFilterKP(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">全部知识点</option>
                {KP_OPTIONS.map(kp => (
                  <option key={kp} value={kp}>{kp}</option>
                ))}
              </select>
              <select
                value={filterDifficulty}
                onChange={e => setFilterDifficulty(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">全部难度</option>
                <option value="easy">简单</option>
                <option value="medium">中等</option>
                <option value="hard">困难</option>
              </select>
              <select
                value={filterMastered}
                onChange={e => setFilterMastered(e.target.value)}
                className="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
              >
                <option value="">全部状态</option>
                <option value="false">未掌握</option>
                <option value="true">已掌握</option>
              </select>
            </div>

            {/* Loading */}
            {loading ? (
              <div className="flex items-center justify-center h-64">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600" />
              </div>
            ) : items.length === 0 ? (
              /* Empty */
              <div className="flex flex-col items-center justify-center h-64 text-gray-400">
                <Trophy className="w-12 h-12 mb-3 opacity-40" />
                <p className="text-sm">暂无错题，继续保持！</p>
              </div>
            ) : (
              /* 列表 */
              <div className="max-w-3xl mx-auto space-y-3">
                {items.map(item => {
                  const status = getReviewStatus(item)
                  return (
                    <div
                      key={item.id}
                      className={`rounded-xl border transition-all ${
                        item.mastered ? 'border-green-200 bg-green-50/50' :
                        status === 'overdue' ? 'border-red-200 bg-red-50/30' :
                        'border-gray-200 bg-white'
                      }`}
                    >
                      {/* 头部 */}
                      <div
                        className="flex items-start gap-3 px-4 py-3 cursor-pointer"
                        onClick={() => toggleExpand(item)}
                      >
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1 flex-wrap">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${
                              TYPE_LABELS[item.question_type] ? 'bg-violet-100 text-violet-700' : 'bg-gray-100 text-gray-600'
                            }`}>
                              {TYPE_LABELS[item.question_type] || item.question_type}
                            </span>
                            {item.difficulty && (
                              <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[item.difficulty] || 'bg-gray-100 text-gray-600'}`}>
                                {DIFFICULTY_LABELS[item.difficulty] || item.difficulty}
                              </span>
                            )}
                            {item.knowledge_point && (
                              <span className="text-xs text-gray-400">{item.knowledge_point}</span>
                            )}
                            {item.mastered ? (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">已掌握</span>
                            ) : status === 'overdue' ? (
                              <span className="text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-700">待复习</span>
                            ) : null}
                          </div>
                          <p className="text-sm text-gray-800 line-clamp-2">{item.question_text}</p>
                          <div className="flex items-center gap-3 mt-1.5 text-xs text-gray-400">
                            <span>错 {item.error_count} 次</span>
                            <span>{item.last_wrong_at?.slice(0, 10)}</span>
                            {!item.mastered && item.next_review_at && (
                              <span className="flex items-center gap-1">
                                <Calendar className="w-3 h-3" />
                                {formatReviewDate(item.next_review_at)}
                              </span>
                            )}
                            {item.repetition_count > 0 && (
                              <span className="flex items-center gap-1">
                                <RotateCcw className="w-3 h-3" />
                                已复习 {item.repetition_count} 次
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5 flex-shrink-0 mt-1">
                          {!item.mastered && (
                            <button
                              onClick={e => { e.stopPropagation(); handleMastered(item.id) }}
                              className="p-1.5 rounded-lg text-green-500 hover:bg-green-100 transition-colors"
                              title="标记已掌握"
                            >
                              <CheckCircle2 className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={e => { e.stopPropagation(); handleGenerateTutor(item) }}
                            disabled={tutorGeneratingIds.has(item.id)}
                            className="p-1.5 rounded-lg text-violet-500 hover:bg-violet-100 transition-colors disabled:opacity-50 disabled:cursor-wait"
                            title="生成辅导短视频"
                          >
                            {tutorGeneratingIds.has(item.id)
                              ? <Loader2 className="w-4 h-4 animate-spin" />
                              : <Video className="w-4 h-4" />}
                          </button>
                          <button
                            onClick={e => { e.stopPropagation(); handleDelete(item.id) }}
                            className="p-1.5 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default ErrorBookView
