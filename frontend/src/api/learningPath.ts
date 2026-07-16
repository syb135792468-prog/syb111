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

export interface CommonMistake {
  wrong: string
  error_type: string
  reason: string
}

export interface CollaborationAgent {
  name: string
  role: string
  action: string
}

export interface CollaborationInfo {
  agents: CollaborationAgent[]
  description: string
}

export interface PreTest {
  question: string
  answer: string
  explanation: string
  common_mistakes: CommonMistake[]
  difficulty: string
  resource_id: number
  cached: boolean
  collaboration_info?: CollaborationInfo
}

export interface PreTestSubmitResult {
  is_correct: boolean
  correct_answer: string
  explanation: string
  matched_error_type: string | null
  path: LearningPathData | null
}

// ==================== API 函数 ====================

/** 获取用户的学习路径列表 */
export async function listLearningPaths(status?: string) {
  const params = status ? `?status=${status}` : ''
  return apiGet<PathListResponse>(`/api/learning-path/${params}`, 10000)
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

/** 生成节点前置测试题（PathAgent 调 QuizAgent，Agent 间协作） */
export async function generatePreTest(nodeId: number) {
  return apiPost<PreTest>(
    `/api/learning-path/nodes/${nodeId}/pre-test`,
    {},
    60000
  )
}

/** 提交前置测试答案（答对则节点跳过并推进路径进度） */
export async function submitPreTest(
  nodeId: number,
  body: { user_answer: string; resource_id: number }
) {
  return apiPost<PreTestSubmitResult>(
    `/api/learning-path/nodes/${nodeId}/pre-test/submit`,
    body,
    15000
  )
}

/** 取消跳过节点（恢复 NOT_STARTED，路径进度回退） */
export async function unskipNode(nodeId: number) {
  return apiPost<LearningPathData>(
    `/api/learning-path/nodes/${nodeId}/unskip`,
    {},
    10000
  )
}

/** 规则重排路径 NOT_STARTED 节点（薄弱点优先 + 难度递增） */
export async function reorderPath(pathId: number) {
  return apiPost<LearningPathData & { reorder_info?: { reordered_count: number; weak_points_prioritized: string[] } }>(
    `/api/learning-path/${pathId}/reorder`,
    {},
    15000
  )
}

// ==================== 评估闭环（偏差 F）====================

export interface PathEvaluationReport {
  goal_achievement: 'high' | 'medium' | 'low'
  strengths: string[]
  weaknesses: string[]
  goal_analysis: string
  suggestions: string[]
}

export interface PathRecommendation {
  topic: string
  reason: string
  difficulty: string
}

export interface PathEvaluation {
  achievement_score: number
  mastery_stats: { avg: number; min: number; max: number }
  completion_rate: number
  error_distribution: Record<string, number>
  report: PathEvaluationReport
  recommendations: PathRecommendation[]
  level_upgraded: { from: string; to: string } | null
}

/** 评估路径完成度：规则评分 + LLM 报告 + 画像升级 + 进阶推荐 */
export async function evaluatePath(pathId: number) {
  return apiPost<PathEvaluation>(`/api/learning-path/${pathId}/evaluate`, {}, 90000)
}

/** 基于评估推荐创建进阶学习路径（一键创建） */
export async function createAdvancePath(
  pathId: number,
  topic: string,
  reason: string
) {
  return apiPost<LearningPathData>(
    `/api/learning-path/${pathId}/advance`,
    { topic, reason },
    120000
  )
}
