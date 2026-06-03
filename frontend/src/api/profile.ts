import { apiGet, apiPut, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function loadProfile(userId: string | number) {
  return apiGet(`${API_BASE}/profile/${userId}`)
}

export function updateProfile(userId: string | number, data: Record<string, unknown>) {
  return apiPut(`${API_BASE}/profile/${userId}/update`, data)
}

export function resetProfile(userId: string | number) {
  if (!userId) return Promise.reject(new Error('用户未登录'))
  return apiDelete(`${API_BASE}/profile/${userId}`)
}
