import { apiGet, apiPost, apiPut, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function listConversations() {
  return apiGet(`${API_BASE}/conversation`)
}

export function createConversation(title?: string) {
  return apiPost(`${API_BASE}/conversation`, { title: title || null })
}

export function getConversation(conversationId: string | number) {
  return apiGet(`${API_BASE}/conversation/${conversationId}`)
}

export function updateConversation(conversationId: string | number, title: string) {
  return apiPut(`${API_BASE}/conversation/${conversationId}`, { title })
}

export function deleteConversation(conversationId: string | number) {
  return apiDelete(`${API_BASE}/conversation/${conversationId}`)
}
