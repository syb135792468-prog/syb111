/**
 * codeEditor.ts - 代码编辑器共享工具
 * 从 CodePlaygroundView 提取，供 DailyChallengeView 等复用
 */
import { EditorView, Decoration, DecorationSet, ViewPlugin, ViewUpdate } from '@codemirror/view'
import { EditorSelection, RangeSetBuilder } from '@codemirror/state'

// --- 括号自动补全 ---
const BRACKET_PAIRS: Record<string, string> = { '(': ')', '[': ']', '{': '}' }
const QUOTE_PAIRS: Record<string, string> = { "'": "'", '"': '"' }
const CLOSE_BEFORE = ')]}:;>'

export const autoCloseBrackets = EditorView.inputHandler.of((view, from, to, insert) => {
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
export function createErrorLineHighlighter(errorLines: Set<number>) {
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
export interface ExecResult {
  success: boolean
  stdout: string
  stderr: string
  execution_time: number
  network_time: number
  total_time: number
  timed_out: boolean
}

export interface HistoryEntry {
  id: number
  code: string
  success: boolean
  output: string
  execution_time: number
  timestamp: number
}

// --- 常量 ---
export const DEFAULT_CODE = `# 在这里输入你的 Python 代码
print("Hello, Python!")

# 试试计算
result = 1 + 2 * 3
print(f"计算结果: {result}")
`

export const CODE_SNIPPETS = [
  { label: 'for 循环', code: 'for i in range(5):\n    print(i)' },
  { label: '列表推导式', code: 'squares = [x**2 for x in range(10)]\nprint(squares)' },
  { label: '字典操作', code: 'd = {"name": "Python", "version": 3}\nfor k, v in d.items():\n    print(f"{k}: {v}")' },
  { label: '函数定义', code: 'def greet(name: str) -> str:\n    return f"Hello, {name}!"\n\nprint(greet("World"))' },
  { label: '异常处理', code: 'try:\n    result = 10 / 0\nexcept ZeroDivisionError as e:\n    print(f"错误: {e}")' },
  { label: '文件读写', code: 'import tempfile, os\npath = os.path.join(tempfile.gettempdir(), "test.txt")\nwith open(path, "w") as f:\n    f.write("Hello!")\nwith open(path) as f:\n    print(f.read())' },
  { label: '类定义', code: 'class Animal:\n    def __init__(self, name: str):\n        self.name = name\n    def speak(self) -> str:\n        return f"{self.name} makes a sound"\n\ncat = Animal("Cat")\nprint(cat.speak())' },
  { label: '排序算法', code: 'def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n-i-1):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr\n\nprint(bubble_sort([64, 34, 25, 12, 22, 11, 90]))' },
]

export const BASIC_SETUP = {
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

export function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1)
    req.onupgradeneeded = () => {
      req.result.createObjectStore(DB_STORE, { keyPath: 'id' })
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function saveHistory(entry: HistoryEntry): Promise<void> {
  try {
    const db = await openDB()
    const tx = db.transaction(DB_STORE, 'readwrite')
    const store = tx.objectStore(DB_STORE)
    store.put(entry)
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

export async function loadHistory(): Promise<HistoryEntry[]> {
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
export function cleanOutput(text: string): string {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '')
}

export function formatTime(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(1)
  return `${m}m ${s}s`
}

export function formatTimestamp(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`
}

export function parseErrorLines(stderr: string): Set<number> {
  const lines = new Set<number>()
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
