import React, { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react'
import { Send, Square } from 'lucide-react'

// --- 类型定义 ---
interface ChatInputProps {
  isStreaming?: boolean
  placeholder?: string
  onSend: (text: string) => void
  onAbort: () => void
}

export interface ChatInputHandle {
  focus: () => void
}

// --- 常量 ---
const DEFAULT_PLACEHOLDER = '输入你的问题... (Shift+Enter 换行)'

// --- 组件 ---
const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  ({ isStreaming = false, placeholder = '', onSend, onAbort }, ref) => {
    const [message, setMessage] = useState('')
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    const currentPlaceholder = placeholder || DEFAULT_PLACEHOLDER
    const trimmed = message.trim()

    // --- 暴露 focus 方法 ---
    useImperativeHandle(ref, () => ({
      focus: () => {
        requestAnimationFrame(() => textareaRef.current?.focus())
      }
    }), [])

    // --- 调整高度 ---
    const adjustHeight = useCallback(() => {
      const el = textareaRef.current
      if (!el) return
      el.style.height = 'auto'
      el.style.height = Math.min(el.scrollHeight, 128) + 'px'
    }, [])

    // --- 发送 ---
    const handleSend = useCallback(() => {
      const text = message.trim()
      if (!text || isStreaming) return
      onSend(text)
      setMessage('')
      requestAnimationFrame(adjustHeight)
    }, [message, isStreaming, onSend, adjustHeight])

    // --- 键盘事件 ---
    const handleKeydown = useCallback((e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    }, [handleSend])

    // placeholder 变化时同步高度
    useEffect(() => {
      adjustHeight()
    }, [placeholder, adjustHeight])

    return (
      <div style={{ padding: '16px 64px' }}>
        <div
          style={{
            background: '#f9fafb', border: '1px solid #e5e7eb',
            borderRadius: 12, padding: '12px 16px', transition: 'border-color 0.15s ease',
          }}
          onFocusCapture={e => {
            (e.currentTarget as HTMLElement).style.borderColor = '#10b981'
          }}
          onBlurCapture={e => {
            (e.currentTarget as HTMLElement).style.borderColor = '#e5e7eb'
          }}
        >
          <form
            onSubmit={e => { e.preventDefault(); handleSend() }}
            style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}
          >
            <textarea
              ref={textareaRef}
              value={message}
              onChange={e => setMessage(e.target.value)}
              onKeyDown={handleKeydown}
              onInput={adjustHeight}
              placeholder={currentPlaceholder}
              rows={1}
              style={{
                flex: 1, background: 'transparent', border: 'none', outline: 'none',
                resize: 'none', fontSize: 15, color: '#111827', lineHeight: 1.5,
                maxHeight: 128, minHeight: 24, fontFamily: 'inherit',
              }}
            />
            {isStreaming ? (
              <button
                type="button"
                onClick={onAbort}
                style={{
                  padding: '6px 14px', borderRadius: 8, border: 'none',
                  background: '#ef4444', color: '#ffffff', cursor: 'pointer',
                  transition: 'background 0.15s ease', display: 'flex', alignItems: 'center',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#dc2626')}
                onMouseLeave={e => (e.currentTarget.style.background = '#ef4444')}
              >
                <Square style={{ width: 16, height: 16 }} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!trimmed}
                style={{
                  padding: '6px 14px', borderRadius: 8, border: 'none',
                  background: '#10b981', color: '#ffffff',
                  cursor: trimmed ? 'pointer' : 'not-allowed',
                  transition: 'background 0.15s ease', display: 'flex', alignItems: 'center',
                  opacity: trimmed ? 1 : 0.4,
                }}
                onMouseEnter={e => { if (trimmed) e.currentTarget.style.background = '#059669' }}
                onMouseLeave={e => (e.currentTarget.style.background = '#10b981')}
              >
                <Send style={{ width: 16, height: 16 }} />
              </button>
            )}
          </form>
        </div>
        <p style={{ fontSize: 12, color: '#9ca3af', margin: '8px 0 0', textAlign: 'center' }}>
          按 Enter 发送，Shift+Enter 换行
        </p>
      </div>
    )
  }
)

ChatInput.displayName = 'ChatInput'

export default ChatInput
