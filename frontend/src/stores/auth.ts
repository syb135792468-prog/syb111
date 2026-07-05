import { create } from 'zustand'
import { login as apiLogin, register as apiRegister, getMe } from '../api/auth'
import { setAuthGetter } from '../api/index'
import { setImageTokenGetter } from '../api/images'
import { setMultimodalTokenGetter } from '../api/multimodal'

interface AuthData {
  access_token: string
  username: string
  user_id: number | string
}

interface AuthResult {
  success: boolean
  message?: string
}

interface AuthState {
  token: string
  username: string
  userId: string
  showAuthModal: boolean
  isLoggedIn: boolean
  login: (username: string, password: string) => Promise<AuthResult>
  register: (username: string, password: string) => Promise<AuthResult>
  logout: () => void
  checkAuth: () => Promise<boolean>
  setAuth: (data: AuthData) => void
  setShowAuthModal: (show: boolean) => void
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('auth_token') || '',
  username: localStorage.getItem('auth_username') || '',
  userId: localStorage.getItem('auth_user_id') || '',
  showAuthModal: false,
  isLoggedIn: !!localStorage.getItem('auth_token'),

  setAuth: (data) => {
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('auth_username', data.username)
    localStorage.setItem('auth_user_id', String(data.user_id))
    set({
      token: data.access_token,
      username: data.username,
      userId: String(data.user_id),
      isLoggedIn: true,
      showAuthModal: false,
    })
  },

  logout: () => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_username')
    localStorage.removeItem('auth_user_id')
    set({ token: '', username: '', userId: '', isLoggedIn: false, showAuthModal: true })
  },

  setShowAuthModal: (show) => set({ showAuthModal: show }),

  login: async (username, password) => {
    const resp = await apiLogin(username, password)
    if (resp.code === 200 && resp.data) {
      get().setAuth(resp.data)
      return { success: true }
    }
    return { success: false, message: resp.message || '登录失败' }
  },

  register: async (username, password) => {
    const resp = await apiRegister(username, password)
    if (resp.code === 200 && resp.data) {
      get().setAuth(resp.data)
      return { success: true }
    }
    return { success: false, message: resp.message || '注册失败' }
  },

  checkAuth: async () => {
    const { token, logout } = get()
    if (!token) {
      set({ showAuthModal: true })
      return false
    }
    try {
      const resp = await getMe()
      if (resp.code === 200 && resp.data) {
        set({
          username: resp.data.username,
          userId: String(resp.data.user_id),
        })
        localStorage.setItem('auth_username', resp.data.username)
        localStorage.setItem('auth_user_id', String(resp.data.user_id))
        return true
      }
    } catch {
      // token invalid
    }
    logout()
    return false
  },
}))

// Register auth getter for API layer (breaks circular dependency)
setAuthGetter(
  () => useAuthStore.getState().token,
  () => useAuthStore.getState().logout()
)
setImageTokenGetter(() => useAuthStore.getState().token)
setMultimodalTokenGetter(() => useAuthStore.getState().token)
