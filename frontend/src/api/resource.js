import { apiGet, apiPost, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function listResources(userId, { resourceType, status = 'completed', limit = 50, offset = 0 } = {}) {
  let url = `${API_BASE}/resource/?user_id=${userId}&limit=${limit}&offset=${offset}`
  if (resourceType) url += `&resource_type=${resourceType}`
  if (status) url += `&status=${status}`
  return apiGet(url)
}

export function getResource(resourceId, userId) {
  return apiGet(`${API_BASE}/resource/${resourceId}?user_id=${userId}`)
}

export function generateResource(userId, topic, resourceType, difficulty = 2) {
  return apiPost(`${API_BASE}/resource/generate`, {
    user_id: String(userId),
    topic,
    resource_type: resourceType,
    difficulty,
  })
}

export function deleteResource(resourceId, userId) {
  return apiDelete(`${API_BASE}/resource/${resourceId}?user_id=${userId}`)
}
