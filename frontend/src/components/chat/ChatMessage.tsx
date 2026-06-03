import React, { useMemo, useEffect, useRef } from 'react'
import { Bot } from 'lucide-react'
import { renderMarkdown, highlightCodeBlocks } from '../../utils/markdown'
import { ContentCardRef, ContentBlock, CardBlock } from '../../stores/chat'
import ContentCardRenderer from '../cards/ContentCardRenderer'
import SkeletonCard from '../cards/SkeletonCard'

// --- 类型定义 ---
interface ChatMessageProps {
  role: 'user' | 'assistant' | 'system'
  content: string
  cards?: ContentCardRef[]
  content_blocks?: ContentBlock[]
  createdAt?: string
  isStreaming?: boolean
}

// --- 占位标记解析 ---
interface ContentSegment {
  type: 'text' | 'card'
  value: string  // text content or card id
}

const CARD_MARKER_RE = /\{\{card:([^}]+)\}\}/g

function parseContentSegments(content: string): ContentSegment[] {
  const segments: ContentSegment[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = CARD_MARKER_RE.exec(content)) !== null) {
    // Text before marker
    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: content.slice(lastIndex, match.index) })
    }
    // Card marker
    segments.push({ type: 'card', value: match[1] })
    lastIndex = match.index + match[0].length
  }

  // Remaining text
  if (lastIndex < content.length) {
    segments.push({ type: 'text', value: content.slice(lastIndex) })
  }

  // If no markers found, return entire content as single text segment
  if (segments.length === 0) {
    segments.push({ type: 'text', value: content })
  }

  return segments
}

function findCardById(cards: ContentCardRef[] | undefined, id: string): ContentCardRef | undefined {
  if (!cards) return undefined
  return cards.find(c => c.id === id)
}

// --- 组件 ---
const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, cards, content_blocks, createdAt, isStreaming }) => {
  const contentRef = useRef<HTMLDivElement>(null)

  const isUser = useMemo(() => role === 'user', [role])
  const isSystem = useMemo(() => role === 'system', [role])
  const isAssistant = useMemo(() => role === 'assistant', [role])

  // Parse content into segments (text + card placeholders) - 旧格式回退
  const segments = useMemo(() => {
    if (!isAssistant || !content) return []
    return parseContentSegments(content)
  }, [isAssistant, content])

  // Cards map for quick lookup
  const cardsMap = useMemo(() => {
    if (!cards) return new Map<string, ContentCardRef>()
    return new Map(cards.map(c => [c.id, c]))
  }, [cards])

  // Cards referenced by markers in content
  const referencedCardIds = useMemo(() => {
    return new Set(segments.filter(s => s.type === 'card').map(s => s.value))
  }, [segments])

  // Unreferenced cards (not mentioned in content, append at end)
  const unreferencedCards = useMemo(() => {
    if (!cards) return []
    return cards.filter(c => !referencedCardIds.has(c.id))
  }, [cards, referencedCardIds])

  const timeStr = useMemo(() => {
    if (!createdAt) return ''
    const d = new Date(createdAt)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })
  }, [createdAt])

  // Code highlight
  useEffect(() => {
    if (contentRef.current && isAssistant) {
      highlightCodeBlocks(contentRef.current)
    }
  }, [isAssistant, content])

  // --- User message ---
  if (isUser) {
    return (
      <div className="msg-enter" style={{ display: 'flex', justifyContent: 'flex-end', paddingLeft: 48, paddingRight: 0 }}>
        <div style={{ maxWidth: 800, display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
          <p style={{ fontSize: 15, color: '#111827', whiteSpace: 'pre-wrap', lineHeight: 1.7, margin: 0 }}>{content}</p>
          {timeStr && <span style={{ fontSize: 12, color: '#9ca3af', marginTop: 8 }}>{timeStr}</span>}
        </div>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', background: '#10b981',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0, marginLeft: 12,
        }}>
          <span style={{ color: '#ffffff', fontSize: 13, fontWeight: 600 }}>我</span>
        </div>
      </div>
    )
  }

  // --- System message ---
  if (isSystem) {
    return (
      <div className="msg-enter" style={{ display: 'flex', justifyContent: 'center' }}>
        <span style={{ fontSize: 12, color: '#9ca3af', background: '#f3f4f6', padding: '4px 12px', borderRadius: 6 }}>
          {content}
        </span>
      </div>
    )
  }

  // --- Assistant message with inline card support ---
  const hasMarkers = segments.some(s => s.type === 'card')
  const hasContentBlocks = content_blocks && content_blocks.length > 0

  return (
    <div className="msg-enter" style={{ display: 'flex', paddingLeft: 0, paddingRight: 48 }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%', background: '#f3f4f6',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, marginRight: 12,
      }}>
        <Bot style={{ width: 16, height: 16, color: '#6b7280' }} />
      </div>
      <div style={{ maxWidth: 800, flex: 1, minWidth: 0 }}>
        {hasContentBlocks ? (
          // 新架构：从 content_blocks 渲染
          <div>
            {content_blocks!.map((block, i) => {
              if (block.type === 'text') {
                return (
                  <div
                    key={`block-${i}`}
                    ref={i === 0 ? contentRef : undefined}
                    className="md-content"
                    style={{ color: '#374151', lineHeight: 1.7 }}
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
                return (
                  <div key={`block-${i}`} style={{ marginTop: 12 }}>
                    <ContentCardRenderer card={cardRef} />
                  </div>
                )
              }
              if (block.type === 'thinking') {
                return (
                  <div key={`block-${i}`} style={{
                    color: '#7c3aed', fontSize: 13, fontStyle: 'italic',
                    padding: '8px 12px', background: '#f5f3ff',
                    borderRadius: 8, marginTop: 8,
                  }}>
                    {block.text}
                  </div>
                )
              }
              return null
            })}
          </div>
        ) : hasMarkers ? (
          // 旧格式：inline card rendering with markers
          <div>
            {segments.map((seg, i) => {
              if (seg.type === 'card') {
                const card = cardsMap.get(seg.value)
                if (!card) return null
                return (
                  <div key={`card-${seg.value}`} style={{ marginTop: 12 }}>
                    <ContentCardRenderer card={card} />
                  </div>
                )
              }
              return (
                <div
                  key={`text-${i}`}
                  ref={i === 0 ? contentRef : undefined}
                  className="md-content"
                  style={{ color: '#374151', lineHeight: 1.7 }}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(seg.value) }}
                />
              )
            })}
          </div>
        ) : (
          // 旧格式：无 markers
          <div>
            <div
              ref={contentRef}
              className="md-content"
              style={{ color: '#374151', lineHeight: 1.7 }}
              dangerouslySetInnerHTML={{ __html: renderMarkdown(content) }}
            />
            {cards && cards.length > 0 && (
              <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {cards.map(card => (
                  <ContentCardRenderer key={card.id} card={card} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* Unreferenced cards (appended at end) - 旧格式 */}
        {unreferencedCards.length > 0 && hasMarkers && !hasContentBlocks && (
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {unreferencedCards.map(card => (
              <ContentCardRenderer key={card.id} card={card} />
            ))}
          </div>
        )}

        {/* Skeleton while streaming */}
        {isStreaming && (!cards || cards.length === 0) && (!content_blocks || content_blocks.length === 0) && content.length > 50 && (
          <div style={{ marginTop: 12 }}>
            <SkeletonCard />
          </div>
        )}

        {timeStr && (
          <span style={{ fontSize: 12, color: '#9ca3af', marginTop: 8, display: 'inline-block' }}>
            {timeStr}
          </span>
        )}
      </div>
    </div>
  )
}

export default ChatMessage
