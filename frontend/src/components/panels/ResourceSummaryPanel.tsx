import React, { useState, useCallback, useEffect } from 'react'
import { useAppStore } from '../../stores/app'
import { saveResourceNote } from '../../api/resource'
import { useAuthStore } from '../../stores/auth'
import MarkdownText from '../common/MarkdownText'
import { BookOpen, FileText, Clock, Save, Loader2, Check, Sparkles, NotebookPen } from 'lucide-react'

const TYPE_LABELS: Record<string, string> = {
  doc: '文档', quiz: '测验', mindmap: '思维导图', code: '代码',
  video: '视频', slides: '幻灯片', daily_challenge: '每日挑战', daily_extra: '额外挑战', multimodal: '多模态',
}

const ResourceSummaryPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const resource = data?.resource as Record<string, unknown> | undefined
  const authStore = useAuthStore()

  const [note, setNote] = useState('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  // 初始化笔记
  useEffect(() => {
    if (resource) {
      setNote((resource.note as string) || '')
      setSaved(false)
    }
  }, [resource])

  // 保存笔记
  const handleSave = useCallback(async () => {
    if (!resource?.id || !authStore.userId) return
    setSaving(true)
    try {
      const resp = await saveResourceNote(resource.id as number, authStore.userId, note)
      if (resp.code === 200) {
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      }
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }, [resource, note, authStore.userId])

  if (!resource) {
    return (
      <div className="flex h-full items-center justify-center px-5 py-6">
        <div className="w-full rounded-[26px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.96),rgba(240,245,252,0.94))] p-6 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_20px_48px_rgba(148,163,184,0.10)]">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-3xl border border-slate-300/76 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(235,241,249,0.92))] shadow-[inset_0_1px_0_rgba(255,255,255,0.85),0_12px_28px_rgba(148,163,184,0.12)]">
            <BookOpen className="h-7 w-7 text-brand-500" />
          </div>
          <div className="mb-2 inline-flex items-center rounded-full border border-slate-300/76 bg-white/82 px-3 py-1 text-[11px] font-semibold tracking-[0.16em] text-slate-600">
            RESOURCE
          </div>
          <p className="text-sm font-semibold text-slate-800">资源详情</p>
          <p className="mt-1 text-xs leading-relaxed text-slate-500">点击资源列表中的卡片后，这里会展示摘要、标签和学习笔记。</p>
        </div>
      </div>
    )
  }

  const title = (resource.title as string) || ''
  const resourceType = (resource.resource_type as string) || ''
  const content = (resource.content as string) || ''
  const createdAt = (resource.created_at as string) || ''
  const knowledgePoints = (resource.knowledge_points as string[]) || []
  const formattedDate = createdAt ? new Date(createdAt).toLocaleDateString('zh-CN') : ''

  // 内容摘要（前300字）
  const summary = content.length > 300 ? content.slice(0, 300) + '...' : content

  return (
    <div className="h-full overflow-y-auto px-4 py-4">
      <div className="flex min-h-full flex-col gap-4">
        <section className="rounded-[26px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.96),rgba(240,245,252,0.94))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_20px_48px_rgba(148,163,184,0.10)]">
          <div className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-slate-300/76 bg-white/82 px-3 py-1 text-[11px] font-semibold tracking-[0.16em] text-slate-600">
            <Sparkles className="h-3.5 w-3.5" />
            RESOURCE DETAIL
          </div>
          <h3 className="text-base font-semibold leading-6 text-slate-900">{title}</h3>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {resourceType && (
              <span className="rounded-full border border-slate-300/76 bg-white/82 px-2.5 py-1 text-[11px] font-medium text-slate-700">
                {TYPE_LABELS[resourceType] || resourceType}
              </span>
            )}
            {formattedDate && (
              <span className="inline-flex items-center gap-1 rounded-full border border-slate-300/76 bg-white/82 px-2.5 py-1 text-[11px] text-slate-500">
                <Clock className="h-3 w-3" />
                {formattedDate}
              </span>
            )}
          </div>
          {knowledgePoints.length > 0 && (
            <div className="mt-4 rounded-2xl border border-slate-300/76 bg-white/72 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.82)]">
              <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.14em] text-slate-500">
                <BookOpen className="h-3.5 w-3.5" />
                关联知识点
              </div>
              <div className="flex flex-wrap gap-2">
                {knowledgePoints.slice(0, 6).map((kp, i) => (
                  <span key={i} className="rounded-full border border-slate-300/76 bg-[linear-gradient(135deg,rgba(255,255,255,0.92),rgba(236,241,248,0.9))] px-2.5 py-1 text-[11px] text-slate-600">
                    {kp}
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>

        {summary && (
          <section className="rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.94),rgba(242,246,252,0.92))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_18px_42px_rgba(148,163,184,0.08)]">
            <div className="mb-3 flex items-center gap-2 text-slate-700">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl border border-slate-300/76 bg-white/82 text-brand-600">
                <FileText className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-500">内容摘要</p>
                <p className="text-[11px] text-slate-400">快速浏览这份资源的核心信息</p>
              </div>
            </div>
            <div className="rounded-2xl border border-slate-300/76 bg-white/82 p-4 text-sm leading-7 text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)]">
              <MarkdownText content={summary} />
            </div>
          </section>
        )}

        <section className="flex-1 rounded-[24px] border border-slate-300/76 bg-[linear-gradient(180deg,rgba(250,252,255,0.94),rgba(242,246,252,0.92))] p-4 shadow-[inset_0_1px_0_rgba(255,255,255,0.82),0_18px_42px_rgba(148,163,184,0.08)]">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-slate-700">
              <div className="flex h-8 w-8 items-center justify-center rounded-2xl border border-slate-300/76 bg-white/82 text-brand-600">
                <NotebookPen className="h-4 w-4" />
              </div>
              <div>
                <p className="text-xs font-semibold tracking-[0.14em] text-slate-500">学习笔记</p>
                <p className="text-[11px] text-slate-400">记录自己的理解、难点和后续复习点</p>
              </div>
            </div>
            <button
              onClick={handleSave}
              disabled={saving}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-300/76 bg-white/82 px-3 py-2 text-xs font-medium text-slate-700 shadow-[inset_0_1px_0_rgba(255,255,255,0.84)] transition-all hover:border-slate-400/70 hover:text-brand-700 disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : saved ? (
                <Check className="h-3.5 w-3.5 text-emerald-500" />
              ) : (
                <Save className="h-3.5 w-3.5" />
              )}
              {saved ? '已保存' : '保存笔记'}
            </button>
          </div>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="写下你的学习笔记、易错点或后续要回顾的内容..."
            rows={12}
            className="min-h-[260px] w-full resize-none rounded-[20px] border border-slate-300/76 bg-white/84 px-4 py-3 text-sm leading-6 text-slate-700 outline-none transition-all placeholder:text-slate-400 focus:border-slate-400/80 focus:ring-4 focus:ring-slate-200/70"
          />
        </section>
      </div>
    </div>
  )
}

export default ResourceSummaryPanel
