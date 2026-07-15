import { create } from 'zustand'
import type { LearningProfile } from '../api/learningProfile'
import type { LearningPathData, PathNode } from '../api/learningPath'

export type LearningEventAction =
  | 'chat_explained'
  | 'resource_viewed'
  | 'multimodal_analyzed'
  | 'quiz_submitted'
  | 'quiz_passed'
  | 'code_run_success'
  | 'challenge_submitted'
  | 'challenge_passed'
  | 'error_reviewed'
  | 'path_node_completed'

export interface LearningEvent {
  id: string
  userId?: string | number
  sourcePage: string
  actionType: LearningEventAction
  topic?: string
  knowledgePoint?: string
  knowledgePoints?: string[]
  pathId?: number
  nodeId?: number
  resourceId?: number
  score?: number
  duration?: number
  timestamp: string
}

export interface RelatedPathNodeRef {
  pathId: number
  nodeId: number
  nodeName: string
  status: string
}

export interface KnowledgePointState {
  key: string
  knowledgePoint: string
  mastery: number
  activityScore: number
  lastStudyAt: string
  evidenceCount: number
  sourcePages: string[]
  relatedPathNodes: RelatedPathNodeRef[]
}

export interface PathProgressStats {
  pathId: number
  pathTitle: string
  completedNodes: number
  totalNodes: number
  timeLeft: number
  pathProgress: number
  pathMasteryHealth: number
  updatedAt: string
}

interface LearningCenterState {
  events: LearningEvent[]
  knowledgePoints: Record<string, KnowledgePointState>
  pathStatsById: Record<number, PathProgressStats>
  profileSnapshot: LearningProfile | null
  pathSnapshotsById: Record<number, LearningPathData>
  syncPaths: (paths: LearningPathData[]) => void
  syncProfile: (profile: LearningProfile | null) => void
  recordEvent: (event: Omit<LearningEvent, 'id' | 'timestamp'>) => void
  reset: () => void
}

const STATUS_PROGRESS_WEIGHT: Record<string, number> = {
  not_started: 0,
  in_progress: 60,
  completed: 100,
  needs_review: 85,
  skipped: 20,
  failed: 25,
}

const EVENT_ACTIVITY_WEIGHT: Record<LearningEventAction, number> = {
  chat_explained: 10,
  resource_viewed: 18,
  multimodal_analyzed: 28,
  quiz_submitted: 25,
  quiz_passed: 45,
  code_run_success: 35,
  challenge_submitted: 30,
  challenge_passed: 50,
  error_reviewed: 22,
  path_node_completed: 60,
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)))
}

