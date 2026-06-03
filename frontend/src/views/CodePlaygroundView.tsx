import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { executeCode } from '../api/code'
import { Play, Trash2, RotateCcw, Zap, Wifi, Clock, ChevronDown, ChevronUp, Code2, History, X } from 'lucide-react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { EditorView, Decoration, DecorationSet, ViewPlugin, ViewUpdate } from '@codemirror/view'
import { EditorSelection, RangeSetBuilder } from '@codemirror/state'

// --- 括号自动补全 ---
const BRACKET_PAIRS: Record<string, string> = { '(': ')', '[': ']', '{': '}' }
const QUOTE_PAIRS: Record<string, string> = { "'": "'", '"': '"' }
const CLOSE_BEFORE = ')]}:;>'

const autoCloseBrackets = EditorView.inputHandler.of((view, from, to, insert) => {
  if (view.compositionStarted || view.state.readOnly) return false
  if (insert.length !== 1) return false
  if (from !== view.state.selection.main.from || to !== view.state.selection.main.to) return false

  const state = view.state
  const sel = state.selection.main

  if (BRACKET_PAIRS[insert]) {
    const close = BRACKET_PAIRS[insert]
    const next = state.sliceDoc(sel.head, sel.head + 1)
    if (!sel.empty) {
      const tr = state.update({
        changes: [{ insert, from: sel.from }, { insert: close, from: sel.to }],
        selection: EditorSelection.cursor(sel.head + 1),
        userEvent: 'input.type',
      })
      view.dispatch(tr)
      return true
    }
    if (!next || /\s/.test(next) || CLOSE_BEFORE.includes(next)) {
      const tr = state.update({
        changes: { insert: insert + close, from: sel.head },
        selection: EditorSelection.cursor(sel.head + 1),
        userEvent: 'input.type',
      })
      view.dispatch(tr)
      return true
    }
    return false
  }

  if (QUOTE_PAIRS[insert]) {
    const close = QUOTE_PAIRS[insert]
    const next = state.sliceDoc(sel.head, sel.head + 1)
    if (next === close) {
      view.dispatch({ selection: EditorSelection.cursor(sel.head + 1) })
      return true
    }
    if (!sel.empty) {
      const tr = state.update({
        changes: [{ insert, from: sel.from }, { insert: close, from: sel.to }],
        selection: EditorSelection.cursor(sel.head + 1),
        userEvent: 'input.type',
      })
      view.dispatch(tr)
      return true
    }
    if (!next || /\s/.test(next) || CLOSE_BEFORE.includes(next) || next === close) {
      const tr = state.update({
        changes: { insert: insert + close, from: sel.head },
        selection: EditorSelection.cursor(sel.head + 1),
        userEvent: 'input.type',
      })
      view.dispatch(tr)
      return true
    }
    return false
  }

  const closingChars = new Set(Object.values(BRACKET_PAIRS).concat(Object.values(QUOTE_PAIRS)))
  if (closingChars.has(insert) && state.sliceDoc(sel.head, sel.head + 1) === insert) {
    view.dispatch({ selection: EditorSelection.cursor(sel.head + 1) })
    return true
  }

  return false
})

// --- 错误行高亮 ---
function createErrorLineHighlighter(errorLines: Set<number>) {
  return ViewPlugin.fromClass(
    class {
      decorations: DecorationSet
      constructor(view: EditorView) {
        this.decorations = this.buildDecorations(view)
      }
      update(update: ViewUpdate) {
        if (update.docChanged || update.viewportChanged) {
          this.decorations = this.buildDecorations(update.view)
        }
      }
      buildDecorations(view: EditorView): DecorationSet {
        const builder = new RangeSetBuilder<Decoration>()
        for (const { from, to } of view.visibleRanges) {
          for (let pos = from; pos <= to; ) {
            const line = view.state.doc.lineAt(pos)
            const lineNum = line.number
            if (errorLines.has(lineNum)) {
              builder.add(
                line.from,
                line.from,
                Decoration.line({ class: 'cm-error-line' })
              )
            }
            pos = line.to + 1
          }
        }
        return builder.finish()
      }
    },
    { decorations: (v) => v.decorations }
  )
}

// --- 类型定义 ---
interface ExecResult {
  success: boolean
  stdout: string
  stderr: string
  execution_time: number
  network_time: number
  total_time: number
  timed_out: boolean
}

