import { apiGet, apiPost, apiPatch, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

interface ResourceListParams {
  resourceType?: string
  status?: string
  inLibrary?: boolean
  limit?: number
  offset?: number
}

export function listResources(userId: string | number, params: ResourceListParams = {}) {
  const { resourceType, status = 'completed', inLibrary, limit = 50, offset = 0 } = params
  let url = `${API_BASE}/resource/?user_id=${userId}&limit=${limit}&offset=${offset}`
  if (resourceType) url += `&resource_type=${resourceType}`
  if (status) url += `&status=${status}`
  if (inLibrary !== undefined) url += `&in_library=${inLibrary}`
  return apiGet(url)
}

export function getResource(resourceId: string | number, userId: string | number) {
  return apiGet(`${API_BASE}/resource/${resourceId}?user_id=${userId}`)
}

export function generateResource(
  userId: string | number,
  topic: string,
  resourceType: string,
  config: Record<string, unknown> | null = null
) {
  const body: Record<string, unknown> = {
    user_id: String(userId),
    topic,
    resource_type: resourceType,
  }
  if (config && Object.keys(config).length > 0) {
    body.config = config
  }
  return apiPost(`${API_BASE}/resource/generate`, body, 180000)
}

/**
 * 异步资源生成（立即返回 task_id，前端轮询 /tasks/{task_id} 拿进度）。
 * 用于 video + 多题测验等慢速生成，配合 pollTaskProgress 显示进度条。
 */
export function generateResourceAsync(
  userId: string | number,
  topic: string,
  resourceType: string,
  config: Record<string, unknown> | null = null
) {
  const body: Record<string, unknown> = {
    user_id: String(userId),
    topic,
    resource_type: resourceType,
  }
  if (config && Object.keys(config).length > 0) {
    body.config = config
  }
  return apiPost<{ task_id: string }>(`${API_BASE}/resource/generate-async`, body, 10000)
}

export function deleteResource(resourceId: string | number, userId: string | number) {
  return apiDelete(`${API_BASE}/resource/${resourceId}?user_id=${userId}`)
}

export function addToLibrary(resourceId: string | number, userId: string | number) {
  return apiPatch(`${API_BASE}/resource/${resourceId}/add-to-library?user_id=${userId}`)
}

export function saveResourceNote(resourceId: string | number, userId: string | number, note: string) {
  return apiPatch(`${API_BASE}/resource/${resourceId}/note?user_id=${userId}`, { note })
}

export function expandMindmapNode(params: {
  userId: string | number
  resourceId: number
  nodeId: string
  nodeTopic: string
  nodeDefinition?: string
  nodeSyntax?: string
  nodeExamples?: string[]
  nodePitfalls?: string[]
  nodeAdvice?: string
}) {
  return apiPost(`${API_BASE}/resource/expand-node`, {
    user_id: String(params.userId),
    resource_id: params.resourceId,
    node_id: params.nodeId,
    node_topic: params.nodeTopic,
    node_definition: params.nodeDefinition || '',
    node_syntax: params.nodeSyntax || '',
    node_examples: params.nodeExamples || [],
    node_pitfalls: params.nodePitfalls || [],
    node_advice: params.nodeAdvice || '',
  }, 60000)
}

export function renderVideo(resourceId: number, userId: string | number) {
  return apiPost(`${API_BASE}/resource/${resourceId}/render-video?user_id=${userId}`, {}, 300000)
}

// ==================== 推荐资源（画像驱动精准推送） ====================

export interface Recommendation {
  resource_type: string
  knowledge_point: string
  title: string
  content_preview: string
  difficulty: string
  reason: string
  resource_data: {
    title: string
    content: string
    knowledge_points: string[]
    extra_metadata: Record<string, unknown>
  }
}

export interface RecommendResult {
  recommendations: Recommendation[]
  profile_summary: {
    learning_style: string
    motivation_level: string
    weak_points_count: number
  }
}

/** 基于画像 8 维度生成 3 条精准推荐资源（按需生成） */
export function recommendResources(userId: string | number) {
  return apiGet<RecommendResult>(
    `${API_BASE}/resource/recommend?user_id=${userId}`,
    90000
  )
}
