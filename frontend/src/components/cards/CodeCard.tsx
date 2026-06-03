import React, { useState, useMemo } from 'react'
import CodeMirror from '@uiw/react-codemirror'
import { python } from '@codemirror/lang-python'
import { oneDark } from '@codemirror/theme-one-dark'
import { executeCode } from '../../api/code'

interface CodeCardProps {
  data: {
    language?: string
    code?: string
    runnable?: boolean
    expectedOutput?: string
    hint?: string
    [key: string]: any
  }
}

const CodeCard: React.FC<CodeCardProps> = ({ data }) => {
  const initialCode = data?.code || ''
  const [code, setCode] = useState(initialCode)
  const [output, setOutput] = useState<string | null>(null)
  const [outputType, setOutputType] = useState<'success' | 'error' | null>(null)
  const [running, setRunning] = useState(false)
  const [elapsed, setElapsed] = useState<number | null>(null)

  const extensions = useMemo(() => [python()], [])

  const handleRun = async () => {
    setRunning(true)
    setOutput(null)
    setOutputType(null)
    setElapsed(null)

    const result = await executeCode(code, 10)

    if (result.success) {
      setOutput(result.stdout || '(无输出)')
      setOutputType('success')
    } else {
      setOutput(result.stderr || '执行失败')
      setOutputType('error')
    }
    setElapsed(result.execution_time)
    setRunning(false)
  }

  return (
    <div>
      {/* Code editor */}
      <div style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid #374151' }}>
        <CodeMirror
          value={code}
          onChange={(val) => setCode(val)}
          extensions={extensions}
          theme={oneDark}
          basicSetup={{
            lineNumbers: true,
            bracketMatching: true,
            tabSize: 4,
          }}
          style={{ fontSize: 13, maxHeight: 300 }}
        />
      </div>

      {/* Run button */}
      {data?.runnable !== false && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
          <button
            onClick={handleRun}
            disabled={running}
            style={{
              background: running ? '#9ca3af' : '#10b981',
              color: '#fff', border: 'none', borderRadius: 8,
              padding: '8px 16px', fontSize: 12, fontWeight: 600,
              cursor: running ? 'default' : 'pointer',
              display: 'flex', alignItems: 'center', gap: 4,
              minHeight: 36,
            }}
          >
            {running ? '⏳ 执行中...' : '▶ 运行'}
          </button>
          {elapsed !== null && (
            <span style={{ fontSize: 11, color: '#9ca3af' }}>
              耗时 {elapsed}ms
            </span>
          )}
        </div>
      )}

      {/* Output */}
      {output !== null && (
        <div style={{
          marginTop: 8, padding: '10px 12px', borderRadius: 8,
          background: outputType === 'success' ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${outputType === 'success' ? '#bbf7d0' : '#fecaca'}`,
        }}>
          <div style={{
            fontSize: 11, fontWeight: 600, marginBottom: 4,
            color: outputType === 'success' ? '#16a34a' : '#dc2626',
          }}>
            {outputType === 'success' ? '✅ 输出' : '❌ 错误'}
          </div>
          <pre style={{
            margin: 0, fontSize: 12, fontFamily: 'Consolas, Monaco, monospace',
            whiteSpace: 'pre-wrap', wordBreak: 'break-all',
            color: outputType === 'success' ? '#166534' : '#991b1b',
          }}>
            {output}
          </pre>
        </div>
      )}

      {/* Hint */}
      {data?.hint && (
        <div style={{
          marginTop: 8, padding: '8px 12px', borderRadius: 8,
          background: '#fffbeb', border: '1px solid #fde68a',
          fontSize: 12, color: '#92400e',
        }}>
          💡 提示：{data.hint}
        </div>
      )}
    </div>
  )
}

export default CodeCard
