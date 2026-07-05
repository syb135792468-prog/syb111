import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useChatStore } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useSSE } from '../composables/useSSE'
import { toggleMessageBookmark } from '../api/chat'
import AppHeader from '../components/layout/AppHeader'
import ChatWelcome from '../components/chat/ChatWelcome'
import ChatMessage from '../components/chat/ChatMessage'
import ChatTyping from '../components/chat/ChatTyping'
import ChatInput from '../components/chat/ChatInput'
import SocraticControls from '../components/chat/SocraticControls'
import { MasteryBar } from '../components/chat/MasteryBar'
import { Trash2, Zap, Brain, GraduationCap, Sparkles } from 'lucide-react'

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
  const { sendMessage, sendSocraticAction } = useSSE()

  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<{ focus: () => void }>(null)
  const thinkingClearTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const userScrolledUp = useRef(false)

  const [inputPlaceholder, setInputPlaceholder] = useState('')
  const [chatMode, setChatMode] = useState<'fast' | 'deep' | 'socratic'>('fast')

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
  const showTypingIndicator = useMemo(() => {
    if (!isStreaming) return false
    const lastAssistant = [...messages].reverse().find((message) => message.role === 'assistant')
    if (!lastAssistant) return true
    const hasContent = lastAssistant.content || (lastAssistant.content_blocks && lastAssistant.content_blocks.length > 0)
    return !hasContent
  }, [isStreaming, messages])

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
          <ChatWelcome onSelectMode={handleSelectMode} />
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
                      {thinkingCompleted ? '开始组织回答' : '正在处理你的问题'}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--mute)' }}>
                      {thinkingCompleted ? '思考阶段已完成，正在生成内容。' : '系统正在梳理重点、路由工具和知识结构。'}
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {thinkingSteps.map((step, index) => (
                    <div
                      key={index}
                      className="thinking-step"
                      style={{
                        fontSize: 12,
                        color: thinkingCompleted ? 'var(--mute)' : 'var(--ink-soft)',
                        lineHeight: 1.7,
                        textDecoration: thinkingCompleted ? 'line-through' : 'none',
                      }}
                    >
                      {step}
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
