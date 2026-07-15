import { apiGet } from './index'
import { API_BASE } from '../utils/constants'

export interface GraphNode {
  code: string
  name: string
  module: string
  level: number
  difficulty: number
  estimated_time: number
  description: string | null
  mastery_score: number
  state: 'locked' | 'available' | 'learning' | 'mastered'
  evidence_count: number
  quiz_correct_count: number
  quiz_total_count: number
  code_practice_count: number
  last_evidence_at: string | null
}

export interface GraphEdge {
  source_code: string
  target_code: string
  edge_type: 'prerequisite' | 'contains' | 'related'
}

export interface GraphStats {
  total: number
  mastered: number
  learning: number
  available: number
  locked: number
}

export interface ModuleMeta {
  name: string
  color: string
  order: number
}

export interface StateMeta {
  name: string
  color: string
}

export interface GraphSnapshot {
  nodes: GraphNode[]
  edges: GraphEdge[]
  stats: GraphStats
  modules: Record<string, ModuleMeta>
  states: Record<string, StateMeta>
}

export interface NodePrerequisite {
  code: string
  name: string
  state: string
  mastery_score: number
}

export interface NodeEvidence {
  id: number
  source_type: string
  source_id: number | null
  score: number
  weight: number
  detail: Record<string, unknown> | null
  created_at: string
}

export interface NodeDetail {
  node: {
    id: number
    code: string
    name: string
    module: string
    level: number
    description: string | null
    difficulty: number
    estimated_time: number
    mastery_threshold: number
    aliases: string[]
    is_active: boolean
  }
  mastery: {
    mastery_score: number
    state: string
    evidence_count: number
    quiz_correct_count: number
    quiz_total_count: number
    code_practice_count: number
    last_evidence_at: string | null
  } | null
  effective_state: string
  prerequisites: NodePrerequisite[]
  recent_evidences: NodeEvidence[]
  threshold: number
  evidence_threshold: number
  error_count: number
  related_paths: Array<{
    path_id: number
    path_title: string
    node_id: number
    node_status: string
  }>
  modules: Record<string, ModuleMeta>
  states: Record<string, StateMeta>
}

export interface PracticeQuestion {
  resource_id: number
  question_index: number
  title: string
  resource_type: string
  weight: number
  attempted: boolean
  last_correct: boolean
  priority: number
}

export interface NodePractice {
  node_code: string
  node_name: string
  questions: PracticeQuestion[]
  total: number
}

export interface GraphOverviewStats {
  total_nodes: number
  state_counts: {
    locked: number
    available: number
    learning: number
    mastered: number
  }
  module_stats: Array<{
    module: string
    module_name: string
    color: string
    touched: number
    mastered: number
  }>
  recent_evidence_count_7d: number
  states: Record<string, StateMeta>
}

export function getGraphSnapshot(params?: { module?: string; state?: string }) {
  const search = new URLSearchParams()
  if (params?.module) search.set('module', params.module)
  if (params?.state) search.set('state', params.state)
  const qs = search.toString()
  return apiGet(`${API_BASE}/graph/snapshot${qs ? `?${qs}` : ''}`)
}

export function getNodeDetail(nodeCode: string) {
  return apiGet(`${API_BASE}/graph/node/${nodeCode}`)
}

export function getNodePractice(nodeCode: string, limit = 5) {
  return apiGet(`${API_BASE}/graph/node/${nodeCode}/practice?limit=${limit}`)
}

export function getGraphStats() {
  return apiGet(`${API_BASE}/graph/stats`)
}
