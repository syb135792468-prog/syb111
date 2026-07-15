import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { executeCode } from '../api/code'
import { DailyApiError, getTodayChallenge, submitDailyAnswer, getDailyHint, getNextChallenge, submitNextChallenge, getNextChallengeHint, type DailyChallengeData, type DailySubmitResult, type NextChallengeData, type NextChallengeSubmitResult } from '../api/daily'
import { Play, Send, CheckCircle, XCircle, RotateCcw, Lightbulb, Flame, Trophy, Zap, Copy, Check, Users, Target, Clock, ChevronRight, ArrowRight, ArrowLeft, Bookmark } from 'lucide-react'
import { addToLibrary } from '../api/resource'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useLearningCenterStore } from '../stores/learningCenter'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import {
  autoCloseBrackets, createErrorLineHighlighter, BASIC_SETUP,
  cleanOutput, formatTime, parseErrorLines,
} from '../utils/codeEditor'

// --- Streak color config ---
function getStreakTheme(days: number) {
  if (days >= 90) return { color: 'text-yellow-500', fill: 'text-yellow-400', bg: 'from-yellow-50 via-amber-50 to-orange-50', border: 'border-yellow-200', glow: 'drop-shadow-[0_0_8px_rgba(234,179,8,0.4)]', label: '传奇' }
  if (days >= 30) return { color: 'text-purple-500', fill: 'text-purple-400', bg: 'from-purple-50 via-fuchsia-50 to-pink-50', border: 'border-purple-200', glow: 'drop-shadow-[0_0_8px_rgba(168,85,247,0.4)]', label: '大师' }
  if (days >= 7) return { color: 'text-blue-500', fill: 'text-blue-400', bg: 'from-blue-50 via-cyan-50 to-sky-50', border: 'border-blue-200', glow: 'drop-shadow-[0_0_8px_rgba(59,130,246,0.3)]', label: '进阶' }
  return { color: 'text-orange-500', fill: 'text-orange-400', bg: 'from-amber-50 via-orange-50 to-red-50', border: 'border-orange-200', glow: '', label: '起步' }
}

function getNextMilestone(days: number): { target: number; label: string } {
  if (days < 3) return { target: 3, label: '青铜徽章' }
  if (days < 7) return { target: 7, label: '白银徽章' }
  if (days < 14) return { target: 14, label: '黄金徽章' }
  if (days < 30) return { target: 30, label: '铂金徽章' }
  if (days < 90) return { target: 90, label: '钻石徽章' }
  return { target: Math.ceil(days / 100) * 100 + 100, label: '传奇徽章' }
}

const DIFFICULTY_MAP: Record<string, { label: string; color: string }> = {
  easy: { label: '简单', color: 'bg-green-100 text-green-600' },
  medium: { label: '中等', color: 'bg-yellow-100 text-yellow-600' },
  hard: { label: '困难', color: 'bg-red-100 text-red-500' },
}

function getDailyErrorViewModel(error?: DailyApiError | null, fallbackMessage?: string) {
  switch (error?.errorCode) {
    case 'daily_bank_empty':
      return {
        title: '当前没有可用题目',
        description: '本地题库里暂时没有可用的编程题，可以稍后再试，或先去练习页和资源页学习。',
        actionLabel: '稍后重试',
      }
    case 'daily_resource_missing':
      return {
        title: '题目资源已失效',
        description: '题目记录还在，但对应资源不存在了。重新加载通常可以拿到新的题目。',
        actionLabel: '重新加载',
      }
    case 'daily_conflict':
      return {
        title: '题目正在生成中',
        description: '刚刚发生了并发生成冲突，重新加载一次通常就能拿到已经生成好的题目。',
        actionLabel: '重新加载',
      }
    default:
      return {
        title: fallbackMessage || error?.message || '题目加载失败，请稍后重试',
        description: error?.errorDetail || '如果反复失败，可以先刷新页面或稍后重试。',
        actionLabel: '重新加载',
      }
  }
}

