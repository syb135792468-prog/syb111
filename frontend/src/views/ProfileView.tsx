import React, { useState, useEffect, useCallback, useRef, useImperativeHandle, forwardRef } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { fetchLearningProfile } from '../api/learningProfile'
import type { LearningProfile } from '../api/learningProfile'
import { resetProgress } from '../api/progress'
import { resetProfile } from '../api/profile'
import AppHeader from '../components/layout/AppHeader'
import ProfileCards from '../components/profile/ProfileCards'
import RadarChart from '../components/profile/RadarChart'
import StyleChart from '../components/profile/StyleChart'
import KnowledgeTags from '../components/profile/KnowledgeTags'
import StudyTimeChart from '../components/profile/StudyTimeChart'
import ConfirmDialog from '../components/common/ConfirmDialog'
import { RefreshCw, Activity, RotateCcw, UserCog } from 'lucide-react'

export interface ProfileViewHandle {
  refresh: () => void
}

// --- 组件 ---
const ProfileView = forwardRef<ProfileViewHandle>((_props, ref) => {
  const authStore = useAuthStore()
  const appStore = useAppStore()

  // --- 状态 ---
  const [profile, setProfile] = useState<LearningProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  // 重置状态（各自独立）
  const [resettingProgress, setResettingProgress] = useState(false)
  const [resettingProfile, setResettingProfile] = useState(false)

  // 确认弹窗状态
  const [confirmProgress, setConfirmProgress] = useState(false)
  const [confirmProfile, setConfirmProfile] = useState(false)

  // --- 加载画像 ---
  const loadProfile = useCallback(async () => {
    if (!authStore.userId) {
      if (mountedRef.current) {
        setError('请先登录')
        setLoading(false)
      }
      return
    }
    setLoading(true)
    setError(null)
    try {
      const data = await fetchLearningProfile(authStore.userId)
      if (!mountedRef.current) return
      setProfile(data)
    } catch (e) {
      if (!mountedRef.current) return
      console.error('Failed to load learning profile:', e)
      setError('加载学习画像失败，请稍后重试')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [authStore.userId])

  // --- 暴露给外部调用 ---
  useImperativeHandle(ref, () => ({ refresh: loadProfile }), [loadProfile])

  // --- 初始加载 ---
  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  // --- 监听学习事件，自动刷新画像 ---
  useEffect(() => {
    let debounceTimer: ReturnType<typeof setTimeout> | null = null
    const handleDirty = () => {
      // 防抖：多次事件在 1.5s 内合并为一次刷新
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadProfile()
      }, 1500)
    }
    window.addEventListener('learning-profile-dirty', handleDirty)
    return () => {
      window.removeEventListener('learning-profile-dirty', handleDirty)
      if (debounceTimer) clearTimeout(debounceTimer)
    }
  }, [loadProfile])

  // --- 重置进度 ---
  const handleResetProgress = useCallback(async () => {
    if (resettingProgress) return
    setResettingProgress(true)
    try {
      const resp = await resetProgress(authStore.userId)
      if (resp.code === 200) {
        appStore.showToast(resp.message || '学习进度已重置', 'success')
        setConfirmProgress(false)
        await loadProfile()
      } else {
        appStore.showToast(resp.message || '重置失败', 'error')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('重置进度失败：' + msg, 'error')
    } finally {
      setResettingProgress(false)
    }
  }, [resettingProgress, authStore.userId, appStore, loadProfile])

  // --- 重置画像 ---
  const handleResetProfile = useCallback(async () => {
    if (resettingProfile) return
    setResettingProfile(true)
    try {
      // 先清除进度，成功后再重置画像
      const progressResp = await resetProgress(authStore.userId)
      if (progressResp.code !== 200) {
        appStore.showToast(progressResp.message || '重置进度失败', 'error')
        return
      }

      const profileResp = await resetProfile(authStore.userId)
      if (profileResp.code === 200) {
        appStore.showToast('学习画像和进度已重置', 'success')
        setConfirmProfile(false)
        await loadProfile()
      } else {
        appStore.showToast(profileResp.message || '重置画像失败', 'error')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误'
      appStore.showToast('重置画像失败：' + msg, 'error')
    } finally {
      setResettingProfile(false)
    }
  }, [resettingProfile, authStore.userId, appStore, loadProfile])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="学习画像">
        <button
          onClick={loadProfile}
          className="text-gray-400 hover:text-gray-600 p-2 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* 骨架屏加载态 */}
        {loading ? (
          <div className="max-w-5xl mx-auto space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {[1, 2, 3].map(i => (
                <div key={i} className="rounded-xl overflow-hidden shadow-sm animate-pulse">
                  <div className="h-24 bg-gray-200" />
                  <div className="h-12 bg-gray-100" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2].map(i => (
                <div key={i} className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                  <div className="h-4 w-24 bg-gray-200 rounded mb-4 animate-pulse" />
                  <div className="h-[280px] bg-gray-100 rounded animate-pulse" />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2].map(i => (
                <div key={i} className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
                  <div className="h-4 w-28 bg-gray-200 rounded mb-3 animate-pulse" />
                  <div className="flex flex-wrap gap-2">
                    {[1, 2, 3, 4].map(j => (
                      <div key={j} className="h-6 w-20 bg-gray-100 rounded-full animate-pulse" />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : error ? (
          /* 错误态 */
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <Activity className="w-10 h-10 mb-3 text-gray-300" />
            <p className="text-sm">{error}</p>
            <button
              onClick={loadProfile}
              className="mt-3 text-sm text-brand-600 hover:text-brand-700 underline"
            >
              重新加载
            </button>
          </div>
        ) : profile ? (
          /* 正常内容 */
          <div className="max-w-5xl mx-auto space-y-6">
            {/* 顶部状态卡片 */}
            <ProfileCards
              level={profile.knowledgeLevel}
              levelDesc="根据你的学习表现自动评估"
              goal={profile.learningGoal}
              goalDesc="影响推荐资源的类型和难度"
              motivation={profile.learningMotivation.status}
              motivationDesc="基于最近7天学习频率分析"
              motivationValue={profile.learningMotivation.value}
            />

            {/* 雷达图 + 饼图 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <RadarChart radarData={profile.radarData} />
              <StyleChart styleData={profile.learningStyle} />
            </div>

            {/* 学习时间 */}
            <StudyTimeChart
              data={profile.dailyStudyTime}
              totalHours={profile.totalStudyHours}
            />

            {/* 已掌握 / 薄弱知识点 */}
            <KnowledgeTags
              mastered={profile.masteredPoints}
              weak={profile.weakPoints}
            />

            {/* 画像详情 */}
            <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-4">画像详情</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                  <p className="text-xs text-gray-400">学习风格</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{profile.learningStyle.dominant}</p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {({
                      '视觉型': '你喜欢通过图表和示例来学习',
                      '听觉型': '你喜欢通过听讲解来学习',
                      '动手型': '你喜欢通过编写代码来学习',
                      '混合型': '你有均衡的学习风格',
                    } as Record<string, string>)[profile.learningStyle.dominant] || '你有均衡的学习风格'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">时长偏好</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{profile.timePreference}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">最后学习</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{profile.lastStudyTime}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">答题正确率</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">
                    {profile.accuracy > 0 ? `${profile.accuracy}%` : '暂无'}
                  </p>
                </div>
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4 pt-4 border-t border-gray-50">
                <div>
                  <p className="text-xs text-gray-400">总学习时长</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">
                    {profile.totalStudyHours > 0 ? `${profile.totalStudyHours} 小时` : '暂无'}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">知识水平</p>
                  <p className="text-sm font-medium text-gray-700 mt-1">{profile.knowledgeLevel}</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">已掌握</p>
                  <p className="text-sm font-medium text-green-600 mt-1">{profile.masteredPoints.length} 个知识点</p>
                </div>
                <div>
                  <p className="text-xs text-gray-400">薄弱项</p>
                  <p className="text-sm font-medium text-orange-500 mt-1">{profile.weakPoints.length} 个知识点</p>
                </div>
              </div>
            </div>

            {/* 重置操作区 */}
            <div className="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">数据管理</h3>
              <p className="text-xs text-gray-400 mb-4">重置操作不可撤销，请谨慎操作</p>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setConfirmProgress(true)}
                  disabled={resettingProgress || resettingProfile}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm text-amber-700 border border-amber-200 bg-amber-50 rounded-lg hover:bg-amber-100 transition-colors disabled:opacity-40"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  重置学习进度
                </button>
                <button
                  onClick={() => setConfirmProfile(true)}
                  disabled={resettingProgress || resettingProfile}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm text-red-700 border border-red-200 bg-red-50 rounded-lg hover:bg-red-100 transition-colors disabled:opacity-40"
                >
                  <UserCog className="w-3.5 h-3.5" />
                  重置学习画像
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {/* 确认弹窗：重置进度 */}
      <ConfirmDialog
        show={confirmProgress}
        title="重置学习进度"
        message={`将清除所有知识点的学习记录，包括：\n• 所有课程的完成状态\n• 所有章节的学习进度\n• 所有测验的分数和时长\n\n将保留：\n• 你的学习画像和能力评估\n• 你的错题本记录\n\n此操作不可撤销，确定继续吗？`}
        confirmText="确认重置"
        dangerLevel="warning"
        isLoading={resettingProgress}
        onConfirm={handleResetProgress}
        onCancel={() => setConfirmProgress(false)}
      />

      {/* 确认弹窗：重置画像 */}
      <ConfirmDialog
        show={confirmProfile}
        title="重置学习画像"
        message={`将完全重置你的学习数据，包括：\n• 所有知识点的学习记录\n• 所有课程的完成状态\n• AI生成的7维学习画像\n• 所有个性化学习推荐\n\n将保留：\n• 你的用户账号和基本信息\n• 你的错题本记录\n\n此操作不可撤销，确定继续吗？`}
        confirmText="确认重置"
        dangerLevel="danger"
        isLoading={resettingProfile}
        onConfirm={handleResetProfile}
        onCancel={() => setConfirmProfile(false)}
      />
    </div>
  )
})

ProfileView.displayName = 'ProfileView'

export default ProfileView
