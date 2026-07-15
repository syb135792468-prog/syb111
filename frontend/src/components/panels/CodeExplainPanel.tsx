import React, { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { explainText, followUpExplain } from '../../api/chat'
import MarkdownText from '../common/MarkdownText'
import { Loader2, Copy, Check, Send, Code2, Sparkles, RotateCw, MessageSquareText } from 'lucide-react'

const CodeExplainPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const selectedCode = (data?.code as string) || ''

  const [explanation, setExplanation] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  // 追问
  const [followUpInput, setFollowUpInput] = useState('')
  const [followUpAnswer, setFollowUpAnswer] = useState('')
  const [followUpLoading, setFollowUpLoading] = useState(false)
  const [explanationId, setExplanationId] = useState<number | null>(null)

  // 生成解释
  const generateExplanation = useCallback(async () => {
    if (!selectedCode) return
    setLoading(true)
    setError('')
    setExplanation('')
    setFollowUpAnswer('')
    setFollowUpInput('')
    setExplanationId(null)
    try {
      const resp = await explainText(selectedCode, 0)
      if (resp.code === 200 && resp.data) {
        const d = resp.data as { explanation?: string; id?: number }
        setExplanation(d.explanation || (resp.data as unknown as string) || '')
        setExplanationId(d.id || null)
      } else {
        setError(resp.message || '解释失败')
      }
    } catch (e) {
      setError('生成解释失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [selectedCode])

  // 新代码传入时自动生成
  useEffect(() => {
    if (selectedCode) {
      generateExplanation()
    }
  }, [selectedCode])

  // 复制
  const handleCopy = useCallback(async () => {
    if (!explanation) return
    try {
      await navigator.clipboard.writeText(explanation)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }, [explanation])

  // 追问
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
        // 没有 explanationId，直接用 explainText 做追问
        const resp = await explainText(`关于这段代码的追问：${followUpInput.trim()}\n\n原始代码：\n${selectedCode}`, 0)
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
  }, [followUpInput, explanationId, selectedCode])

  if (!selectedCode) {
    return (
      <div className="flex h-full items-center justify-center px-5 py-6">
        <div className="w-full rounded-[26px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.96),rgba(240,245,252,0.94))] p-6 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_20px_48px_rgba(148,163,184,0.10)]">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-slate-300/76 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(235,241,249,0.92))] shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_12px_28px_rgba(148,163,184,0.12)]">
            <Code2 className="h-7 w-7 text-brand-500" />
          </div>
          <div className="mb-2 inline-flex items-center rounded-full border border-slate-300/76 bg-white/82 px-3 py-1 text-[11px] font-semibold tracking-[0.16em] text-slate-600">
            CODE EXPLAIN
          </div>
          <p className="text-sm font-semibold text-slate-800">代码解释</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">在编辑器中选中代码并点击“解释”后，这里会生成结构化说明和追问结果。</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col overflow-y-auto px-4 py-4">
      <div className="space-y-4">
        <section className="rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.96),rgba(240,245,252,0.94))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_20px_48px_rgba(148,163,184,0.10)]">
          <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-slate-300/76 bg-white/82 px-3 py-1 text-[11px] font-semibold tracking-[0.16em] text-slate-600">
            <Sparkles className="h-3.5 w-3.5" />
            SELECTED CODE
          </div>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">当前代码片段</p>
              <p className="text-[11px] text-slate-500">右侧会基于这段代码生成解释、追问和复用内容。</p>
            </div>
            <button
              onClick={generateExplanation}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300/76 bg-white/82 px-3 py-2 text-xs font-medium text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)] transition-all hover:border-slate-400/70 hover:text-brand-700"
            >
              <RotateCw className="h-3.5 w-3.5" />
              重新解释
            </button>
          </div>
          <div className="rounded-[20px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(248,250,252,0.94),rgba(241,245,249,0.94))] p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]">
            <pre className="max-h-40 overflow-x-auto overflow-y-auto rounded-2xl bg-slate-900 p-3 font-mono text-xs leading-relaxed text-slate-100">
              {selectedCode}
            </pre>
          </div>
        </section>

        <section className="rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.94),rgba(242,246,252,0.92))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_18px_42px_rgba(148,163,184,0.08)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-slate-700">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl border border-slate-300/76 bg-white/82 text-brand-600">
                <Code2 className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-500">AI 解释</p>
                <p className="text-[11px] text-slate-400">用更容易理解的方式拆解当前代码</p>
              </div>
            </div>
            {explanation && !loading && (
              <button
                onClick={handleCopy}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300/76 bg-white/82 px-3 py-2 text-xs font-medium text-slate-600 transition-all hover:border-slate-400/70 hover:text-brand-700"
              >
                {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />}
                {copied ? '已复制' : '复制内容'}
              </button>
            )}
          </div>

        {loading && (
          <div className="flex flex-col items-center justify-center rounded-[20px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.92),rgba(241,245,251,0.92))] py-10 text-slate-500 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]">
            <Loader2 className="mb-2 h-5 w-5 animate-spin text-brand-500" />
            <p className="text-xs font-medium tracking-[0.14em] text-slate-700">正在分析代码...</p>
            <p className="mt-1 text-[11px] text-slate-400">AI 正在整理逻辑、语法和关键流程</p>
          </div>
        )}

        {error && (
          <div className="rounded-[18px] border border-red-100 bg-red-50/90 p-3 text-xs leading-6 text-red-500">
            {error}
          </div>
        )}

        {explanation && !loading && (
          <div className="rounded-[20px] border border-slate-300/76 bg-white/82 p-4 text-sm leading-7 text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]">
              <MarkdownText content={explanation} />
          </div>
        )}
        </section>

        {/* 追问结果 */}
        {followUpAnswer && (
          <section className="rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.94),rgba(242,246,252,0.92))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_18px_42px_rgba(148,163,184,0.08)]">
            <div className="mb-3 flex items-center gap-2 text-slate-700">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl border border-slate-300/76 bg-white/82 text-brand-600">
                <MessageSquareText className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-500">追问结果</p>
                <p className="text-[11px] text-slate-400">基于当前解释继续深挖代码细节</p>
              </div>
            </div>
            <div className="rounded-[18px] border border-slate-300/76 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(236,241,248,0.9))] px-3 py-2 text-xs leading-6 text-slate-700">
              {followUpInput}
            </div>
            <div className="mt-3 rounded-[18px] border border-slate-300/76 bg-white/82 px-3 py-3 text-sm leading-7 text-slate-700">
              <MarkdownText content={followUpAnswer} />
            </div>
          </section>
        )}

        {/* 底部追问 */}
        {explanation && !loading && (
          <section className="rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.94),rgba(242,246,252,0.92))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_18px_42px_rgba(148,163,184,0.08)]">
            <div className="mb-3 flex items-center gap-2 text-slate-700">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl border border-slate-300/76 bg-white/82 text-brand-600">
                <Send className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-500">继续追问</p>
                <p className="text-[11px] text-slate-400">例如：这段代码为什么这样写？有没有更简单的写法？</p>
              </div>
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={followUpInput}
                onChange={(e) => setFollowUpInput(e.target.value)}
                onKeyDown={(e) => { if (e.nativeEvent.isComposing) return; if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp() } }}
                placeholder="针对这段代码追问..."
                disabled={followUpLoading}
                className="flex-1 rounded-[18px] border border-slate-300/76 bg-white/84 px-4 py-3 text-sm text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-slate-400/80 focus:ring-4 focus:ring-slate-200/70 disabled:opacity-50"
              />
              <button
                onClick={handleFollowUp}
                disabled={!followUpInput.trim() || followUpLoading}
                className="inline-flex items-center justify-center rounded-[18px] border border-slate-300/76 bg-[linear-gradient(135deg,rgba(255,255,255,0.94),rgba(232,240,252,0.92))] px-4 py-3 text-brand-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.84),0_10px_20px_rgba(148,163,184,0.10)] transition-all hover:border-slate-400/72 hover:text-brand-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {followUpLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}

export default CodeExplainPanel
