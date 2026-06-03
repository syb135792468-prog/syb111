/**
 * 学习路径 API 客户端（软件杯A3赛题核心功能）
 * 封装 /api/learning-path 相关接口
 */
import { apiGet, apiPost, apiDelete } from './index'

// ==================== 类型定义 ====================

export interface PathNodeResource {
  id: number
  node_id: number
  resource_type: string
  title: string
  description?: string
  content?: string
  resource_id?: number
  duration: number
  difficulty: number
  status: string
  is_cached: boolean
  created_at?: string
  updated_at?: string
}

export interface PathNode {
  id: number
  learning_path_id: number
  knowledge_point: string
  description?: string
  order: number
  prerequisites: string[]
  difficulty: number
  estimated_time: number
  mastery_threshold: number
  mastery: number
  status: 'not_started' | 'in_progress' | 'completed' | 'needs_review' | 'skipped'
  progress: number
  node_type: 'new' | 'review'
  started_at?: string
  completed_at?: string
  last_study_at?: string
  created_at?: string
  resources: PathNodeResource[]
}

export interface LearningPathData {
  id: number
  user_id: number
  title: string
  description?: string
  goal?: string
  topic: string
  status: 'active' | 'paused' | 'completed' | 'archived'
  total_nodes: number
  completed_nodes: number
  total_estimated_time: number
  progress_percent: number
  created_at?: string
  updated_at?: string
  nodes: PathNode[]
}

export interface PathListResponse {
  paths: LearningPathData[]
  total: number
}

export interface GeneratePathRequest {
  topic?: string
  goal?: string
  max_steps?: number
  mastered_points?: string[]
  weak_points?: string[]
}

export interface NodeResourceResponse {
  node_id: number
  knowledge_point: string
  resources: PathNodeResource[]
  cached_count: number
  total_count: number
}

export interface QuizSubmitResult {
  path: LearningPathData
  quiz_result: {
    node_id: number
    correct_count: number
    total_questions: number
    mastery: number
  }
}

// ==================== API 函数 ====================

/** 获取用户的学习路径列表 */
export async function listLearningPaths(status?: string) {
  const params = status ? `?status=${status}` : ''
  return apiGet<PathListResponse>(`/api/learning-path${params}`, 10000)
}

/** 获取单条路径详情（含节点和资源） */
export async function getLearningPath(pathId: number) {
  return apiGet<LearningPathData>(`/api/learning-path/${pathId}`, 10000)
}

/** 生成新的学习路径 */
export async function generateLearningPath(req: GeneratePathRequest = {}) {
  return apiPost<LearningPathData>('/api/learning-path/generate', req, 120000)
}

/** 标记节点完成 */
export async function completePathNode(nodeId: number, mastery?: number) {
  return apiPost<LearningPathData>(
    `/api/learning-path/nodes/${nodeId}/complete`,
    mastery !== undefined ? { mastery } : {},
    10000
  )
}

/** 获取/生成节点资源 */
export async function getNodeResources(nodeId: number, resourceTypes?: string[]) {
  const params = resourceTypes ? `?resource_types=${resourceTypes.join(',')}` : ''
  return apiPost<NodeResourceResponse>(
    `/api/learning-path/nodes/${nodeId}/resources${params}`,
    undefined,
    180000
  )
}

/** 提交测验结果 */
export async function submitQuizResult(
  nodeId: number,
  totalQuestions: number,
  correctCount: number,
  details?: Record<string, unknown>[]
) {
  return apiPost<QuizSubmitResult>('/api/learning-path/quiz/submit', {
    node_id: nodeId,
    total_questions: totalQuestions,
    correct_count: correctCount,
    details,
  }, 15000)
}

/** 删除学习路径 */
export async function deleteLearningPath(pathId: number) {
  return apiDelete(`/api/learning-path/${pathId}`)
}
