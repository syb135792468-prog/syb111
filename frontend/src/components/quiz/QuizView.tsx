import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import {
  X, Loader2, CheckCircle2, XCircle, RotateCcw, ChevronRight, ChevronLeft,
  Trophy, Lightbulb, ListChecks
} from 'lucide-react'
import { getQuiz, submitQuizAnswer, updateQuizStats, generateQuizAnswer } from '../../api/quiz'
import { getResource } from '../../api/resource'
import { executeCode } from '../../api/code'
import { useAuthStore } from '../../stores/auth'
import { useCodeTextarea } from '../../composables/useCodeTextarea'
import { useAppStore } from '../../stores/app'

// --- 类型定义 ---
interface Question {
  index: number
  questionText: string
  options: string[]
  type: string
  answer: string
  explanation: string
}

interface QuizResult {
  is_correct: boolean
  correct_answer: string
  explanation: string
  score: number
  spent_time: number
}

interface CodeOutput {
  stdout: string
  stderr: string
  success: boolean
  timed_out: boolean
  execution_time: number
  network_time?: number
  total_time?: number
}

interface QuizViewProps {
  resourceId: string
  show?: boolean
  onClose: () => void
}

// --- 常量 ---
const TYPE_LABELS: Record<string, string> = { choice: '选择题', fill: '填空题', code: '编程题', multi: '综合练习' }
const TYPE_COLORS: Record<string, string> = {
  choice: 'bg-violet-100 text-violet-700',
  fill: 'bg-amber-100 text-amber-700',
  code: 'bg-sky-100 text-sky-700',
}

// --- 工具函数 ---
function formatExecTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(1)
  return `${m}m ${s}s`
}

function formatTime(seconds: number): string {
  if (!seconds && seconds !== 0) return ''
  if (seconds < 60) return `${seconds}秒`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
}