function uniqueNodeRefs(values: RelatedPathNodeRef[]) {
  const seen = new Set<string>()
  return values.filter((item) => {
    const key = `${item.pathId}:${item.nodeId}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

export function normalizeKnowledgePointKey(value?: string | null) {
  return (value || '').trim().toLowerCase().replace(/\s+/g, '')
}

function resolveEventKnowledgeTargets(
  event: Pick<LearningEvent, 'knowledgePoint' | 'knowledgePoints' | 'topic'>,
) {
  const explicitTargets = uniqueStrings([
    ...(event.knowledgePoints || []),
    event.knowledgePoint || '',
  ].map((item) => item.trim()))

  if (explicitTargets.length > 0) return explicitTargets

  const topic = (event.topic || '').trim()
  return topic && topic.length <= 40 ? [topic] : []
}

function toPercent(value?: number | null) {
  if (value == null || Number.isNaN(value)) return 0
  if (value <= 1) return Math.round(value * 100)
  return Math.round(value)
}

export function computeNodeProgress(node: PathNode) {
  const statusProgress = STATUS_PROGRESS_WEIGHT[node.status] ?? 0
  const rawProgress = toPercent(node.progress)
  const masteryPercent = toPercent(node.mastery)
  const blendedProgress = Math.round(statusProgress * 0.7 + masteryPercent * 0.3)
  return Math.max(rawProgress, blendedProgress)
}

function computeNodeProgressWithKnowledge(
  node: PathNode,
  knowledgeState?: KnowledgePointState,
) {
  const baseProgress = computeNodeProgress(node)
  if (!knowledgeState) return baseProgress
  if (node.status === 'completed') return 100
  const inferredProgress = Math.min(
    95,
    Math.round(knowledgeState.activityScore * 0.6 + knowledgeState.mastery * 0.4),
  )
  return Math.max(baseProgress, inferredProgress)
}

export function computePathProgress(nodes: PathNode[]) {
  if (!nodes.length) return 0
  const weighted = nodes.reduce(
    (acc, node) => {
      const weight = node.estimated_time > 0 ? node.estimated_time : 1
      acc.totalWeight += weight
      acc.totalScore += computeNodeProgress(node) * weight
      return acc
    },
    { totalWeight: 0, totalScore: 0 },
  )
  if (weighted.totalWeight === 0) return 0
  return Math.round(weighted.totalScore / weighted.totalWeight)
}

export function computePathMasteryHealth(nodes: PathNode[]) {
  if (!nodes.length) return 0
  const weighted = nodes.reduce(
    (acc, node) => {
      const weight = node.estimated_time > 0 ? node.estimated_time : 1
      acc.totalWeight += weight
      acc.totalScore += toPercent(node.mastery) * weight
      return acc
    },
    { totalWeight: 0, totalScore: 0 },
  )
  if (weighted.totalWeight === 0) return 0
  return Math.round(weighted.totalScore / weighted.totalWeight)
}

function buildPathStats(
  pathSnapshotsById: Record<number, LearningPathData>,
  knowledgePoints: Record<string, KnowledgePointState>,
) {
  const nextPathStats: Record<number, PathProgressStats> = {}
  const updatedAt = new Date().toISOString()

  Object.values(pathSnapshotsById).forEach((path) => {
    const nodes = path.nodes || []
    const completedNodes = nodes.filter((node) => node.status === 'completed').length
    const totalNodes = path.total_nodes || nodes.length
    const timeLeft = nodes
      .filter((node) => node.status !== 'completed')
      .reduce((sum, node) => sum + (node.estimated_time || 0), 0)

    const progressWeighted = nodes.reduce(
      (acc, node) => {
        const weight = node.estimated_time > 0 ? node.estimated_time : 1
        const knowledgeState = knowledgePoints[normalizeKnowledgePointKey(node.knowledge_point)]
        acc.totalWeight += weight
        acc.totalScore += computeNodeProgressWithKnowledge(node, knowledgeState) * weight
        return acc
      },
      { totalWeight: 0, totalScore: 0 },
    )

    nextPathStats[path.id] = {
      pathId: path.id,
      pathTitle: path.title,
      completedNodes,
      totalNodes,
      timeLeft,
      pathProgress: progressWeighted.totalWeight > 0
        ? Math.round(progressWeighted.totalScore / progressWeighted.totalWeight)
        : 0,
      pathMasteryHealth: computePathMasteryHealth(nodes),
      updatedAt,
    }
  })

  return nextPathStats
}

function mergeKnowledgePoint(
  existing: KnowledgePointState | undefined,
  partial: Partial<KnowledgePointState> & Pick<KnowledgePointState, 'key' | 'knowledgePoint'>,
): KnowledgePointState {
  return {
    key: partial.key,
    knowledgePoint: partial.knowledgePoint,
    mastery: Math.max(existing?.mastery || 0, partial.mastery || 0),
    activityScore: Math.max(existing?.activityScore || 0, partial.activityScore || 0),
    lastStudyAt: partial.lastStudyAt || existing?.lastStudyAt || '',
    evidenceCount: Math.max(existing?.evidenceCount || 0, partial.evidenceCount || 0),
    sourcePages: uniqueStrings([...(existing?.sourcePages || []), ...(partial.sourcePages || [])]),
    relatedPathNodes: uniqueNodeRefs([...(existing?.relatedPathNodes || []), ...(partial.relatedPathNodes || [])]),
  }
}

// --- sessionStorage 持久化（会话内刷新恢复） ---
const STORAGE_KEY = 'lc_events_kp'

function loadPersisted(): Partial<Pick<LearningCenterState, 'events' | 'knowledgePoints'>> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return {
      events: Array.isArray(parsed.events) ? parsed.events : [],
      knowledgePoints: parsed.knowledgePoints && typeof parsed.knowledgePoints === 'object'
        ? parsed.knowledgePoints : {},
    }
  } catch {
    return {}
  }
}

function persistState(state: Pick<LearningCenterState, 'events' | 'knowledgePoints'>) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
      events: state.events,
      knowledgePoints: state.knowledgePoints,
    }))
  } catch {
    // sessionStorage 满或不可用时静默忽略
  }
}

const persisted = loadPersisted()

export const useLearningCenterStore = create<LearningCenterState>((rawSet) => {
  const set: typeof rawSet = (partial, replace) => {
    rawSet(partial, replace as false | undefined)
    const state = useLearningCenterStore.getState()
    persistState(state)
  }

  return {
  events: persisted.events || [],
  knowledgePoints: persisted.knowledgePoints || {},
  pathStatsById: {},
  profileSnapshot: null,
  pathSnapshotsById: {},

  syncPaths: (paths) => {
    set((state) => {
      const nextKnowledgePoints = { ...state.knowledgePoints }
      const nextPathSnapshots = { ...state.pathSnapshotsById }

      paths.forEach((path) => {
        nextPathSnapshots[path.id] = path

        ;(path.nodes || []).forEach((node) => {
          const key = normalizeKnowledgePointKey(node.knowledge_point)
          if (!key) return
          nextKnowledgePoints[key] = mergeKnowledgePoint(nextKnowledgePoints[key], {
            key,
            knowledgePoint: node.knowledge_point,
            mastery: toPercent(node.mastery),
            activityScore: computeNodeProgress(node),
            lastStudyAt: node.last_study_at || node.completed_at || node.started_at || '',
            evidenceCount: Math.max((nextKnowledgePoints[key]?.evidenceCount || 0), 1),
            sourcePages: ['path'],
            relatedPathNodes: [{
              pathId: path.id,
              nodeId: node.id,
              nodeName: node.knowledge_point,
              status: node.status,
            }],
          })
        })
      })

      return {
        pathSnapshotsById: nextPathSnapshots,
        knowledgePoints: nextKnowledgePoints,
        pathStatsById: buildPathStats(nextPathSnapshots, nextKnowledgePoints),
      }
    })
  },

  syncProfile: (profile) => {
    set((state) => {
      if (!profile) {
        return { profileSnapshot: null }
      }

      const nextKnowledgePoints = { ...state.knowledgePoints }
      const markPoints = (
        points: Array<{ name: string; mastery: number }>,
        partial: Partial<KnowledgePointState>,
      ) => {
        points.forEach((point) => {
          const key = normalizeKnowledgePointKey(point.name)
          if (!key) return
          nextKnowledgePoints[key] = mergeKnowledgePoint(nextKnowledgePoints[key], {
            key,
            knowledgePoint: point.name,
            mastery: point.mastery,
            evidenceCount: Math.max((nextKnowledgePoints[key]?.evidenceCount || 0), 1),
            sourcePages: ['profile'],
            ...partial,
          })
        })
      }

      markPoints(profile.radarData.map((item) => ({ name: item.name, mastery: item.mastery })), {
        activityScore: 0,
        lastStudyAt: profile.lastStudyTime === '暂无记录' ? '' : profile.lastStudyTime,
      })
      markPoints(profile.masteredPoints.map((item) => ({ name: item.name, mastery: item.mastery })), {
        activityScore: 80,
      })
      markPoints(profile.weakPoints.map((item) => ({ name: item.name, mastery: item.mastery })), {
        activityScore: 20,
      })

      return {
        profileSnapshot: profile,
        knowledgePoints: nextKnowledgePoints,
        pathStatsById: buildPathStats(state.pathSnapshotsById, nextKnowledgePoints),
      }
    })
  },

  recordEvent: (event) => {
    set((state) => {
      const timestamp = new Date().toISOString()
      const newEvent: LearningEvent = {
        ...event,
        id: `${timestamp}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp,
      }
      const nextKnowledgePoints = { ...state.knowledgePoints }
      const targets = resolveEventKnowledgeTargets(event)
      const activityWeight = EVENT_ACTIVITY_WEIGHT[event.actionType] || 10
      const activityDelta = Math.max(4, Math.round(activityWeight / Math.max(targets.length, 1)))

      targets.forEach((target) => {
        const key = normalizeKnowledgePointKey(target)
        if (!key) return
        const existing = nextKnowledgePoints[key]
        const currentActivity = existing?.activityScore || 0
        const scoreWeight = event.score != null ? Math.round(Math.max(0, Math.min(100, event.score))) : 0
        nextKnowledgePoints[key] = mergeKnowledgePoint(existing, {
          key,
          knowledgePoint: target || existing?.knowledgePoint || '',
          mastery: Math.max(existing?.mastery || 0, scoreWeight),
          activityScore: Math.min(100, currentActivity + activityDelta),
          lastStudyAt: timestamp,
          evidenceCount: (existing?.evidenceCount || 0) + 1,
          sourcePages: [event.sourcePage],
        })
      })

      return {
        events: [...state.events, newEvent].slice(-200),
        knowledgePoints: nextKnowledgePoints,
        pathStatsById: buildPathStats(state.pathSnapshotsById, nextKnowledgePoints),
      }
    })
  },

  reset: () => {
    set({
      events: [],
      knowledgePoints: {},
      pathStatsById: {},
      profileSnapshot: null,
      pathSnapshotsById: {},
    })
    try { sessionStorage.removeItem(STORAGE_KEY) } catch {}
  },
  }})
