import React, { useState, useEffect, useCallback } from 'react'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { getCourseInfo, type CourseInfo } from '../api/course'
import AppHeader from '../components/layout/AppHeader'
import { GraduationCap, BookOpen, Target, Users, CheckCircle, AlertTriangle, Circle, FileText, AlertCircle, Trophy } from 'lucide-react'

const STATUS_META: Record<string, { label: string; color: string; bg: string; icon: React.ReactNode }> = {
  mastered: { label: '已掌握', color: '#059669', bg: 'rgba(5,150,105,0.10)', icon: <CheckCircle style={{ width: 14, height: 14 }} /> },
  weak: { label: '薄弱', color: '#ea580c', bg: 'rgba(234,88,12,0.10)', icon: <AlertTriangle style={{ width: 14, height: 14 }} /> },
  not_started: { label: '未学', color: '#94a3b8', bg: 'rgba(148,163,184,0.10)', icon: <Circle style={{ width: 14, height: 14 }} /> },
}

const LEVEL_LABEL: Record<string, string> = {
  beginner: '零基础',
  intermediate: '入门级',
  advanced: '进阶级',
}

const GOAL_LABEL: Record<string, string> = {
  exam: '备考',
  interest: '兴趣',
  employment: '就业',
  competition: '竞赛',
}

const CourseView: React.FC = () => {
  const authStore = useAuthStore()
  const showToast = useAppStore((state) => state.showToast)
  const [info, setInfo] = useState<CourseInfo | null>(null)
  const [loading, setLoading] = useState(true)

  const loadInfo = useCallback(async () => {
    if (!authStore.userId) return
    setLoading(true)
    try {
      const resp = await getCourseInfo(authStore.userId)
      if (resp.code === 200 && resp.data) {
        setInfo(resp.data)
      } else {
        showToast(resp.message || '加载课程信息失败', 'error')
      }
    } catch (err) {
      console.error('加载课程信息失败:', err)
      showToast('加载课程信息失败', 'error')
    } finally {
      setLoading(false)
    }
  }, [authStore.userId, showToast])

  useEffect(() => {
    loadInfo()
  }, [loadInfo])

  return (
    <div className="chat-stage">
      <AppHeader title="课程概览">
        <span
          className="shell-title-eyebrow"
          style={{
            color: 'var(--py-blue-deep)',
            background: 'rgba(48, 105, 152, 0.08)',
            border: '1px solid rgba(48, 105, 152, 0.14)',
          }}
        >
          <GraduationCap style={{ width: 12, height: 12 }} />
          {info?.course?.competition?.problem_id || 'A3'}
        </span>
      </AppHeader>

      <div className="chat-scroll-zone smooth-scroll" style={{ padding: '20px 24px' }}>
        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0', color: 'var(--mute)' }}>
            正在加载课程信息...
          </div>
        ) : !info ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: '60px 0', color: 'var(--mute)' }}>
            课程信息加载失败
          </div>
        ) : (
          <div style={{ maxWidth: 960, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* 课程信息卡 */}
            <div className="rail-card" style={{ padding: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    background: 'var(--py-blue)',
                    color: '#fff',
                  }}
                >
                  <BookOpen style={{ width: 22, height: 22 }} />
                </div>
                <div>
                  <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: 'var(--ink)', letterSpacing: '-0.02em' }}>
                    {info.course.name}
                  </h1>
                  <div style={{ fontSize: 12, color: 'var(--mute)', marginTop: 4 }}>
                    {info.course.competition.name} · {info.course.competition.problem_id} · {info.course.competition.problem_name}
                  </div>
                </div>
              </div>
              <p style={{ margin: '0 0 16px', fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.7 }}>
                {info.course.intro}
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Target style={{ width: 16, height: 16, color: 'var(--py-blue)', flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--mute)', marginBottom: 2 }}>课程目标</div>
                    <div style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.6 }}>{info.course.target}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                  <Users style={{ width: 16, height: 16, color: 'var(--py-blue)', flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontSize: 12, color: 'var(--mute)', marginBottom: 2 }}>服务对象</div>
                    <div style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.6 }}>{info.course.audience}</div>
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 14, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {info.course.modules.map((m) => (
                  <span
                    key={m}
                    style={{
                      fontSize: 12,
                      padding: '3px 10px',
                      borderRadius: 12,
                      background: 'rgba(48,105,152,0.08)',
                      color: 'var(--py-blue-deep)',
                    }}
                  >
                    {m}
                  </span>
                ))}
              </div>
            </div>

            {/* 学习进度卡 */}
            <div className="rail-card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <Trophy style={{ width: 16, height: 16, color: 'var(--py-yellow-deep)' }} />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>学习进度</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
                <ProgressStat
                  icon={<CheckCircle style={{ width: 16, height: 16, color: '#059669' }} />}
                  label="已掌握"
                  value={`${info.progress.mastered_count}/${info.progress.total_points}`}
                />
                <ProgressStat
                  icon={<AlertTriangle style={{ width: 16, height: 16, color: '#ea580c' }} />}
                  label="薄弱点"
                  value={`${info.progress.weak_count}`}
                />
                <ProgressStat
                  icon={<FileText style={{ width: 16, height: 16, color: 'var(--py-blue)' }} />}
                  label="学习资源"
                  value={`${info.progress.resource_count}`}
                />
                <ProgressStat
                  icon={<AlertCircle style={{ width: 16, height: 16, color: '#dc2626' }} />}
                  label="错题数"
                  value={`${info.progress.error_count}`}
                />
              </div>
              <div style={{ marginTop: 14, display: 'flex', gap: 16, fontSize: 12, color: 'var(--mute)' }}>
                <span>基础水平：{LEVEL_LABEL[info.progress.knowledge_level] || info.progress.knowledge_level}</span>
                <span>学习目标：{GOAL_LABEL[info.progress.learning_goal] || info.progress.learning_goal}</span>
              </div>
            </div>

            {/* 知识点大纲 */}
            <div className="rail-card" style={{ padding: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
                <GraduationCap style={{ width: 16, height: 16, color: 'var(--py-blue)' }} />
                <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink)' }}>知识点大纲</span>
                <div style={{ marginLeft: 'auto', display: 'flex', gap: 10, fontSize: 11 }}>
                  {Object.entries(STATUS_META).map(([k, m]) => (
                    <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 4, color: m.color }}>
                      {m.icon}
                      {m.label}
                    </span>
                  ))}
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                {info.outline.map((item) => {
                  const meta = STATUS_META[item.status]
                  return (
                    <div
                      key={item.order}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        padding: '10px 12px',
                        borderRadius: 10,
                        background: meta.bg,
                        border: `1px solid ${meta.color}22`,
                      }}
                    >
                      <span style={{ fontSize: 11, color: 'var(--mute)', minWidth: 20 }}>{String(item.order).padStart(2, '0')}</span>
                      <span style={{ color: meta.color }}>{meta.icon}</span>
                      <span style={{ fontSize: 13, color: 'var(--ink)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {item.name}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const ProgressStat: React.FC<{ icon: React.ReactNode; label: string; value: string }> = ({ icon, label, value }) => (
  <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '10px 12px', borderRadius: 10, background: 'rgba(48,105,152,0.04)' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      {icon}
      <span style={{ fontSize: 11, color: 'var(--mute)' }}>{label}</span>
    </div>
    <div style={{ fontSize: 18, fontWeight: 700, color: 'var(--ink)' }}>{value}</div>
  </div>
)

export default CourseView
