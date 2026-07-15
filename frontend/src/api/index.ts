// Lazy auth getter - set by the auth store to break circular dependency
let _getToken: () => string = () => ''
let _onUnauthorized: () => void = () => {}

export function setAuthGetter(getToken: () => string, onUnauthorized: () => void) {
  _getToken = getToken
  _onUnauthorized = onUnauthorized
}

export interface ApiResponse<T = unknown> {
  code: number
  message?: string
  data?: T
  request_id?: string
}

export class ApiError extends Error {
  httpStatus: number
  code: number
  detail?: unknown
  url: string

  constructor(message: string, httpStatus: number, code: number, url: string, detail?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.httpStatus = httpStatus
    this.code = code
    this.url = url
    this.detail = detail
  }
}

interface FetchOptions extends RequestInit {
  headers?: Record<string, string>
  timeout?: number
}

export async function apiFetch(url: string, options: FetchOptions = {}): Promise<Response> {
  const token = _getToken()

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers,
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const timeout = options.timeout ?? 20000
  let controller: AbortController | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  if (!options.signal) {
    controller = new AbortController()
    timeoutId = setTimeout(() => controller!.abort(), timeout)
  }

  try {
    const response = await fetch(url, {
      ...options,
      headers,
      signal: options.signal || controller!.signal,
    })

    if (response.status === 401) {
      _onUnauthorized()
      throw new Error('认证已过期，请重新登录')
    }

    return response
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') {
      throw new Error('请求超时，请检查网络连接')
    }
    throw e
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }
}

async function parseResponse<T>(resp: Response, url: string): Promise<ApiResponse<T>> {
  let body: ApiResponse<T>
  try {
    body = await resp.json() as ApiResponse<T>
  } catch {
    const rawText = await resp.text().catch(() => '<unreadable>')
    console.error(`[API ${resp.status}] ${url} 响应非 JSON:`, rawText)
    throw new ApiError(`HTTP ${resp.status} 响应非 JSON`, resp.status, resp.status, url)
  }

  if (!resp.ok || body.code !== 200) {
    const detail = (body.data as { detail?: unknown } | undefined)?.detail
    console.error(`[API ${resp.status}] ${url}`, {
      code: body.code,
      message: body.message,
      detail,
      request_id: body.request_id,
    })
    throw new ApiError(
      body.message || `HTTP ${resp.status}`,
      resp.status,
      body.code ?? resp.status,
      url,
      detail ?? body.data,
    )
  }

  return body
}

export async function apiGet<T = unknown>(url: string, timeout?: number): Promise<ApiResponse<T>> {
  const resp = await apiFetch(url, { timeout })
  return parseResponse<T>(resp, url)
}

export async function apiPost<T = unknown>(url: string, data?: unknown, timeout?: number): Promise<ApiResponse<T>> {
  const resp = await apiFetch(url, {
    method: 'POST',
    body: data ? JSON.stringify(data) : undefined,
    timeout,
  })
  return parseResponse<T>(resp, url)
}

export async function apiPut<T = unknown>(url: string, data?: unknown): Promise<ApiResponse<T>> {
  const resp = await apiFetch(url, {
    method: 'PUT',
    body: data ? JSON.stringify(data) : undefined,
  })
  return parseResponse<T>(resp, url)
}

export async function apiPatch<T = unknown>(url: string, data?: unknown): Promise<ApiResponse<T>> {
  const resp = await apiFetch(url, {
    method: 'PATCH',
    body: data ? JSON.stringify(data) : undefined,
  })
  return parseResponse<T>(resp, url)
}

export async function apiDelete<T = unknown>(url: string): Promise<ApiResponse<T>> {
  const resp = await apiFetch(url, { method: 'DELETE' })
  return parseResponse<T>(resp, url)
}
