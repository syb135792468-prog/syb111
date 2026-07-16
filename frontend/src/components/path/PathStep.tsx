import React, { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  CheckCircle, Clock, AlertTriangle, SkipForward, ChevronDown, ChevronUp,
  FileText, HelpCircle, GitBranch, Code, PlayCircle, Loader2, Award,
  Zap, RotateCcw, Video
} from 'lucide-react'
import {
  generatePreTest, submitPreTest, unskipNode,
  type PreTest,
} from '../../api/learningPath'
import { listErrorBook, generateTutorVideo } from '../../api/errorBook'
import { useAuthStore } from '../../stores/auth'
import { useAppStore } from '../../stores/app'
import { useTaskStore } from '../../stores/taskStore'
import { pollTaskProgress } from '../../composables/useSSE'

// --- 类型定义 ---
export interface PathNodeResource {
  id: number
  resource_type: string
  title: string
  status: string
  is_cached: boolean
  duration?: number
  description?: string
  content?: string
  resource_id?: number
  difficulty?: number
  created_at?: string
  updated_at?: string
}

export interface PathNodeData {
  id?: number
  order: number
  type: string
  node_type?: string
  knowledge_point: string
  estimated_time?: number
  estimated_time_min?: number
  status?: string
  mastery?: number
  mastery_threshold?: number
  progress?: number
  difficulty?: number
  prerequisites?: string[]
  resources?: PathNodeResource[]
  [key: string]: unknown
}

interface PathStepProps {
  step: PathNodeData
  isLast?: boolean
  onNodeClick?: (nodeId: number) => void
  onResourceClick?: (nodeId: number, resourceType: string) => void
  onComplete?: (nodeId: number) => void
  onPathUpdated?: (path: import('../../api/learningPath').LearningPathData) => void
}

// --- 状态配置：py-blue=进行中 / green=完成 / py-yellow=需复习 / faint=未开始 ---
interface StatusStyle {
  dotBg: string
  dotBorder: string
  dotColor: string
  label: string
  icon: React.ReactNode
  labelColor: string
}

const STATUS_STYLES: Record<string, StatusStyle> = {
  not_started: {
    dotBg: 'var(--paper)',
    dotBorder: 'var(--rule)',
    dotColor: 'var(--faint)',
    label: '未开始',
    icon: <Clock style={{ width: 12, height: 12 }} />,
    labelColor: 'var(--faint)',
  },
  in_progress: {
    dotBg: 'var(--py-blue-tint)',
    dotBorder: 'var(--py-blue)',
    dotColor: 'var(--py-blue)',
    label: '学习中',
    icon: <Loader2 style={{ width: 12, height: 12, animation: 'spin 1.2s linear infinite' }} />,
    labelColor: 'var(--py-blue)',
  },
  completed: {
    dotBg: '#ecfdf5',
    dotBorder: '#10b981',
    dotColor: '#059669',
    label: '已完成',
    icon: <CheckCircle style={{ width: 12, height: 12 }} />,
    labelColor: '#059669',
  },
  needs_review: {
    dotBg: 'var(--py-yellow-tint)',
    dotBorder: 'var(--py-yellow-deep)',
    dotColor: 'var(--py-yellow-deep)',
    label: '需复习',
    icon: <AlertTriangle style={{ width: 12, height: 12 }} />,
    labelColor: 'var(--py-yellow-deep)',
  },
  skipped: {
    dotBg: 'var(--paper-soft)',
    dotBorder: 'var(--rule-soft)',
    dotColor: 'var(--faint)',
    label: '已跳过',
    icon: <SkipForward style={{ width: 12, height: 12 }} />,
    labelColor: 'var(--faint)',
  },
}

const RESOURCE_ICONS: Record<string, React.ReactNode> = {
  doc: <FileText style={{ width: 13, height: 13 }} />,
  quiz: <HelpCircle style={{ width: 13, height: 13 }} />,
  mindmap: <GitBranch style={{ width: 13, height: 13 }} />,
  code: <Code style={{ width: 13, height: 13 }} />,
  video: <PlayCircle style={{ width: 13, height: 13 }} />,
}

const RESOURCE_LABELS: Record<string, string> = {
  doc: '文档',
  quiz: '练习',
  mindmap: '导图',
  code: '代码',
  video: '视频',
}

function difficultyLabel(d?: number): string {
  if (d === undefined) return ''
  if (d <= 0.3) return '入门'
  if (d <= 0.6) return '进阶'
  return '高级'
}

