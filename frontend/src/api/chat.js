import { apiFetch, apiGet, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function chatStream(message, conversationId, signal) {
  const body = { message }
  if (conversationId) body.conversation_id = conversationId

  return apiFetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export function getChatHistory(limit = 100, conversationId) {
  let url = `${API_BASE}/chat/history?limit=${limit}`
  if (conversationId) url += `&conversation_id=${conversationId}`
  return apiGet(url)
}

export function clearChatHistory() {
  return apiDelete(`${API_BASE}/chat/history`)
}
