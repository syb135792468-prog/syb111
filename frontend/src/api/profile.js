import { apiGet, apiPut, apiDelete } from './index'
import { API_BASE } from '../utils/constants'

export function loadProfile(userId) {
  return apiGet(`${API_BASE}/profile/${userId}`)
}

export function updateProfile(userId, data) {
  return apiPut(`${API_BASE}/profile/${userId}/update`, data)
}

export function resetProfile(userId) {
  return apiDelete(`${API_BASE}/profile/${userId}`)
}
