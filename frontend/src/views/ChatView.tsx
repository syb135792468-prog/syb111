import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useChatStore } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useAuthStore } from '../stores/auth'
import { useSSE } from '../composables/useSSE'
import { toggleMessageBookmark } from '../api/chat'
import { recommendResources, type Recommendation } from '../api/resource'
import AppHeader from '../components/layout/AppHeader'
import ChatWelcome from '../components/chat/ChatWelcome'
import ChatMessage from '../components/chat/ChatMessage'
import ChatTyping from '../components/chat/ChatTyping'
import ChatInput from '../components/chat/ChatInput'
import SocraticControls from '../components/chat/SocraticControls'
import { MasteryBar } from '../components/chat/MasteryBar'
import { Trash2, Zap, Brain, GraduationCap, Sparkles, FileText, Video, Code, HelpCircle, Presentation, BookOpen } from 'lucide-react'

interface ModeOption {
  key: string
  placeholder: string
  guide: string
  label?: string
  desc?: string
}

const MODE_OPTIONS: Array<{
  key: 'fast' | 'deep' | 'socratic'
  label: string
  icon: React.ReactNode
  description: string
}> = [
  { key: 'fast', label: '快速模式', icon: <Zap style={{ width: 12, height: 12 }} />, description: '先给方向，再继续追问' },
  { key: 'deep', label: '深度思考', icon: <Brain style={{ width: 12, height: 12 }} />, description: '适合系统拆解问题' },
  { key: 'socratic', label: '交互学习', icon: <GraduationCap style={{ width: 12, height: 12 }} />, description: '通过提问引导理解' },
]

// 资源类型 -> 图标/标签/颜色映射（推荐卡片用）
const RESOURCE_TYPE_META: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
  doc: { icon: <FileText style={{ width: 14, height: 14 }} />, label: '文档', color: '#2563eb' },
  video: { icon: <Video style={{ width: 14, height: 14 }} />, label: '视频', color: '#7c3aed' },
  code: { icon: <Code style={{ width: 14, height: 14 }} />, label: '代码', color: '#059669' },
  mindmap: { icon: <Brain style={{ width: 14, height: 14 }} />, label: '思维导图', color: '#ea580c' },
  quiz: { icon: <HelpCircle style={{ width: 14, height: 14 }} />, label: '练习题', color: '#dc2626' },
  slides: { icon: <Presentation style={{ width: 14, height: 14 }} />, label: '讲义', color: '#0891b2' },
  reading: { icon: <BookOpen style={{ width: 14, height: 14 }} />, label: '阅读', color: '#475569' },
}

const RECOMMEND_TYPE_LABEL: Record<string, string> = {
  doc: '文档', video: '视频', code: '代码示例', mindmap: '思维导图',
  quiz: '练习题', slides: '讲义', reading: '阅读材料',
}

// Agent 协作可见性：Agent 名 -> 图标 + 中文名
const AGENT_DISPLAY: Record<string, { icon: string; name: string }> = {
  UnifiedRouter: { icon: '🧭', name: '路由 Agent' },
  TutorAgent: { icon: '👨‍🏫', name: '教学 Agent' },
  ContentAgent: { icon: '📦', name: '文档 Agent' },
  CodeAgent: { icon: '💻', name: '代码 Agent' },
  MindmapAgent: { icon: '🗺️', name: '思维导图 Agent' },
  QuizAgent: { icon: '📝', name: '测验 Agent' },
  PathAgent: { icon: '🛤️', name: '路径 Agent' },
  ProfileAgent: { icon: '👤', name: '画像 Agent' },
  AggregatorAgent: { icon: '🔗', name: '聚合 Agent' },
  VideoAgent: { icon: '🎬', name: '视频 Agent' },
}

const RecommendCard: React.FC<{ rec: Recommendation; onClick: () => void }> = ({ rec, onClick }) => {
  const meta = RESOURCE_TYPE_META[rec.resource_type] || RESOURCE_TYPE_META.doc
  return (
    <button
      onClick={onClick}
      className="btn-click-feedback"
      style={{
        textAlign: 'left',
        padding: 12,
        borderRadius: 12,
        border: '1px solid rgba(48,105,152,0.12)',
        background: 'rgba(255,255,255,0.92)',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        transition: 'transform 0.2s, box-shadow 0.2s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-2px)'
        e.currentTarget.style.boxShadow = '0 8px 20px rgba(48,105,152,0.12)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = 'translateY(0)'
        e.currentTarget.style.boxShadow = 'none'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: meta.color }}>
        {meta.icon}
        <span style={{ fontSize: 11, fontWeight: 600 }}>{meta.label}</span>
        <span style={{ fontSize: 10, color: 'var(--mute)', marginLeft: 'auto' }}>{rec.difficulty}</span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)', lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
        {rec.title}
      </div>
      <div style={{ fontSize: 11, color: 'var(--mute)', lineHeight: 1.5 }}>
        {rec.reason}
      </div>
    </button>
  )
}

