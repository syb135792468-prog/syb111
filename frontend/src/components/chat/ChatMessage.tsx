import React, { useMemo, useEffect, useRef, useState, useCallback, useId } from 'react'
import { Bot, Bookmark, MessageCircle, Sparkles } from 'lucide-react'
import { useAppStore } from '../../stores/app'
import { renderMarkdown, highlightCodeBlocks, highlightCodeToHtml } from '../../utils/markdown'
import { ContentCardRef, ContentBlock } from '../../stores/chat'
import ContentCardRenderer from '../cards/ContentCardRenderer'

interface ChatMessageProps {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  cards?: ContentCardRef[]
  content_blocks?: ContentBlock[]
  imageUrls?: string[]
  createdAt?: string
  isStreaming?: boolean
  isBookmarked?: boolean
  onBookmark?: () => void
  conversationId?: number | string | null
}

interface ContentSegment {
  type: 'text' | 'card'
  value: string
}

const CARD_MARKER_RE = /\{\{card:([^}]+)\}\}/g

function parseContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = CARD_MARKER_RE.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: content.slice(lastIndex, match.index) })
    }
    segments.push({ type: 'card', value: match[1] })
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < content.length) {
    segments.push({ type: 'text', value: content.slice(lastIndex) })
  }

  if (segments.length === 0) {
    segments.push({ type: 'text', value: content })
  }

  return segments
}

function hasTextSelection(): boolean {
  const selection = window.getSelection()
  return !!selection && selection.toString().trim().length > 0
}

