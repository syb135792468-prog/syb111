import { apiGet, apiPost } from './index'
import { API_BASE } from '../utils/constants'

interface ApiResponse<T = unknown> {
  code: number
  message?: string
  data?: T
  error_code?: string
  error_detail?: string
}

export class DailyApiError extends Error {
  errorCode?: string
  errorDetail?: string

  constructor(message: string, errorCode?: string, errorDetail?: string) {
    super(message)
    this.name = 'DailyApiError'
    this.errorCode = errorCode
    this.errorDetail = errorDetail
  }
}

export interface StreakData {
  current_streak: number
  longest_streak: number
  streak_status: string
  recovery_progress: number
}

export interface CompletionStats {
  total_users: number
  completed_users: number
  correct_users: number
  correct_rate: number
}

export interface DailyChallengeData {
  challenge: {
    id: number
    resource_id: number
    date: string
    questionText: string
    options: string[]
    type: string
    title: string
    completed: boolean
    is_correct: boolean | null
    difficulty: string
    knowledge_point: string | null
  }
  streak: StreakData
  completion_stats: CompletionStats
}

export interface DailySubmitResult {
  is_correct: boolean
  correct_answer: string
  explanation: string
  feedback: string
  streak: StreakData
}

export interface HintResult {
  hint: string
  hint_index: number
  remaining: number
}

function unwrapResponse<T>(resp: ApiResponse<T>, fallbackMessage: string): T {
  if (resp.code === 200 && resp.data) return resp.data
  throw new DailyApiError(
    resp.message || fallbackMessage,
    resp.error_code,
    resp.error_detail,
  )
}

let todayChallengePromise: Promise<DailyChallengeData> | null = null

export async function getTodayChallenge(): Promise<DailyChallengeData> {
  if (todayChallengePromise) return todayChallengePromise

  todayChallengePromise = (async () => {
    try {
      const resp = await apiGet<DailyChallengeData>(`${API_BASE}/daily/today`)
      return unwrapResponse(resp, '题目加载失败，请稍后重试')
    } finally {
      todayChallengePromise = null
    }
  })()

  return todayChallengePromise
}

export async function submitDailyAnswer(answer: string): Promise<DailySubmitResult> {
  const resp = await apiPost<DailySubmitResult>(`${API_BASE}/daily/submit`, { user_answer: answer })
  return unwrapResponse(resp, '提交失败，请稍后重试')
}

export async function getStreakInfo(): Promise<StreakData | null> {
  const resp = await apiGet<StreakData>(`${API_BASE}/daily/streak`)
  if (resp.code === 200 && resp.data) return resp.data
  return null
}

export async function getDailyHint(hintIndex: number): Promise<HintResult> {
  const resp = await apiPost<HintResult>(`${API_BASE}/daily/hint`, { hint_index: hintIndex })
  return unwrapResponse(resp, '获取提示失败，请稍后重试')
}

// --- 额外挑战 ---

export interface NextChallengeData {
  challenge: {
    id: number
    resource_id: number
    questionText: string
    options: string[]
    type: string
    title: string
    difficulty: string
    knowledge_point: string | null
  }
}

export interface NextChallengeSubmitResult {
  is_correct: boolean
  correct_answer: string
  explanation: string
  feedback: string
}

export async function getNextChallenge(): Promise<NextChallengeData> {
  const resp = await apiGet<NextChallengeData>(`${API_BASE}/daily/next-challenge`, 60000)
  return unwrapResponse(resp, '题目生成失败，请稍后重试')
}

export async function submitNextChallenge(resourceId: number, answer: string): Promise<NextChallengeSubmitResult> {
  const resp = await apiPost<NextChallengeSubmitResult>(`${API_BASE}/daily/next-challenge/submit`, { resource_id: resourceId, user_answer: answer })
  return unwrapResponse(resp, '提交失败，请稍后重试')
}

export async function getNextChallengeHint(resourceId: number, hintIndex: number): Promise<HintResult> {
  const resp = await apiPost<HintResult>(`${API_BASE}/daily/next-challenge/hint`, { resource_id: resourceId, hint_index: hintIndex }, 60000)
  return unwrapResponse(resp, '获取提示失败，请稍后重试')
}
