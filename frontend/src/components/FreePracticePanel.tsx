import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { Play, Send, CheckCircle, XCircle, RotateCcw, Lightbulb, Copy, Check, Bookmark, Sparkles, ChevronDown } from 'lucide-react'
import { executeCode } from '../api/code'
import { generateCodeQuiz, type FreePracticeQuestion } from '../api/playground'
import { submitQuizAnswer } from '../api/quiz'
import { addToLibrary } from '../api/resource'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useLearningCenterStore } from '../stores/learningCenter'
import { PYTHON_KNOWLEDGE_POINTS } from '../utils/constants'
import {
  autoCloseBrackets, createErrorLineHighlighter, BASIC_SETUP,
  cleanOutput, formatTime, parseErrorLines,
} from '../utils/codeEditor'

interface SubmitResult {
  is_correct: boolean
  correct_answer: string
  explanation: string
  feedback: string
  score: number
}

const DIFFICULTY_OPTIONS: { value: 'easy' | 'medium' | 'hard'; label: string; color: string }[] = [
  { value: 'easy', label: '简单', color: 'bg-green-100 text-green-600 border-green-200' },
  { value: 'medium', label: '中等', color: 'bg-yellow-100 text-yellow-600 border-yellow-200' },
  { value: 'hard', label: '困难', color: 'bg-red-100 text-red-500 border-red-200' },
]

