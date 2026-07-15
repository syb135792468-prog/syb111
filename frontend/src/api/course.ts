/**
 * 课程信息 API 客户端（赛题对齐：高等教育 Python 课程入口展示）
 */
import { apiGet } from './index'
import { API_BASE } from '../utils/constants'

export interface OutlineItem {
  order: number
  name: string
  status: 'mastered' | 'weak' | 'not_started'
}

export interface CourseInfo {
  course: {
    name: string
    intro: string
    target: string
    audience: string
    modules: string[]
    competition: { name: string; problem_id: string; problem_name: string }
  }
  outline: OutlineItem[]
  progress: {
    mastered_count: number
    weak_count: number
    total_points: number
    resource_count: number
    error_count: number
    knowledge_level: string
    learning_goal: string
  }
}

export function getCourseInfo(userId: string | number) {
  return apiGet<CourseInfo>(`${API_BASE}/course/info?user_id=${userId}`, 10000)
}