const DailyChallengeView: React.FC = () => {
  const authStore = useAuthStore()
  const showToast = useAppStore((state) => state.showToast)
  const openRightPanel = useAppStore((state) => state.openRightPanel)
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [loadErrorMeta, setLoadErrorMeta] = useState<DailyApiError | null>(null)
  const [challenge, setChallenge] = useState<DailyChallengeData | null>(null)
  const [code, setCode] = useState('')
  const [output, setOutput] = useState('')
  const [outputType, setOutputType] = useState<'success' | 'error' | ''>('')
  const [isRunning, setIsRunning] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<DailySubmitResult | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [errorLines, setErrorLines] = useState<Set<number>>(new Set())
  const [hints, setHints] = useState<string[]>([])
  const [hintLoading, setHintLoading] = useState(false)

  const [copied, setCopied] = useState(false)
  const [savedDaily, setSavedDaily] = useState(false)
  const [savedExtra, setSavedExtra] = useState(false)
  const [savingBookmark, setSavingBookmark] = useState(false)

  // Extra challenge state
  const [extraChallenge, setExtraChallenge] = useState<NextChallengeData | null>(null)
  const [extraSubmitResult, setExtraSubmitResult] = useState<NextChallengeSubmitResult | null>(null)
  const [isExtraMode, setIsExtraMode] = useState(false)
  const [extraLoading, setExtraLoading] = useState(false)
  const [isExtraSubmitting, setIsExtraSubmitting] = useState(false)
  const [extraHints, setExtraHints] = useState<string[]>([])

  const outputRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const errorHighlighter = useMemo(() => createErrorLineHighlighter(errorLines), [errorLines])
  const extensions = useMemo(() => [python(), autoCloseBrackets, errorHighlighter], [errorHighlighter])

  const clearTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }, [])

  useEffect(() => () => clearTimer(), [clearTimer])

  const loadTodayChallenge = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    setLoadErrorMeta(null)
    try {
      const data = await getTodayChallenge()
      setChallenge(data)
      setSavedDaily(false)
    } catch (e: unknown) {
      const error = e instanceof DailyApiError ? e : null
      const msg = e instanceof Error ? e.message : '题目加载失败，请稍后重试'
      setChallenge(null)
      setLoadError(msg)
      setLoadErrorMeta(error)
      showToast(msg, 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => {
    void loadTodayChallenge()
  }, [loadTodayChallenge])

  const streak = challenge?.streak
  const stats = challenge?.completion_stats
  const isCompleted = challenge?.challenge.completed ?? false
  const currentStreak = streak?.current_streak ?? 0
  const longestStreak = streak?.longest_streak ?? 0
  const isBroken = streak?.streak_status === 'broken'
  const recoveryProgress = streak?.recovery_progress ?? 0
  const theme = getStreakTheme(currentStreak)
  const milestone = getNextMilestone(currentStreak)
  const diffInfo = DIFFICULTY_MAP[challenge?.challenge.difficulty ?? 'medium'] ?? DIFFICULTY_MAP.medium

  const runCode = useCallback(async () => {
    if (isRunning || !code.trim()) return
    setIsRunning(true); setOutput(''); setOutputType(''); setErrorLines(new Set()); setElapsed(0)
    const t0 = Date.now()
    timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 100)
    try {
      const result = await executeCode(code, 10)
      clearTimer(); setElapsed(result.total_time)
      const cleanStdout = cleanOutput(result.stdout)
      const cleanStderr = cleanOutput(result.stderr)
      if (result.success) {
        setOutput(cleanStdout || '代码执行成功，无输出'); setOutputType('success'); setErrorLines(new Set())
        const activeChallenge = isExtraMode ? extraChallenge?.challenge : challenge?.challenge
        recordLearningEvent({
          userId: authStore.userId,
          sourcePage: 'daily-challenge',
          actionType: 'code_run_success',
          topic: activeChallenge?.knowledge_point || (isExtraMode ? '额外挑战' : '每日一题'),
          knowledgePoint: activeChallenge?.knowledge_point || undefined,
          resourceId: activeChallenge?.resource_id,
          duration: Math.round((result.total_time || result.execution_time * 1000 || 0) / 1000),
          score: 80,
        })
      } else {
        setOutput(cleanStderr || '执行失败'); setOutputType('error'); setErrorLines(parseErrorLines(cleanStderr))
      }
      requestAnimationFrame(() => { if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight })
    } catch (e: unknown) {
      clearTimer(); setOutput(e instanceof Error ? e.message : '未知错误'); setOutputType('error')
    } finally { setIsRunning(false) }
  }, [authStore.userId, challenge, clearTimer, code, extraChallenge, isExtraMode, isRunning, recordLearningEvent])

  const handleSubmit = useCallback(async () => {
    if (isSubmitting || !code.trim() || isCompleted) return
    setIsSubmitting(true)
    try {
      const result = await submitDailyAnswer(code)
      setSubmitResult(result)
      recordLearningEvent({
        userId: authStore.userId,
        sourcePage: 'daily-challenge',
        actionType: result.is_correct ? 'challenge_passed' : 'challenge_submitted',
        topic: challenge?.challenge.knowledge_point || challenge?.challenge.title || '每日一题',
        knowledgePoint: challenge?.challenge.knowledge_point || undefined,
        resourceId: challenge?.challenge.resource_id,
        score: result.is_correct ? 100 : 45,
      })
      if (challenge) {
        setChallenge({ ...challenge, challenge: { ...challenge.challenge, completed: true, is_correct: result.is_correct }, streak: result.streak })
      }
      // 打开右侧面板显示解题思路
      openRightPanel('challenge-solution', {
        challenge: challenge?.challenge,
        submitResult: result,
        code,
        hints,
      })
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '提交失败，请稍后重试', 'error')
    } finally { setIsSubmitting(false) }
  }, [authStore.userId, challenge, code, hints, isCompleted, isSubmitting, openRightPanel, recordLearningEvent, showToast])

  const handleHint = useCallback(async () => {
    if (hintLoading || hints.length >= 3) return
    setHintLoading(true)
    try {
      const result = await getDailyHint(hints.length)
      setHints((prev) => [...prev, result.hint])
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '获取提示失败，请稍后重试', 'error')
    } finally { setHintLoading(false) }
  }, [hintLoading, hints.length, showToast])

  const resetCode = useCallback(() => {
    setCode(''); setOutput(''); setOutputType(''); setErrorLines(new Set()); setSubmitResult(null)
    if (isExtraMode) setExtraSubmitResult(null)
  }, [isExtraMode])

  const copyOutput = useCallback(() => {
    if (!output) return
    navigator.clipboard.writeText(output).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500) })
  }, [output])

  const handleBookmark = useCallback(async () => {
    if (savingBookmark) return
    const resourceId = isExtraMode ? extraChallenge?.challenge.resource_id : challenge?.challenge.resource_id
    if (!resourceId) return
    setSavingBookmark(true)
    try {
      const resp = await addToLibrary(resourceId, authStore.userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library: boolean })?.in_library
        if (isExtraMode) setSavedExtra(newState)
        else setSavedDaily(newState)
        showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
      } else {
        showToast(resp.message || '操作失败', 'error')
      }
    } catch {
      showToast('操作失败，请重试', 'error')
    } finally {
      setSavingBookmark(false)
    }
  }, [savingBookmark, isExtraMode, extraChallenge, challenge, authStore.userId, showToast])

  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runCode() }
  }, [runCode])

  // --- Extra challenge handlers ---
  const loadNextChallenge = useCallback(async () => {
    setExtraLoading(true)
    try {
      const data = await getNextChallenge()
      setExtraChallenge(data)
      setIsExtraMode(true)
      setCode('')
      setOutput('')
      setOutputType('')
      setErrorLines(new Set())
      setSubmitResult(null)
      setExtraSubmitResult(null)
      setExtraHints([])
      setSavedExtra(false)
    } catch (e: unknown) {
      const error = e instanceof DailyApiError ? e : null
      const viewModel = getDailyErrorViewModel(error, e instanceof Error ? e.message : '加载失败，请重试')
      const msg = viewModel.title
      setOutput(`${viewModel.title}\n${viewModel.description}`)
      setOutputType('error')
      showToast(msg, 'error')
    } finally { setExtraLoading(false) }
  }, [showToast])

  const handleExtraSubmit = useCallback(async () => {
    if (isExtraSubmitting || !code.trim() || !extraChallenge) return
    setIsExtraSubmitting(true)
    try {
      const result = await submitNextChallenge(extraChallenge.challenge.resource_id, code)
      setExtraSubmitResult(result)
      recordLearningEvent({
        userId: authStore.userId,
        sourcePage: 'daily-challenge',
        actionType: result.is_correct ? 'challenge_passed' : 'challenge_submitted',
        topic: extraChallenge.challenge.knowledge_point || extraChallenge.challenge.title || '额外挑战',
        knowledgePoint: extraChallenge.challenge.knowledge_point || undefined,
        resourceId: extraChallenge.challenge.resource_id,
        score: result.is_correct ? 100 : 45,
      })
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '提交失败，请稍后重试', 'error')
    } finally { setIsExtraSubmitting(false) }
  }, [authStore.userId, code, extraChallenge, isExtraSubmitting, recordLearningEvent, showToast])

  const backToDaily = useCallback(() => {
    setIsExtraMode(false)
    setExtraChallenge(null)
    setExtraSubmitResult(null)
    setExtraHints([])
    setSavedExtra(false)
    setCode('')
    setOutput('')
    setOutputType('')
    setErrorLines(new Set())
  }, [])

  const handleExtraHint = useCallback(async () => {
    if (hintLoading || extraHints.length >= 3 || !extraChallenge) return
    setHintLoading(true)
    try {
      const result = await getNextChallengeHint(extraChallenge.challenge.resource_id, extraHints.length)
      setExtraHints((prev) => [...prev, result.hint])
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '获取提示失败，请稍后重试', 'error')
    } finally { setHintLoading(false) }
  }, [hintLoading, extraHints.length, extraChallenge, showToast])

  // --- Loading / Error ---
  if (loading) return (
    <div className="flex-1 flex items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-3">
        <span className="w-8 h-8 border-3 border-gray-200 border-t-green-500 rounded-full animate-spin" />
        <span className="text-sm text-gray-400">加载今日题目...</span>
      </div>
    </div>
  )

  if (!challenge) return (
    <div className="flex-1 flex items-center justify-center bg-gray-50">
      <div className="flex flex-col items-center gap-3 text-center px-6 max-w-md">
        <div className="text-base font-semibold text-gray-700">
          {getDailyErrorViewModel(loadErrorMeta, loadError).title}
        </div>
        <div className="text-sm text-gray-500 leading-6">
          {getDailyErrorViewModel(loadErrorMeta, loadError).description}
        </div>
        <button
          onClick={loadTodayChallenge}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-500 transition-colors"
        >
          {getDailyErrorViewModel(loadErrorMeta, loadError).actionLabel}
        </button>
      </div>
    </div>
  )

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-gray-50" onKeyDown={handleKeydown}>
      <div className="flex-1 flex min-h-0 overflow-hidden">

        {/* ==================== LEFT PANEL ==================== */}
        <div className="w-[42%] min-w-[360px] flex flex-col border-r border-gray-200 bg-white overflow-hidden">

          {/* Zone 1: Streak / Achievement */}
          <div className={`flex-shrink-0 px-6 py-5 bg-gradient-to-br ${theme.bg} border-b ${theme.border}`}>
            <div className="flex items-center justify-between">
              {/* Fire + count */}
              <div className="flex items-center gap-4">
                <div className="relative">
                  <div className={`transition-transform ${currentStreak > 0 ? 'animate-pulse' : ''}`}>
                    <Flame
                      className={`w-12 h-12 ${theme.glow} ${isBroken ? 'text-gray-300' : theme.color}`}
                      fill={isBroken ? 'none' : currentStreak > 0 ? 'currentColor' : 'none'}
                      strokeWidth={isBroken ? 1.5 : 0}
                    />
                  </div>
                  {currentStreak >= 7 && !isBroken && (
                    <div className="absolute -top-1 -right-1 w-5 h-5 bg-white rounded-full flex items-center justify-center shadow-sm">
                      <Zap className="w-3 h-3 text-yellow-500" fill="currentColor" />
                    </div>
                  )}
                </div>
                <div>
                  <div className={`text-4xl font-black leading-none ${isBroken ? 'text-gray-300 line-through' : theme.color}`}>
                    {isBroken ? currentStreak : currentStreak}
                  </div>
                  <div className="text-sm text-gray-500 font-medium mt-1">天连续打卡</div>
                </div>
              </div>

              {/* Right side: best + badge */}
              <div className="flex flex-col items-end gap-2">
                <div className="flex items-center gap-1.5 text-xs text-gray-400">
                  <Trophy className="w-3.5 h-3.5" />
                  <span>最长 <b className="text-gray-600">{longestStreak}</b> 天</span>
                </div>
                {!isBroken && currentStreak > 0 && (
                  <span className={`px-2.5 py-1 rounded-full text-xs font-bold ${theme.color} bg-white/60 backdrop-blur-sm`}>
                    {theme.label}
                  </span>
                )}
              </div>
            </div>

            {/* Broken streak recovery */}
            {isBroken && (
              <div className="mt-4 p-3 bg-white/60 rounded-xl backdrop-blur-sm">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-semibold text-red-500">火花已断，恢复中</span>
                  <span className="text-xs text-gray-400">{recoveryProgress}/3</span>
                </div>
                <div className="flex gap-1.5">
                  {[0, 1, 2].map((i) => (
                    <div key={i} className={`flex-1 h-2 rounded-full transition-all duration-500 ${
                      i < recoveryProgress ? 'bg-green-400 shadow-sm shadow-green-200' : 'bg-gray-200'
                    }`} />
                  ))}
                </div>
                <p className="text-xs text-gray-400 mt-2">连续答对 3 题即可恢复火花，答错会重置恢复进度</p>
              </div>
            )}

            {/* Milestone progress (when active) */}
            {!isBroken && currentStreak > 0 && (
              <div className="mt-3">
                <div className="flex items-center justify-between text-xs text-gray-400 mb-1.5">
                  <span>距离 <b className="text-gray-500">{milestone.label}</b></span>
                  <span>{currentStreak}/{milestone.target}</span>
                </div>
                <div className="w-full h-1.5 bg-white/60 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${theme.color.replace('text-', 'bg-')}`}
                    style={{ width: `${Math.min(100, (currentStreak / milestone.target) * 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Zone 2: Question */}
          <div className="flex-1 overflow-auto">
            <div className="p-6">
              {/* Back button for extra mode */}
              {isExtraMode && (
                <button
                  onClick={backToDaily}
                  className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 mb-4 transition-colors"
                >
                  <ArrowLeft className="w-4 h-4" />
                  返回今日题目
                </button>
              )}

              {/* Question header */}
              <div className="flex items-center gap-2 mb-4 flex-wrap">
                {(() => {
                  const diff = isExtraMode ? (extraChallenge?.challenge.difficulty ?? 'medium') : (challenge.challenge.difficulty ?? 'medium')
                  const diffEntry = DIFFICULTY_MAP[diff] ?? DIFFICULTY_MAP.medium
                  return <span className={`px-2.5 py-1 rounded-md text-xs font-bold ${diffEntry.color}`}>{diffEntry.label}</span>
                })()}
                {(isExtraMode ? extraChallenge?.challenge.knowledge_point : challenge.challenge.knowledge_point) && (
                  <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-500">
                    {isExtraMode ? extraChallenge!.challenge.knowledge_point : challenge.challenge.knowledge_point}
                  </span>
                )}
                {/* Bookmark button */}
                <button
                  onClick={handleBookmark}
                  disabled={savingBookmark}
                  className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    (isExtraMode ? savedExtra : savedDaily)
                      ? 'bg-green-50 text-green-600 hover:bg-green-100'
                      : 'bg-amber-50 text-amber-600 hover:bg-amber-100'
                  } disabled:opacity-70`}
                  title={(isExtraMode ? savedExtra : savedDaily) ? '取消收藏' : '收藏到资源库'}
                >
                  <Bookmark className={`w-3.5 h-3.5 ${(isExtraMode ? savedExtra : savedDaily) ? 'fill-current' : ''}`} />
                  {(isExtraMode ? savedExtra : savedDaily) ? '已收藏' : '收藏'}
                </button>
                {!isExtraMode && isCompleted && (
                  <>
                    <span className={`ml-auto px-3 py-1 rounded-lg text-sm font-semibold ${
                      challenge.challenge.is_correct ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-500'
                    }`}>
                      {challenge.challenge.is_correct ? '已通过' : '未通过'}
                    </span>
                    <button
                      onClick={loadNextChallenge}
                      disabled={extraLoading}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-sm font-semibold bg-blue-600 text-white hover:bg-blue-500 active:scale-[0.97] shadow-sm shadow-blue-200 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {extraLoading ? (
                        <><span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" /> 生成中...</>
                      ) : (
                        <><ArrowRight className="w-3.5 h-3.5" /> 继续挑战</>
                      )}
                    </button>
                  </>
                )}
              </div>

              {/* Question text */}
              <div className="text-base text-gray-700 leading-relaxed whitespace-pre-wrap mb-4">
                {isExtraMode ? extraChallenge?.challenge.questionText : challenge.challenge.questionText}
              </div>
              {(isExtraMode ? extraChallenge?.challenge.options : challenge.challenge.options) && (isExtraMode ? extraChallenge!.challenge.options : challenge.challenge.options).length > 0 && (
                <div className="space-y-2 mb-4">
                  {(isExtraMode ? extraChallenge!.challenge.options : challenge.challenge.options).map((opt, i) => (
                    <div key={i} className="text-base text-gray-500 pl-1">{opt}</div>
                  ))}
                </div>
              )}

              {/* Hints */}
              <div className="mt-4">
                <button
                  onClick={isExtraMode ? handleExtraHint : handleHint}
                  disabled={hintLoading || (isExtraMode ? extraHints.length : hints.length) >= 3}
                  className="flex items-center gap-2 text-sm text-amber-600 hover:text-amber-700 disabled:text-gray-300 disabled:cursor-not-allowed transition-colors"
                >
                  <Lightbulb className="w-4 h-4" />
                  {(isExtraMode ? extraHints.length : hints.length) >= 3 ? '提示已用完' : hintLoading ? '生成中...' : `获取提示 (${isExtraMode ? extraHints.length : hints.length}/3)`}
                </button>
                {(isExtraMode ? extraHints : hints).length > 0 && (
                  <div className="mt-3 space-y-2">
                    {(isExtraMode ? extraHints : hints).map((h, i) => (
                      <div key={i} className="p-3 bg-amber-50 rounded-lg border border-amber-100">
                        <div className="text-xs text-amber-500 font-bold mb-1">提示 {i + 1}</div>
                        <div className="text-sm text-gray-700 leading-relaxed">{h}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Submit result (daily or extra) */}
            {(() => {
              const result = isExtraMode ? extraSubmitResult : submitResult
              if (!result) return null
              return (
                <div className="border-t border-gray-100 p-5 bg-gray-50/80">
                  <div className={`flex items-center gap-2 mb-2.5 ${result.is_correct ? 'text-green-600' : 'text-red-500'}`}>
                    {result.is_correct ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                    <span className="text-sm font-bold">{result.is_correct ? '恭喜，答对了！' : '答错了，继续努力'}</span>
                  </div>
                  {result.feedback && (
                    <div className="text-[13px] text-gray-600 mb-2.5">{result.feedback}</div>
                  )}
                  {!result.is_correct && result.correct_answer && (
                    <div className="mt-3">
                      <div className="text-xs text-gray-400 mb-1.5 font-medium">参考答案</div>
                      <pre className="text-[13px] text-green-700 bg-green-50 rounded-lg p-3.5 overflow-auto border border-green-100">{result.correct_answer}</pre>
                    </div>
                  )}
                  {result.explanation && (
                    <div className="mt-3.5">
                      <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-1.5 font-medium">
                        <Lightbulb className="w-3 h-3" /> 解析
                      </div>
                      <div className="text-[13px] text-gray-600 leading-relaxed">{result.explanation}</div>
                    </div>
                  )}
                  {isExtraMode && (
                    <div className="mt-4">
                      <button
                        onClick={backToDaily}
                        className="flex items-center gap-2 h-9 px-5 rounded-lg text-sm font-semibold text-gray-600 bg-gray-100 hover:bg-gray-200 transition-colors"
                      >
                        <ArrowLeft className="w-4 h-4" /> 返回今日题目
                      </button>
                    </div>
                  )}
                </div>
              )
            })()}
          </div>

          {/* Zone 3: Stats bar (bottom) */}
          <div className="flex-shrink-0 border-t border-gray-100 px-6 py-3 bg-gray-50/50">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5 text-xs text-gray-400">
                  <Users className="w-3.5 h-3.5" />
                  <span><b className="text-gray-600">{stats?.completed_users ?? 0}</b> 人已完成</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-gray-400">
                  <Target className="w-3.5 h-3.5" />
                  <span>正确率 <b className="text-gray-600">{stats?.correct_rate ?? 0}%</b></span>
                </div>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-gray-400">
                <Clock className="w-3.5 h-3.5" />
                <span>{isExtraMode ? '额外挑战' : '今日题目'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* ==================== RIGHT PANEL ==================== */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* Toolbar */}
          <div className="flex-shrink-0 h-12 px-4 flex items-center justify-between bg-[#1e1e2e] border-b border-gray-700/40">
            <div className="flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-green-400" />
              <span className="text-sm text-gray-300 font-medium">Python</span>
              <span className="text-xs text-gray-500 border-l border-gray-700 pl-3 ml-1">Ctrl+Enter 运行</span>
            </div>
            <div className="flex items-center gap-2">
              <button onClick={resetCode} className="p-2 text-gray-400 hover:text-gray-200 rounded-md transition-colors" title="重置代码">
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={runCode}
                disabled={isRunning || !code.trim()}
                className={`flex items-center gap-2 h-8 px-5 rounded-lg text-sm font-semibold transition-all shadow-sm ${
                  isRunning
                    ? 'bg-amber-500/20 text-amber-400 cursor-not-allowed'
                    : 'bg-green-600 text-white hover:bg-green-500 active:scale-[0.97] shadow-green-200'
                }`}
              >
                {isRunning ? (
                  <><span className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" /> 运行中 {formatTime(elapsed)}</>
                ) : (
                  <><Play className="w-4 h-4" /> 运行</>
                )}
              </button>
              {(isExtraMode || !isCompleted) && (
                <button
                  onClick={isExtraMode ? handleExtraSubmit : handleSubmit}
                  disabled={isExtraMode ? (isExtraSubmitting || !code.trim()) : (isSubmitting || !code.trim())}
                  className={`flex items-center gap-2 h-8 px-5 rounded-lg text-sm font-semibold transition-all shadow-sm ${
                    (isExtraMode ? isExtraSubmitting : isSubmitting)
                      ? 'bg-blue-500/20 text-blue-400 cursor-not-allowed'
                      : 'bg-blue-600 text-white hover:bg-blue-500 active:scale-[0.97] shadow-blue-200'
                  }`}
                >
                  {(isExtraMode ? isExtraSubmitting : isSubmitting) ? (
                    <><span className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" /> 判分中</>
                  ) : (
                    <><Send className="w-4 h-4" /> 提交答案</>
                  )}
                </button>
              )}
              {isExtraMode && (
                <button
                  onClick={backToDaily}
                  className="flex items-center gap-1.5 h-8 px-3 rounded-lg text-xs text-gray-400 hover:text-gray-200 transition-colors"
                  title="返回今日题目"
                >
                  <ArrowLeft className="w-3.5 h-3.5" />
                  今日题目
                </button>
              )}
            </div>
          </div>

          {/* Editor */}
          <div className="flex-[3] min-h-0 border-b border-gray-700/30">
            <CodeMirror
              value={code}
              onChange={setCode}
              theme={oneDark}
              extensions={extensions}
              indentWithTab={true}
              basicSetup={BASIC_SETUP}
              style={{ height: '100%', fontSize: '14px' }}
              height="100%"
            />
          </div>

          {/* Output */}
          <div className="flex-[2] min-h-0 flex flex-col bg-[#1e1e2e]">
            <div className="flex-shrink-0 px-4 py-2.5 flex items-center justify-between border-b border-gray-700/30">
              <div className="flex items-center gap-2">
                <span className={`w-2.5 h-2.5 rounded-full transition-colors ${
                  outputType === 'success' ? 'bg-green-400' : outputType === 'error' ? 'bg-red-400' : 'bg-gray-500'
                }`} />
                <span className="text-sm text-gray-300 font-medium">输出</span>
                {isRunning && <span className="text-xs text-amber-400 ml-2">{formatTime(elapsed)}</span>}
              </div>
              <div className="flex items-center gap-2">
                {output && !isRunning && (
                  <span className="text-xs text-gray-500">{formatTime(elapsed)}</span>
                )}
                {output && (
                  <button onClick={copyOutput} className="p-1.5 text-gray-500 hover:text-gray-300 rounded transition-colors" title="复制输出">
                    {copied ? <Check className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                )}
              </div>
            </div>
            <div ref={outputRef} className="flex-1 p-4 overflow-auto">
              {(isExtraMode ? extraSubmitResult : submitResult) ? (
                (() => {
                  const result = isExtraMode ? extraSubmitResult! : submitResult!
                  return (
                    <div className="space-y-3">
                      <div className={`flex items-center gap-2 text-sm font-bold ${result.is_correct ? 'text-green-400' : 'text-red-400'}`}>
                        {result.is_correct ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                        {result.is_correct ? '测试通过！' : '未通过'}
                      </div>
                      {result.feedback && <div className="text-sm text-gray-300 leading-relaxed">{result.feedback}</div>}
                      {!result.is_correct && result.correct_answer && (
                        <pre className="text-sm text-green-400 bg-black/30 rounded-lg p-3 overflow-auto">{result.correct_answer}</pre>
                      )}
                      {result.explanation && <div className="text-sm text-gray-400 leading-relaxed">{result.explanation}</div>}
                      <button
                        onClick={loadNextChallenge}
                        disabled={extraLoading}
                        className="flex items-center gap-2 mt-2 h-8 px-4 rounded-lg text-sm font-semibold bg-blue-600 text-white hover:bg-blue-500 transition-all disabled:opacity-50"
                      >
                        {extraLoading ? (
                          <><span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> 生成中...</>
                        ) : (
                          <><ArrowRight className="w-4 h-4" /> 继续挑战</>
                        )}
                      </button>
                    </div>
                  )
                })()
              ) : output ? (
                <pre className={`text-sm font-mono whitespace-pre-wrap break-words ${outputType === 'error' ? 'text-red-400' : 'text-green-400'}`}>{output}</pre>
              ) : isRunning ? (
                <div className="flex items-center gap-2 text-amber-400 text-sm">
                  <span className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin" />
                  正在执行代码...
                </div>
              ) : (
                <div className="text-gray-500 text-sm space-y-1.5">
                  <p>编写代码后点击 <span className="text-gray-400 font-medium">运行</span> 测试</p>
                  <p>满意后点击 <span className="text-gray-400 font-medium">提交答案</span> 判分</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

export default DailyChallengeView
