import { useState, useCallback, useEffect, useRef } from 'react'
import { fetchLearningProfile, recordLearningEvent } from '../api/learningProfile'
import type { LearningProfile } from '../api/learningProfile'
import { useAuthStore } from '../stores/auth'

interface LearningEvent {
  action: string
  topic: string
  score?: number
  duration?: number
}

// 共享的画像数据（模块级）
let sharedProfile: LearningProfile | null = null
const listeners = new Set<(profile: LearningProfile | null) => void>()

function notifyListeners() {
  listeners.forEach((cb) => {
    try { cb(sharedProfile) } catch (e) { console.error(e) }
  })
}

/**
 * 学习画像 React Hook
 */
export function useLearningProfile() {
  const [profile, setProfile] = useState<LearningProfile | null>(sharedProfile)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { userId } = useAuthStore()
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // 订阅画像更新
  useEffect(() => {
    const callback = (p: LearningProfile | null) => {
      if (mountedRef.current) setProfile(p)
    }
    listeners.add(callback)
    return () => { listeners.delete(callback) }
  }, [])

  const loadProfile = useCallback(async (uid?: string | number) => {
    const targetId = uid || userId
    if (!targetId) return

    setLoading(true)
    setError(null)
    try {
      const data = await fetchLearningProfile(targetId)
      sharedProfile = data
      if (mountedRef.current) setProfile(data)
      notifyListeners()
    } catch (e) {
      console.error('Failed to load learning profile:', e)
      if (mountedRef.current) setError('加载学习画像失败')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [userId])

  const notifyLearningEvent = useCallback(async (event: LearningEvent) => {
    const uid = userId
    if (!uid) return

    try {
      const updated = await recordLearningEvent(uid, event)
      sharedProfile = updated
      if (mountedRef.current) setProfile(updated)
      notifyListeners()
    } catch (e) {
      console.error('Failed to record learning event:', e)
    }
  }, [userId])

  return { profile, loading, error, loadProfile, notifyLearningEvent }
}
