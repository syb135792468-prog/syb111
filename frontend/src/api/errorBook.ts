import { apiGet, apiPost, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

interface ErrorBookParams {
  knowledge_point?: string
  difficulty?: string
  mastered?: boolean | number
  limit?: number
  offset?: number
}

export function listErrorBook(userId: string | number, params: ErrorBookParams = {}) {
  const query = new URLSearchParams()
  if (params.knowledge_point) query.set('knowledge_point', params.knowledge_point)
  if (params.difficulty) query.set('difficulty', params.difficulty)
  if (params.mastered !== undefined && params.mastered !== null) query.set('mastered', String(params.mastered))
  if (params.limit) query.set('limit', String(params.limit))
  if (params.offset) query.set('offset', String(params.offset))
  const qs = query.toString()
  return apiGet(`${API_BASE}/error-book/${userId}${qs ? '?' + qs : ''}`)
}

export function listDueReviews(userId: string | number, limit = 50) {
  return apiGet(`${API_BASE}/error-book/${userId}/due?limit=${limit}`)
}

export function recordReview(id: string | number, quality: number) {
  return apiPost(`${API_BASE}/error-book/${id}/review?quality=${quality}`, {})
}

export function markMastered(id: string | number) {
  return apiPost(`${API_BASE}/error-book/${id}/mastered`, {})
}

export function deleteErrorBook(id: string | number) {
  return apiDelete(`${API_BASE}/error-book/${id}`)
}
