import { apiGet, apiPost, apiDelete, apiFetch } from './index'
import { API_BASE } from '../utils/constants'

export function getProgress(userId: string | number, topic?: string) {
  let url = `${API_BASE}/progress/${userId}`
  if (topic) url += `?topic=${encodeURIComponent(topic)}`
  return apiGet(url)
}

export async function updateProgress(
  userId: string | number,
  params: { topic: string; status?: string; score?: number; duration?: number }
) {
  let url = `${API_BASE}/progress/update?user_id=${userId}&topic=${encodeURIComponent(params.topic)}`
  if (params.status) url += `&status=${params.status}`
  if (params.score !== undefined) url += `&score=${params.score}`
  if (params.duration !== undefined) url += `&duration=${params.duration}`
  const resp = await apiFetch(url, { method: 'POST' })
  return resp.json()
}

export function resetProgress(userId: string | number, topic?: string) {
  if (!userId) return Promise.reject(new Error('用户未登录'))
  let url = `${API_BASE}/progress/${userId}`
  if (topic) url += `?topic=${encodeURIComponent(topic)}`
  return apiDelete(url)
}
