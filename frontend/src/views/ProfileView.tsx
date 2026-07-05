import React, { useState, useEffect, useCallback, useRef, useImperativeHandle, forwardRef, useMemo } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useLearningCenterStore, type LearningEvent } from '../stores/learningCenter'
import { fetchLearningProfile } from '../api/learningProfile'
import type { LearningProfile } from '../api/learningProfile'
import { normalizeKnowledgePointKey } from '../stores/learningCenter'
import { calcKnowledgeLevel, smoothKnowledgeScore } from '../utils/scoringEngine'
import { resetProgress } from '../api/progress'
import { resetProfile } from '../api/profile'
import AppHeader from '../components/layout/AppHeader'
import ProfileCards from '../components/profile/ProfileCards'
import RadarChart from '../components/profile/RadarChart'
import StyleChart from '../components/profile/StyleChart'
import KnowledgeTags from '../components/profile/KnowledgeTags'
import StudyTimeChart from '../components/profile/StudyTimeChart'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { RefreshCw, Activity, RotateCcw, UserCog, Lightbulb } from 'lucide-react'

export interface ProfileViewHandle {
  refresh: () => void
}

interface ProfileKnowledgePoint {
  id: string
  name: string
  mastery: number
  category?: string
}

interface ProfileStudyTimePoint {
  date: string
  label: string
  minutes: number
}

const EVENT_DURATION_FALLBACK_SECONDS: Partial<Record<LearningEvent['actionType'], number>> = {
  chat_explained: 90,
  resource_viewed: 180,
  multimodal_analyzed: 300,
  quiz_submitted: 180,
  quiz_passed: 240,
  code_run_success: 60,
  challenge_submitted: 240,
  challenge_passed: 300,
  error_reviewed: 240,
  path_node_completed: 300,
}

function formatLastStudyLabel(lastStudyAt: string) {
  if (!lastStudyAt) return '暂无记录'

  const studyDate = new Date(lastStudyAt)
  if (Number.isNaN(studyDate.getTime())) return '暂无记录'

  return studyDate.toLocaleDateString('zh-CN')
}

function mergeKnowledgeLists(
  basePoints: ProfileKnowledgePoint[],
  livePoints: ProfileKnowledgePoint[],
  sortDirection: 'asc' | 'desc',
) {
  const merged = new Map<string, ProfileKnowledgePoint>()

  basePoints.forEach((point) => {
    merged.set(normalizeKnowledgePointKey(point.name), point)
  })

  livePoints.forEach((point) => {
    const key = normalizeKnowledgePointKey(point.name)
    const existing = merged.get(key)
    if (!existing) {
      merged.set(key, point)
      return
    }

    merged.set(key, {
      ...existing,
      mastery: sortDirection === 'desc'
        ? Math.max(existing.mastery, point.mastery)
        : Math.min(existing.mastery, point.mastery),
    })
  })

  return Array.from(merged.values()).sort((a, b) => (
    sortDirection === 'desc' ? b.mastery - a.mastery : a.mastery - b.mastery
  ))
}

function getEventDurationSeconds(event: LearningEvent) {
  if (typeof event.duration === 'number' && event.duration > 0) return event.duration
  return EVENT_DURATION_FALLBACK_SECONDS[event.actionType] || 0
}

function buildRecentStudyTimeBase(baseData: ProfileStudyTimePoint[]) {
  if (baseData.length > 0) {
    return baseData.map((item) => ({ ...item }))
  }

  const dayLabels = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const result: ProfileStudyTimePoint[] = []
  for (let i = 6; i >= 0; i -= 1) {
    const day = new Date()
    day.setHours(0, 0, 0, 0)
    day.setDate(day.getDate() - i)
    result.push({
      date: `${day.getMonth() + 1}/${day.getDate()}`,
      label: dayLabels[day.getDay()],
      minutes: 0,
    })
  }
  return result
}

function mergeStudyTimeWithEvents(
  baseData: ProfileStudyTimePoint[],
  baseTotalHours: number,
  events: LearningEvent[],
) {
  const nextData = buildRecentStudyTimeBase(baseData)
  const dayIndexByKey = new Map<string, number>()

  nextData.forEach((item, index) => {
    dayIndexByKey.set(item.date, index)
  })

  let addedSeconds = 0
  events.forEach((event) => {
    const durationSeconds = getEventDurationSeconds(event)
    if (durationSeconds <= 0) return

    const eventDate = new Date(event.timestamp)
    if (Number.isNaN(eventDate.getTime())) return

    const dateKey = `${eventDate.getMonth() + 1}/${eventDate.getDate()}`
    const dayIndex = dayIndexByKey.get(dateKey)
    if (dayIndex === undefined) return

    nextData[dayIndex] = {
      ...nextData[dayIndex],
      minutes: nextData[dayIndex].minutes + Math.max(1, Math.round(durationSeconds / 60)),
    }
    addedSeconds += durationSeconds
  })

  return {
    dailyStudyTime: nextData,
    totalStudyHours: Math.round((baseTotalHours + addedSeconds / 3600) * 10) / 10,
  }
}