const ChatMessage: React.FC<ChatMessageProps> = ({
  id,
  role,
  content,
  cards,
  content_blocks,
  imageUrls,
  createdAt,
  isStreaming,
  isBookmarked,
  onBookmark,
  conversationId,
}) => {
  const contentRef = useRef<HTMLDivElement>(null)
  const reactId = useId()
  const messageId = id ?? reactId
  const chatSelection = useAppStore((state) => state.chatSelection)
  const setChatSelection = useAppStore((state) => state.setChatSelection)
  const isMySelection = chatSelection?.messageId === messageId
  const selectedText = isMySelection ? chatSelection!.text : ''
  const selectPos = isMySelection ? { x: chatSelection!.x, y: chatSelection!.y } : null
  const [copied, setCopied] = useState(false)

  const isUser = role === 'user'
  const isSystem = role === 'system'
  const isAssistant = role === 'assistant'

  const segments = useMemo(() => {
    if (!isAssistant || !content) return []
    return parseContentSegments(content)
  }, [isAssistant, content])

  const cardsMap = useMemo(() => {
    if (!cards) return new Map<string, ContentCardRef>()
    return new Map(cards.map((card) => [card.id, card]))
  }, [cards])

  const referencedCardIds = useMemo(() => new Set(segments.filter((segment) => segment.type === 'card').map((segment) => segment.value)), [segments])
  const unreferencedCards = useMemo(() => {
    if (!cards) return []
    return cards.filter((card) => !referencedCardIds.has(card.id))
  }, [cards, referencedCardIds])

  const timeStr = useMemo(() => {
    if (!createdAt) return ''
    const date = new Date(createdAt)
    const now = new Date()
    const sameDay =
      date.getFullYear() === now.getFullYear() &&
      date.getMonth() === now.getMonth() &&
      date.getDate() === now.getDate()

    const time = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
    if (sameDay) return time
    return `${date.getMonth() + 1}/${date.getDate()} ${time}`
  }, [createdAt])

  useEffect(() => {
    if (contentRef.current && isAssistant && !isStreaming) {
      highlightCodeBlocks(contentRef.current)
    }
  }, [isAssistant, content, isStreaming])

  const openExplainPanel = useCallback(
    (text: string, context: string, extra?: Record<string, unknown>) => {
      useAppStore.getState().openRightPanel('chat-explain', {
        text,
        context,
        messageId: id,
        conversationId: conversationId ? Number(conversationId) : undefined,
        ...extra,
      })
    },
    [conversationId, id],
  )

  const handleMouseUp = useCallback(() => {
    if (!isAssistant) return
    setTimeout(() => {
      const selection = window.getSelection()
      const text = selection?.toString().trim()
      if (text && text.length > 1 && selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        if (contentRef.current && contentRef.current.contains(selection.anchorNode)) {
          setChatSelection({ messageId, text, x: rect.left + rect.width / 2, y: rect.top })
          setCopied(false)
        }
      } else if (isMySelection) {
        setChatSelection(null)
      }
    }, 10)
  }, [isAssistant, isMySelection, messageId, setChatSelection])

  const handleCopy = useCallback(() => {
    if (!selectedText) return
    navigator.clipboard.writeText(selectedText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }, [selectedText])

  const handleExplainSelection = useCallback(() => {
    if (!selectedText) return
    openExplainPanel(selectedText, content.slice(0, 1000))
    setChatSelection(null)
  }, [selectedText, openExplainPanel, content, setChatSelection])

  useEffect(() => {
    if (!selectPos) return

    const handleDismiss = () => {
      setTimeout(() => {
        const selection = window.getSelection()
        if (!selection || selection.toString().trim().length === 0) {
          setChatSelection(null)
        }
      }, 200)
    }

    const handleScroll = (event: Event) => {
      const target = event.target as HTMLElement | Document
      if (!(target instanceof HTMLElement && target.classList.contains('smooth-scroll'))) return
      setChatSelection(null)
      window.getSelection()?.removeAllRanges()
    }

    document.addEventListener('mousedown', handleDismiss)
    document.addEventListener('scroll', handleScroll, true)

    return () => {
      document.removeEventListener('mousedown', handleDismiss)
      document.removeEventListener('scroll', handleScroll, true)
    }
  }, [selectPos, setChatSelection])

  const renderCard = useCallback(
    (card: ContentCardRef) => (
      <div
        key={card.id}
        style={{ marginTop: 12 }}
        onClick={(event) => {
          const target = event.target as HTMLElement
          if (target.closest('button, input, select, textarea, a')) return
          if (hasTextSelection()) return
          if (card.title) {
            openExplainPanel(card.title, JSON.stringify(card.data || {}), {
              topic: card.title,
              knowledgePoint: card.title,
            })
          }
        }}
        className="card-clickable"
      >
        <ContentCardRenderer card={card} />
      </div>
    ),
    [openExplainPanel],
  )

  const renderBlock = useCallback(
    (block: ContentBlock, index: number) => {
      if (block.type === 'text') {
        return (
          <div
            key={`block-${index}`}
            className="md-content"
            style={{ color: 'var(--ink-soft)', lineHeight: 1.8 }}
            dangerouslySetInnerHTML={{ __html: renderMarkdown(block.text) }}
          />
        )
      }

      if (block.type === 'card') {
        const cardRef: ContentCardRef = {
          id: String(block.card_id),
          type: block.card_type as ContentCardRef['type'],
          title: block.title,
          data: block.data,
          collapsed: false,
        }

        return renderCard(cardRef)
      }

      if (block.type === 'code') {
        return (
          <div
            key={`block-${index}`}
            style={{
              marginTop: 12,
              borderRadius: 18,
              overflow: 'hidden',
              border: '1px solid rgba(112, 137, 175, 0.14)',
              boxShadow: '0 18px 40px rgba(23, 37, 61, 0.08)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                background: '#182235',
                color: '#d8e1f1',
                fontSize: 12,
              }}
            >
              <span style={{ fontFamily: 'var(--font-mono)' }}>{block.language || 'code'}</span>
              <button
                type="button"
                onClick={() => {
                  if (block.code) {
                    openExplainPanel(block.code, `语言: ${block.language || 'python'}\n说明: ${block.title || '代码片段'}`, {
                      topic: block.title || `${block.language || '代码'}示例`,
                      knowledgePoint: block.title || undefined,
                    })
                  }
                }}
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: 'var(--py-yellow)',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                点击解释
              </button>
            </div>
            <pre
              style={{
                margin: 0,
                padding: 16,
                background: '#0f172a',
                color: '#f3f4f6',
                fontSize: 13.5,
                overflow: 'auto',
              }}
            >
              <code
                className={`language-${block.language || 'python'} hljs`}
                data-highlighted="true"
                dangerouslySetInnerHTML={{ __html: highlightCodeToHtml(block.code, block.language) }}
              />
            </pre>
          </div>
        )
      }

      if (block.type === 'thinking') {
        return (
          <div
            key={`block-${index}`}
            style={{
              marginTop: 10,
              borderRadius: 16,
              padding: '10px 12px',
              background: 'rgba(255, 212, 59, 0.12)',
              border: '1px solid rgba(255, 212, 59, 0.3)',
              color: 'var(--ink-soft)',
              fontSize: 13,
              fontStyle: 'italic',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
            }}
          >
            <Sparkles style={{ width: 14, height: 14, color: 'var(--py-yellow-deep)', marginTop: 2, flexShrink: 0 }} />
            <span>{block.text}</span>
          </div>
        )
      }

      return null
    },
    [openExplainPanel, renderCard],
  )

  if (isUser) {
    return (
      <article
        role="article"
        aria-label={`用户消息: ${content.slice(0, 50)}...`}
        className="msg-enter"
        style={{ display: 'flex', justifyContent: 'flex-end', paddingLeft: 24 }}
      >
        <div className="chat-user-column" style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
          <div className="message-meta">
            <strong>你</strong>
            {timeStr && <span>{timeStr}</span>}
          </div>

          {imageUrls && imageUrls.length > 0 && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 10, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
              {imageUrls.map((url, index) => (
                <img
                  key={index}
                  src={url}
                  alt="用户上传的图片"
                  loading="lazy"
                  className="user-image-thumb"
                  style={{
                    maxWidth: 132,
                    maxHeight: 132,
                    borderRadius: 16,
                    cursor: 'pointer',
                    objectFit: 'cover',
                    border: '1px solid rgba(112, 137, 175, 0.16)',
                    transition: 'transform 0.2s ease',
                  }}
                  onClick={() => window.open(url, '_blank')}
                  onError={(event) => {
                    event.currentTarget.style.opacity = '0.3'
                  }}
                />
              ))}
            </div>
          )}

          <div className="chat-bubble-user" style={{ padding: '14px 18px', maxWidth: '100%' }}>
            <p style={{ fontSize: 15, color: 'inherit', whiteSpace: 'pre-wrap', lineHeight: 1.8, margin: 0 }}>{content}</p>
          </div>
        </div>

        <div className="message-avatar user-avatar" style={{ marginLeft: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 700 }}>你</span>
        </div>
      </article>
    )
  }

  if (isSystem) {
    return (
      <div
        role="status"
        aria-label="系统消息"
        className="msg-enter"
        style={{ display: 'flex', justifyContent: 'center', flexDirection: 'column', alignItems: 'center', gap: 6 }}
      >
        <span
          style={{
            fontSize: 12,
            color: 'var(--mute)',
            background: 'rgba(255,255,255,0.68)',
            padding: '6px 12px',
            borderRadius: 999,
            border: '1px solid rgba(112, 137, 175, 0.14)',
          }}
        >
          {content}
        </span>
        {timeStr && <time dateTime={createdAt} style={{ fontSize: 11, color: 'var(--faint)' }}>{timeStr}</time>}
      </div>
    )
  }

  const hasMarkers = segments.some((segment) => segment.type === 'card')
  const hasContentBlocks = content_blocks && content_blocks.length > 0

  return (
    <article
      role="article"
      aria-label="助手消息"
      className="msg-enter"
      style={{ display: 'flex', paddingRight: 24, position: 'relative' }}
    >
      <div className="message-avatar assistant-avatar" style={{ marginRight: 14 }}>
        <Bot style={{ width: 18, height: 18 }} />
      </div>

      <div className="chat-answer-column" style={{ width: '100%', flex: 1, minWidth: 0 }}>
        <div className="message-meta">
          <strong>Python 导学助手</strong>
          {timeStr && <span>{timeStr}</span>}
        </div>

        <div
          ref={contentRef}
          onMouseUp={handleMouseUp}
          className="main-content chat-bubble-assistant chat-answer-surface"
        >
          {hasContentBlocks ? (
            <div>{content_blocks!.map(renderBlock)}</div>
          ) : hasMarkers ? (
            <div>
              {segments.map((segment, index) => {
                if (segment.type === 'card') {
                  const card = cardsMap.get(segment.value)
                  return card ? renderCard(card) : null
                }
                return (
                  <div
                    key={`text-${index}`}
                    className="md-content"
                    style={{ color: 'var(--ink-soft)', lineHeight: 1.8 }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(segment.value) }}
                  />
                )
              })}
            </div>
          ) : (
            <div>
              <div
                className="md-content"
                style={{ color: 'var(--ink-soft)', lineHeight: 1.8 }}
                dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
              />
              {cards && cards.length > 0 && (
                <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {cards.map(renderCard)}
                </div>
              )}
            </div>
          )}
        </div>

        {unreferencedCards.length > 0 && hasMarkers && !hasContentBlocks && (
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {unreferencedCards.map(renderCard)}
          </div>
        )}

        <div
          className="message-actions"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            marginTop: 12,
            paddingTop: 10,
            borderTop: '1px solid rgba(112, 137, 175, 0.1)',
            flexWrap: 'wrap',
          }}
        >
          {onBookmark && (
            <button
              onClick={onBookmark}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 10px',
                borderRadius: 999,
                border: '1px solid rgba(112, 137, 175, 0.14)',
                background: isBookmarked ? 'var(--py-yellow-tint)' : 'rgba(255,255,255,0.58)',
                color: isBookmarked ? 'var(--py-yellow-deep)' : 'var(--mute)',
                fontSize: 12,
                cursor: 'pointer',
              }}
              title={isBookmarked ? '取消收藏' : '收藏此回答'}
            >
              <Bookmark style={{ width: 13, height: 13 }} fill={isBookmarked ? 'currentColor' : 'none'} />
              {isBookmarked ? '已收藏' : '收藏'}
            </button>
          )}

          <button
            disabled={isStreaming || !id}
            onClick={() => {
              const selection = window.getSelection()
              const text = selection?.toString().trim()
              if (text && text.length > 1) {
                openExplainPanel(text, content.slice(0, 1000))
                selection?.removeAllRanges()
              } else {
                openExplainPanel(content.slice(0, 500), '')
              }
            }}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              padding: '6px 10px',
              borderRadius: 999,
              border: '1px solid rgba(112, 137, 175, 0.14)',
              background: 'rgba(255,255,255,0.58)',
              color: 'var(--mute)',
              fontSize: 12,
              cursor: isStreaming || !id ? 'not-allowed' : 'pointer',
              opacity: isStreaming || !id ? 0.5 : 1,
            }}
            title={isStreaming ? '生成中，暂时无法解释' : !id ? '消息尚未保存，暂时无法解释' : '解释这段内容'}
          >
            <MessageCircle style={{ width: 13, height: 13 }} />
            解释
          </button>
        </div>
      </div>

      {selectedText && selectPos && (
        <div
          className="chat-selection-popup"
          style={{
            left: selectPos.x,
            top: selectPos.y < 110 ? selectPos.y + 16 : selectPos.y - 110,
          }}
        >
          <div
            style={{
              borderRadius: 16,
              background: 'linear-gradient(180deg, rgba(255,255,255,0.96), rgba(250,252,255,0.98))',
              border: '1px solid rgba(112, 137, 175, 0.18)',
              boxShadow: '0 24px 48px rgba(23, 37, 61, 0.12)',
              padding: '12px 14px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
              <div
                style={{
                  width: 4,
                  minHeight: 42,
                  borderRadius: 999,
                  background: 'linear-gradient(180deg, var(--py-blue), var(--py-yellow))',
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--ink)',
                    lineHeight: 1.65,
                    display: '-webkit-box',
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                    wordBreak: 'break-word',
                    marginBottom: 10,
                  }}
                >
                  {selectedText}
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button
                    onClick={handleCopy}
                    style={{
                      border: 'none',
                      background: copied ? 'rgba(48,105,152,0.12)' : 'transparent',
                      color: copied ? 'var(--py-blue)' : 'var(--mute)',
                      padding: '5px 8px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    {copied ? '已复制' : '复制'}
                  </button>
                  <button
                    onClick={handleExplainSelection}
                    style={{
                      border: 'none',
                      background: 'transparent',
                      color: 'var(--py-blue)',
                      padding: '5px 8px',
                      borderRadius: 8,
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: 600,
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 4,
                    }}
                  >
                    <MessageCircle style={{ width: 13, height: 13 }} />
                    解释
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      <style>{`
        .card-clickable {
          cursor: pointer;
          transition: transform 0.15s ease;
        }
        .card-clickable:hover {
          transform: translateY(-1px);
        }
        .main-content {
          user-select: text;
        }
        .user-image-thumb:hover {
          transform: scale(1.04);
        }
      `}</style>
    </article>
  )
}

export default ChatMessage