interface HistoryEntry {
  id: number
  code: string
  success: boolean
  output: string
  execution_time: number
  timestamp: number
}

// --- 常量 ---
const DEFAULT_CODE = `# 在这里输入你的 Python 代码
print("Hello, Python!")

# 试试计算
result = 1 + 2 * 3
print(f"计算结果: {result}")
`

const CODE_SNIPPETS = [
  { label: 'for 循环', code: 'for i in range(5):\n    print(i)' },
  { label: '列表推导式', code: 'squares = [x**2 for x in range(10)]\nprint(squares)' },
  { label: '字典操作', code: 'd = {"name": "Python", "version": 3}\nfor k, v in d.items():\n    print(f"{k}: {v}")' },
  { label: '函数定义', code: 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n\nprint(greet("World"))' },
  { label: '异常处理', code: 'try:\n    result = 10 / 0\nexcept ZeroDivisionError as e:\n    print(f"错误: {e}")' },
  { label: '文件读写', code: 'import tempfile, os\npath = os.path.join(tempfile.gettempdir(), "test.txt")\nwith open(path, "w") as f:\n    f.write("Hello!")\nwith open(path) as f:\n    print(f.read())' },
  { label: '类定义', code: 'class Animal:\n    def __init__(self, name: str):\n        self.name = name\n    def speak(self) -> str:\n        return f"{self.name} makes a sound"\n\ncat = Animal("Cat")\nprint(cat.speak())' },
  { label: '排序算法', code: 'def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n-i-1):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr\n\nprint(bubble_sort([64, 34, 25, 12, 22, 11, 90]))' },
]

const BASIC_SETUP = {
  lineNumbers: true,
  highlightActiveLineGutter: true,
  highlightActiveLine: true,
  bracketMatching: true,
  closeBrackets: false,
  indentOnInput: true,
  tabSize: 4,
  autocompletion: true,
}

// --- IndexedDB 历史记录 ---
const DB_NAME = 'code_playground'
const DB_STORE = 'history'
const MAX_HISTORY = 50

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DB_STORE, { keyPath: 'id' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function saveHistory(entry: HistoryEntry): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(DB_STORE, 'readwrite')
    const store = tx.objectStore(DB_STORE)
    store.put(entry)
    // 清理旧记录
    const allReq = store.getAll()
    allReq.onsuccess = () => {
      const items = allReq.result as HistoryEntry[]
      if (items.length > MAX_HISTORY) {
        const toDelete = items.sort((a, b) => a.timestamp - b.timestamp).slice(0, items.length - MAX_HISTORY)
        toDelete.forEach((item) => store.delete(item.id))
      }
    }
  } catch {
    // IndexedDB 不可用时静默失败
  }
}

async function loadHistory(): Promise<HistoryEntry[]> {
  try {
    const db = await openDB()
    const tx = db.transaction(DB_STORE, 'readonly')
    const store = tx.objectStore(DB_STORE)
    return new Promise((resolve) => {
      const req = store.getAll()
      req.onsuccess = () => resolve((req.result as HistoryEntry[]).sort((a, b) => b.timestamp - a.timestamp).slice(0, 20))
      req.onerror = () => resolve([])
    })
  } catch {
    return []
  }
}

// --- 工具函数 ---
function cleanOutput(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '')
}

function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(1)
  return `${m}m ${s}s`
}

function formatTimestamp(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
}

function parseErrorLines(stderr: string): Set<number> {
  const lines = new Set<number>()
  // 匹配 "line N" 或 "第N行" 模式
  const patterns = [/line\s+(\d+)/gi, /第\s*(\d+)\s*行/gi]
  for (const pat of patterns) {
    let m
    while ((m = pat.exec(stderr)) !== null) {
      const num = parseInt(m[1], 10)
      if (num > 0 && num < 1000) lines.add(num)
    }
  }
  return lines
}

// --- 组件 ---
const CodePlaygroundView: React.FC = () => {
  // --- 状态 ---
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
            <h1 className="text-lg font-bold text-gray-800">代码练习场</h1>
            <p className="text-xs text-gray-400 mt-0.5">在沙箱中安全运行 Python 代码 · Ctrl+Enter 运行</p>
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

      {/* Main: Editor + Output */}
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
    </div>
  )
}

export default CodePlaygroundView
