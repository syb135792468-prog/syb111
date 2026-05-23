import { apiGet, apiPost, apiDelete, apiFetch } from './index'
import { API_BASE } from '../utils/constants'

export function getProgress(userId, topic) {
  let url = `${API_BASE}/progress/${userId}`
  if (topic) url += `?topic=${encodeURIComponent(topic)}`
  return apiGet(url)
}

export async function updateProgress(userId, { topic, status, score, duration }) {
  let url = `${API_BASE}/progress/update?user_id=${userId}&topic=${encodeURIComponent(topic)}`
  if (status) url += `&status=${status}`
  if (score !== undefined) url += `&score=${score}`
  if (duration !== undefined) url += `&duration=${duration}`
  const resp = await apiFetch(url, { method: 'POST' })
  return resp.json()
}

export function resetProgress(userId, topic) {
  let url = `${API_BASE}/progress/${userId}`
  if (topic) url += `?topic=${encodeURIComponent(topic)}`
  return apiDelete(url)
}
