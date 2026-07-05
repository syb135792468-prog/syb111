import { create } from 'zustand'
import { listConversations, getConversation, deleteConversation as apiDeleteConv } from '../api/conversation'

export interface ContentCardRef {
  id: string
  type: 'quiz' | 'mindmap' | 'code' | 'video' | 'document' | 'slides'
  title: string
  data: any
  collapsed?: boolean
}

// --- Content Block 类型（统一内容块架构） ---
export interface TextBlock { type: 'text'; text: string }
export interface CodeBlock { type: 'code'; code: string; language: string; title?: string }
export interface ThinkingBlock { type: 'thinking'; text: string }
export interface CardBlock {
  type: 'card'
  card_type: string
  card_id: number
  title: string
  data?: any
}
export type ContentBlock = TextBlock | CodeBlock | ThinkingBlock | CardBlock

// 流式构建时带临时 blockId 的 block
export type StreamingContentBlock = ContentBlock & { _blockId?: string }

interface Message {
  id?: number
  role: 'user' | 'assistant' | 'system'
  content: string
  cards?: ContentCardRef[]
  content_blocks?: ContentBlock[]
  image_urls?: string[]
  is_bookmarked?: boolean
  created_at?: string
}

interface Conversation {
  id: number | string
  title?: string
  [key: string]: unknown
}

interface ConversationDetail {
  messages: Message[]
}

interface MasteryData {
  mastery_level: Record<string, number>
  changes: Record<string, { from: number; to: number }>
  current_stage: string
}

interface ChatState {
  messages: Message[]
  isStreaming: boolean
  isLoadingConversation: boolean
  currentConversationId: number | string | null
  conversations: Conversation[]
  currentIntent: string
  lastLearningPath: unknown
  thinkingSteps: string[]
  thinkingCompleted: boolean
  socraticThreadId: string | null
  masteryData: MasteryData | null
  streamingConversationId: number | string | null

  startNewChat: () => void
  addMessage: (role: 'user' | 'assistant' | 'system', content: string, imageUrls?: string[]) => void
  appendToLastAssistant: (text: string) => void
  setStreaming: (val: boolean, conversationId?: number | string | null) => void
  setAbortController: (controller: AbortController | null) => void
  abort: () => void
  loadConversations: () => Promise<void>
  switchConversation: (conversationId: number | string) => Promise<void>
  deleteConversation: (conversationId: number | string) => Promise<boolean>
  setCurrentIntent: (intent: string) => void
  setLastLearningPath: (path: unknown) => void
  addThinkingStep: (step: string) => void
  clearThinkingSteps: () => void
  setThinkingCompleted: (val: boolean) => void
  appendCardToLastAssistant: (card: ContentCardRef) => void
  toggleCardCollapse: (messageIndex: number, cardId: string) => void
  setSocraticThreadId: (threadId: string | null) => void
  restoreSocraticSession: () => boolean
  setMasteryData: (data: MasteryData | null) => void
  // Content Block actions
  ensureAssistantMessage: () => void
  startContentBlock: (block: StreamingContentBlock) => void
  appendBlockDelta: (blockId: string, delta: string) => void
  finishContentBlock: (blockId: string) => void
  setContentBlocks: (blocks: ContentBlock[]) => void
  updateMessageBookmark: (index: number, isBookmarked: boolean) => void
}

let abortController: AbortController | null = null
let socraticPersistTimer: ReturnType<typeof setTimeout> | null = null

