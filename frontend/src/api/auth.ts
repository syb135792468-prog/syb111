import { apiPost, apiGet } from './index'
import { API_BASE } from '../utils/constants'

interface AuthData {
  access_token: string
  username: string
  user_id: number
}

interface UserProfile {
  username: string
  user_id: number
}

export function register(username: string, password: string) {
  return apiPost<AuthData>(`${API_BASE}/auth/register`, { username, password })
}

export function login(username: string, password: string) {
  return apiPost<AuthData>(`${API_BASE}/auth/login`, { username, password })
}

export function getMe() {
  return apiGet<UserProfile>(`${API_BASE}/auth/me`)
}
