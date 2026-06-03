import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useChatStore } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useSSE } from '../composables/useSSE'
import { clearChatHistory } from '../api/chat'
import AppHeader from '../components/layout/AppHeader'
import ChatWelcome from '../components/chat/ChatWelcome'
import ChatMessage from '../components/chat/ChatMessage'
import ChatTyping from '../components/chat/ChatTyping'
import ChatInput from '../components/chat/ChatInput'
import SocraticControls from '../components/chat/SocraticControls'
import { MasteryBar } from '../components/chat/MasteryBar'
import { Trash2, Zap, Brain, GraduationCap } from 'lucide-react'

// --- 类型定义 ---
interface ModeOption {
  key: string
  placeholder: string
  guide: string
  label?: string
  desc?: string
}

// --- 组件 ---
const ChatView: React.FC = () => {
  const chatStore = useChatStore()
  const appStore = useAppStore()
  const { sendMessage, sendSocraticAction } = useSSE()

  // --- Refs ---
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const chatInputRef = useRef<{ focus: () => void }>(null)

  // --- 状态 ---
  const [showTyping, setShowTyping] = useState(false)
  const [activeMode, setActiveMode] = useState<string | null>(null)
  const [inputPlaceholder, setInputPlaceholder] = useState('')
  const [chatMode, setChatMode] = useState<'fast' | 'deep' | 'socratic'>('fast')

  // --- 滚动相关 ---
  const userScrolledUp = useRef(false)

  const scrollToBottom = useCallback((force: boolean = false) => {
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

  // --- 发送消息 ---
  const handleSend = useCallback((text: string) => {
    resetScrollState()
    setShowTyping(true)
    setActiveMode(null)
    setInputPlaceholder('')
    window.dispatchEvent(new Event('robot-think'))
    sendMessage(text, chatMode).finally(() => {
      setShowTyping(false)
    })
  }, [sendMessage, resetScrollState, chatMode])

  // --- 中止 ---
  const handleAbort = useCallback(() => {
    chatStore.abort()
  }, [chatStore])

  // --- 清空对话 ---
  const clearChat = useCallback(async () => {
    try {
      await clearChatHistory()
    } catch {
      // ignore
    }
    chatStore.startNewChat()
    chatStore.setSocraticThreadId(null)
    setActiveMode(null)
    setInputPlaceholder('')
    appStore.showToast('对话已清空', 'success')
  }, [chatStore, appStore])

  // --- 选择模式 ---
  const handleSelectMode = useCallback((mode: ModeOption) => {
    setActiveMode(mode.key)
    setInputPlaceholder(mode.placeholder)

    // 添加系统引导消息
    chatStore.addMessage('assistant', mode.guide)

    // 聚焦输入框
    requestAnimationFrame(() => {
      chatInputRef.current?.focus()
    })
  }, [chatStore])

  // --- 消息变化时自动滚动 ---
  useEffect(() => {
    scrollToBottom(true)
  }, [chatStore.messages.length, scrollToBottom])

  // --- 流式输出时自动滚动 ---
  useEffect(() => {
    const last = chatStore.messages[chatStore.messages.length - 1]
    if (last?.role === 'assistant') {
      scrollToBottom()
    }
  }, [chatStore.messages, scrollToBottom])

  // --- 卸载时中止 SSE 连接 ---
  useEffect(() => {
    return () => {
      if (chatStore.isStreaming) {
        chatStore.abort()
      }
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // --- 派生状态 ---
  const messages = chatStore.messages
  const thinkingSteps = chatStore.thinkingSteps
  const thinkingCompleted = chatStore.thinkingCompleted
  const hasMessages = useMemo(() => messages.length > 0, [messages.length])
  const showWelcome = useMemo(
    () => !hasMessages && !chatStore.isLoadingConversation,
    [hasMessages, chatStore.isLoadingConversation]
  )
  const showTypingIndicator = useMemo(
    () => showTyping && !messages.some(m => m.role === 'assistant' && m.content),
    [showTyping, messages]
  )

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
      {/* Header */}
      <AppHeader title="智能对话">
        {chatStore.currentIntent && (
          <span style={{ fontSize: 12, color: '#10b981', background: '#f0fdf4', padding: '2px 8px', borderRadius: 6 }}>
            {chatStore.currentIntent}
          </span>
        )}
        <button
          onClick={clearChat}
          style={{ color: '#9ca3af', padding: 6, borderRadius: 6, border: 'none', background: 'transparent', cursor: 'pointer', transition: 'color 0.15s' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#374151')}
          onMouseLeave={e => (e.currentTarget.style.color = '#9ca3af')}
          title="清空对话"
        >
          <Trash2 style={{ width: 16, height: 16 }} />
        </button>
      </AppHeader>

      {/* Messages */}
      <div
        ref={messagesContainerRef}
        onScroll={handleScroll}
        style={{ flex: 1, overflowY: 'auto', padding: '24px 0', position: 'relative' }}
      >
        {showWelcome ? (
          <ChatWelcome onSelectMode={handleSelectMode} />
        ) : (
          <div style={{ maxWidth: 800, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 32 }}>
            {messages.map((msg, i) => (
              <ChatMessage
                key={i}
                role={msg.role as 'user' | 'assistant' | 'system'}
                content={msg.content}
                cards={msg.cards}
                content_blocks={msg.content_blocks}
                createdAt={msg.created_at}
                isStreaming={chatStore.isStreaming && i === messages.length - 1 && msg.role === 'assistant'}
              />
            ))}
            {showTypingIndicator && <ChatTyping />}

            {/* Thinking Panel */}
            {thinkingSteps.length > 0 && (
              <div style={{
                background: thinkingCompleted
                  ? 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)'
                  : 'linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)',
                border: thinkingCompleted ? '1px solid #bbf7d0' : '1px solid #ddd6fe',
                borderRadius: 12,
                padding: '12px 16px',
                maxWidth: 480,
                transition: 'all 0.5s ease',
                opacity: thinkingCompleted ? 0.85 : 1,
              }}>
                <div style={{
                  fontSize: 13, fontWeight: 600,
                  color: thinkingCompleted ? '#059669' : '#7c3aed',
                  marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6,
                }}>
                  <Brain style={{ width: 14, height: 14 }} />
                  {thinkingCompleted ? '思考完成，正在生成回答...' : '深度思考中...'}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {thinkingSteps.map((step, i) => (
                    <div key={i} style={{
                      fontSize: 12,
                      color: thinkingCompleted ? '#16a34a' : '#6d28d9',
                      lineHeight: 1.6,
                      animation: 'fadeIn 0.3s ease-in',
                      opacity: thinkingCompleted ? 0.7 : 1,
                      textDecoration: thinkingCompleted ? 'line-through' : 'none',
                    }}>
                      {step}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Loading overlay when switching conversations */}
        {chatStore.isLoadingConversation && (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            background: 'rgba(255,255,255,0.8)', zIndex: 10,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: 14 }}>
              <div style={{
                width: 16, height: 16,
                border: '2px solid #e5e7eb', borderTopColor: '#10b981',
                borderRadius: '50%', animation: 'spin 0.6s linear infinite',
              }} />
              加载中...
            </div>
          </div>
        )}
      </div>

      {/* Mode Toggle + Input */}
      <div style={{ borderTop: '1px solid #f3f4f6', background: '#fff' }}>
        {/* Mode Toggle */}
        <div style={{ display: 'flex', justifyContent: 'center', padding: '8px 24px 0', gap: 8 }}>
          <button
            onClick={() => setChatMode('fast')}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 500,
              border: chatMode === 'fast' ? '1px solid #10b981' : '1px solid #e5e7eb',
              background: chatMode === 'fast' ? '#f0fdf4' : '#fff',
              color: chatMode === 'fast' ? '#059669' : '#6b7280',
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <Zap style={{ width: 12, height: 12 }} />
            快速模式
          </button>
          <button
            onClick={() => setChatMode('deep')}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 500,
              border: chatMode === 'deep' ? '1px solid #8b5cf6' : '1px solid #e5e7eb',
              background: chatMode === 'deep' ? '#f5f3ff' : '#fff',
              color: chatMode === 'deep' ? '#7c3aed' : '#6b7280',
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <Brain style={{ width: 12, height: 12 }} />
            深度思考
          </button>
          <button
            onClick={() => setChatMode('socratic')}
            style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 12px', borderRadius: 16, fontSize: 12, fontWeight: 500,
              border: chatMode === 'socratic' ? '1px solid #2563eb' : '1px solid #e5e7eb',
              background: chatMode === 'socratic' ? '#eff6ff' : '#fff',
              color: chatMode === 'socratic' ? '#2563eb' : '#6b7280',
              cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            <GraduationCap style={{ width: 12, height: 12 }} />
            交互式学习
          </button>
        </div>

        {/* Socratic Controls */}
        {chatMode === 'socratic' && (
          <SocraticControls
            threadId={chatStore.socraticThreadId}
            isStreaming={chatStore.isStreaming}
            onHint={() => sendSocraticAction('hint')}
            onConfused={() => sendSocraticAction('confused')}
            onEnd={() => sendSocraticAction('end')}
          />
        )}

        {/* Mastery Bar */}
        {chatMode === 'socratic' && chatStore.socraticThreadId && (
          <MasteryBar />
        )}

        <ChatInput
          ref={chatInputRef}
          isStreaming={chatStore.isStreaming}
          placeholder={
            chatMode === 'deep' ? '深度思考模式：5个Agent将协作为你生成完整学习内容...' :
            chatMode === 'socratic' ? '交互式学习：描述你想学习的知识点，AI将引导你思考...' :
            inputPlaceholder
          }
          onSend={handleSend}
          onAbort={handleAbort}
        />
      </div>

    </div>
  )
}

export default ChatView
