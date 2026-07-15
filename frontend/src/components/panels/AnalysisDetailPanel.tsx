import React, { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { explainText, followUpExplain } from '../../api/chat'
import MarkdownText from '../common/MarkdownText'
import { Code, Loader2, Sparkles, RotateCw, Copy, Check, Send, MessageSquareText } from 'lucide-react'

function clampText(text: string, maxLength: number): string {
  if (!text) return ''
  return text.length > maxLength ? `${text.slice(0, maxLength)}...` : text
}

const AnalysisDetailPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)

  const selectedCode = typeof data?.selectedCode === 'string' ? data.selectedCode : ''
  const fullContext = typeof data?.fullContext === 'string' ? data.fullContext : ''

  const [explanation, setExplanation] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [explanationId, setExplanationId] = useState<number | null>(null)
  const [copied, setCopied] = useState(false)

  const [followUpInput, setFollowUpInput] = useState('')
  const [followUpAnswer, setFollowUpAnswer] = useState('')
  const [followUpLoading, setFollowUpLoading] = useState(false)

  const generateExplanation = useCallback(async () => {
    if (!selectedCode) return
    setLoading(true)
    setError('')
    setExplanation('')
    setFollowUpAnswer('')
    setFollowUpInput('')
    setExplanationId(null)
    try {
      const context = clampText(fullContext, 4500)
      const resp = await explainText(selectedCode, 0, undefined, context)
      if (resp.code === 200 && resp.data) {
        const d = resp.data as { explanation?: string; id?: number }
        setExplanation(d.explanation || (resp.data as unknown as string) || '')
        setExplanationId(d.id || null)
      } else {
        setError(resp.message || '解释失败')
      }
    } catch {
      setError('生成解释失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [selectedCode, fullContext])

  // 选中代码变化时自动生成（用户主动选段触发，非路由进入触发）
  useEffect(() => {
    if (selectedCode) {
      generateExplanation()
    } else {
      setExplanation('')
      setError('')
      setExplanationId(null)
      setFollowUpAnswer('')
      setFollowUpInput('')
    }
  }, [selectedCode, generateExplanation])

  const handleCopy = useCallback(async () => {
    if (!explanation) return
    try {
      await navigator.clipboard.writeText(explanation)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }, [explanation])

  const handleFollowUp = useCallback(async () => {
    if (!followUpInput.trim()) return
    setFollowUpLoading(true)
    setFollowUpAnswer('')
    try {
      if (explanationId) {
        const resp = await followUpExplain(explanationId, followUpInput.trim())
        if (resp.code === 200 && resp.data) {
          const answer = typeof resp.data === 'string' ? resp.data : (resp.data as { answer?: string }).answer || ''
          setFollowUpAnswer(answer)
        }
      } else {
        const context = clampText(fullContext, 4500)
        const resp = await explainText(
          `关于这段代码的追问：${followUpInput.trim()}\n\n原始代码：\n${selectedCode}`,
          0,
          undefined,
          context,
        )
        if (resp.code === 200 && resp.data) {
          const d = resp.data as { explanation?: string }
          setFollowUpAnswer(d.explanation || '')
        }
      }
    } catch {
      setFollowUpAnswer('追问失败，请稍后重试')
    } finally {
      setFollowUpLoading(false)
    }
  }, [followUpInput, explanationId, selectedCode, fullContext])

  if (!selectedCode) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <Code className="w-8 h-8 mb-3 opacity-30" />
        <p className="text-sm text-center">在识别的代码中选中几行</p>
        <p className="text-xs text-center mt-1">点击浮动的"解释"按钮查看讲解</p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      {/* 选中代码片段 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-emerald-600">
            <Code className="w-3.5 h-3.5" />
            <span className="text-xs font-semibold uppercase tracking-wide">选中代码</span>
          </div>
          <button
            onClick={generateExplanation}
            disabled={loading}
            className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
          >
            <RotateCw className="w-3 h-3" />
            重新解释
          </button>
        </div>
        <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto font-mono leading-relaxed">
          {selectedCode}
        </pre>
      </div>

      {/* AI 解释 */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-blue-600">
            <Sparkles className="w-3.5 h-3.5" />
            <span className="text-xs font-semibold uppercase tracking-wide">AI 解释</span>
          </div>
          {explanation && !loading && (
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              {copied ? <Check className="w-3 h-3 text-emerald-500" /> : <Copy className="w-3 h-3" />}
              {copied ? '已复制' : '复制'}
            </button>
          )}
        </div>

        {loading && (
          <div className="flex items-center justify-center py-6 text-gray-400">
            <Loader2 className="w-4 h-4 animate-spin mr-2" />
            <span className="text-xs">AI 正在解释选中代码...</span>
          </div>
        )}

        {error && (
          <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-lg p-3">
            {error}
          </div>
        )}

        {explanation && !loading && (
          <div className="text-xs text-gray-700 leading-relaxed bg-blue-50 border border-blue-100 rounded-lg p-3">
            <MarkdownText content={explanation} />
          </div>
        )}
      </div>

      {/* 追问 */}
      {explanation && !loading && (
        <div>
          <div className="flex items-center gap-1.5 mb-2 text-violet-600">
            <MessageSquareText className="w-3.5 h-3.5" />
            <span className="text-xs font-semibold uppercase tracking-wide">追问</span>
          </div>
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={followUpInput}
              onChange={(e) => setFollowUpInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleFollowUp() }}
              placeholder="对这段代码还有疑问？"
              className="flex-1 px-2.5 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-violet-200 focus:border-transparent"
            />
            <button
              onClick={handleFollowUp}
              disabled={followUpLoading || !followUpInput.trim()}
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-white bg-violet-500 rounded-lg hover:bg-violet-600 transition-colors disabled:opacity-50"
            >
              {followUpLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : <Send className="w-3 h-3" />}
              追问
            </button>
          </div>
          {followUpAnswer && (
            <div className="text-xs text-gray-700 leading-relaxed bg-violet-50 border border-violet-100 rounded-lg p-3">
              <MarkdownText content={followUpAnswer} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default AnalysisDetailPanel
