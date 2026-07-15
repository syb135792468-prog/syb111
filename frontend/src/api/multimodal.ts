import { API_BASE } from '../utils/constants'

export interface MultimodalAnalysisResult {
  code_text: string
  explanation: string
  problems: CodeProblem[]
  exercises: Exercise[]
  knowledge_points: string[]
  recognition_warning?: string | null
}

export interface CodeProblem {
  type: string
  description: string
  line?: string
  fix: string
}

export interface Exercise {
  type: string
  question: string
  options?: string[]
  answer: string
  explanation: string
}

let _getToken: () => string = () => ''

export function setMultimodalTokenGetter(getToken: () => string) {
  _getToken = getToken
}

/**
 * 流式分析代码图片
 * 使用与 chat 相同的 SSE 解析方式（按 \n\n 分割事件块）
 */
export async function analyzeCodeImage(
  imageUrl: string,
  onEvent: (event: string, data: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const token = _getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}/multimodal/analyze`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ image_url: imageUrl }),
    signal,
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `分析失败: ${response.status}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取响应流')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    // 按双换行分割事件块（标准 SSE 格式）
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''

    for (const part of parts) {
      if (!part.trim()) continue

      const lines = part.split('\n')
      let eventType = ''
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          dataStr += (dataStr ? '\n' : '') + line.slice(6)
        }
      }

      if (!eventType || !dataStr) continue

      try {
        const data = JSON.parse(dataStr)
        onEvent(eventType, data)
      } catch {
        // 忽略解析错误
      }
    }
  }
}

/**
 * 获取多模态分析历史列表
 */
export interface MultimodalHistoryItem {
  id: number
  title: string
  code_text: string
  image_url: string
  explanation: string
  problems: CodeProblem[]
  exercises: Exercise[]
  knowledge_points: string[]
  in_library: boolean
  created_at: string
}

export interface MultimodalHistoryResponse {
  items: MultimodalHistoryItem[]
  total: number
  limit: number
  offset: number
  has_more: boolean
}

export async function getMultimodalHistory(
  limit = 10,
  offset = 0
): Promise<MultimodalHistoryResponse> {
  const token = _getToken()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(
    `${API_BASE}/multimodal/history?limit=${limit}&offset=${offset}`,
    { headers }
  )

  if (!response.ok) {
    throw new Error(`获取历史失败: ${response.status}`)
  }

  const json = await response.json()
  if (json.code !== 200 || !json.data) {
    throw new Error(json.message || '获取历史失败')
  }

  return json.data
}

/**
 * 收藏/取消收藏分析结果
 */
export async function toggleFavorite(resourceId: number): Promise<{ id: number; in_library: boolean }> {
  const token = _getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}/multimodal/${resourceId}/favorite`, {
    method: 'POST',
    headers,
  })

  if (!response.ok) {
    throw new Error(`操作失败: ${response.status}`)
  }

  const json = await response.json()
  if (json.code !== 200 || !json.data) {
    throw new Error(json.message || '操作失败')
  }

  return json.data
}

/**
 * 保存分析结果到资源库（收藏）
 */
export async function saveAnalysisResult(
  imageUrl: string,
  result: MultimodalAnalysisResult
): Promise<{ id: number; title: string }> {
  const token = _getToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const response = await fetch(`${API_BASE}/multimodal/save`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      image_url: imageUrl,
      code_text: result.code_text,
      explanation: result.explanation,
      problems: result.problems,
      exercises: result.exercises,
      knowledge_points: result.knowledge_points,
    }),
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }))
    throw new Error(error.detail || `保存失败: ${response.status}`)
  }

  const json = await response.json()
  if (json.code !== 200 || !json.data) {
    throw new Error(json.message || '保存失败')
  }

  return json.data
}