// --- 组件 ---
const QuizView: React.FC<QuizViewProps> = ({ resourceId, show, onClose }) => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // 状态
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [quizTitle, setQuizTitle] = useState('')
  const [questions, setQuestions] = useState<Question[]>([])
  const [currentIndex, setCurrentIndex] = useState(0)
  const [userAnswers, setUserAnswers] = useState<string[]>([])
  const [submittedFlags, setSubmittedFlags] = useState<boolean[]>([])
  const [results, setResults] = useState<(QuizResult | null)[]>([])
  const [startTime, setStartTime] = useState<number>(Date.now())
  const [submitting, setSubmitting] = useState(false)
  const [showSummary, setShowSummary] = useState(false)
  const [hasAnswer, setHasAnswer] = useState(false)
  const [generatingAnswer, setGeneratingAnswer] = useState(false)

  // 代码执行
  const [codeRunning, setCodeRunning] = useState(false)
  const [codeOutput, setCodeOutput] = useState<(CodeOutput | null)[]>([])
  const [codeElapsed, setCodeElapsed] = useState(0)
  const codeTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 派生状态
  const currentQuestion = useMemo(() => questions[currentIndex] || null, [questions, currentIndex])
  const totalQuestions = useMemo(() => questions.length, [questions])
  const currentAnswer = userAnswers[currentIndex] || ''
  const currentSubmitted = submittedFlags[currentIndex] || false
  const currentResult = results[currentIndex] || null
  const currentIsCorrect = currentResult?.is_correct
  const currentCodeOutput = codeOutput[currentIndex] || null
  const correctCount = useMemo(() => results.filter(r => r?.is_correct).length, [results])
  const answeredCount = useMemo(() => submittedFlags.filter(Boolean).length, [submittedFlags])
  const progressPercent = useMemo(() => totalQuestions ? Math.round(answeredCount / totalQuestions * 100) : 0, [answeredCount, totalQuestions])

  // 清理定时器
  const clearCodeTimer = useCallback(() => {
    if (codeTimerRef.current) {
      clearInterval(codeTimerRef.current)
      codeTimerRef.current = null
    }
  }, [])

  useEffect(() => () => clearCodeTimer(), [clearCodeTimer])

  // ESC 关闭
  useEffect(() => {
    if (show === false || show === undefined) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [show, onClose])

  // 更新当前答案
  const setCurrentAnswer = useCallback((val: string) => {
    setUserAnswers(prev => {
      const next = [...prev]
      next[currentIndex] = val
      return next
    })
  }, [currentIndex])

  // 代码编辑便利功能（括号补全、自动缩进）
  const { handleKeyDown: handleCodeKeyDown } = useCodeTextarea(currentAnswer, setCurrentAnswer)

  // 选项样式
  const optionClass = useCallback((opt: string): string => {
    const letter = opt.charAt(0)
    const q = currentQuestion
    if (!currentSubmitted) {
      return currentAnswer === letter
        ? 'border-brand-500 bg-brand-50 shadow-sm ring-1 ring-brand-200'
        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
    }
    if (letter === q?.answer) return 'border-green-400 bg-green-50 ring-1 ring-green-200'
    if (letter === currentAnswer && !currentResult?.is_correct) return 'border-red-400 bg-red-50 ring-1 ring-red-200'
    return 'border-gray-200 opacity-40'
  }, [currentQuestion, currentSubmitted, currentAnswer, currentResult])

  const selectOption = useCallback((opt: string) => {
    if (currentSubmitted) return
    setCurrentAnswer(opt.charAt(0))
  }, [currentSubmitted, setCurrentAnswer])

  // 加载题目
  const loadQuiz = useCallback(async () => {
    if (!resourceId) return
    setLoading(true)
    setError('')
    setShowSummary(false)

    try {
      type QuizData = { id: number | string; title: string; is_multi: boolean; question_count: number; questions: Question[] }
      let data: QuizData | null = null
      try {
        const resp = await getQuiz(resourceId)
        if (resp.code === 200 && resp.data) data = resp.data as QuizData
      } catch { /* ignore */ }

      if (!data) {
        const resp = await getResource(resourceId, authStore.userId)
        if (resp.code === 200 && resp.data) {
          const res = resp.data as { id: number | string; title: string; extra_metadata?: Record<string, unknown> }
          const meta = (res.extra_metadata || {}) as { quiz_type?: string; answer?: string; explanation?: string; question_count?: number; questions?: Array<{ quiz_type: string; answer: string; explanation: string }> }
          if (meta.quiz_type === 'multi') {
            data = {
              id: res.id, title: res.title, is_multi: true,
              question_count: meta.question_count || 0,
              questions: (meta.questions || []).map((q, i) => ({
                index: i + 1, questionText: '', options: [],
                type: q.quiz_type, answer: q.answer, explanation: q.explanation,
              })),
            }
          } else {
            data = {
              id: res.id, title: res.title, is_multi: false, question_count: 1,
              questions: [{ index: 1, questionText: '', options: [], type: meta.quiz_type || 'choice', answer: meta.answer || '', explanation: meta.explanation || '' }],
            }
          }
        } else { throw new Error(resp.message || '加载题目失败') }
      }

      setQuizTitle(data.title || '练习题')
      const qs = data.questions || []
      setQuestions(qs)
      setUserAnswers(new Array(qs.length).fill(''))
      setSubmittedFlags(new Array(qs.length).fill(false))
      setResults(new Array(qs.length).fill(null))
      setCurrentIndex(0)
      setHasAnswer(qs.some(q => !!q.answer))
      setStartTime(Date.now())
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '加载题目失败'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [resourceId, authStore.userId])

  useEffect(() => { if (show) loadQuiz() }, [show, loadQuiz])

  // 提交答案
  const handleSubmitCurrent = useCallback(async () => {
    if (!currentAnswer || submitting) return
    setSubmitting(true)
    const idx = currentIndex
    const q = questions[idx]
    const spentTime = Math.round((Date.now() - startTime) / 1000)

    try {
      let submitResult: QuizResult | null = null
      try {
        const resp = await submitQuizAnswer(resourceId, currentAnswer, spentTime, idx)
        if (resp.code === 200 && resp.data) submitResult = resp.data as QuizResult
      } catch { /* ignore */ }

      if (!submitResult) {
        const correct = currentAnswer.toUpperCase().trim() === q.answer.toUpperCase().trim()
        submitResult = { is_correct: correct, correct_answer: q.answer, explanation: q.explanation, score: correct ? 10 : 0, spent_time: spentTime }
      }
      setResults(prev => { const next = [...prev]; next[idx] = submitResult; return next })
      setSubmittedFlags(prev => { const next = [...prev]; next[idx] = true; return next })
      try { updateQuizStats(resourceId, submitResult.is_correct, spentTime) } catch { /* ignore */ }
      // 通知 ProfileView 刷新学习画像
      window.dispatchEvent(new CustomEvent('learning-profile-dirty'))
    } catch {
      appStore.showToast('提交失败', 'error')
    } finally {
      setSubmitting(false)
    }
  }, [currentAnswer, submitting, currentIndex, questions, startTime, resourceId, appStore])

  // 生成答案
  const handleGenerateAnswer = useCallback(async () => {
    if (generatingAnswer || !currentAnswer) return
    setGeneratingAnswer(true)
    const idx = currentIndex
    try {
      const resp = await generateQuizAnswer(resourceId, idx)
      if (resp.code === 200 && resp.data) {
        const data = resp.data as { correct_answer?: string; correctAnswer?: string; explanation?: string }
        const newAnswer = data.correct_answer || data.correctAnswer || ''
        const newExplanation = data.explanation || ''
        // Immutable update for the questions array
        setQuestions(prev => {
          const next = [...prev]
          next[idx] = { ...next[idx], answer: newAnswer, explanation: newExplanation }
          return next
        })
        setHasAnswer(true)
        const spentTime = Math.round((Date.now() - startTime) / 1000)
        const correct = currentAnswer.toUpperCase().trim() === newAnswer.toUpperCase().trim()
        setResults(prev => { const next = [...prev]; next[idx] = { is_correct: correct, correct_answer: newAnswer, explanation: newExplanation, score: correct ? 10 : 0, spent_time: spentTime }; return next })
        setSubmittedFlags(prev => { const next = [...prev]; next[idx] = true; return next })
      } else { appStore.showToast('生成答案失败', 'error') }
    } catch { appStore.showToast('生成答案失败', 'error') }
    finally { setGeneratingAnswer(false) }
  }, [generatingAnswer, currentAnswer, currentIndex, resourceId, startTime, appStore])

  // 运行代码
  const handleRunCode = useCallback(async () => {
    if (!currentAnswer || codeRunning) return
    setCodeRunning(true)
    setCodeElapsed(0)
    const idx = currentIndex
    const t0 = Date.now()
    codeTimerRef.current = setInterval(() => setCodeElapsed(Date.now() - t0), 100)

    try {
      const result = await executeCode(currentAnswer, 5)
      clearCodeTimer()
      setCodeElapsed(result.total_time)
      setCodeOutput(prev => { const next = [...prev]; next[idx] = result; return next })
    } catch (e: unknown) {
      clearCodeTimer()
      const msg = e instanceof Error ? e.message : '执行异常'
      setCodeOutput(prev => { const next = [...prev]; next[idx] = { stdout: '', stderr: msg, success: false, timed_out: false, execution_time: 0 }; return next })
    } finally {
      setCodeRunning(false)
    }
  }, [currentAnswer, codeRunning, currentIndex, clearCodeTimer])

  // 导航
  const goNext = useCallback(() => {
    if (currentIndex < totalQuestions - 1) { setCurrentIndex(currentIndex + 1); setStartTime(Date.now()) }
  }, [currentIndex, totalQuestions])
  const goPrev = useCallback(() => { if (currentIndex > 0) setCurrentIndex(currentIndex - 1) }, [currentIndex])
  const goTo = useCallback((idx: number) => { setCurrentIndex(idx); setShowSummary(false); setStartTime(Date.now()) }, [])
  const resetCurrent = useCallback(() => {
    setUserAnswers(prev => { const next = [...prev]; next[currentIndex] = ''; return next })
    setSubmittedFlags(prev => { const next = [...prev]; next[currentIndex] = false; return next })
    setResults(prev => { const next = [...prev]; next[currentIndex] = null; return next })
    setStartTime(Date.now())
  }, [currentIndex])
  const resetAll = useCallback(() => {
    setUserAnswers(new Array(questions.length).fill(''))
    setSubmittedFlags(new Array(questions.length).fill(false))
    setResults(new Array(questions.length).fill(null))
    setCurrentIndex(0)
    setShowSummary(false)
    setStartTime(Date.now())
  }, [questions.length])

  // --- 渲染：题目视图 ---
  const renderQuestionView = () => (
    <>
      {/* Question header */}
      <div className="px-6 pt-5 pb-1 flex items-center gap-2">
        <span className="text-xs font-bold text-brand-600">第 {currentIndex + 1} 题</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[currentQuestion!.type] || TYPE_COLORS.choice}`}>
          {TYPE_LABELS[currentQuestion!.type] || currentQuestion!.type}
        </span>
      </div>

      {/* Question text */}
      <div className="px-6 py-3">
        <p className="text-base text-gray-800 leading-relaxed whitespace-pre-wrap font-medium">{currentQuestion!.questionText}</p>
      </div>

      {/* Choice options */}
      {currentQuestion!.type === 'choice' && currentQuestion!.options.length > 0 && (
        <div className="px-6 pb-4 space-y-2">
          {currentQuestion!.options.map(opt => (
            <button
              key={opt}
              onClick={() => selectOption(opt)}
              className={`w-full text-left px-4 py-3 rounded-xl border-2 transition-all text-sm flex items-center gap-3 ${optionClass(opt)} ${currentSubmitted ? 'cursor-default' : ''}`}
            >
              <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${
                !currentSubmitted && currentAnswer === opt.charAt(0) ? 'bg-brand-500 text-white' : 'bg-gray-100 text-gray-500'
              } ${currentSubmitted && opt.charAt(0) === currentQuestion!.answer ? 'bg-green-500 text-white' : ''} ${
                currentSubmitted && opt.charAt(0) === currentAnswer && !currentResult?.is_correct ? 'bg-red-500 text-white' : ''
              }`}>{opt.charAt(0)}</span>
              <span className="text-gray-700">{opt.slice(opt.indexOf('.') + 1).trim()}</span>
              {currentSubmitted && opt.charAt(0) === currentQuestion!.answer && <CheckCircle2 className="w-5 h-5 text-green-500 ml-auto flex-shrink-0" />}
              {currentSubmitted && opt.charAt(0) === currentAnswer && !currentResult?.is_correct && opt.charAt(0) !== currentQuestion!.answer && <XCircle className="w-5 h-5 text-red-500 ml-auto flex-shrink-0" />}
            </button>
          ))}
        </div>
      )}

      {/* Fill input */}
      {currentQuestion!.type === 'fill' && (
        <div className="px-6 pb-4">
          <div className="relative">
            <input
              value={currentAnswer}
              onChange={e => setCurrentAnswer(e.target.value)}
              disabled={currentSubmitted}
              type="text"
              placeholder="输入你的答案..."
              className={`w-full px-4 py-3.5 border-2 rounded-xl text-sm font-mono transition-all focus:outline-none ${
                currentSubmitted
                  ? currentIsCorrect ? 'border-green-400 bg-green-50' : 'border-red-400 bg-red-50'
                  : 'border-gray-200 focus:border-brand-500'
              } ${currentSubmitted ? 'disabled:opacity-100' : ''}`}
            />
            {currentSubmitted && currentIsCorrect && <CheckCircle2 className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-500" />}
            {currentSubmitted && !currentIsCorrect && <XCircle className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-red-500" />}
          </div>
        </div>
      )}

      {/* Code textarea */}
      {currentQuestion!.type === 'code' && (
        <div className="px-6 pb-4">
          <textarea
            value={currentAnswer}
            onChange={e => setCurrentAnswer(e.target.value)}
            onKeyDown={handleCodeKeyDown}
            disabled={currentSubmitted}
            rows={6}
            placeholder="在此编写代码..."
            className={`w-full px-4 py-3.5 border-2 rounded-xl text-sm font-mono leading-relaxed resize-y transition-all focus:outline-none ${
              currentSubmitted
                ? currentIsCorrect ? 'border-green-400 bg-green-50' : 'border-red-400 bg-red-50'
                : 'border-gray-200 focus:border-brand-500'
            } ${currentSubmitted ? 'disabled:opacity-100' : ''}`}
          />
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={handleRunCode}
              disabled={!currentAnswer || codeRunning || currentSubmitted}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-sky-600 text-white text-xs rounded-lg hover:bg-sky-700 transition-colors disabled:opacity-50"
            >
              {codeRunning && <RotateCcw className="w-3.5 h-3.5 animate-spin" />}
              <span>{codeRunning ? `运行中 ${formatExecTime(codeElapsed)}` : '运行代码'}</span>
            </button>
            {codeRunning && <span className="text-xs text-amber-500">已等待 {formatExecTime(codeElapsed)}</span>}
          </div>
          {/* 代码执行输出 */}
          {currentCodeOutput && (
            <div className="mt-3">
              <div className={`rounded-lg border px-3 py-2 text-xs font-mono ${currentCodeOutput.success ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
                {currentCodeOutput.stdout && <p className="text-gray-800 whitespace-pre-wrap">{currentCodeOutput.stdout}</p>}
                {currentCodeOutput.stderr && <p className="text-red-600 whitespace-pre-wrap">{currentCodeOutput.stderr}</p>}
                {!currentCodeOutput.stdout && !currentCodeOutput.stderr && <p className="text-gray-400">无输出</p>}
                <div className="flex items-center gap-3 mt-1 text-gray-400">
                  <span>执行 {formatExecTime((currentCodeOutput.execution_time || 0) * 1000)}</span>
                  <span>网络 {formatExecTime(currentCodeOutput.network_time || 0)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Result card */}
      {currentSubmitted && currentResult && (
        <div className="mx-6 mb-4">
          <div className={`rounded-xl px-4 py-3 mb-3 flex items-center gap-3 ${currentIsCorrect ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
            <div className={`w-9 h-9 rounded-full flex items-center justify-center ${currentIsCorrect ? 'bg-green-100' : 'bg-red-100'}`}>
              {currentIsCorrect ? <CheckCircle2 className="w-5 h-5 text-green-600" /> : <XCircle className="w-5 h-5 text-red-600" />}
            </div>
            <p className={`text-sm font-bold ${currentIsCorrect ? 'text-green-700' : 'text-red-700'}`}>
              {currentIsCorrect ? '回答正确！' : '回答错误'}
            </p>
          </div>
          {!currentIsCorrect && (
            <div className="bg-gray-50 rounded-xl px-4 py-3 mb-3">
              <p className="text-xs text-gray-400 mb-1">正确答案</p>
              <p className="text-sm font-semibold text-gray-800">{currentResult.correct_answer}</p>
            </div>
          )}
          {currentResult.explanation && (
            <div className="bg-amber-50 border border-amber-100 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2 mb-1.5">
                <Lightbulb className="w-4 h-4 text-amber-500" />
                <p className="text-xs font-semibold text-amber-700">答案解析</p>
              </div>
              <p className="text-sm text-amber-900 leading-relaxed whitespace-pre-wrap">{currentResult.explanation}</p>
            </div>
          )}
        </div>
      )}
    </>
  )

  // --- 渲染：总览 ---
  const renderSummary = () => (
    <div className="p-6">
      <div className="text-center mb-6">
        <div className={`w-16 h-16 rounded-full mx-auto flex items-center justify-center mb-3 ${correctCount === totalQuestions ? 'bg-green-100' : 'bg-amber-100'}`}>
          <Trophy className={`w-8 h-8 ${correctCount === totalQuestions ? 'text-green-500' : 'text-amber-500'}`} />
        </div>
        <h2 className="text-xl font-bold text-gray-800">
          {correctCount === totalQuestions ? '全部答对！' : `答对 ${correctCount} / ${totalQuestions} 题`}
        </h2>
        <p className="text-sm text-gray-400 mt-1">
          {correctCount === totalQuestions ? '太棒了，继续保持！' : '继续加油，多练习就能掌握！'}
        </p>
      </div>
      <div className="space-y-2">
        {questions.map((q, i) => (
          <button
            key={i}
            onClick={() => goTo(i)}
            className="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-gray-100 hover:bg-gray-50 transition-colors text-left"
          >
            <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0 ${results[i]?.is_correct ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'}`}>
              {results[i]?.is_correct ? '✓' : '✗'}
            </span>
            <span className="text-sm text-gray-700 truncate">第 {i + 1} 题</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ml-auto flex-shrink-0 ${TYPE_COLORS[q.type] || TYPE_COLORS.choice}`}>
              {TYPE_LABELS[q.type] || q.type}
            </span>
          </button>
        ))}
      </div>
      <div className="flex justify-center gap-3 mt-6">
        <button onClick={resetAll} className="flex items-center gap-1.5 px-4 py-2.5 text-sm text-gray-500 border border-gray-200 rounded-xl hover:bg-gray-50 transition-colors">
          <RotateCcw className="w-4 h-4" /> 重新作答
        </button>
        <button onClick={onClose} className="flex items-center gap-1.5 px-5 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 transition-all shadow-sm">
          完成 <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  )

  // --- 渲染：内容区 ---
  const renderContent = () => {
    if (loading) return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
        <p className="text-sm text-gray-400">加载题目中...</p>
      </div>
    )
    if (error) return (
      <div className="flex flex-col items-center justify-center h-64 gap-3">
        <XCircle className="w-10 h-10 text-red-300" />
        <p className="text-sm text-gray-500">{error}</p>
        <button onClick={loadQuiz} className="text-sm text-brand-600 font-medium">重新加载</button>
      </div>
    )
    if (showSummary) return renderSummary()
    if (currentQuestion) return renderQuestionView()
    return null
  }

  // --- 渲染：底部按钮 ---
  const renderFooter = () => (
    <div className="border-t border-gray-100 px-6 py-3.5 flex items-center justify-between flex-shrink-0 bg-gray-50/50">
      <div className="flex items-center gap-2">
        {currentIndex > 0 && (
          <button onClick={goPrev} className="flex items-center gap-1 px-3 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">
            <ChevronLeft className="w-4 h-4" /> 上一题
          </button>
        )}
        {currentSubmitted && (
          <button onClick={resetCurrent} className="flex items-center gap-1 px-3 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">
            <RotateCcw className="w-3.5 h-3.5" /> 重做
          </button>
        )}
      </div>
      <div className="flex items-center gap-2">
        {!currentSubmitted && (
          <button onClick={onClose} className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors">退出</button>
        )}
        {!currentSubmitted && hasAnswer && (
          <button onClick={handleSubmitCurrent} disabled={!currentAnswer || submitting}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm">
            {submitting && <Loader2 className="w-4 h-4 animate-spin" />}
            {submitting ? '提交中...' : '提交'}
          </button>
        )}
        {!currentSubmitted && !hasAnswer && (
          <button onClick={handleGenerateAnswer} disabled={!currentAnswer || generatingAnswer}
            className="flex items-center gap-2 px-5 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-sm">
            {generatingAnswer && <Loader2 className="w-4 h-4 animate-spin" />}
            {generatingAnswer ? '生成中...' : '查看答案'}
          </button>
        )}
        {currentSubmitted && currentIndex < totalQuestions - 1 && (
          <button onClick={goNext} className="flex items-center gap-1 px-5 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 transition-all shadow-sm">
            下一题 <ChevronRight className="w-4 h-4" />
          </button>
        )}
        {currentSubmitted && currentIndex === totalQuestions - 1 && (
          <button onClick={() => setShowSummary(true)} className="flex items-center gap-1 px-5 py-2.5 bg-brand-600 text-white text-sm font-medium rounded-xl hover:bg-brand-700 transition-all shadow-sm">
            <ListChecks className="w-4 h-4" /> 查看结果
          </button>
        )}
      </div>
    </div>
  )

  // --- 模态框模式 vs 页面模式 ---
  if (show !== undefined) {
    if (!show) return null
    return createPortal(
      <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[90vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
          {/* Header */}
          <div className="px-6 pt-4 pb-3 border-b border-gray-100 bg-gray-50/50 flex-shrink-0">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-800 truncate">{quizTitle}</h3>
              <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded-lg hover:bg-gray-100 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>
            {totalQuestions > 1 && (
              <>
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div className="h-full bg-brand-500 rounded-full transition-all duration-300" style={{ width: `${progressPercent}%` }} />
                  </div>
                  <span className="text-xs text-gray-400 flex-shrink-0">{answeredCount}/{totalQuestions}</span>
                </div>
                <div className="flex items-center gap-1.5 mt-2.5 flex-wrap">
                  {questions.map((_, i) => (
                    <button
                      key={i}
                      onClick={() => goTo(i)}
                      className={`w-7 h-7 rounded-full text-xs font-medium transition-all border ${
                        i === currentIndex ? 'border-brand-500 bg-brand-500 text-white shadow-sm' :
                        submittedFlags[i] ? (results[i]?.is_correct ? 'border-green-400 bg-green-50 text-green-700' : 'border-red-400 bg-red-50 text-red-700') :
                        'border-gray-200 bg-white text-gray-400 hover:border-gray-300'
                      }`}
                    >{i + 1}</button>
                  ))}
                  {answeredCount === totalQuestions && !showSummary && (
                    <button onClick={() => setShowSummary(true)} className="ml-auto flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium">
                      <ListChecks className="w-3.5 h-3.5" /> 查看总览
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
          {/* Content */}
          <div className="flex-1 overflow-y-auto">{renderContent()}</div>
          {/* Footer */}
          {!loading && !error && !showSummary && renderFooter()}
        </div>
      </div>,
      document.body
    )
  }

  // 页面模式
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <div className="flex-1 overflow-y-auto px-6 py-5 max-w-2xl mx-auto w-full">
        {renderContent()}
      </div>
    </div>
  )
}

export default QuizView
