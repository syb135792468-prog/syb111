import { apiFetch, apiGet, apiPost, apiDelete, apiPatch } from './index'
import { API_BASE } from '../utils/constants'

export function chatStream(message: string, conversationId: string | number | null, signal?: AbortSignal, images?: string[]) {
  const body: Record<string, unknown> = { message }
  if (conversationId) body.conversation_id = conversationId
  if (images && images.length > 0) body.images = images

  return apiFetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    body: JSON.stringify(body),
    signal,
  })
}

export function deepChatStream(message: string, conversationId: string | number | null, signal?: AbortSignal, images?: string[]) {
  const body: Record<string, unknown> = { message }
  if (conversationId) body.conversation_id = conversationId
  if (images && images.length > 0) body.images = images

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
  images?: string[],
) {
  const body: Record<string, unknown> = { message, action }
  if (conversationId) body.conversation_id = conversationId
  if (threadId) body.thread_id = threadId
  if (images && images.length > 0) body.images = images

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

export function toggleMessageBookmark(messageId: number) {
  return apiPatch(`${API_BASE}/chat/messages/${messageId}/bookmark`)
}

export function getBookmarkedMessages(limit = 50, offset = 0) {
  return apiGet(`${API_BASE}/chat/bookmarks?limit=${limit}&offset=${offset}`)
}

export interface ExplanationData {
  id: number
  user_id: number
  conversation_id: number
  message_id: number
  selected_text: string
  explanation: string
  follow_ups: Array<{ question: string; answer: string; created_at: string }>
  created_at?: string
  updated_at?: string
}

export function explainText(text: string, messageId?: number, conversationId?: number, context?: string) {
  const body: Record<string, unknown> = { text }
  if (messageId) body.message_id = messageId
  if (conversationId) body.conversation_id = conversationId
  if (context) body.context = context
  return apiPost<ExplanationData>(`${API_BASE}/chat/explain`, body, 30000)
}

export function followUpExplain(explanationId: number, question: string) {
  return apiPost<{ answer: string }>(`${API_BASE}/chat/explain/follow-up`, {
    explanation_id: explanationId,
    question,
  }, 30000)
}

export function listExplanations(conversationId: number) {
  return apiGet<{ explanations: ExplanationData[]; total: number }>(
    `${API_BASE}/chat/explanations/${conversationId}`,
  )
}
