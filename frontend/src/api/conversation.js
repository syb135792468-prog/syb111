import { apiGet, apiPost, apiPut, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function listConversations() {
  return apiGet(`${API_BASE}/conversation`)
}

export function createConversation(title) {
  return apiPost(`${API_BASE}/conversation`, { title: title || null })
}

export function getConversation(conversationId) {
  return apiGet(`${API_BASE}/conversation/${conversationId}`)
}

export function updateConversation(conversationId, title) {
  return apiPut(`${API_BASE}/conversation/${conversationId}`, { title })
}

export function deleteConversation(conversationId) {
  return apiDelete(`${API_BASE}/conversation/${conversationId}`)
}
