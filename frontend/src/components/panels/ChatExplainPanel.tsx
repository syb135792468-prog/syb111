import React, { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { useChatStore } from '../../stores/chat'
import { useAuthStore } from '../../stores/auth'
import { useLearningCenterStore } from '../../stores/learningCenter'
import { explainText, followUpExplain, listExplanations, type ExplanationData } from '../../api/chat'
import MarkdownText from '../common/MarkdownText'
import { Loader2, Copy, Check, ChevronLeft, ChevronRight, Send, MessageCircle, Sparkles, RotateCcw } from 'lucide-react'

const ChatExplainPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const authStore = useAuthStore()
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)
  const text = (data?.text as string) || ''
  const context = (data?.context as string) || ''
  const topic = (data?.topic as string) || ''
  const knowledgePoint = (data?.knowledgePoint as string) || ''
  const knowledgePoints = Array.isArray(data?.knowledgePoints)
    ? (data?.knowledgePoints as string[]).filter((item) => typeof item === 'string' && item.trim().length > 0)
    : []
  const resourceId = typeof data?.resourceId === 'number'
    ? data.resourceId
    : typeof data?.resourceId === 'string' && !Number.isNaN(Number(data.resourceId))
      ? Number(data.resourceId)
      : undefined
  const messageId = (data?.messageId as number) || 0
  const conversationId = (data?.conversationId as number) || useChatStore.getState().currentConversationId || 0

  // 解释列表 + 当前索引
  const [explanations, setExplanations] = useState<ExplanationData[]>([])
  const [currentIndex, setCurrentIndex] = useState(-1)
  const [loading, setLoading] = useState(false)
  const [loadingList, setLoadingList] = useState(false)

  // 追问
  const [followUpInput, setFollowUpInput] = useState('')
  const [followUpAnswer, setFollowUpAnswer] = useState('')
  const [followUpLoading, setFollowUpLoading] = useState(false)

  // 复制
  const [copied, setCopied] = useState(false)

  // 当前显示的解释
  const current = currentIndex >= 0 && currentIndex < explanations.length ? explanations[currentIndex] : null
  const displaySelectedText = current?.selected_text || text

  // 加载会话的所有解释
  const loadExplanations = useCallback(async () => {
    if (!conversationId) return
    setLoadingList(true)
    try {
      const resp = await listExplanations(Number(conversationId))
      if (resp.code === 200 && resp.data) {
        const list = resp.data.explanations || []
        setExplanations(list)
        // 如果有新的 text+messageId，定位到对应解释；否则显示最新的
        if (text && messageId) {
          const idx = list.findIndex(e => e.message_id === messageId && e.selected_text === text)
          if (idx >= 0) {
            setCurrentIndex(idx)
          } else {
            // 新解释还没在列表里，请求生成
            await generateExplanation(list)
          }
        } else if (list.length > 0) {
          setCurrentIndex(list.length - 1)
        }
      }
    } catch (e) {
      console.error('加载解释列表失败:', e)
    } finally {
      setLoadingList(false)
    }
  }, [conversationId, text, messageId])

  // 生成新解释
  const generateExplanation = useCallback(async (existingList?: ExplanationData[]) => {
    if (!text || !messageId) return
    setLoading(true)
    setFollowUpAnswer('')
    setFollowUpInput('')
    try {
      const resp = await explainText(
        text,
        messageId,
        conversationId ? Number(conversationId) : undefined,
        context || undefined,
      )
      if (resp.code === 200 && resp.data) {
        const newExp = resp.data as unknown as ExplanationData
        const list = existingList || explanations
        const newList = [...list, newExp]
        setExplanations(newList)
        setCurrentIndex(newList.length - 1)
        recordLearningEvent({
          userId: authStore.userId,
          sourcePage: 'chat',
          actionType: 'chat_explained',
          topic: topic || newExp.selected_text,
          knowledgePoint: knowledgePoint || knowledgePoints[0] || undefined,
          knowledgePoints,
          resourceId,
        })
      }
    } catch (e) {
      console.error('生成解释失败:', e)
    } finally {
      setLoading(false)
    }
  }, [
    authStore.userId,
    context,
    conversationId,
    explanations,
    knowledgePoint,
    knowledgePoints,
    messageId,
    recordLearningEvent,
    resourceId,
    text,
    topic,
  ])

  // 首次打开 / 切换会话时加载列表
  useEffect(() => {
    setExplanations([])
    setCurrentIndex(-1)
    setFollowUpAnswer('')
    setFollowUpInput('')
    loadExplanations()
  }, [conversationId])

  // 新的 text 传入时（点击新的"解释"按钮）
  useEffect(() => {
    if (!text || !messageId) return
    // 检查是否已在列表中
    const idx = explanations.findIndex(e => e.message_id === messageId && e.selected_text === text)
    if (idx >= 0) {
      setCurrentIndex(idx)
    } else if (explanations.length > 0 || !loadingList) {
      // 不在列表中，生成新的
      generateExplanation()
    }
  }, [text, messageId])

  // 翻页
  const goPrev = useCallback(() => {
    setCurrentIndex(i => Math.max(0, i - 1))
    setFollowUpAnswer('')
    setFollowUpInput('')
  }, [])

  const goNext = useCallback(() => {
    setCurrentIndex(i => Math.min(explanations.length - 1, i + 1))
    setFollowUpAnswer('')
    setFollowUpInput('')
  }, [explanations.length])

  // 复制
  const handleCopy = useCallback(async () => {
    const textToCopy = current?.explanation || ''
    if (!textToCopy) return
    try {
      await navigator.clipboard.writeText(textToCopy)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch { /* ignore */ }
  }, [current])

  // 提交追问
  const handleFollowUp = useCallback(async () => {
    if (!followUpInput.trim() || !current) return
    setFollowUpLoading(true)
    setFollowUpAnswer('')
    try {
      const resp = await followUpExplain(current.id, followUpInput.trim())
      if (resp.code === 200 && resp.data) {
        const answer = typeof resp.data === 'string' ? resp.data : (resp.data as any).answer || ''
        setFollowUpAnswer(answer)
        // 更新本地 explanations 列表中的 follow_ups
        setExplanations(prev => prev.map((e, i) =>
          i === currentIndex
            ? { ...e, follow_ups: [...(e.follow_ups || []), { question: followUpInput.trim(), answer, created_at: new Date().toISOString() }] }
            : e,
        ))
      }
    } catch (e) {
      console.error('追问失败:', e)
      setFollowUpAnswer('追问失败，请稍后重试')
    } finally {
      setFollowUpLoading(false)
    }
  }, [followUpInput, current, currentIndex])

  // 重新解释
  const handleReExplain = useCallback(() => {
    generateExplanation()
  }, [generateExplanation])

  // ---- 渲染 ----

  // 无会话 / 无消息
  if (!conversationId || !messageId) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        background: '#f9fafb',
      }}>
        <div style={{
          width: 64,
          height: 64,
          borderRadius: 16,
          background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: 16,
          boxShadow: '0 4px 12px rgba(16, 185, 129, 0.3)',
        }}>
          <MessageCircle style={{ width: 28, height: 28, color: 'white' }} />
        </div>
        <p style={{ fontSize: 14, color: '#6b7280', textAlign: 'center', margin: 0 }}>
          在聊天中选中文字或点击代码块<br />点击"解释"按钮获取详细说明
        </p>
      </div>
    )
  }

  // 加载中
  if (loadingList && explanations.length === 0) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: '#f9fafb',
        padding: 16,
      }}>
        {displaySelectedText ? (
          <div style={{
            padding: 12,
            background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)',
            borderLeft: '3px solid #10b981',
            borderRadius: '0 8px 8px 0',
            marginBottom: 16,
          }}>
            <p style={{
              fontSize: 11,
              color: '#059669',
              marginBottom: 6,
              fontWeight: 500,
            }}>
              你选中的内容
            </p>
            <p style={{
              color: '#374151',
              fontSize: 13,
              lineHeight: 1.6,
              margin: 0,
              wordBreak: 'break-word',
            }}>
              {displaySelectedText}
            </p>
          </div>
        ) : null}
        <div style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <div className="loading-spinner" style={{ marginBottom: 12 }} />
          <p style={{ fontSize: 13, color: '#9ca3af', margin: 0 }}>加载解释记录...</p>
        </div>
      </div>
    )
  }

  return (
    <div style={{
      height: '100%',
      display: 'flex',
      flexDirection: 'column',
      background: '#ffffff',
    }}>
      {/* 顶部：翻页导航 */}
      {explanations.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          borderBottom: '1px solid #f3f4f6',
          flexShrink: 0,
        }}>
          <button
            onClick={goPrev}
            disabled={currentIndex <= 0}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: 8,
              border: 'none',
              background: currentIndex <= 0 ? 'transparent' : '#f3f4f6',
              color: currentIndex <= 0 ? '#d1d5db' : '#6b7280',
              cursor: currentIndex <= 0 ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            <ChevronLeft style={{ width: 18, height: 18 }} />
          </button>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <Sparkles style={{ width: 14, height: 14, color: '#10b981' }} />
            <span style={{ fontSize: 13, color: '#6b7280' }}>
              {currentIndex + 1} / {explanations.length}
            </span>
          </div>
          <button
            onClick={goNext}
            disabled={currentIndex >= explanations.length - 1}
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 32,
              height: 32,
              borderRadius: 8,
              border: 'none',
              background: currentIndex >= explanations.length - 1 ? 'transparent' : '#f3f4f6',
              color: currentIndex >= explanations.length - 1 ? '#d1d5db' : '#6b7280',
              cursor: currentIndex >= explanations.length - 1 ? 'not-allowed' : 'pointer',
              transition: 'all 0.15s',
            }}
          >
            <ChevronRight style={{ width: 18, height: 18 }} />
          </button>
        </div>
      )}

      {/* 主体区域 */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: 16,
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
      }}>
        {/* 生成中 */}
        {loading && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}>
            {displaySelectedText ? (
              <div style={{
                padding: 12,
                background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)',
                borderLeft: '3px solid #10b981',
                borderRadius: '0 8px 8px 0',
              }}>
                <p style={{
                  fontSize: 11,
                  color: '#059669',
                  marginBottom: 6,
                  fontWeight: 500,
                }}>
                  你选中的内容
                </p>
                <p style={{
                  color: '#374151',
                  fontSize: 13,
                  lineHeight: 1.6,
                  margin: 0,
                  wordBreak: 'break-word',
                }}>
                  {displaySelectedText}
                </p>
              </div>
            ) : null}
            <div style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 16,
            }}>
              <div className="loading-spinner" style={{ marginBottom: 12 }} />
              <p style={{ fontSize: 13, color: '#6b7280', margin: 0 }}>正在生成解释...</p>
              <p style={{ fontSize: 12, color: '#9ca3af', marginTop: 4 }}>AI 正在分析你刚刚选中的内容</p>
            </div>
          </div>
        )}

        {/* 有解释内容 */}
        {current && !loading && (
          <>
            {/* 顶部固定：被解释的原句 */}
            <div style={{
              padding: 12,
              background: 'linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%)',
              borderLeft: '3px solid #10b981',
              borderRadius: '0 8px 8px 0',
            }}>
              <p style={{
                fontSize: 11,
                color: '#059669',
                marginBottom: 6,
                display: 'flex',
                alignItems: 'center',
                gap: 4,
                fontWeight: 500,
              }}>
                <MessageCircle style={{ width: 12, height: 12 }} />
                引用内容
                {current.created_at && (
                  <span style={{ marginLeft: 8, fontWeight: 400 }}>
                    {new Date(current.created_at).toLocaleString('zh-CN', {
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit'
                    })}
                  </span>
                )}
              </p>
              <p style={{
                color: '#374151',
                fontSize: 13,
                lineHeight: 1.6,
                margin: 0,
                wordBreak: 'break-word',
              }}>
                {current.selected_text}
              </p>
            </div>

            {/* 解释内容 */}
            <div>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: 10,
              }}>
                <p style={{
                  fontSize: 13,
                  fontWeight: 600,
                  color: '#111827',
                  margin: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}>
                  <Sparkles style={{ width: 14, height: 14, color: '#10b981' }} />
                  AI 解释
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button
                    onClick={handleCopy}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '4px 8px',
                      borderRadius: 6,
                      border: 'none',
                      background: copied ? '#f0fdf4' : '#f3f4f6',
                      color: copied ? '#059669' : '#6b7280',
                      fontSize: 12,
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    {copied ? <Check style={{ width: 12, height: 12 }} /> : <Copy style={{ width: 12, height: 12 }} />}
                    {copied ? '已复制' : '复制'}
                  </button>
                  <button
                    onClick={handleReExplain}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '4px 8px',
                      borderRadius: 6,
                      border: 'none',
                      background: '#f3f4f6',
                      color: '#6b7280',
                      fontSize: 12,
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    <RotateCcw style={{ width: 12, height: 12 }} />
                    重新解释
                  </button>
                </div>
              </div>
              <div style={{
                fontSize: 13,
                color: '#374151',
                lineHeight: 1.8,
                background: '#ffffff',
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                padding: 16,
                wordBreak: 'break-word',
              }}>
                <MarkdownText content={current.explanation} />
              </div>
            </div>

            {/* 历史追问记录（只展示最近一条） */}
            {current.follow_ups && current.follow_ups.length > 0 && !followUpAnswer && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <p style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: '#6b7280',
                  margin: 0,
                }}>
                  最近追问
                </p>
                {(() => {
                  const last = current.follow_ups[current.follow_ups.length - 1]
                  return (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <div style={{
                        fontSize: 12,
                        color: '#059669',
                        background: '#f0fdf4',
                        padding: '8px 12px',
                        borderRadius: 8,
                        fontWeight: 500,
                      }}>
                        {last.question}
                      </div>
                      <div style={{
                        fontSize: 12,
                        color: '#374151',
                        background: '#f9fafb',
                        padding: '8px 12px',
                        borderRadius: 8,
                        lineHeight: 1.6,
                      }}>
                        <MarkdownText content={last.answer} />
                      </div>
                    </div>
                  )
                })()}
              </div>
            )}

            {/* 当前追问结果 */}
            {followUpAnswer && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <p style={{
                  fontSize: 12,
                  fontWeight: 500,
                  color: '#6b7280',
                  margin: 0,
                }}>
                  追问结果
                </p>
                <div style={{
                  fontSize: 12,
                  color: '#059669',
                  background: '#f0fdf4',
                  padding: '8px 12px',
                  borderRadius: 8,
                  fontWeight: 500,
                }}>
                  {followUpInput}
                </div>
                <div style={{
                  fontSize: 12,
                  color: '#374151',
                  background: '#f9fafb',
                  padding: '8px 12px',
                  borderRadius: 8,
                  lineHeight: 1.6,
                  wordBreak: 'break-word',
                }}>
                  <MarkdownText content={followUpAnswer} />
                </div>
              </div>
            )}
          </>
        )}

        {/* 无解释 */}
        {!loading && !current && explanations.length === 0 && (
          <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 32,
          }}>
            <MessageCircle style={{ width: 32, height: 32, color: '#d1d5db', marginBottom: 12 }} />
            <p style={{ fontSize: 13, color: '#9ca3af', margin: 0 }}>暂无解释记录</p>
          </div>
        )}
      </div>

      {/* 底部：追问输入框 */}
      {current && !loading && (
        <div style={{
          flexShrink: 0,
          borderTop: '1px solid #f3f4f6',
          padding: 12,
          background: '#ffffff',
        }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              value={followUpInput}
              onChange={(e) => setFollowUpInput(e.target.value)}
              onKeyDown={(e) => { if (e.nativeEvent.isComposing) return; if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp() } }}
              placeholder="针对这个解释追问..."
              disabled={followUpLoading}
              style={{
                flex: 1,
                padding: '10px 12px',
                fontSize: 13,
                border: '1px solid #e5e7eb',
                borderRadius: 8,
                outline: 'none',
                transition: 'border-color 0.15s',
                color: '#111827',
              }}
              onFocus={(e) => e.target.style.borderColor = '#10b981'}
              onBlur={(e) => e.target.style.borderColor = '#e5e7eb'}
            />
            <button
              onClick={handleFollowUp}
              disabled={!followUpInput.trim() || followUpLoading}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 40,
                height: 40,
                background: followUpInput.trim() && !followUpLoading ? '#10b981' : '#f3f4f6',
                color: followUpInput.trim() && !followUpLoading ? '#ffffff' : '#9ca3af',
                border: 'none',
                borderRadius: 8,
                cursor: followUpInput.trim() && !followUpLoading ? 'pointer' : 'not-allowed',
                transition: 'all 0.15s',
              }}
            >
              {followUpLoading ? (
                <div style={{
                  width: 16,
                  height: 16,
                  border: '2px solid rgba(255,255,255,0.3)',
                  borderTopColor: '#ffffff',
                  borderRadius: '50%',
                  animation: 'spin 0.6s linear infinite',
                }} />
              ) : (
                <Send style={{ width: 16, height: 16 }} />
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default ChatExplainPanel
