import { apiPost, apiGet } from './index'
import { API_BASE } from '../utils/constants'

export function register(username, password) {
  return apiPost(`${API_BASE}/auth/register`, { username, password })
}

export function login(username, password) {
  return apiPost(`${API_BASE}/auth/login`, { username, password })
}

export function getMe() {
  return apiGet(`${API_BASE}/auth/me`)
}
