import { apiGet, apiPost, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

interface ResourceListParams {
  resourceType?: string
  status?: string
  limit?: number
  offset?: number
}

export function listResources(userId: string | number, params: ResourceListParams = {}) {
  const { resourceType, status = 'completed', limit = 50, offset = 0 } = params
  let url = `${API_BASE}/resource/?user_id=${userId}&limit=${limit}&offset=${offset}`
  if (resourceType) url += `&resource_type=${resourceType}`
  if (status) url += `&status=${status}`
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
  return apiPost(`${API_BASE}/resource/generate`, body, 120000)
}

export function deleteResource(resourceId: string | number, userId: string | number) {
  return apiDelete(`${API_BASE}/resource/${resourceId}?user_id=${userId}`)
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
