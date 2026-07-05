import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { executeCode } from '../api/code'
import { useAppStore } from '../stores/app'
import { Play, Trash2, RotateCcw, Zap, Wifi, Clock, ChevronDown, ChevronUp, Code2, History, MessageCircle } from 'lucide-react'
import type { EditorView } from '@codemirror/view'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import {
  autoCloseBrackets, createErrorLineHighlighter, BASIC_SETUP,
  DEFAULT_CODE, CODE_SNIPPETS,
  cleanOutput, formatTime, formatTimestamp, parseErrorLines,
  saveHistory, loadHistory,
  type ExecResult, type HistoryEntry,
} from '../utils/codeEditor'
import DailyChallengeView from './DailyChallengeView'

// --- 组件 ---
const CodePlaygroundView: React.FC = () => {
  // --- 状态 ---
  const [activeTab, setActiveTab] = useState<'daily' | 'free'>('daily')
  const [code, setCode] = useState(DEFAULT_CODE)
  const [output, setOutput] = useState('')
  const [outputType, setOutputType] = useState<'success' | 'error' | ''>('')
  const [isRunning, setIsRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [execResult, setExecResult] = useState<ExecResult | null>(null)
  const [errorLines, setErrorLines] = useState<Set<number>>(new Set())
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [showHistory, setShowHistory] = useState(false)
  const [showSnippets, setShowSnippets] = useState(false)

  // --- Refs ---
  const outputRef = useRef<HTMLDivElement>(null)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const editorViewRef = useRef<EditorView | null>(null)

  // --- CodeMirror 扩展 ---
  const errorHighlighter = useMemo(() => createErrorLineHighlighter(errorLines), [errorLines])
  const extensions = useMemo(() => [python(), autoCloseBrackets, errorHighlighter], [errorHighlighter])

  // --- 派生状态 ---
  const codeTrimmed = useMemo(() => code.trim(), [code])

  // --- 加载历史记录 ---
  useEffect(() => {
    loadHistory().then(setHistory)
  }, [])

  // --- 定时器清理 ---
  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => clearTimer()
  }, [clearTimer])

  // --- 运行代码 ---
  const runCode = useCallback(async () => {
    if (isRunning || !codeTrimmed) return

    setIsRunning(true)
    setOutput('')
    setOutputType('')
    setExecResult(null)
    setErrorLines(new Set())
    setElapsed(0)

    const t0 = Date.now()
    timerRef.current = setInterval(() => setElapsed(Date.now() - t0), 100)

    try {
      const result = await executeCode(code, 10)
      clearTimer()
      setElapsed(result.total_time)
      setExecResult(result)

      const cleanStdout = cleanOutput(result.stdout)
      const cleanStderr = cleanOutput(result.stderr)

      if (result.success) {
        setOutput(cleanStdout || '代码执行成功，无输出')
        setOutputType('success')
        setErrorLines(new Set())
      } else {
        setOutput(cleanStderr || '执行失败')
        setOutputType('error')
        setErrorLines(parseErrorLines(cleanStderr))
      }

      // 保存到历史记录
      const entry: HistoryEntry = {
        id: Date.now(),
        code,
        success: result.success,
        output: result.success ? cleanStdout : cleanStderr,
        execution_time: result.execution_time,
        timestamp: Date.now(),
      }
      saveHistory(entry)
      setHistory((prev) => [entry, ...prev].slice(0, 20))

      requestAnimationFrame(() => {
        if (outputRef.current) {
          outputRef.current.scrollTop = outputRef.current.scrollHeight
        }
      })
    } catch (e: unknown) {
      clearTimer()
      const msg = e instanceof Error ? e.message : '未知错误'
      setOutput(msg)
      setOutputType('error')
    } finally {
      setIsRunning(false)
    }
  }, [isRunning, codeTrimmed, code, clearTimer])

  // --- 清空输出 ---
  const clearOutput = useCallback(() => {
    setOutput('')
    setOutputType('')
    setExecResult(null)
    setElapsed(0)
    setErrorLines(new Set())
  }, [])

  // --- 重置代码 ---
  const resetCode = useCallback(() => {
    setCode(DEFAULT_CODE)
    clearOutput()
  }, [clearOutput])

  // --- 从历史恢复 ---
  const restoreFromHistory = useCallback((entry: HistoryEntry) => {
    setCode(entry.code)
    setShowHistory(false)
    clearOutput()
  }, [clearOutput])

  // --- 插入代码片段 ---
  const insertSnippet = useCallback((snippetCode: string) => {
    setCode((prev) => prev.trimEnd() + '\n\n' + snippetCode)
    setShowSnippets(false)
  }, [])

  // --- 解释选中代码 ---
  const handleExplainCode = useCallback(() => {
    const view = editorViewRef.current
    if (!view) return
    const selected = view.state.sliceDoc(view.state.selection.main.from, view.state.selection.main.to)
    const text = selected.trim()
    if (text) {
      useAppStore.getState().openRightPanel('code-explain', { code: text })
    } else {
      // 没有选区，解释全部代码
      useAppStore.getState().openRightPanel('code-explain', { code: code.trim() })
    }
  }, [code])

  // --- 键盘快捷键 ---
  const handleKeydown = useCallback((e: React.KeyboardEvent) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      runCode()
    }
  }, [runCode])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden" onKeyDown={handleKeydown}>
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-100 bg-white">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-bold text-gray-800">每日编程</h1>
            <p className="text-xs text-gray-400 mt-0.5">在沙箱中安全运行 Python 代码 · Ctrl+Enter 运行</p>
          </div>
          <div className="flex items-center gap-1.5 mr-4 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setActiveTab('daily')}
              className={`px-5 py-2 text-sm font-semibold rounded-md transition-all ${
                activeTab === 'daily'
                  ? 'bg-white text-green-600 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              每日一题
            </button>
            <button
              onClick={() => setActiveTab('free')}
              className={`px-5 py-2 text-sm font-semibold rounded-md transition-all ${
                activeTab === 'free'
                  ? 'bg-white text-green-600 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              自由练习
            </button>
          </div>
          <div className="flex items-center gap-2">
            {/* 代码片段下拉 */}
            <div className="relative">
              <button
                onClick={() => { setShowSnippets(!showSnippets); setShowHistory(false) }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <Code2 className="w-3.5 h-3.5" />
                代码模板
                {showSnippets ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showSnippets && (
                <div className="absolute right-0 top-full mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-72 overflow-auto">
                  {CODE_SNIPPETS.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => insertSnippet(s.code)}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 border-b border-gray-50 last:border-0 transition-colors"
                    >
                      <div className="font-medium text-gray-700">{s.label}</div>
                      <div className="text-gray-400 mt-0.5 truncate font-mono">{s.code.split('\n')[0]}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 历史记录下拉 */}
            <div className="relative">
              <button
                onClick={() => { setShowHistory(!showHistory); setShowSnippets(false) }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <History className="w-3.5 h-3.5" />
                历史
                {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
              {showHistory && (
                <div className="absolute right-0 top-full mt-1 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50 max-h-72 overflow-auto">
                  {history.length === 0 ? (
                    <div className="px-3 py-4 text-xs text-gray-400 text-center">暂无执行历史</div>
                  ) : (
                    history.map((h) => (
                      <button
                        key={h.id}
                        onClick={() => restoreFromHistory(h)}
                        className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 border-b border-gray-50 last:border-0 transition-colors"
                      >
                        <div className="flex items-center justify-between">
                          <span className={h.success ? 'text-green-600' : 'text-red-500'}>
                            {h.success ? '✓ 成功' : '✗ 失败'}
                          </span>
                          <span className="text-gray-400 flex items-center gap-1">
                            <Clock className="w-3 h-3" />
                            {formatTimestamp(h.timestamp)} · {formatTime(h.execution_time * 1000)}
                          </span>
                        </div>
                        <div className="text-gray-500 mt-0.5 truncate font-mono">{h.code.split('\n')[0]}</div>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>

            <button
              onClick={resetCode}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-gray-500 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              重置
            </button>
            <button
              onClick={handleExplainCode}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-blue-600 border border-blue-200 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors"
              title="解释选中的代码（未选中则解释全部）"
            >
              <MessageCircle className="w-3.5 h-3.5" />
              解释
            </button>
            <button
              onClick={runCode}
              disabled={isRunning || !codeTrimmed}
              className={`flex items-center gap-1.5 px-4 py-1.5 text-xs font-medium rounded-lg transition-all ${
                isRunning
                  ? 'bg-amber-500 text-white cursor-not-allowed'
                  : 'bg-green-600 text-white hover:bg-green-700'
              }`}
            >
              {isRunning ? (
                <>
                  <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin inline-block" />
                  运行中 {formatTime(elapsed)}
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  运行代码
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Main: Daily Challenge or Free Practice */}
      {activeTab === 'daily' ? (
        <DailyChallengeView />
      ) : (
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Editor */}
        <div className="flex-1 flex flex-col border-r border-gray-100 min-w-0">
          <div className="flex-shrink-0 px-4 py-2 bg-gray-800 text-white text-xs font-medium flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-green-400" />
            编辑器
          </div>
          <CodeMirror
            value={code}
            onChange={setCode}
            theme={oneDark}
            extensions={extensions}
            indentWithTab={true}
            basicSetup={BASIC_SETUP}
            style={{ flex: 1, fontSize: '14px' }}
            height="100%"
            onCreateEditor={(view) => { editorViewRef.current = view }}
          />
        </div>

        {/* Output */}
        <div className="flex-1 flex flex-col min-w-0">
          <div className="flex-shrink-0 px-4 py-2 bg-gray-800 text-white text-xs font-medium flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${
                outputType === 'success' ? 'bg-green-400' : outputType === 'error' ? 'bg-red-400' : 'bg-gray-500'
              }`} />
              输出
              {isRunning && (
                <span className="text-amber-300 ml-2">已等待 {formatTime(elapsed)}</span>
              )}
            </div>
            {execResult && !isRunning ? (
              <div className="flex items-center gap-3 text-gray-400">
                <span className="flex items-center gap-1">
                  <Zap className="w-3 h-3" />
                  执行 {formatTime((execResult.execution_time || 0) * 1000)}
                </span>
                <span className="flex items-center gap-1">
                  <Wifi className="w-3 h-3" />
                  网络 {formatTime(execResult.network_time || 0)}
                </span>
                {errorLines.size > 0 && (
                  <span className="text-red-400 flex items-center gap-1">
                    错误行: {Array.from(errorLines).join(', ')}
                  </span>
                )}
                <button
                  onClick={clearOutput}
                  className="flex items-center gap-1 text-gray-500 hover:text-gray-300 transition-colors ml-2"
                >
                  <Trash2 className="w-3 h-3" />
                  清空
                </button>
              </div>
            ) : !isRunning && output ? (
              <button
                onClick={clearOutput}
                className="text-gray-500 hover:text-gray-300 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            ) : null}
          </div>
          <div ref={outputRef} className="flex-1 bg-gray-900 p-4 overflow-auto">
            {output ? (
              <pre className={`text-sm font-mono whitespace-pre-wrap break-words ${
                outputType === 'error' ? 'text-red-400' : 'text-green-400'
              }`}>{output}</pre>
            ) : isRunning ? (
              <div className="flex items-center gap-2 text-amber-400 text-sm">
                <span className="w-4 h-4 border-2 border-amber-400/30 border-t-amber-400 rounded-full animate-spin inline-block" />
                正在执行代码...
              </div>
            ) : (
              <p className="text-gray-500 text-sm">点击"运行代码"或按 Ctrl+Enter 执行</p>
            )}
          </div>
        </div>
      </div>
      )}
    </div>
  )
}

export default CodePlaygroundView