const FreePracticePanel: React.FC = () => {
  const authStore = useAuthStore()
  const showToast = useAppStore((s) => s.showToast)
  const openRightPanel = useAppStore((s) => s.openRightPanel)
  const recordLearningEvent = useLearningCenterStore((s) => s.recordEvent)

  // 配置
  const [kp, setKp] = useState<string>(PYTHON_KNOWLEDGE_POINTS[0])
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard'>('medium')
  const [kpDropdownOpen, setKpDropdownOpen] = useState(false)

  // 题目
  const [question, setQuestion] = useState<FreePracticeQuestion | null>(null)
  const [generating, setGenerating] = useState(false)

  // 编辑器/运行
  const [code, setCode] = useState('')
  const [output, setOutput] = useState('')
  const [outputType, setOutputType] = useState<'success' | 'error' | ''>('')
  const [isRunning, setIsRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [errorLines, setErrorLines] = useState<Set<number>>(new Set())

  // 提交
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [submitResult, setSubmitResult] = useState<SubmitResult | null>(null)
  const [codeStartTime, setCodeStartTime] = useState<number | null>(null)

  // 收藏
  const [savedBookmark, setSavedBookmark] = useState(false)
  const [savingBookmark, setSavingBookmark] = useState(false)

  const outputRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const errorHighlighter = useMemo(() => createErrorLineHighlighter(errorLines), [errorLines])
  const extensions = useMemo(() => [python(), autoCloseBrackets, errorHighlighter], [errorHighlighter])

  const clearTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null }
  }, [])

  useEffect(() => () => clearTimer(), [clearTimer])

  // 出题
  const generateQuestion = useCallback(async () => {
    if (generating) return
    setGenerating(true)
    setQuestion(null)
    setCode('')
    setOutput('')
    setOutputType('')
    setErrorLines(new Set())
    setSubmitResult(null)
    setSavedBookmark(false)
    try {
      const q = await generateCodeQuiz(kp, difficulty)
      setQuestion(q)
      setCodeStartTime(Date.now())
      showToast('题目已生成，开始作答吧', 'success')
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '出题失败，请稍后重试', 'error')
    } finally {
      setGenerating(false)
    }
  }, [generating, kp, difficulty, showToast])

  // 运行代码
  const runCode = useCallback(async () => {
    if (isRunning || !code.trim()) return
    setIsRunning(true); setOutput(''); setOutputType(''); setErrorLines(new Set()); setElapsed(0)
    const t0 = Date.now()
    timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 100)
    try {
      const result = await executeCode(code, 10, question?.knowledge_point)
      clearTimer(); setElapsed(result.total_time)
      const cleanStdout = cleanOutput(result.stdout)
      const cleanStderr = cleanOutput(result.stderr)
      if (result.success) {
        setOutput(cleanStdout || '代码执行成功，无输出'); setOutputType('success'); setErrorLines(new Set())
        if (question) {
          recordLearningEvent({
            userId: authStore.userId,
            sourcePage: 'free-practice',
            actionType: 'code_run_success',
            topic: question.knowledge_point,
            knowledgePoint: question.knowledge_point,
            resourceId: question.resource_id,
            duration: Math.round((result.total_time || result.execution_time * 1000 || 0) / 1000),
            score: 80,
          })
        }
      } else {
        setOutput(cleanStderr || '执行失败'); setOutputType('error'); setErrorLines(parseErrorLines(cleanStderr))
      }
      requestAnimationFrame(() => { if (outputRef.current) outputRef.current.scrollTop = outputRef.current.scrollHeight })
    } catch (e: unknown) {
      clearTimer(); setOutput(e instanceof Error ? e.message : '未知错误'); setOutputType('error')
    } finally { setIsRunning(false) }
  }, [authStore.userId, clearTimer, code, isRunning, question, recordLearningEvent])

  // 提交答案
  const handleSubmit = useCallback(async () => {
    if (isSubmitting || !code.trim() || !question) return
    setIsSubmitting(true)
    const spentTime = codeStartTime ? Math.round((Date.now() - codeStartTime) / 1000) : 0
    try {
      const resp = await submitQuizAnswer(question.resource_id, code, spentTime, 0)
      if (resp.code === 200 && resp.data) {
        const result = resp.data as SubmitResult
        setSubmitResult(result)
        recordLearningEvent({
          userId: authStore.userId,
          sourcePage: 'free-practice',
          actionType: result.is_correct ? 'challenge_passed' : 'challenge_submitted',
          topic: question.knowledge_point,
          knowledgePoint: question.knowledge_point,
          resourceId: question.resource_id,
          score: result.is_correct ? 100 : 45,
          duration: spentTime,
        })
        if (result.is_correct) {
          showToast('恭喜答对！', 'success')
        } else {
          showToast('答错了，已收录到错题本，可在错题本复习', 'info')
        }
        openRightPanel('challenge-solution', {
          challenge: {
            title: question.title,
            questionText: question.question_text,
            knowledge_point: question.knowledge_point,
          },
          submitResult: result,
          code,
        })
      } else {
        showToast(resp.message || '提交失败，请稍后重试', 'error')
      }
    } catch (e: unknown) {
      showToast(e instanceof Error ? e.message : '提交失败，请稍后重试', 'error')
    } finally { setIsSubmitting(false) }
  }, [authStore.userId, code, codeStartTime, isSubmitting, openRightPanel, question, recordLearningEvent, showToast])

  const resetCode = useCallback(() => {
    setCode(''); setOutput(''); setOutputType(''); setErrorLines(new Set()); setSubmitResult(null)
  }, [])

  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); runCode() }
  }, [runCode])

  const copyOutput = useCallback(() => {
    if (!output) return
    navigator.clipboard.writeText(output).then(() => {
      showToast('已复制', 'success')
    }).catch(() => {})
  }, [output, showToast])

  const handleBookmark = useCallback(async () => {
    if (savingBookmark || !question) return
    setSavingBookmark(true)
    try {
      const resp = await addToLibrary(question.resource_id, authStore.userId)
      if (resp.code === 200) {
        const newState = (resp.data as { in_library: boolean })?.in_library
        setSavedBookmark(newState)
        showToast(newState ? '已收藏到资源库' : '已取消收藏', 'success')
      } else {
        showToast(resp.message || '操作失败', 'error')
      }
    } catch {
      showToast('操作失败，请重试', 'error')
    } finally {
      setSavingBookmark(false)
    }
  }, [savingBookmark, question, authStore.userId, showToast])

  const diffInfo = DIFFICULTY_OPTIONS.find(d => d.value === (question?.difficulty || difficulty))

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-gray-50" onKeyDown={handleKeydown}>
      {/* 顶部配置条 */}
      <div className="flex-shrink-0 px-6 py-3 bg-white border-b border-gray-200">
        <div className="flex items-center gap-3">
          {/* 知识点下拉 */}
          <div className="relative">
            <button
              onClick={() => setKpDropdownOpen(!kpDropdownOpen)}
              disabled={generating}
              className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 bg-gray-50 border border-gray-200 rounded-lg hover:bg-gray-100 disabled:opacity-50 transition-colors min-w-[140px] justify-between"
            >
              <span className="truncate">{kp}</span>
              <ChevronDown className="w-4 h-4 flex-shrink-0" />
            </button>
            {kpDropdownOpen && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setKpDropdownOpen(false)} />
                <div className="absolute left-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-72 overflow-auto">
                  {PYTHON_KNOWLEDGE_POINTS.map((p) => (
                    <button
                      key={p}
                      onClick={() => { setKp(p); setKpDropdownOpen(false) }}
                      className={`w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors ${p === kp ? 'text-green-600 font-medium bg-green-50' : 'text-gray-700'}`}
                    >
                      {p}
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* 难度三选一 */}
          <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-1">
            {DIFFICULTY_OPTIONS.map(d => (
              <button
                key={d.value}
                onClick={() => setDifficulty(d.value)}
                disabled={generating}
                className={`px-3 py-1.5 text-xs font-semibold rounded-md transition-all ${
                  difficulty === d.value
                    ? 'bg-white text-gray-700 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                } disabled:opacity-50`}
              >
                {d.label}
              </button>
            ))}
          </div>

          {/* 出题按钮 */}
          <button
            onClick={generateQuestion}
            disabled={generating}
            className={`flex items-center gap-2 px-5 py-2 text-sm font-semibold rounded-lg transition-all ml-auto ${
              generating
                ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                : 'bg-green-600 text-white hover:bg-green-500 active:scale-[0.97] shadow-sm shadow-green-200'
            }`}
          >
            {generating ? (
              <>
                <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                出题中...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                {question ? '换一题' : '出题'}
              </>
            )}
          </button>
        </div>
      </div>

      {/* 主体：无题目时提示，有题目时分栏 */}
      {!question ? (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center px-6 max-w-md">
            <div className="mx-auto mb-4 w-16 h-16 rounded-full bg-green-50 flex items-center justify-center">
              <Sparkles className="w-8 h-8 text-green-500" />
            </div>
            <p className="text-base font-semibold text-gray-700 mb-2">选择知识点和难度，开始练习</p>
            <p className="text-sm text-gray-500 leading-6">
              AI 会生成编程题，判分后答错自动收录错题本，同步学习路径掌握度。
              <br />支持运行测试代码（Ctrl+Enter），满意后再提交判分。
            </p>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex min-h-0 overflow-hidden">
          {/* 左：题目 + 结果 */}
          <div className="w-[42%] min-w-[360px] flex flex-col border-r border-gray-200 bg-white overflow-hidden">
            <div className="flex-1 overflow-auto">
              <div className="p-6">
                {/* 题目头部 */}
                <div className="flex items-center gap-2 mb-4 flex-wrap">
                  {diffInfo && (
                    <span className={`px-2.5 py-1 rounded-md text-xs font-bold border ${diffInfo.color}`}>
                      {diffInfo.label}
                    </span>
                  )}
                  <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-500">
                    {question.knowledge_point}
                  </span>
                  {question.has_test_cases && (
                    <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-purple-50 text-purple-500">
                      测试用例判分
                    </span>
                  )}
                  <button
                    onClick={handleBookmark}
                    disabled={savingBookmark}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ml-auto ${
                      savedBookmark
                        ? 'bg-green-50 text-green-600 hover:bg-green-100'
                        : 'bg-amber-50 text-amber-600 hover:bg-amber-100'
                    } disabled:opacity-70`}
                  >
                    <Bookmark className={`w-3.5 h-3.5 ${savedBookmark ? 'fill-current' : ''}`} />
                    {savedBookmark ? '已收藏' : '收藏'}
                  </button>
                </div>

                <div className="text-base text-gray-700 leading-relaxed whitespace-pre-wrap mb-2">
                  {question.question_text}
                </div>
                <p className="text-xs text-gray-400 mt-4 flex items-center gap-1">
                  <Lightbulb className="w-3 h-3" />
                  编写代码后先点"运行"测试，再点"提交答案"判分
                </p>
              </div>

              {/* 提交结果 */}
              {submitResult && (
                <div className="border-t border-gray-100 p-5 bg-gray-50/80">
                  <div className={`flex items-center gap-2 mb-2.5 ${submitResult.is_correct ? 'text-green-600' : 'text-red-500'}`}>
                    {submitResult.is_correct ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                    <span className="text-sm font-bold">{submitResult.is_correct ? '恭喜，答对了！' : '答错了，继续努力'}</span>
                  </div>
                  {submitResult.feedback && (
                    <div className="text-[13px] text-gray-600 mb-2.5">{submitResult.feedback}</div>
                  )}
                  {!submitResult.is_correct && submitResult.correct_answer && (
                    <div className="mt-3">
                      <div className="text-xs text-gray-400 mb-1.5 font-medium">参考答案</div>
                      <pre className="text-[13px] text-green-700 bg-green-50 rounded-lg p-3.5 overflow-auto border border-green-100">{submitResult.correct_answer}</pre>
                    </div>
                  )}
                  {submitResult.explanation && (
                    <div className="mt-3.5">
                      <div className="flex items-center gap-1.5 text-xs text-gray-400 mb-1.5 font-medium">
                        <Lightbulb className="w-3 h-3" /> 解析
                      </div>
                      <div className="text-[13px] text-gray-600 leading-relaxed">{submitResult.explanation}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 右：编辑器 + 输出 */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
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
                <button
                  onClick={handleSubmit}
                  disabled={isSubmitting || !code.trim()}
                  className={`flex items-center gap-2 h-8 px-5 rounded-lg text-sm font-semibold transition-all shadow-sm ${
                    isSubmitting
                      ? 'bg-blue-500/20 text-blue-400 cursor-not-allowed'
                      : 'bg-blue-600 text-white hover:bg-blue-500 active:scale-[0.97] shadow-blue-200'
                  }`}
                >
                  {isSubmitting ? (
                    <><span className="w-4 h-4 border-2 border-blue-400/30 border-t-blue-400 rounded-full animate-spin" /> 判分中</>
                  ) : (
                    <><Send className="w-4 h-4" /> 提交答案</>
                  )}
                </button>
              </div>
            </div>

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
                  {output && !isRunning && <span className="text-xs text-gray-500">{formatTime(elapsed)}</span>}
                  {output && (
                    <button onClick={copyOutput} className="p-1.5 text-gray-500 hover:text-gray-300 rounded transition-colors" title="复制输出">
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
              <div ref={outputRef} className="flex-1 p-4 overflow-auto">
                {submitResult ? (
                  <div className="space-y-3">
                    <div className={`flex items-center gap-2 text-sm font-bold ${submitResult.is_correct ? 'text-green-400' : 'text-red-400'}`}>
                      {submitResult.is_correct ? <CheckCircle className="w-5 h-5" /> : <XCircle className="w-5 h-5" />}
                      {submitResult.is_correct ? '测试通过！' : '未通过'}
                    </div>
                    {submitResult.feedback && <div className="text-sm text-gray-300 leading-relaxed">{submitResult.feedback}</div>}
                    {!submitResult.is_correct && submitResult.correct_answer && (
                      <pre className="text-sm text-green-400 bg-black/30 rounded-lg p-3 overflow-auto">{submitResult.correct_answer}</pre>
                    )}
                    {submitResult.explanation && <div className="text-sm text-gray-400 leading-relaxed">{submitResult.explanation}</div>}
                  </div>
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
      )}
    </div>
  )
}

export default FreePracticePanel
