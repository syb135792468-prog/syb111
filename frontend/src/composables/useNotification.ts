/**
 * useNotification - 用户实时通知 SSE 长连接（全局单例）
 *
 * 后端 GET /api/notifications/stream 推送事件：
 * - path_updated: 检测到薄弱点自动插入复习节点
 * - path_reordered: 路径手动重排
 * - evaluation_completed: 路径评估完成
 * - quiz_synced: 测验结果同步到路径
 * - resource_ready: 异步资源生成完成
 * - tutor_video_ready: 辅导视频生成完成
 *
 * 收到事件后：
 * 1. 调 useAppStore.showToast 显示提示
 * 2. dispatchEvent 触发对应页面数据刷新
 *
 * 与 useSSE 不同：useSSE 是按需建立的短连接（每次 sendMessage），
 * useNotification 是全局长连接，App 启动登录后建立，登出时断开。
 */
import { useEffect } from 'react'
import { API_BASE } from '../utils/constants'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'

let _controller: AbortController | null = null
let _reconnectTimer: ReturnType<typeof setTimeout> | null = null
let _reconnectDelay = 5000
const MAX_RECONNECT_DELAY = 30000

const EVENT_BUS_MAP: Record<string, string> = {
  path_updated: 'path-dirty',
  path_reordered: 'path-dirty',
  evaluation_completed: 'path-dirty',
  quiz_synced: 'path-dirty',
  resource_ready: 'resource-dirty',
  tutor_video_ready: 'error-book-dirty',
}

function handleEvent(eventType: string, data: any) {
  const message = data?.message || ''
  if (message) {
    useAppStore.getState().showToast(message, 'info')
  }
  const busEvent = EVENT_BUS_MAP[eventType]
  if (busEvent) {
    window.dispatchEvent(new CustomEvent(busEvent, { detail: { eventType, ...data } }))
  }
}

async function startStream() {
  const token = useAuthStore.getState().token
  if (!token) return

  _controller = new AbortController()

  try {
    const resp = await fetch(`${API_BASE}/notifications/stream`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream',
      },
      signal: _controller.signal,
    })
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }
    _reconnectDelay = 5000  // 连接成功后重置退避

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''

      for (const part of parts) {
        if (!part.trim() || part.startsWith(':')) continue  // 心跳注释
        const lines = part.split('\n')
        let eventType = ''
        let dataStr = ''
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            eventType = line.slice(7).trim()
          } else if (line.startsWith('data: ')) {
            dataStr += (dataStr ? '\n' : '') + line.slice(6)
          }
        }
        if (!eventType || !dataStr) continue
        try {
          const data = JSON.parse(dataStr)
          handleEvent(eventType, data)
        } catch (e) {
          console.error('[notification] 解析事件失败:', e, 'raw=', dataStr)
        }
      }
    }
  } catch (e: unknown) {
    if (e instanceof Error && e.name === 'AbortError') {
      return  // 主动断开，不重连
    }
    console.error('[notification] 连接失败:', e instanceof Error ? e.message : e)
  } finally {
    _controller = null
  }

  // 自动重连（带退避）
  if (useAuthStore.getState().token) {
    if (_reconnectTimer) clearTimeout(_reconnectTimer)
    _reconnectTimer = setTimeout(() => {
      _reconnectDelay = Math.min(_reconnectDelay * 2, MAX_RECONNECT_DELAY)
      startStream()
    }, _reconnectDelay)
  }
}

export function connectNotification() {
  if (_controller) return  // 已连接
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }
  _reconnectDelay = 5000
  startStream()
}

export function disconnectNotification() {
  if (_reconnectTimer) {
    clearTimeout(_reconnectTimer)
    _reconnectTimer = null
  }
  if (_controller) {
    _controller.abort()
    _controller = null
  }
}

export function useNotification() {
  const isLoggedIn = useAuthStore((s) => s.isLoggedIn)

  useEffect(() => {
    if (isLoggedIn) {
      connectNotification()
    } else {
      disconnectNotification()
    }
    return () => {
      // 组件卸载不主动断开（保持全局长连接）
    }
  }, [isLoggedIn])
}
