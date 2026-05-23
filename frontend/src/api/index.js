import { useAuthStore } from '../stores/auth'

export async function apiFetch(url, options = {}) {
  const authStore = useAuthStore()

  const headers = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (authStore.token) {
    headers['Authorization'] = `Bearer ${authStore.token}`
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (response.status === 401) {
    authStore.logout()
    throw new Error('认证已过期，请重新登录')
  }

  return response
}

export async function apiGet(url) {
  const resp = await apiFetch(url)
  return resp.json()
}

export async function apiPost(url, data) {
  const resp = await apiFetch(url, {
    method: 'POST',
    body: JSON.stringify(data),
  })
  return resp.json()
}

export async function apiPut(url, data) {
  const resp = await apiFetch(url, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
  return resp.json()
}

export async function apiDelete(url) {
  const resp = await apiFetch(url, { method: 'DELETE' })
  return resp.json()
}
