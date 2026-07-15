import { apiPost } from './index'
import { API_BASE } from '../utils/constants'

interface ApiResponse<T = unknown> {
  code: number
  message?: string
  data?: T
}

export interface FreePracticeQuestion {
  resource_id: number
  title: string
  question_text: string
  difficulty: 'easy' | 'medium' | 'hard'
  knowledge_point: string
  has_test_cases: boolean
}

function unwrap<T>(resp: ApiResponse<T>, fallback: string): T {
  if (resp.code === 200 && resp.data) return resp.data
  throw new Error(resp.message || fallback)
}

export async function generateCodeQuiz(
  knowledgePoint: string,
  difficulty: 'easy' | 'medium' | 'hard',
): Promise<FreePracticeQuestion> {
  const resp = await apiPost<FreePracticeQuestion>(
    `${API_BASE}/playground/generate-code-quiz`,
    { knowledge_point: knowledgePoint, difficulty },
    60000,
  )
  return unwrap(resp, '出题失败，请稍后重试')
}