function mergeMotivationWithEvents(
  baseMotivation: LearningProfile['learningMotivation'],
  events: LearningEvent[],
) {
  if (events.length === 0) return baseMotivation

  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000
  const recentEvents = events.filter((event) => {
    const time = new Date(event.timestamp).getTime()
    return !Number.isNaN(time) && time >= sevenDaysAgo
  })
  if (recentEvents.length === 0) return baseMotivation

  const activeDays = new Set(
    recentEvents.map((event) => {
      const date = new Date(event.timestamp)
      return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`
    }),
  ).size

  const totalHours = recentEvents.reduce((sum, event) => sum + getEventDurationSeconds(event), 0) / 3600
  const eventCount = recentEvents.length
  const liveValue = Math.min(
    100,
    Math.round(activeDays * 10 + totalHours * 8 + Math.min(eventCount, 8) * 4),
  )
  const value = Math.max(baseMotivation.value, liveValue)
  const status = value >= 75 ? '高涨' : value >= 35 ? '适中' : '低迷'

  return { status, value }
}

function resolveAccuracySample(event: LearningEvent) {
  switch (event.actionType) {
    case 'quiz_passed':
    case 'challenge_passed':
      return 100
    case 'quiz_submitted':
    case 'challenge_submitted':
      return 0
    default:
      return null
  }
}

function mergeAccuracyWithEvents(baseAccuracy: number, events: LearningEvent[]) {
  const samples = events
    .map(resolveAccuracySample)
    .filter((value): value is NonNullable<typeof value> => value != null)

  if (samples.length === 0) return baseAccuracy

  if (baseAccuracy <= 0) {
    return Math.round(samples.reduce<number>((sum, value) => sum + value, 0) / samples.length)
  }

  const baseSampleWeight = 6
  const mergedTotal = baseAccuracy * baseSampleWeight + samples.reduce<number>((sum, value) => sum + value, 0)
  return Math.round(mergedTotal / (baseSampleWeight + samples.length))
}

// --- 组件 ---
const KNOWLEDGE_ATTEMPT_ACTIONS = new Set<LearningEvent['actionType']>([
  'quiz_submitted',
  'quiz_passed',
  'challenge_submitted',
  'challenge_passed',
])

const KNOWLEDGE_SCORE_FALLBACK: Partial<Record<LearningEvent['actionType'], number>> = {
  quiz_passed: 90,
  challenge_passed: 92,
  code_run_success: 78,
  path_node_completed: 82,
}

interface LiveKnowledgeAdjustment {
  attempts: number
  bestScore: number
  passiveCount: number
}

function resolveKnowledgeTargets(event: LearningEvent) {
  return Array.from(new Set(
    [event.knowledgePoint, ...(event.knowledgePoints || [])]
      .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
      .map((value) => value.trim()),
  ))
}

function resolveKnowledgeEventScore(event: LearningEvent) {
  if (typeof event.score === 'number') {
    return Math.round(Math.max(0, Math.min(100, event.score)))
  }
  return KNOWLEDGE_SCORE_FALLBACK[event.actionType] || 0
}

function buildLiveKnowledgeAdjustments(events: LearningEvent[]) {
  const adjustments = new Map<string, LiveKnowledgeAdjustment>()

  events.forEach((event) => {
    const targets = resolveKnowledgeTargets(event)
    if (targets.length === 0) return

    const score = resolveKnowledgeEventScore(event)
    const countsAsAttempt = KNOWLEDGE_ATTEMPT_ACTIONS.has(event.actionType)
    const countsAsPassive = !countsAsAttempt && score <= 0

    targets.forEach((target) => {
      const key = normalizeKnowledgePointKey(target)
      if (!key) return

      const existing = adjustments.get(key) || { attempts: 0, bestScore: 0, passiveCount: 0 }
      adjustments.set(key, {
        attempts: existing.attempts + (countsAsAttempt ? 1 : 0),
        bestScore: Math.max(existing.bestScore, score),
        passiveCount: existing.passiveCount + (countsAsPassive ? 1 : 0),
      })
    })
  })

  return adjustments
}

const ProfileView = forwardRef<ProfileViewHandle>((_props, ref) => {
  const authStore = useAuthStore()
  const appStore = useAppStore()
  const syncProfile = useLearningCenterStore((state) => state.syncProfile)
  const profileSnapshot = useLearningCenterStore((state) => state.profileSnapshot)
  const learningEvents = useLearningCenterStore((state) => state.events)

  // --- 状态 ---
  const [profile, setProfile] = useState<LearningProfile | null>(profileSnapshot)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [profileLoadedAt, setProfileLoadedAt] = useState<number>(0)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])


  // 重置状态（各自独立）
  const [resettingProgress, setResettingProgress] = useState(false)
  const [resettingProfile, setResettingProfile] = useState(false)

  // 确认弹窗状态
  const [confirmProgress, setConfirmProgress] = useState(false)
  const [confirmProfile, setConfirmProfile] = useState(false)

  // --- 加载画像 ---
  const loadProfile = useCallback(async () => {
    if (!authStore.userId) {
      if (mountedRef.current) {
        setError('请先登录')
        setLoading(false)
      }
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await fetchLearningProfile(authStore.userId)
      if (!mountedRef.current) return
      setProfile(data)
      syncProfile(data)
      setProfileLoadedAt(Date.now())
    } catch (e) {
      if (!mountedRef.current) return
      console.error('Failed to load learning profile:', e)
      setError('加载学习画像失败，请稍后重试')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [authStore.userId, syncProfile])

  useEffect(() => {
    if (!profile && profileSnapshot) {
      setProfile(profileSnapshot)
    }
  }, [profile, profileSnapshot])

  const mergedProfile = useMemo(() => {
    if (!profile) return null
    const incrementalEvents = profileLoadedAt <= 0 ? [] : learningEvents.filter((event) => {
      if (!profileLoadedAt) return true
      const eventTime = new Date(event.timestamp).getTime()
      return !Number.isNaN(eventTime) && eventTime > profileLoadedAt
    })

    // 统计每个知识点的答题次数（用于 P2 平滑）
    const liveAdjustments = buildLiveKnowledgeAdjustments(incrementalEvents)

    // 画像基准分类集合（用于确定平滑基准分）
    const profileMasteredKeys = new Set(profile.masteredPoints.map((p) => normalizeKnowledgePointKey(p.name)))
    const profileWeakKeys = new Set(profile.weakPoints.map((p) => normalizeKnowledgePointKey(p.name)))

    const radarData = profile.radarData.map((point) => {
      const key = normalizeKnowledgePointKey(point.name)
      const adjustment = liveAdjustments.get(key)
      if (!adjustment) return point

      const isMastered = profileMasteredKeys.has(key)
      const isWeak = profileWeakKeys.has(key)
      const passiveBoost = Math.min(9, adjustment.passiveCount * 3)

      if (adjustment.bestScore <= 0) {
        return {
          ...point,
          mastery: Math.min(100, point.mastery + passiveBoost),
        }
      }

      const targetScore = Math.max(point.mastery, adjustment.bestScore)
      const attempts = Math.max(adjustment.attempts, targetScore >= 80 ? 2 : 1)
      const smoothedScore = smoothKnowledgeScore(targetScore, attempts, isMastered, isWeak)

      return {
        ...point,
        mastery: Math.max(point.mastery, smoothedScore),
      }
    })

    const avgMastery = radarData.length > 0
      ? radarData.reduce((sum, point) => sum + point.mastery, 0) / radarData.length
      : 0

    const liveMastered = radarData.filter((point) => point.mastery >= 75)
    const liveWeak = radarData.filter((point) => point.mastery > 0 && point.mastery <= 35)
    const latestEventAt = [...incrementalEvents]
      .map((event) => event.timestamp)
      .filter(Boolean)
      .sort((a, b) => new Date(b).getTime() - new Date(a).getTime())[0] || ''
    const mergedStudyTime = mergeStudyTimeWithEvents(
      profile.dailyStudyTime,
      profile.totalStudyHours,
      incrementalEvents,
    )
    const mergedMotivation = mergeMotivationWithEvents(
      profile.learningMotivation,
      incrementalEvents,
    )
    const mergedAccuracy = mergeAccuracyWithEvents(
      profile.accuracy,
      incrementalEvents,
    )

    return {
      ...profile,
      knowledgeLevel: calcKnowledgeLevel(avgMastery),
      learningMotivation: mergedMotivation,
      radarData,
      masteredPoints: mergeKnowledgeLists(profile.masteredPoints, liveMastered, 'desc'),
      weakPoints: mergeKnowledgeLists(profile.weakPoints, liveWeak, 'asc'),
      lastStudyTime: latestEventAt ? formatLastStudyLabel(latestEventAt) : profile.lastStudyTime,
      dailyStudyTime: mergedStudyTime.dailyStudyTime,
      totalStudyHours: mergedStudyTime.totalStudyHours,
      accuracy: mergedAccuracy,
    }
  }, [learningEvents, profile, profileLoadedAt])

  // --- 暴露给外部调用 ---
  useImperativeHandle(ref, () => ({ refresh: loadProfile }), [loadProfile])

  // --- 初始加载 ---
  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  // --- 监听学习事件，自动刷新画像 ---
  useEffect(() => {
    let debounceTimer: ReturnType<typeof setTimeout> | null = null
    const handleDirty = () => {
      // 防抖：多次事件在 1.5s 内合并为一次刷新
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadProfile()
      }, 1500)
    }
    window.addEventListener('learning-profile-dirty', handleDirty)
    return () => {
      window.removeEventListener('learning-profile-dirty', handleDirty)
      if (debounceTimer) clearTimeout(debounceTimer)
    }
  }, [loadProfile])

  // --- 重置进度 ---
  const handleResetProgress = useCallback(async () => {
    if (resettingProgress) return
    setResettingProgress(true)
    try {
      const resp = await resetProgress(authStore.userId)
      if (resp.code === 200) {
        appStore.showToast(resp.message || '学习进度已重置', 'success')
        setConfirmProgress(false)
        await loadProfile()
      } else {
        appStore.showToast(resp.message || '重置失败', 'error')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('重置进度失败：' + msg, 'error')
    } finally {
      setResettingProgress(false)
    }
  }, [resettingProgress, authStore.userId, appStore, loadProfile])

  // --- 重置画像 ---
  const handleResetProfile = useCallback(async () => {
    if (resettingProfile) return
    setResettingProfile(true)
    try {
      // 先清除进度，成功后再重置画像
      const progressResp = await resetProgress(authStore.userId)
      if (progressResp.code !== 200) {
        appStore.showToast(progressResp.message || '重置进度失败', 'error')
        return
      }

      const profileResp = await resetProfile(authStore.userId)
      if (profileResp.code === 200) {
        appStore.showToast('学习画像和进度已重置', 'success')
        setConfirmProfile(false)
        await loadProfile()
      } else {
        appStore.showToast(profileResp.message || '重置画像失败', 'error')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('重置画像失败：' + msg, 'error')
    } finally {
      setResettingProfile(false)
    }
  }, [resettingProfile, authStore.userId, appStore, loadProfile])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="学习画像">
        <button
          onClick={() => useAppStore.getState().openRightPanel('ai-suggestion')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-amber-600 border border-amber-200 bg-amber-50 rounded-lg hover:bg-amber-100 transition-colors"
        >
          <Lightbulb className="w-3.5 h-3.5" />
          AI 学习建议
        </button>
        <button
          onClick={loadProfile}
          className="text-gray-400 hover:text-gray-600 p-2 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </AppHeader>

      <div className="page-scroll-area">
        {/* 骨架屏加载态 */}
        {loading ? (
          <div className="page-content max-w-5xl mx-auto space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="page-panel overflow-hidden animate-pulse">
                  <div className="h-24 bg-gray-200" />
                  <div className="h-12 bg-gray-100" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2].map(i => (
                <div key={i} className="page-panel p-5">
                  <div className="h-4 w-24 bg-gray-200 rounded mb-4 animate-pulse" />
                  <div className="h-[280px] bg-gray-100 rounded animate-pulse" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2].map(i => (
                <div key={i} className="page-panel p-5">
                  <div className="h-4 w-28 bg-gray-200 rounded mb-3 animate-pulse" />
                  <div className="flex flex-wrap gap-2">
                    {[1, 2, 3, 4].map(j => (
                      <div key={j} className="h-6 w-20 bg-gray-100 rounded-full animate-pulse" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : error ? (
          /* 错误态 */
          <div className="page-content">
            <div className="page-panel flex flex-col items-center justify-center h-64 text-gray-400">
            <Activity className="w-10 h-10 mb-3 text-gray-300" />
            <p className="text-sm">{error}</p>
            <button
              onClick={loadProfile}
              className="mt-3 text-sm text-brand-600 hover:text-brand-700 underline"
            >
              重新加载
            </button>
            </div>
          </div>
        ) : mergedProfile ? (
          /* 正常内容 */
          <div className="page-content max-w-5xl mx-auto space-y-6">
            {/* 顶部状态卡片 */}
            <ProfileCards
              level={mergedProfile.knowledgeLevel}
              levelDesc="根据你的学习表现自动评估"
              goal={mergedProfile.learningGoal}
              goalDesc="影响推荐资源的类型和难度"
              motivation={mergedProfile.learningMotivation.status}
              motivationDesc="基于最近7天学习频率分析"
              motivationValue={mergedProfile.learningMotivation.value}
            />

            {/* 雷达图 + 饼图 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RadarChart radarData={mergedProfile.radarData} />
              <StyleChart styleData={mergedProfile.learningStyle} />
            </div>

            {/* 学习时间 */}
            <StudyTimeChart
              data={mergedProfile.dailyStudyTime}
              totalHours={mergedProfile.totalStudyHours}
            />

            {/* 已掌握 / 薄弱知识点 */}
            <KnowledgeTags
              mastered={mergedProfile.masteredPoints}
              weak={mergedProfile.weakPoints}
            />

            {/* 画像详情 */}
            <div className="page-panel p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-500 mb-2">Profile Insight</p>
              <h3 className="text-base font-semibold text-slate-800 mb-4">画像详情</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-gray-400">学习风格</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{mergedProfile.learningStyle.dominant}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {({
                      '视觉型': '你喜欢通过图表和示例来学习',
                      '听觉型': '你喜欢通过听讲解来学习',
                      '动手型': '你喜欢通过编写代码来学习',
                      '混合型': '你有均衡的学习风格',
                    } as Record<string, string>)[mergedProfile.learningStyle.dominant] || '你有均衡的学习风格'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">时长偏好</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{mergedProfile.timePreference}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">最后学习</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{mergedProfile.lastStudyTime}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">答题正确率</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">
                    {mergedProfile.accuracy > 0 ? `${mergedProfile.accuracy}%` : '暂无'}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-brand-50">
                <div>
                  <p className="text-xs text-gray-400">总学习时长</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">
                    {mergedProfile.totalStudyHours > 0 ? `${mergedProfile.totalStudyHours} 小时` : '暂无'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">知识水平</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{mergedProfile.knowledgeLevel}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">已掌握</p>
                  <p className="text-sm font-medium text-green-600 mt-1">{mergedProfile.masteredPoints.length} 个知识点</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">薄弱项</p>
                  <p className="text-sm font-medium text-orange-500 mt-1">{mergedProfile.weakPoints.length} 个知识点</p>
                </div>
              </div>
            </div>

            {/* 重置操作区 */}
            <div className="page-panel p-5">
              <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-500 mb-2">Data Control</p>
              <h3 className="text-base font-semibold text-slate-800 mb-3">数据管理</h3>
              <p className="text-xs text-gray-400 mb-4">重置操作不可撤销，请谨慎操作</p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setConfirmProgress(true)}
                  disabled={resettingProgress || resettingProfile}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm text-amber-700 border border-amber-200 bg-amber-50 rounded-lg hover:bg-amber-100 transition-colors disabled:opacity-40"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  重置学习进度
                </button>
                <button
                  onClick={() => setConfirmProfile(true)}
                  disabled={resettingProgress || resettingProfile}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm text-red-700 border border-red-200 bg-red-50 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-40"
                >
                  <UserCog className="w-3.5 h-3.5" />
                  重置学习画像
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* 确认弹窗：重置进度 */}
      <ConfirmDialog
        show={confirmProgress}
        title="重置学习进度"
        message={`将清除所有知识点的学习记录，包括：\n• 所有课程的完成状态\n• 所有章节的学习进度\n• 所有测验的分数和时长\n\n将保留：\n• 你的学习画像和能力评估\n• 你的错题本记录\n\n此操作不可撤销，确定继续吗？`}
        confirmText="确认重置"
        dangerLevel="warning"
        isLoading={resettingProgress}
        onConfirm={handleResetProgress}
        onCancel={() => setConfirmProgress(false)}
      />

      {/* 确认弹窗：重置画像 */}
      <ConfirmDialog
        show={confirmProfile}
        title="重置学习画像"
        message={`将完全重置你的学习数据，包括：\n• 所有知识点的学习记录\n• 所有课程的完成状态\n• AI生成的7维学习画像\n• 所有个性化学习推荐\n\n将保留：\n• 你的用户账号和基本信息\n• 你的错题本记录\n\n此操作不可撤销，确定继续吗？`}
        confirmText="确认重置"
        dangerLevel="danger"
        isLoading={resettingProfile}
        onConfirm={handleResetProfile}
        onCancel={() => setConfirmProfile(false)}
      />
    </div>
  )
})

ProfileView.displayName = 'ProfileView'

export default ProfileView
