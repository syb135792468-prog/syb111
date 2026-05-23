import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { login as apiLogin, register as apiRegister, getMe } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('auth_token') || '')
  const username = ref(localStorage.getItem('auth_username') || '')
  const userId = ref(localStorage.getItem('auth_user_id') || '')
  const showAuthModal = ref(false)

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(data) {
    token.value = data.access_token
    username.value = data.username
    userId.value = String(data.user_id)
    localStorage.setItem('auth_token', data.access_token)
    localStorage.setItem('auth_username', data.username)
    localStorage.setItem('auth_user_id', String(data.user_id))
    showAuthModal.value = false
  }

  function logout() {
    token.value = ''
    username.value = ''
    userId.value = ''
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_username')
    localStorage.removeItem('auth_user_id')
    showAuthModal.value = true
  }

  async function login(usernameStr, password) {
    const resp = await apiLogin(usernameStr, password)
    if (resp.code === 200) {
      setAuth(resp.data)
      return { success: true }
    }
    return { success: false, message: resp.message || '登录失败' }
  }

  async function register(usernameStr, password) {
    const resp = await apiRegister(usernameStr, password)
    if (resp.code === 200) {
      setAuth(resp.data)
      return { success: true }
    }
    return { success: false, message: resp.message || '注册失败' }
  }

  async function checkAuth() {
    if (!token.value) {
      showAuthModal.value = true
      return false
    }
    try {
      const resp = await getMe()
      if (resp.code === 200) {
        username.value = resp.data.username
        userId.value = String(resp.data.user_id)
        localStorage.setItem('auth_username', resp.data.username)
        localStorage.setItem('auth_user_id', String(resp.data.user_id))
        return true
      }
    } catch (e) {
      // token invalid
    }
    logout()
    return false
  }

  return {
    token, username, userId, showAuthModal, isLoggedIn,
    login, register, logout, checkAuth, setAuth,
  }
})