// --- 组件 ---
const PathStep: React.FC<PathStepProps> = ({ step, isLast = false, onNodeClick, onResourceClick, onComplete, onPathUpdated }) => {
  const [expanded, setExpanded] = useState(false)
  const [completing, setCompleting] = useState(false)
  const [preTest, setPreTest] = useState<PreTest | null>(null)
  const [preTestLoading, setPreTestLoading] = useState(false)
  const [preTestSubmitting, setPreTestSubmitting] = useState(false)
  const [selectedAnswer, setSelectedAnswer] = useState<string>('')
  const [preTestResult, setPreTestResult] = useState<{ is_correct: boolean; correct_answer: string; explanation: string; matched_error_type: string | null } | null>(null)
  const [unskipping, setUnskipping] = useState(false)
  const [tutorLoading, setTutorLoading] = useState(false)

  const navigate = useNavigate()
  const authStore = useAuthStore()
  const appStore = useAppStore()

  const isReview = (step.type || step.node_type) === 'review'
  const status = step.status || 'not_started'
  const style = STATUS_STYLES[status] || STATUS_STYLES.not_started
  const mastery = step.mastery ?? 0
  const masteryThreshold = step.mastery_threshold ?? 0.7
  const estimatedTime = step.estimated_time ?? step.estimated_time_min ?? 15
  const resources = step.resources || []
  const masteryAchieved = mastery >= masteryThreshold
  const diffLabel = difficultyLabel(step.difficulty)
  const readyCount = resources.filter(r => r.is_cached).length

  const handleToggle = useCallback(() => {
    setExpanded(prev => !prev)
    if (onNodeClick && step.id) {
      onNodeClick(step.id)
    }
  }, [onNodeClick, step.id, step.knowledge_point, status, expanded])

  const handleComplete = useCallback(async () => {
    if (!step.id || !onComplete || completing) return
    setCompleting(true)
    try {
      await onComplete(step.id)
    } finally {
      setCompleting(false)
    }
  }, [step.id, onComplete, completing])

  const handleGeneratePreTest = useCallback(async () => {
    if (!step.id || preTestLoading) return
    setPreTestLoading(true)
    setPreTestResult(null)
    setSelectedAnswer('')
    try {
      const resp = await generatePreTest(step.id)
      if (resp.code === 200 && resp.data) {
        setPreTest(resp.data)
        if (!resp.data.cached) {
          setExpanded(true)
        }
      }
    } catch (e) {
      console.error('生成前置测试失败:', e)
    } finally {
      setPreTestLoading(false)
    }
  }, [step.id, preTestLoading])

  const handleSubmitPreTest = useCallback(async () => {
    if (!step.id || !preTest || !selectedAnswer || preTestSubmitting) return
    setPreTestSubmitting(true)
    try {
      const resp = await submitPreTest(step.id, {
        user_answer: selectedAnswer,
        resource_id: preTest.resource_id,
      })
      if (resp.code === 200 && resp.data) {
        setPreTestResult({
          is_correct: resp.data.is_correct,
          correct_answer: resp.data.correct_answer,
          explanation: resp.data.explanation,
          matched_error_type: resp.data.matched_error_type,
        })
        if (resp.data.is_correct && resp.data.path && onPathUpdated) {
          onPathUpdated(resp.data.path)
        }
      }
    } catch (e) {
      console.error('提交前置测试失败:', e)
    } finally {
      setPreTestSubmitting(false)
    }
  }, [step.id, preTest, selectedAnswer, preTestSubmitting, onPathUpdated])

  const handleUnskip = useCallback(async () => {
    if (!step.id || unskipping) return
    setUnskipping(true)
    try {
      const resp = await unskipNode(step.id)
      if (resp.code === 200 && resp.data && onPathUpdated) {
        onPathUpdated(resp.data)
      }
    } catch (e) {
      console.error('取消跳过失败:', e)
    } finally {
      setUnskipping(false)
    }
  }, [step.id, unskipping, onPathUpdated])

  // 需复习节点：看辅导短视频（按知识点查最近错题 -> 触发生成）
  const handleWatchTutorVideo = useCallback(async () => {
    if (tutorLoading || !step.knowledge_point) return
    setTutorLoading(true)
    try {
      const listResp = await listErrorBook(authStore.userId, { knowledge_point: step.knowledge_point, limit: 1 })
      const listData = listResp.code === 200 && listResp.data
        ? listResp.data as { items?: Array<{ id: string | number }> }
        : null
      const items = listData?.items || []
      if (items.length === 0) {
        setTutorLoading(false)
        appStore.showToast('该知识点暂无错题记录', 'info')
        return
      }
      const errorId = items[0].id
      const resp = await generateTutorVideo(errorId)
      if (resp.code !== 200 || !resp.data?.task_id) {
        appStore.showToast(resp.message || '提交失败', 'error')
        return
      }
      const taskId = resp.data.task_id
      useTaskStore.getState().addTask({
        taskId,
        resourceType: 'tutor_video',
        topic: step.knowledge_point,
        status: 'pending',
        createdAt: Date.now(),
        progress: 0,
      })
      appStore.showToast('辅导视频生成中，完成后将跳转', 'success')
      pollTaskProgress(
        taskId,
        () => {
          setTutorLoading(false)
          appStore.showToast('辅导视频已生成', 'success')
          navigate('/teaching')
        },
        (err) => {
          setTutorLoading(false)
          appStore.showToast(`生成失败：${err}`, 'error')
        }
      )
    } catch (e) {
      setTutorLoading(false)
      appStore.showToast('提交失败，请稍后重试', 'error')
      console.error('生成辅导视频失败:', e)
    }
  }, [tutorLoading, step.knowledge_point, authStore.userId, appStore, navigate])

  // 从题目内容解析选项（选择题格式：A. xxx / B. xxx）
  const parseOptions = (content: string): string[] => {
    const lines = content.split('\n').map(l => l.trim()).filter(Boolean)
    const optLines = lines.filter(l => /^[A-D][.、)]\s/.test(l))
    return optLines.length >= 2 ? optLines : []
  }
  const preTestOptions = preTest ? parseOptions(preTest.question) : []

  return (
    <div style={{ display: 'flex', gap: 14 }}>
      {/* 时间线圆点 + 连接线 */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
        <div
          style={{
            width: 28, height: 28, borderRadius: '50%',
            background: style.dotBg,
            border: `1.5px solid ${style.dotBorder}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
            fontFamily: 'var(--font-mono)',
            fontSize: 12, fontWeight: 600, color: style.dotColor,
            boxShadow: status === 'in_progress' ? '0 0 0 4px rgba(48, 105, 152, 0.1)' : 'none',
            transition: 'all 0.2s ease',
          }}
        >
          {status === 'completed' ? (
            <CheckCircle style={{ width: 14, height: 14, color: '#059669' }} />
          ) : (
            step.order
          )}
        </div>
        {!isLast && (
          <div style={{
            width: 2, flex: 1, minHeight: 12, marginTop: 2,
            background: status === 'completed' ? '#a7f3d0' : 'var(--rule)',
            transition: 'background 0.2s ease',
          }} />
        )}
      </div>

      {/* 节点卡片 */}
      <div style={{ paddingBottom: 16, flex: 1, minWidth: 0 }}>
        <div
          onClick={handleToggle}
          style={{
            borderRadius: 10,
            border: '1px solid var(--rule)',
            background: status === 'completed' ? 'var(--paper-soft)' : 'var(--paper)',
            padding: '12px 14px',
            cursor: 'pointer',
            transition: 'border-color 0.15s ease, box-shadow 0.15s ease',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = 'var(--py-blue)'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = 'var(--rule)'
          }}
        >
          {/* 行 1：标题 + 状态 + 箭头 */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <h4 style={{
              fontSize: 14, fontWeight: 600, color: 'var(--ink)', margin: 0,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              flex: 1, minWidth: 0,
            }}>
              {step.knowledge_point}
            </h4>
            {isReview && (
              <span style={{
                fontSize: 11, fontWeight: 500, padding: '1px 6px', borderRadius: 4,
                background: 'var(--py-yellow-tint)', color: 'var(--py-yellow-deep)',
                border: '1px solid rgba(255, 212, 59, 0.4)',
                flexShrink: 0,
              }}>
                复习
              </span>
            )}
            <span style={{
              display: 'inline-flex', alignItems: 'center', gap: 4,
              fontSize: 11, color: style.labelColor, flexShrink: 0,
            }}>
              {style.icon}
              {style.label}
            </span>
            {expanded ? (
              <ChevronUp style={{ width: 14, height: 14, color: 'var(--faint)', flexShrink: 0 }} />
            ) : (
              <ChevronDown style={{ width: 14, height: 14, color: 'var(--faint)', flexShrink: 0 }} />
            )}
          </div>

          {/* 行 2：meta（时间 + 难度 + 资源就绪数） */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, marginTop: 6,
            fontSize: 12, color: 'var(--faint)',
          }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
              <Clock style={{ width: 11, height: 11 }} />
              {estimatedTime} 分钟
            </span>
            {diffLabel && (
              <span>{diffLabel}</span>
            )}
            {resources.length > 0 && (
              <span>
                {readyCount}/{resources.length} 资源就绪
              </span>
            )}
          </div>

          {/* 展开详情 */}
          {expanded && (
            <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--rule-soft)' }}>
              {/* 掌握度 */}
              {mastery > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    fontSize: 12, marginBottom: 5,
                  }}>
                    <span style={{ color: 'var(--mute)' }}>掌握度</span>
                    <span style={{
                      fontFamily: 'var(--font-mono)', fontWeight: 600,
                      color: masteryAchieved ? '#059669' : 'var(--py-blue)',
                    }}>
                      {Math.round(mastery * 100)}{masteryAchieved ? ' ✓' : ''}
                    </span>
                  </div>
                  <div style={{
                    width: '100%', height: 4, background: 'var(--rule-soft)',
                    borderRadius: 2, overflow: 'hidden',
                  }}>
                    <div
                      style={{
                        height: '100%', borderRadius: 2,
                        background: masteryAchieved ? '#10b981' : 'var(--py-blue)',
                        width: `${Math.min(100, mastery * 100)}%`,
                        transition: 'width 0.4s ease, background 0.2s ease',
                      }}
                    />
                  </div>
                </div>
              )}

              {/* 前置知识 */}
              {step.prerequisites && step.prerequisites.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{
                    fontSize: 12, color: 'var(--mute)', margin: '0 0 6px',
                  }}>
                    前置知识
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {step.prerequisites.map((pre, i) => (
                      <span key={i} style={{
                        fontSize: 12, padding: '2px 8px',
                        background: 'var(--paper-soft)', color: 'var(--mute)',
                        border: '1px solid var(--rule)',
                        borderRadius: 4,
                      }}>
                        {pre}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* 学习资源 */}
              {resources.length > 0 && (
                <div style={{ marginBottom: 12 }}>
                  <p style={{
                    fontSize: 12, color: 'var(--mute)', margin: '0 0 6px',
                  }}>
                    学习资源
                  </p>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {resources.map(res => (
                      <button
                        key={res.id}
                        onClick={e => {
                          e.stopPropagation()
                          if (onResourceClick && step.id) {
                            onResourceClick(step.id, res.resource_type)
                          }
                        }}
                        style={{
                          display: 'inline-flex', alignItems: 'center', gap: 5,
                          fontSize: 12, padding: '5px 10px', borderRadius: 6,
                          background: res.is_cached ? 'var(--paper)' : 'var(--paper-soft)',
                          border: `1px solid ${res.is_cached ? 'var(--rule)' : 'var(--rule-soft)'}`,
                          color: res.is_cached ? 'var(--ink)' : 'var(--faint)',
                          cursor: 'pointer',
                          transition: 'all 0.15s ease',
                        }}
                        onMouseEnter={e => {
                          if (res.is_cached) {
                            e.currentTarget.style.borderColor = 'var(--py-blue)'
                            e.currentTarget.style.color = 'var(--py-blue)'
                            e.currentTarget.style.background = 'var(--py-blue-tint)'
                          }
                        }}
                        onMouseLeave={e => {
                          e.currentTarget.style.borderColor = res.is_cached ? 'var(--rule)' : 'var(--rule-soft)'
                          e.currentTarget.style.color = res.is_cached ? 'var(--ink)' : 'var(--faint)'
                          e.currentTarget.style.background = res.is_cached ? 'var(--paper)' : 'var(--paper-soft)'
                        }}
                      >
                        {RESOURCE_ICONS[res.resource_type] || <FileText style={{ width: 13, height: 13 }} />}
                        {RESOURCE_LABELS[res.resource_type] || res.resource_type}
                        {res.status === 'generating' && (
                          <Loader2 style={{ width: 11, height: 11, animation: 'spin 0.8s linear infinite', color: 'var(--py-blue)' }} />
                        )}
                        {res.is_cached && (
                          <CheckCircle style={{ width: 11, height: 11, color: '#10b981' }} />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* 前置测试（PathAgent ↔ QuizAgent 协作） */}
              {step.id && onPathUpdated && (status === 'not_started' || status === 'skipped') && (
                <div style={{ marginBottom: 12, padding: 12, background: 'var(--paper-soft)', border: '1px solid var(--rule-soft)', borderRadius: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 12, fontWeight: 600, color: 'var(--py-blue)' }}>
                      <Zap style={{ width: 13, height: 13 }} />
                      前置测试（答对可跳过节点）
                    </span>
                    {!preTest && !preTestLoading && (
                      <button
                        onClick={e => { e.stopPropagation(); handleGeneratePreTest() }}
                        style={{
                          fontSize: 12, padding: '4px 10px', borderRadius: 6,
                          background: 'var(--py-blue-tint)', color: 'var(--py-blue)',
                          border: '1px solid var(--py-blue)', cursor: 'pointer',
                        }}
                      >
                        生成测试题
                      </button>
                    )}
                    {preTestLoading && (
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 12, color: 'var(--py-blue)' }}>
                        <Loader2 style={{ width: 12, height: 12, animation: 'spin 0.8s linear infinite' }} />
                        生成中...
                      </span>
                    )}
                  </div>

                  {/* 题目卡片 */}
                  {preTest && preTestOptions.length > 0 && (
                    <div>
                      {preTest.collaboration_info && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            flexWrap: 'wrap',
                            gap: 6,
                            fontSize: 11,
                            color: 'var(--mute)',
                            margin: '0 0 8px',
                            padding: '4px 8px',
                            background: 'rgba(124,58,237,0.06)',
                            borderRadius: 4,
                          }}
                        >
                          <span>🤝 {preTest.collaboration_info.description}</span>
                          {preTest.collaboration_info.agents.map(a => (
                            <span
                              key={a.name}
                              style={{
                                padding: '1px 6px',
                                background: 'rgba(124,58,237,0.1)',
                                borderRadius: 3,
                                color: '#7c3aed',
                              }}
                            >
                              {a.name}·{a.role}
                            </span>
                          ))}
                        </div>
                      )}
                      <p style={{ fontSize: 13, color: 'var(--ink)', margin: '0 0 8px', lineHeight: 1.5 }}>
                        {preTest.question.split('\n').find(l => !/^[A-D][.、)]\s/.test(l.trim()))}
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 10 }}>
                        {preTestOptions.map((opt, i) => {
                          const letter = opt[0]
                          const isSelected = selectedAnswer === letter
                          const isCorrectAns = preTestResult && letter === preTestResult.correct_answer.replace(/[^A-D]/g, '')
                          const isWrongPick = preTestResult && !preTestResult.is_correct && isSelected
                          return (
                            <button
                              key={i}
                              disabled={!!preTestResult}
                              onClick={e => { e.stopPropagation(); setSelectedAnswer(letter) }}
                              style={{
                                display: 'flex', alignItems: 'center', gap: 8,
                                padding: '8px 12px', fontSize: 13, textAlign: 'left',
                                background: isCorrectAns ? '#ecfdf5' : isWrongPick ? '#fef2f2' : isSelected ? 'var(--py-blue-tint)' : 'var(--paper)',
                                border: `1px solid ${isCorrectAns ? '#a7f3d0' : isWrongPick ? '#fecaca' : isSelected ? 'var(--py-blue)' : 'var(--rule)'}`,
                                borderRadius: 6, cursor: preTestResult ? 'default' : 'pointer',
                                color: 'var(--ink)',
                              }}
                            >
                              {opt}
                              {isCorrectAns && <CheckCircle style={{ width: 14, height: 14, color: '#059669', marginLeft: 'auto' }} />}
                              {isWrongPick && <AlertTriangle style={{ width: 14, height: 14, color: '#dc2626', marginLeft: 'auto' }} />}
                            </button>
                          )
                        })}
                      </div>

                      {/* 提交按钮 */}
                      {!preTestResult && (
                        <button
                          onClick={e => { e.stopPropagation(); handleSubmitPreTest() }}
                          disabled={!selectedAnswer || preTestSubmitting}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 5,
                            padding: '6px 16px', fontSize: 13, fontWeight: 500,
                            background: !selectedAnswer || preTestSubmitting ? 'var(--rule-soft)' : 'var(--py-blue)',
                            color: !selectedAnswer || preTestSubmitting ? 'var(--faint)' : '#fff',
                            border: 'none', borderRadius: 6,
                            cursor: !selectedAnswer || preTestSubmitting ? 'not-allowed' : 'pointer',
                          }}
                        >
                          {preTestSubmitting ? (
                            <Loader2 style={{ width: 13, height: 13, animation: 'spin 0.8s linear infinite' }} />
                          ) : (
                            <CheckCircle style={{ width: 13, height: 13 }} />
                          )}
                          提交答案
                        </button>
                      )}

                      {/* 答题反馈 */}
                      {preTestResult && (
                        <div style={{
                          padding: 10, marginTop: 8, borderRadius: 6,
                          background: preTestResult.is_correct ? '#ecfdf5' : '#fffbeb',
                          border: `1px solid ${preTestResult.is_correct ? '#a7f3d0' : '#fde68a'}`,
                          fontSize: 12,
                        }}>
                          <p style={{ fontWeight: 600, margin: '0 0 6px', color: preTestResult.is_correct ? '#059669' : '#92400e' }}>
                            {preTestResult.is_correct ? '✓ 答对！节点已跳过，路径进度已推进' : `✗ 答错${preTestResult.matched_error_type ? `（错因：${preTestResult.matched_error_type}）` : ''}`}
                          </p>
                          <p style={{ color: 'var(--mute)', margin: 0, lineHeight: 1.5 }}>
                            {preTestResult.explanation}
                          </p>
                          {!preTestResult.is_correct && (
                            <button
                              onClick={e => { e.stopPropagation(); setPreTestResult(null); setSelectedAnswer('') }}
                              style={{
                                marginTop: 8, fontSize: 12, padding: '4px 10px',
                                background: 'var(--paper)', border: '1px solid var(--rule)',
                                borderRadius: 4, cursor: 'pointer', color: 'var(--ink)',
                              }}
                            >
                              再答一次
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {/* 取消跳过按钮（skipped 状态） */}
              {step.id && onPathUpdated && status === 'skipped' && (
                <button
                  onClick={e => { e.stopPropagation(); handleUnskip() }}
                  disabled={unskipping}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '5px 12px', fontSize: 12, fontWeight: 500,
                    background: 'var(--paper)', color: 'var(--mute)',
                    border: '1px solid var(--rule)', borderRadius: 6,
                    cursor: unskipping ? 'not-allowed' : 'pointer',
                    opacity: unskipping ? 0.6 : 1,
                    marginRight: 8,
                  }}
                >
                  {unskipping ? (
                    <Loader2 style={{ width: 12, height: 12, animation: 'spin 0.8s linear infinite' }} />
                  ) : (
                    <RotateCcw style={{ width: 12, height: 12 }} />
                  )}
                  取消跳过
                </button>
              )}

              {/* 看辅导短视频按钮（needs_review 状态） */}
              {step.id && status === 'needs_review' && step.knowledge_point && (
                <button
                  onClick={e => { e.stopPropagation(); handleWatchTutorVideo() }}
                  disabled={tutorLoading}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '6px 14px', fontSize: 13, fontWeight: 500,
                    background: 'var(--py-yellow-tint)', color: 'var(--py-yellow-deep)',
                    border: '1px solid rgba(255, 212, 59, 0.6)', borderRadius: 8,
                    cursor: tutorLoading ? 'not-allowed' : 'pointer',
                    opacity: tutorLoading ? 0.6 : 1,
                    marginRight: 8,
                    transition: 'all 0.15s ease',
                  }}
                >
                  {tutorLoading ? (
                    <Loader2 style={{ width: 13, height: 13, animation: 'spin 0.8s linear infinite' }} />
                  ) : (
                    <Video style={{ width: 13, height: 13 }} />
                  )}
                  {tutorLoading ? '辅导视频生成中...' : '看辅导短视频'}
                </button>
              )}

              {/* 完成按钮 */}
              {step.id && onComplete && status !== 'completed' && (
                <button
                  onClick={e => { e.stopPropagation(); handleComplete() }}
                  disabled={completing}
                  style={{
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '6px 14px', fontSize: 13, fontWeight: 500,
                    background: '#ecfdf5', color: '#059669',
                    border: '1px solid #a7f3d0', borderRadius: 8,
                    cursor: completing ? 'not-allowed' : 'pointer',
                    opacity: completing ? 0.6 : 1,
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={e => { if (!completing) { e.currentTarget.style.background = '#d1fae5'; e.currentTarget.style.borderColor = '#6ee7b7' } }}
                  onMouseLeave={e => { e.currentTarget.style.background = '#ecfdf5'; e.currentTarget.style.borderColor = '#a7f3d0' }}
                >
                  {completing ? (
                    <Loader2 style={{ width: 13, height: 13, animation: 'spin 0.8s linear infinite' }} />
                  ) : (
                    <Award style={{ width: 13, height: 13 }} />
                  )}
                  标记为已完成
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default PathStep
