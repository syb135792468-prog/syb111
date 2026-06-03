import { useEffect, useRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { updateProgress } from '../api/progress'

const TOPIC_PREFIX = '在线学习'
const INTERVAL_SEC = 60

function getDailyTopic(): string {
  const d = new Date()
  const dateStr = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return `${TOPIC_PREFIX}_${dateStr}`
}

export function useStudyTimer() {
  const { userId, isLoggedIn } = useAuthStore()
  const accumulated = useRef(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!isLoggedIn || !userId) return

    const flush = () => {
      if (accumulated.current <= 0) return
      const sec = accumulated.current
      accumulated.current = 0
      updateProgress(userId, { topic: getDailyTopic(), status: 'in_progress', duration: sec }).catch(() => {})
    }

    const tick = () => {
      // 只要页面打开且可见，就累计时间，不要求用户交互
      if (document.visibilityState === 'hidden') return
      accumulated.current += INTERVAL_SEC
      flush()
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        // 页面重新可见时什么都不做，等下一个 tick 自然继续
      } else {
        // 页面隐藏时先保存已积累的时间
        flush()
      }
    }

    timerRef.current = setInterval(tick, INTERVAL_SEC * 1000)
    document.addEventListener('visibilitychange', onVisibilityChange)

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
      flush()
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [isLoggedIn, userId])
}
