import { apiFetch, apiGet, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function chatStream(message: string, conversationId: string | number | null, signal?: AbortSignal) {
  const body: Record<string, unknown> = { message }
  if (conversationId) body.conversation_id = conversationId

  return apiFetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export function deepChatStream(message: string, conversationId: string | number | null, signal?: AbortSignal) {
  const body: Record<string, unknown> = { message }
  if (conversationId) body.conversation_id = conversationId

  return apiFetch(`${API_BASE}/chat/deep-stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export function socraticChatStream(
  message: string,
  conversationId: string | number | null,
  action: 'start' | 'answer' | 'hint' | 'give_up' | 'end' | 'confused' = 'start',
  threadId?: string | null,
  signal?: AbortSignal,
) {
  const body: Record<string, unknown> = { message, action }
  if (conversationId) body.conversation_id = conversationId
  if (threadId) body.thread_id = threadId

  return apiFetch(`${API_BASE}/chat/socratic-stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export function getChatHistory(limit = 100, conversationId?: string | number) {
  let url = `${API_BASE}/chat/history?limit=${limit}`
  if (conversationId) url += `&conversation_id=${conversationId}`
  return apiGet(url)
}

export function clearChatHistory() {
  return apiDelete(`${API_BASE}/chat/history`)
}
