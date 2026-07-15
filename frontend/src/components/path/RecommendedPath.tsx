import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Compass, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { useAuthStore } from '../../stores/auth'
import { fetchLearningProfile, type LearningProfile } from '../../api/learningProfile'
import { getGraphSnapshot, type GraphNode, type GraphSnapshot } from '../../api/graph'

interface RecommendedPathProps {
  onUse: (topic: string) => void
}

function resolveRecommendation(snapshot: GraphSnapshot, profile: LearningProfile) {
  const weakNames = new Set(profile.weakPoints.map((point) => point.name))
  const moduleOrder = (node: GraphNode) => snapshot.modules[node.module]?.order ?? 99
  const candidates = snapshot.nodes
    .filter((node) => node.state === 'learning' || node.state === 'available')
    .sort((a, b) => {
      const aWeak = weakNames.has(a.name) ? 0 : 1
      const bWeak = weakNames.has(b.name) ? 0 : 1
      return aWeak - bWeak
        || (a.state === 'learning' ? 0 : 1) - (b.state === 'learning' ? 0 : 1)
        || moduleOrder(a) - moduleOrder(b)
        || a.level - b.level
    })

  const focus = candidates[0]
  if (!focus) return null
  const isWeak = weakNames.has(focus.name)
  const moduleName = snapshot.modules[focus.module]?.name || focus.module
  return {
    topic: focus.name,
    title: isWeak ? `${focus.name} 巩固路径` : `${moduleName} 推荐路径`,
    reason: isWeak
      ? `你的学习画像将“${focus.name}”识别为需要巩固的知识点。`
      : `它是当前可学习的下一步知识点，位于${moduleName}模块。`,
    focus,
  }
}

export default function RecommendedPath({ onUse }: RecommendedPathProps) {
  const userId = useAuthStore((state) => state.userId)
  const [profile, setProfile] = useState<LearningProfile | null>(null)
  const [snapshot, setSnapshot] = useState<GraphSnapshot | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    try {
      const [nextProfile, graphResponse] = await Promise.all([
        fetchLearningProfile(userId),
        getGraphSnapshot(),
      ])
      setProfile(nextProfile)
      if (graphResponse.code === 200) setSnapshot(graphResponse.data as GraphSnapshot)
    } finally {
      setLoading(false)
    }
  }, [userId])

  useEffect(() => {
    load()
  }, [load])

  const recommendation = useMemo(
    () => (snapshot && profile ? resolveRecommendation(snapshot, profile) : null),
    [profile, snapshot],
  )

  if (!userId) return null

  return (
    <section className="page-panel max-w-2xl mx-auto mb-6 p-5" aria-label="推荐学习路径">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center border border-brand-200 bg-brand-50 text-brand-600">
            <Compass className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-500">Recommended Path</p>
            {loading ? (
              <div className="mt-2 flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" />
                正在结合学习画像与知识图谱生成建议
              </div>
            ) : recommendation ? (
              <>
                <h2 className="mt-1 text-base font-semibold text-slate-800">{recommendation.title}</h2>
                <p className="mt-1 text-sm leading-5 text-slate-600">{recommendation.reason}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <span className="border border-slate-200 bg-slate-50 px-2 py-1">目标：{recommendation.focus.name}</span>
                  <span className="border border-slate-200 bg-slate-50 px-2 py-1">预计 {recommendation.focus.estimated_time} 分钟起步</span>
                  <span className="border border-slate-200 bg-slate-50 px-2 py-1">学习目标：{profile?.learningGoal}</span>
                </div>
              </>
            ) : (
              <p className="mt-2 text-sm text-slate-400">完成一次学习活动后即可生成更贴合你的推荐。</p>
            )}
          </div>
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="p-2 text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-700 disabled:opacity-40"
          aria-label="刷新推荐路径"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {recommendation && (
        <button
          type="button"
          onClick={() => onUse(recommendation.topic)}
          className="mt-4 flex items-center gap-2 text-sm font-medium text-brand-600 transition-colors hover:text-brand-700"
        >
          <Sparkles className="h-4 w-4" />
          使用此推荐创建路径
        </button>
      )}
    </section>
  )
}
