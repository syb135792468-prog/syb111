import React, { useState, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { markMastered } from '../../api/errorBook'
import MarkdownText from '../common/MarkdownText'
import { XCircle, CheckCircle2, BookOpen, RotateCcw, Calendar, Brain, Check } from 'lucide-react'

const TYPE_LABELS: Record<string, string> = { choice: '选择题', fill: '填空题', code: '编程题' }
const DIFFICULTY_LABELS: Record<string, string> = { easy: '简单', medium: '中等', hard: '困难' }
const DIFFICULTY_COLORS: Record<string, string> = {
  easy: 'bg-green-100 text-green-700',
  medium: 'bg-amber-100 text-amber-700',
  hard: 'bg-red-100 text-red-700',
}

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

const ErrorDetailPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const item = data?.item as Record<string, unknown> | undefined
  const onMastered = data?.onMastered as (() => void) | undefined

  const [mastered, setMastered] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleMastered = useCallback(async () => {
    if (!item?.id || loading) return
    setLoading(true)
    try {
      const resp = await markMastered(item.id as number)
      if (resp.code === 200) {
        setMastered(true)
        onMastered?.()
      }
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [item, loading, onMastered])

  if (!item) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <BookOpen className="w-8 h-8 mb-3 opacity-30" />
        <p className="text-sm text-center">点击错题列表中的题目查看详情</p>
      </div>
    )
  }

  const questionType = (item.question_type as string) || ''
  const difficulty = (item.difficulty as string) || ''
  const knowledgePoint = (item.knowledge_point as string) || ''
  const questionText = (item.question_text as string) || ''
  const userAnswer = (item.user_answer as string) || ''
  const correctAnswer = (item.correct_answer as string) || ''
  const explanation = (item.explanation as string) || ''
  const errorCount = (item.error_count as number) || 0
  const lastWrongAt = (item.last_wrong_at as string) || ''
  const nextReviewAt = (item.next_review_at as string) || null
  const reviewIntervalDays = (item.review_interval_days as number) || 0
  const repetitionCount = (item.repetition_count as number) || 0
  const isMastered = mastered || (item.mastered as boolean)

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      {/* 题目信息 */}
      <div className="pb-3 border-b border-gray-100">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          {questionType && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-violet-100 text-violet-700">
              {TYPE_LABELS[questionType] || questionType}
            </span>
          )}
          {difficulty && (
            <span className={`text-xs px-2 py-0.5 rounded-full ${DIFFICULTY_COLORS[difficulty] || 'bg-gray-100 text-gray-600'}`}>
              {DIFFICULTY_LABELS[difficulty] || difficulty}
            </span>
          )}
          {isMastered && (
            <span className="text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">已掌握</span>
          )}
        </div>
        {knowledgePoint && (
          <p className="text-xs text-gray-400 mb-2">{knowledgePoint}</p>
        )}
        <p className="text-sm text-gray-800 leading-relaxed">{questionText}</p>
        <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
          <span>错 {errorCount} 次</span>
          {lastWrongAt && <span>{lastWrongAt.slice(0, 10)}</span>}
        </div>
      </div>

      {/* 用户答案 vs 正确答案 */}
      <div className="space-y-3">
        <div>
          <p className="text-xs text-gray-400 mb-1.5">你的答案</p>
          <div className="bg-red-50 border border-red-200 rounded-lg px-3 py-2 flex items-start gap-2">
            <XCircle className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-500" />
            <pre className="whitespace-pre-wrap font-mono text-xs text-red-700">{userAnswer || '(未作答)'}</pre>
          </div>
        </div>
        <div>
          <p className="text-xs text-gray-400 mb-1.5">正确答案</p>
          <div className="bg-green-50 border border-green-200 rounded-lg px-3 py-2 flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 flex-shrink-0 mt-0.5 text-green-500" />
            <pre className="whitespace-pre-wrap font-mono text-xs text-green-700">{correctAnswer}</pre>
          </div>
        </div>
      </div>

      {/* 解析 */}
      {explanation && (
        <div>
          <div className="flex items-center gap-1.5 mb-1.5">
            <Brain className="w-3.5 h-3.5 text-blue-500" />
            <span className="text-xs font-semibold text-blue-600">解析</span>
          </div>
          <div className="bg-blue-50 border border-blue-100 rounded-lg px-3 py-2.5">
            <div className="text-xs text-blue-800 leading-relaxed"><MarkdownText content={explanation} /></div>
          </div>
        </div>
      )}

      {/* 复习计划 */}
      {!isMastered && (
        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2.5">
          <div className="flex items-center gap-1.5 mb-2">
            <Calendar className="w-3.5 h-3.5 text-amber-600" />
            <span className="text-xs font-semibold text-amber-700">复习计划</span>
          </div>
          <div className="space-y-1 text-xs text-amber-600">
            <div className="flex items-center gap-2">
              <RotateCcw className="w-3 h-3" />
              <span>下次复习：{formatReviewDate(nextReviewAt)}</span>
            </div>
            <div className="flex items-center gap-2">
              <Calendar className="w-3 h-3" />
              <span>间隔：{reviewIntervalDays < 1 ? `${Math.round(reviewIntervalDays * 24)}小时` : `${Math.round(reviewIntervalDays)}天`}</span>
            </div>
            <div className="flex items-center gap-2">
              <RotateCcw className="w-3 h-3" />
              <span>已复习 {repetitionCount} 次</span>
            </div>
          </div>
        </div>
      )}

      {/* 标记已掌握按钮 */}
      {!isMastered && (
        <button
          onClick={handleMastered}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors text-sm font-medium"
        >
          <Check className="w-4 h-4" />
          {loading ? '处理中...' : '标记已掌握'}
        </button>
      )}

      {isMastered && (
        <div className="flex items-center justify-center gap-2 text-green-600 text-sm py-2">
          <CheckCircle2 className="w-5 h-5" />
          <span>已掌握</span>
        </div>
      )}
    </div>
  )
}

export default ErrorDetailPanel
