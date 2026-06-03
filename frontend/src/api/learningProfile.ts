import { apiGet, apiPost } from './index'
import { API_BASE } from '../utils/constants'
import { buildProfileFromProgress } from '../utils/scoringEngine'
import type { LearningProfile, ProgressRecord, BackendProfile } from '../utils/scoringEngine'

export type { LearningProfile }

export async function fetchLearningProfile(userId: string | number): Promise<LearningProfile> {
  const [progressResp, profileResp] = await Promise.all([
    apiGet<ProgressRecord[]>(`${API_BASE}/progress/${userId}`).catch(() => ({ code: 0, data: [] as ProgressRecord[] })),
    apiGet<{ profile?: BackendProfile }>(`${API_BASE}/profile/${userId}`).catch(() => ({ code: 0, data: {} })),
  ])

  const progressRecords = progressResp.code === 200 ? (progressResp.data || []) : []
  const rawProfile = profileResp.code === 200 ? ((profileResp.data as { profile?: BackendProfile })?.profile || {}) : {}

  // 确保 mastered_points 和 weak_points 传递给 scoringEngine
  const backendProfile: BackendProfile = {
    learning_goal: rawProfile.learning_goal,
    learning_style: rawProfile.learning_style,
    mastered_points: rawProfile.mastered_points || [],
    weak_points: rawProfile.weak_points || [],
  }

  return buildProfileFromProgress(progressRecords, backendProfile)
}

export async function recordLearningEvent(
  userId: string | number,
  event: { action: string; topic: string; score?: number; duration?: number }
): Promise<LearningProfile> {
  const { topic, score, duration } = event

  let status = 'in_progress'
  if (event.action === 'quiz_complete' || event.action === 'code_practice') {
    status = score != null && score >= 60 ? 'completed' : 'failed'
  } else if (event.action === 'video_watch' || event.action === 'resource_read') {
    status = 'in_progress'
  }

  await apiPost(
    `${API_BASE}/progress/update?user_id=${userId}&topic=${encodeURIComponent(topic)}` +
    `&status=${status}` +
    (score != null ? `&score=${score}` : '') +
    (duration != null ? `&duration=${duration}` : '')
  )

  return fetchLearningProfile(userId)
}