const ChatView: React.FC = () => {
  const messages = useChatStore((state) => state.messages)
  const isStreaming = useChatStore((state) => state.isStreaming)
  const isLoadingConversation = useChatStore((state) => state.isLoadingConversation)
  const currentConversationId = useChatStore((state) => state.currentConversationId)
  const currentIntent = useChatStore((state) => state.currentIntent)
  const thinkingSteps = useChatStore((state) => state.thinkingSteps)
  const thinkingCompleted = useChatStore((state) => state.thinkingCompleted)
  const socraticThreadId = useChatStore((state) => state.socraticThreadId)
  const addThinkingStep = useChatStore((state) => state.addThinkingStep)
  const abort = useChatStore((state) => state.abort)
  const startNewChat = useChatStore((state) => state.startNewChat)
  const deleteConversation = useChatStore((state) => state.deleteConversation)
  const addMessage = useChatStore((state) => state.addMessage)
  const setThinkingCompleted = useChatStore((state) => state.setThinkingCompleted)
  const clearThinkingSteps = useChatStore((state) => state.clearThinkingSteps)
  const updateMessageBookmark = useChatStore((state) => state.updateMessageBookmark)
  const showToast = useAppStore((state) => state.showToast)
  const authStore = useAuthStore()
  const { sendMessage, sendSocraticAction } = useSSE()

  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<{ focus: () => void }>(null)
  const thinkingClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const userScrolledUp = useRef(false)

  const [inputPlaceholder, setInputPlaceholder] = useState('')
  const [chatMode, setChatMode] = useState<'fast' | 'deep' | 'socratic'>('fast')
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])

  const scrollToBottom = useCallback((force = false) => {
    if (!messagesContainerRef.current) return
    if (!force && userScrolledUp.current) return
    requestAnimationFrame(() => {
      if (messagesContainerRef.current) {
        messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight
      }
    })
  }, [])

  const handleScroll = useCallback(() => {
    if (!messagesContainerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = messagesContainerRef.current
    userScrolledUp.current = scrollHeight - scrollTop - clientHeight > 80
  }, [])

  const resetScrollState = useCallback(() => {
    userScrolledUp.current = false
  }, [])

  const handleSend = useCallback(
    (text: string, imageUrls?: string[]) => {
      resetScrollState()
      setInputPlaceholder('')
      window.dispatchEvent(new Event('robot-think'))
      addThinkingStep(chatMode === 'deep' ? '正在调度多智能体分析你的问题...' : '正在整理你的提问重点...')
      sendMessage(text, chatMode, imageUrls)
    },
    [addThinkingStep, sendMessage, resetScrollState, chatMode],
  )

  const handleAbort = useCallback(() => {
    abort()
  }, [abort])

  const clearChat = useCallback(async () => {
    const conversationId = currentConversationId
    if (conversationId) {
      const success = await deleteConversation(conversationId)
      if (!success) {
        showToast('删除对话失败', 'error')
        return
      }
    } else {
      startNewChat()
    }

    setInputPlaceholder('')
    showToast(conversationId ? '对话已删除' : '当前会话已清空', 'success')
  }, [currentConversationId, deleteConversation, showToast, startNewChat])

  const handleBookmark = useCallback(
    async (messageIndex: number) => {
      const message = messages[messageIndex]
      if (!message?.id) return
      try {
        const response = await toggleMessageBookmark(message.id)
        if (response.code === 200) {
          const newState = (response.data as { is_bookmarked: boolean })?.is_bookmarked
          updateMessageBookmark(messageIndex, newState)
          showToast(newState ? '已收藏回答' : '已取消收藏', 'success')
        }
      } catch {
        showToast('操作失败', 'error')
      }
    },
    [messages, showToast, updateMessageBookmark],
  )

  const handleSelectMode = useCallback(
    (mode: ModeOption) => {
      setInputPlaceholder(mode.placeholder)

      if (mode.key === 'socratic') {
        setChatMode('socratic')
      }

      addMessage('assistant', mode.guide)
      requestAnimationFrame(() => {
        chatInputRef.current?.focus()
      })
    },
    [addMessage],
  )

  const handleRecommendClick = useCallback(
    (rec: Recommendation) => {
      const label = RECOMMEND_TYPE_LABEL[rec.resource_type] || rec.resource_type
      handleSend(`给我看一下「${rec.knowledge_point}」的${label}资源`)
    },
    [handleSend],
  )

  useEffect(() => {
    scrollToBottom(true)
  }, [messages.length, thinkingSteps.length, scrollToBottom])

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (last?.role === 'assistant') {
      scrollToBottom()
    }
  }, [messages, scrollToBottom])

  useEffect(() => {
    const last = messages[messages.length - 1]
    if (last?.role === 'assistant') {
      const hasContent = last.content || (last.content_blocks && last.content_blocks.length > 0)
      if (hasContent && thinkingSteps.length > 0 && !thinkingCompleted) {
        setThinkingCompleted(true)
        thinkingClearTimer.current = setTimeout(() => clearThinkingSteps(), 300)
      }
    }
  }, [messages, thinkingSteps.length, thinkingCompleted, setThinkingCompleted, clearThinkingSteps])

  useEffect(() => {
    return () => {
      if (thinkingClearTimer.current) clearTimeout(thinkingClearTimer.current)
    }
  }, [])

  const hasMessages = messages.length > 0
  const showWelcome = !hasMessages && !isLoadingConversation

  // 按 agent_name 分组 thinkingSteps（协作可见性）
  const groupedThinking = useMemo(() => {
    const groups: Record<string, { agentName: string; agentRole: string; icon: string; steps: typeof thinkingSteps }> = {}
    const order: string[] = []
    for (const step of thinkingSteps) {
      const key = step.agent_name || '_generic'
      if (!groups[key]) {
        const display = step.agent_name
          ? (AGENT_DISPLAY[step.agent_name] || { icon: '🤖', name: step.agent_name })
          : { icon: '🧠', name: '通用' }
        groups[key] = {
          agentName: step.agent_name || '',
          agentRole: step.agent_role || display.name,
          icon: display.icon,
          steps: [],
        }
        order.push(key)
      }
      groups[key].steps.push(step)
    }
    return order.map(k => groups[k])
  }, [thinkingSteps])

  const showTypingIndicator = useMemo(() => {
    if (!isStreaming) return false
    const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    if (!lastAssistant) return true
    const hasContent = lastAssistant.content || (lastAssistant.content_blocks && lastAssistant.content_blocks.length > 0)
    return !hasContent
  }, [isStreaming, messages])

  // 进入欢迎页（showWelcome）时加载一次基于画像的推荐资源
  useEffect(() => {
    if (!showWelcome) return
    const uid = authStore.userId
    if (!uid) return

    let cancelled = false
    recommendResources(uid)
      .then((resp) => {
        if (cancelled) return
        if (resp.code === 200 && resp.data) {
          setRecommendations(resp.data.recommendations || [])
        }
      })
      .catch((err) => {
        console.warn('推荐资源加载失败:', err)
      })

    return () => {
      cancelled = true
    }
  }, [showWelcome, authStore.userId])

  return (
    <div className="chat-stage">
      <style>{`
        @keyframes local-spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>

      <AppHeader title="智能对话">
        {currentIntent && (
          <span
            className="shell-title-eyebrow"
            style={{
              color: 'var(--py-blue-deep)',
              background: 'rgba(48, 105, 152, 0.08)',
              border: '1px solid rgba(48, 105, 152, 0.14)',
            }}
          >
            <Sparkles style={{ width: 12, height: 12 }} />
            {currentIntent}
          </span>
        )}

        <button onClick={clearChat} className="shell-icon-button btn-click-feedback" title="清空对话">
          <Trash2 style={{ width: 16, height: 16 }} />
        </button>
      </AppHeader>

      <div ref={messagesContainerRef} onScroll={handleScroll} className="chat-scroll-zone smooth-scroll">
        {showWelcome ? (
          <>
            {recommendations.length > 0 && (
              <div style={{ padding: '0 20px', marginBottom: 16 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                  <Sparkles style={{ width: 14, height: 14, color: 'var(--py-yellow-deep)' }} />
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink)' }}>今日推荐 · 基于你的画像</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
                  {recommendations.map((rec, i) => (
                    <RecommendCard
                      key={`${rec.knowledge_point}-${rec.resource_type}-${i}`}
                      rec={rec}
                      onClick={() => handleRecommendClick(rec)}
                    />
                  ))}
                </div>
              </div>
            )}
            <ChatWelcome onSelectMode={handleSelectMode} />
          </>
        ) : (
          <div className="chat-feed">
            {messages.map((message, index) => (
              <div key={message.id ?? `${message.role}-${message.created_at ?? index}-${index}`} style={{ paddingBottom: 26 }}>
                <ChatMessage
                  id={message.id}
                  role={message.role as 'user' | 'assistant' | 'system'}
                  content={message.content}
                  cards={message.cards}
                  content_blocks={message.content_blocks}
                  imageUrls={message.image_urls}
                  createdAt={message.created_at}
                  isStreaming={isStreaming && index === messages.length - 1 && message.role === 'assistant'}
                  isBookmarked={message.is_bookmarked}
                  onBookmark={message.role === 'assistant' && message.id ? () => handleBookmark(index) : undefined}
                  conversationId={currentConversationId}
                />
              </div>
            ))}

            {showTypingIndicator && (
              <div style={{ marginTop: 24 }}>
                <ChatTyping />
              </div>
            )}

            {thinkingSteps.length > 0 && (
              <div
                className="thinking-shell"
                style={{
                  opacity: thinkingCompleted ? 0.72 : 1,
                  background: thinkingCompleted
                    ? 'linear-gradient(135deg, rgba(235,245,255,0.94), rgba(245,249,255,0.92))'
                    : 'linear-gradient(135deg, rgba(246,241,255,0.96), rgba(250,245,255,0.92))',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: 12,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      background: thinkingCompleted ? 'rgba(48,105,152,0.12)' : 'rgba(124,58,237,0.12)',
                      color: thinkingCompleted ? '#2563eb' : '#7c3aed',
                    }}
                  >
                    <Brain style={{ width: 14, height: 14 }} />
                  </div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 700, color: thinkingCompleted ? '#2563eb' : '#7c3aed' }}>
                      {thinkingCompleted
                        ? '开始组织回答'
                        : `${groupedThinking.length} 个 Agent 正在协作`}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--mute)' }}>
                      {thinkingCompleted ? '思考阶段已完成，正在生成内容。' : '多智能体协作处理中，各司其职。'}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {groupedThinking.map((group, gIdx) => (
                    <div key={gIdx} style={{ padding: '6px 0' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <span style={{ fontSize: 14 }}>{group.icon}</span>
                        <span style={{ fontSize: 12, fontWeight: 600, color: thinkingCompleted ? 'var(--mute)' : 'var(--ink)' }}>
                          {group.agentRole}
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            color: thinkingCompleted ? '#16a34a' : '#7c3aed',
                            marginLeft: 'auto',
                          }}
                        >
                          {thinkingCompleted ? '✓' : '⏳'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 4, marginLeft: 22 }}>
                        {group.steps.map((step, sIdx) => (
                          <div
                            key={sIdx}
                            className="thinking-step"
                            style={{
                              fontSize: 12,
                              color: thinkingCompleted ? 'var(--mute)' : 'var(--ink-soft)',
                              lineHeight: 1.7,
                              textDecoration: thinkingCompleted ? 'line-through' : 'none',
                            }}
                          >
                            {step.text}
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {isLoadingConversation && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              background: 'rgba(245, 247, 251, 0.74)',
              backdropFilter: 'blur(4px)',
              zIndex: 10,
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                padding: '14px 18px',
                borderRadius: 18,
                border: '1px solid rgba(112, 137, 175, 0.16)',
                background: 'rgba(255,255,255,0.88)',
                color: 'var(--ink-soft)',
                boxShadow: '0 24px 48px rgba(23, 37, 61, 0.08)',
              }}
            >
              <div
                style={{
                  width: 16,
                  height: 16,
                  border: '2px solid rgba(48, 105, 152, 0.2)',
                  borderTopColor: 'var(--py-blue)',
                  borderRadius: '50%',
                  animation: 'local-spin 0.6s linear infinite',
                }}
              />
              正在载入会话...
            </div>
          </div>
        )}
      </div>

      <div style={{ padding: '0 10px 8px' }}>
        <div className="chat-feed" style={{ display: 'flex', justifyContent: 'center', marginBottom: 6 }}>
          <div className="chat-mode-pills">
            {MODE_OPTIONS.map((mode) => {
              const active = chatMode === mode.key
              return (
                <button
                  key={mode.key}
                  onClick={() => setChatMode(mode.key)}
                  disabled={isStreaming}
                  title={isStreaming ? '生成中，暂时无法切换模式' : mode.description}
                  className={`chat-mode-pill btn-click-feedback ${active ? 'chat-mode-pill-active' : ''}`}
                  style={{ opacity: isStreaming ? 0.56 : 1 }}
                >
                  {mode.icon}
                  {mode.label}
                </button>
              )
            })}
          </div>
        </div>

        {chatMode === 'socratic' && (
          <SocraticControls
            threadId={socraticThreadId}
            isStreaming={isStreaming}
            onHint={() => sendSocraticAction('hint')}
            onConfused={() => sendSocraticAction('confused')}
            onEnd={() => sendSocraticAction('end')}
          />
        )}

        {chatMode === 'socratic' && socraticThreadId && <MasteryBar />}

        <ChatInput
          ref={chatInputRef}
          isStreaming={isStreaming}
          placeholder={
            chatMode === 'deep'
              ? '深度思考模式：系统会调度多个 Agent 协同分析，并尽量给出更完整的学习展开。'
              : chatMode === 'socratic'
                ? '交互式学习：描述你想学的知识点，AI 会通过提问一步步带你想清楚。'
                : inputPlaceholder
          }
          onSend={handleSend}
          onAbort={handleAbort}
        />
      </div>
    </div>
  )
}

export default ChatView
