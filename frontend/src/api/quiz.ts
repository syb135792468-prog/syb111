import { apiGet, apiPost } from './index'
import { API_BASE } from '../utils/constants'

export function getQuiz(resourceId: string | number) {
  return apiGet(`${API_BASE}/quiz/${resourceId}`)
}

export function submitQuizAnswer(
  resourceId: string | number,
  userAnswer: string,
  spentTime: number,
  questionIndex = 0
) {
  return apiPost(`${API_BASE}/quiz/${resourceId}/submit`, {
    user_answer: userAnswer,
    spent_time: spentTime,
    question_index: questionIndex,
  })
}

export function updateQuizStats(resourceId: string | number, isCorrect: boolean, spentTime: number) {
  return apiPost(`${API_BASE}/quiz/stats`, {
    resource_id: resourceId,
    is_correct: isCorrect,
    spent_time: spentTime,
  })
}

export function generateQuizAnswer(resourceId: string | number, questionIndex = 0) {
  return apiPost(`${API_BASE}/quiz/${resourceId}/generate-answer`, {
    question_index: questionIndex,
  }, 60000)
}