function persistSocraticMessages(threadId: string, msgs: Message[]) {
  if (socraticPersistTimer) clearTimeout(socraticPersistTimer)
  socraticPersistTimer = setTimeout(() => {
    try {
      localStorage.setItem(`socratic_msgs_${threadId}`, JSON.stringify(msgs))
    } catch (e) {
      console.warn('Failed to persist socratic messages:', e)
    }
  }, 500)
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  isStreaming: false,
  isLoadingConversation: false,
  currentConversationId: null,
  conversations: [],
  currentIntent: '',
  lastLearningPath: null,
  thinkingSteps: [],
  thinkingCompleted: false,
  socraticThreadId: localStorage.getItem('socratic_thread_id') || null,
  masteryData: null,
  streamingConversationId: null,

  startNewChat: () => {
    if (get().isStreaming) {
      get().abort()
    }
    const oldThreadId = get().socraticThreadId
    if (oldThreadId) {
      localStorage.removeItem(`socratic_msgs_${oldThreadId}`)
      localStorage.removeItem('socratic_thread_id')
    }
    set({ messages: [], currentConversationId: null, currentIntent: '', lastLearningPath: null, thinkingSteps: [], thinkingCompleted: false, socraticThreadId: null, masteryData: null, streamingConversationId: null, isStreaming: false })
  },

  addMessage: (role, content, imageUrls) => {
    set((state) => {
      const newMsgs = [...state.messages, { role, content, image_urls: imageUrls, created_at: new Date().toISOString() }]
      if (state.socraticThreadId) {
        persistSocraticMessages(state.socraticThreadId, newMsgs)
      }
      return { messages: newMsgs }
    })
  },

  appendToLastAssistant: (text) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = { ...last, content: last.content + text }
      } else {
        msgs.push({ role: 'assistant' as const, content: text, created_at: new Date().toISOString() })
      }
      if (state.socraticThreadId) {
        persistSocraticMessages(state.socraticThreadId, msgs)
      }
      return { messages: msgs }
    })
  },

  setStreaming: (val, conversationId) => set(val
    ? { isStreaming: true, streamingConversationId: conversationId ?? null }
    : { isStreaming: false, streamingConversationId: null }
  ),

  setAbortController: (controller) => {
    abortController = controller
  },

  abort: () => {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  },

  loadConversations: async () => {
    try {
      const resp = await listConversations()
      if (resp.code === 200) {
        set({ conversations: (resp.data as Conversation[]) || [] })
      }
    } catch (e) {
      console.error('Failed to load conversations:', e)
    }
  },

  switchConversation: async (conversationId) => {
    if (get().isStreaming) {
      get().abort()
    }
    set({ isLoadingConversation: true, currentConversationId: conversationId, currentIntent: '', streamingConversationId: null })
    try {
      const resp = await getConversation(conversationId)
      if (resp.code === 200 && resp.data) {
        const data = resp.data as ConversationDetail
        if (data.messages) {
          set({ messages: data.messages })
        } else {
          set({ messages: [] })
        }
      } else {
        set({ messages: [] })
      }
    } catch (e) {
      console.error('Failed to load conversation:', e)
      set({ messages: [] })
    } finally {
      set({ isLoadingConversation: false })
    }
  },

  deleteConversation: async (conversationId) => {
    try {
      const resp = await apiDeleteConv(conversationId)
      if (resp.code === 200) {
        if (get().currentConversationId === conversationId) {
          get().startNewChat()
        }
        await get().loadConversations()
        return true
      }
    } catch (e) {
      console.error('Failed to delete conversation:', e)
    }
    return false
  },

  setCurrentIntent: (intent) => set({ currentIntent: intent }),
  setLastLearningPath: (path) => set({ lastLearningPath: path }),

  addThinkingStep: (step) => set((state) => ({ thinkingSteps: [...state.thinkingSteps, step] })),
  clearThinkingSteps: () => set({ thinkingSteps: [], thinkingCompleted: false }),
  setThinkingCompleted: (val) => set({ thinkingCompleted: val }),

  appendCardToLastAssistant: (card) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        msgs[msgs.length - 1] = {
          ...last,
          cards: [...(last.cards || []), card],
        }
        return { messages: msgs }
      }
      return state
    })
  },

  toggleCardCollapse: (messageIndex, cardId) => {
    set((state) => {
      const msgs = [...state.messages]
      const msg = msgs[messageIndex]
      if (!msg?.cards) return state
      msgs[messageIndex] = {
        ...msg,
        cards: msg.cards.map(c =>
          c.id === cardId ? { ...c, collapsed: !c.collapsed } : c
        ),
      }
      return { messages: msgs }
    })
  },

  setSocraticThreadId: (threadId) => {
    if (threadId) {
      localStorage.setItem('socratic_thread_id', threadId)
    } else {
      localStorage.removeItem('socratic_thread_id')
    }
    set({ socraticThreadId: threadId })
  },

  restoreSocraticSession: () => {
    const threadId = localStorage.getItem('socratic_thread_id')
    if (!threadId) return false
    try {
      const savedMsgs = localStorage.getItem(`socratic_msgs_${threadId}`)
      if (savedMsgs) {
        const msgs = JSON.parse(savedMsgs)
        if (Array.isArray(msgs) && msgs.length > 0) {
          set({ messages: msgs, socraticThreadId: threadId })
          return true
        }
      }
    } catch {}
    // thread_id 存在但没有消息，只恢复 threadId
    set({ socraticThreadId: threadId })
    return true
  },

  setMasteryData: (data) => set({ masteryData: data }),

  // --- Content Block actions ---

  ensureAssistantMessage: () => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (!last || last.role !== 'assistant') {
        msgs.push({ role: 'assistant' as const, content: '', content_blocks: [], created_at: new Date().toISOString() })
        return { messages: msgs }
      }
      if (!last.content_blocks) {
        msgs[msgs.length - 1] = { ...last, content_blocks: [] }
        return { messages: msgs }
      }
      return state
    })
  },

  startContentBlock: (block) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (!last || last.role !== 'assistant') {
        // 自动创建 assistant 消息
        const newMsg = {
          role: 'assistant' as const,
          content: '',
          content_blocks: [{ ...block } as ContentBlock],
          created_at: new Date().toISOString(),
        }
        return { messages: [...msgs, newMsg] }
      }
      const existingBlocks = [...(last.content_blocks || [])]
      // card blocks: 带完整数据直接添加
      if (block.type === 'card') {
        const { _blockId, ...cleanBlock } = block as StreamingContentBlock
        existingBlocks.push(cleanBlock as CardBlock)
      } else {
        // text/thinking blocks: 初始化为空，后续通过 delta 追加
        existingBlocks.push({ ...block, text: '' } as ContentBlock)
      }
      msgs[msgs.length - 1] = { ...last, content_blocks: existingBlocks }
      return { messages: msgs }
    })
  },

  appendBlockDelta: (blockId, delta) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (!last?.content_blocks) return state
      const blocks = [...last.content_blocks]
      for (let i = blocks.length - 1; i >= 0; i--) {
        const b = blocks[i] as any
        if ((b.type === 'text' || b.type === 'thinking') && b._blockId === blockId) {
          blocks[i] = { ...b, text: (b.text || '') + delta }
          msgs[msgs.length - 1] = { ...last, content_blocks: blocks }
          return { messages: msgs }
        }
      }
      return state
    })
  },

  finishContentBlock: (_blockId) => {
    // 清理临时 _blockId 字段
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (!last?.content_blocks) return state
      const blocks = last.content_blocks.map(b => {
        const { _blockId, ...rest } = b as any
        return rest
      })
      msgs[msgs.length - 1] = { ...last, content_blocks: blocks }
      return { messages: msgs }
    })
  },

  setContentBlocks: (blocks) => {
    set((state) => {
      const msgs = [...state.messages]
      const last = msgs[msgs.length - 1]
      if (last && last.role === 'assistant') {
        // 清理临时 _blockId
        const cleanBlocks = blocks.map(b => {
          const { _blockId, ...rest } = b as any
          return rest
        })
        msgs[msgs.length - 1] = { ...last, content_blocks: cleanBlocks }
        return { messages: msgs }
      }
      return state
    })
  },

  updateMessageBookmark: (index, isBookmarked) => {
    set((state) => {
      const msgs = [...state.messages]
      if (msgs[index]) {
        msgs[index] = { ...msgs[index], is_bookmarked: isBookmarked }
        return { messages: msgs }
      }
      return state
    })
  },
}))
