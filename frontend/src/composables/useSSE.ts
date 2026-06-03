import { useState, useCallback } from 'react'
import { chatStream, deepChatStream, socraticChatStream } from '../api/chat'
import { useChatStore, ContentCardRef, ContentBlock, CardBlock } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { INTENT_MAP } from '../utils/constants'

function tryParseJSON(str: string): any {
  try { return JSON.parse(str) } catch { return str }
}

export function useSSE() {
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (message: string, mode: 'fast' | 'deep' | 'socratic' = 'fast') => {
    setError(null)
    const store = useChatStore.getState()
    const conversationId = store.currentConversationId

    // Clear thinking steps for new message
    store.clearThinkingSteps()

    // Add user message
    store.addMessage('user', message)

    // Prepare streaming
    store.setStreaming(true)
    const controller = new AbortController()
    store.setAbortController(controller)

    // Add empty assistant message for streaming
    store.addMessage('assistant', '')

    try {
      let response: Response

      if (mode === 'socratic') {
        const threadId = store.socraticThreadId
        const action: 'start' | 'answer' = threadId ? 'answer' : 'start'
        response = await socraticChatStream(message, conversationId, action, threadId, controller.signal)
      } else {
        response = mode === 'deep'
          ? await deepChatStream(message, conversationId, controller.signal)
          : await chatStream(message, conversationId, controller.signal)
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullReply = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.trim()) continue

          const lines = part.split('\n')
          let eventType = ''
          let dataStr = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              dataStr += (dataStr ? '\n' : '') + line.slice(6)
            }
          }

          if (!dataStr) continue

          try {
            const data = JSON.parse(dataStr)

            switch (eventType || data.event) {
              // --- 旧格式资源事件（向后兼容） ---
              case 'quiz':
              case 'code':
              case 'doc':
              case 'mindmap':
              case 'video': {
                const rawData = data.data || {}
                const card: ContentCardRef = {
                  id: rawData.id?.toString() || crypto.randomUUID(),
                  type: eventType as ContentCardRef['type'],
                  title: rawData.title || '学习资源',
                  data: rawData.content ? tryParseJSON(rawData.content) : rawData,
                  collapsed: false,
                }
                useChatStore.getState().appendCardToLastAssistant(card)
                break
              }

              // --- Content Block 事件（新架构） ---
              case 'content_block_start': {
                const d = data.data || {}
                const blockId = d.block_id
                const store = useChatStore.getState()
                store.ensureAssistantMessage()
                if (d.block_type === 'card') {
                  // card block 在 start 时不创建，等 data 带完整数据
                  // 但需要记录 blockId 用于后续匹配
                } else if (d.block_type === 'text') {
                  store.startContentBlock({ type: 'text', text: '', _blockId: blockId })
                } else if (d.block_type === 'thinking') {
                  store.startContentBlock({ type: 'thinking', text: '', _blockId: blockId })
                }
                break
              }

              case 'content_block_data': {
                const d = data.data || {}
                const delta = d.delta || ''
                const store = useChatStore.getState()
                const lastMsg = store.messages[store.messages.length - 1]

                // 检查是否是 card block 的 delta（JSON 数据）
                if (delta.startsWith('{') && delta.includes('"type":"card"')) {
                  try {
                    const parsed = JSON.parse(delta)
                    if (parsed.type === 'card') {
                      const cardBlock: CardBlock = {
                        type: 'card',
                        card_type: parsed.card_type,
                        card_id: parsed.card_id,
                        title: parsed.title || '',
                        data: parsed.data,
                      }
                      store.startContentBlock(cardBlock)
                      break
                    }
                  } catch { /* not a card block, treat as text delta */ }
                }

                // text/thinking block delta
                store.appendBlockDelta(d.block_id, delta)
                // 同时更新 content 字段（兼容旧逻辑）
                fullReply += delta
                break
              }

              case 'content_block_stop': {
                useChatStore.getState().finishContentBlock(data.data?.block_id)
                break
              }

              // --- 旧格式 token 事件（向后兼容） ---
              case 'token': {
                fullReply += data.data || ''
                const state = useChatStore.getState()
                const msgs = [...state.messages]
                const last = msgs[msgs.length - 1]
                if (last && last.role === 'assistant') {
                  msgs[msgs.length - 1] = { ...last, content: fullReply }
                  useChatStore.setState({ messages: msgs })
                }
                break
              }

              case 'tutor': {
                const replyText = typeof data.data === 'string' ? data.data : data.data?.reply || ''
                if (!fullReply && replyText) {
                  fullReply = replyText
                  const state = useChatStore.getState()
                  const msgs = [...state.messages]
                  const last = msgs[msgs.length - 1]
                  if (last && last.role === 'assistant') {
                    msgs[msgs.length - 1] = { ...last, content: fullReply }
                    useChatStore.setState({ messages: msgs })
                  }
                }
                break
              }

              case 'intent': {
                const intentValue = typeof data.data === 'string' ? data.data : data.data?.user_intent || ''
                useChatStore.setState({ currentIntent: INTENT_MAP[intentValue] || intentValue || '' })
                break
              }

              case 'path':
                useChatStore.setState({ lastLearningPath: data.data })
                break

              case 'profile':
                // Profile updated silently
                break

              case 'thinking': {
                const thinkingText = typeof data.data === 'string' ? data.data : data.data?.text || ''
                if (thinkingText) {
                  useChatStore.getState().addThinkingStep(thinkingText)
                }
                break
              }

              case 'clear':
                // 标记思考完成，延迟清除（让前端展示完成状态）
                useChatStore.getState().setThinkingCompleted(true)
                setTimeout(() => {
                  useChatStore.getState().clearThinkingSteps()
                }, 2000)
                break

              case 'socratic_question':
              case 'socratic_hint':
              case 'socratic_feedback':
              case 'socratic_answer':
              case 'socratic_summary':
              case 'socratic_explain':
              case 'socratic_demo':
              case 'socratic_practice':
              case 'socratic_relate': {
                const socraticData = data.data || {}
                const content = socraticData.content || ''
                if (content) {
                  fullReply += content
                  const state = useChatStore.getState()
                  const msgs = [...state.messages]
                  const last = msgs[msgs.length - 1]
                  if (last && last.role === 'assistant') {
                    msgs[msgs.length - 1] = { ...last, content: fullReply }
                    useChatStore.setState({ messages: msgs })
                  }
                }
                // 保存 thread_id
                if (socraticData.thread_id) {
                  useChatStore.getState().setSocraticThreadId(socraticData.thread_id)
                }
                break
              }

              case 'mastery_update': {
                const masteryPayload = data.data || {}
                useChatStore.getState().setMasteryData({
                  mastery_level: masteryPayload.mastery_level || {},
                  changes: masteryPayload.changes || {},
                  current_stage: masteryPayload.current_stage || '',
                })
                // 通知 ProfileView 刷新学习画像
                window.dispatchEvent(new CustomEvent('learning-profile-dirty'))
                break
              }

              case 'socratic_end': {
                const endData = data.data || {}
                if (endData.conversation_id) {
                  useChatStore.setState({ currentConversationId: endData.conversation_id })
                }
                // 苏格拉底对话结束，通知刷新画像
                window.dispatchEvent(new CustomEvent('learning-profile-dirty'))
                break
              }

              case 'end': {
                const endData = data.data || {}
                if (endData.conversation_id) {
                  useChatStore.setState({ currentConversationId: endData.conversation_id })
                }
                // 如果 end 事件带了 content_blocks，用它覆盖（最终权威数据）
                if (endData.content_blocks && endData.content_blocks.length > 0) {
                  useChatStore.getState().setContentBlocks(endData.content_blocks)
                }
                useAppStore.getState().showToast('正在分析你的学习状态...', 'info')
                break
              }

              case 'error': {
                const errData = data.data || {}
                throw new Error(typeof errData === 'string' ? errData : errData.error || errData.detail || '服务端错误')
              }
            }
          } catch (e: unknown) {
            if (e instanceof Error && !e.message.includes('JSON')) {
              throw e
            }
          }
        }
      }

      // Final update
      const state = useChatStore.getState()
      const finalMsg = state.messages[state.messages.length - 1]
      if (finalMsg && finalMsg.role === 'assistant' && fullReply) {
        const msgs = [...state.messages]
        msgs[msgs.length - 1] = { ...finalMsg, content: fullReply }
        useChatStore.setState({ messages: msgs })
      }

      // Reload conversations
      await useChatStore.getState().loadConversations()

    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        useChatStore.getState().addMessage('system', '已停止生成')
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        useChatStore.getState().addMessage('system', `错误：${msg}`)
      }
    } finally {
      useChatStore.getState().setStreaming(false)
      useChatStore.getState().setAbortController(null)
    }
  }, [])

  const sendSocraticAction = useCallback(async (action: 'hint' | 'give_up' | 'end' | 'confused') => {
    setError(null)
    const store = useChatStore.getState()
    const threadId = store.socraticThreadId
    const conversationId = store.currentConversationId

    if (!threadId) {
      setError('没有活跃的苏格拉底会话')
      return
    }

    store.setStreaming(true)
    const controller = new AbortController()
    store.setAbortController(controller)

    // 为 hint 和 confused 添加空的 assistant 消息用于流式输出
    if (action !== 'end') {
      store.addMessage('assistant', '')
    }

    try {
      const labels: Record<string, string> = {
        hint: '💡 请求提示...',
        confused: '🤔 我没听懂，请换种方式讲解...',
        give_up: '📖 查看答案...',
        end: '结束学习',
      }
      const label = labels[action] || action
      if (action === 'end') {
        store.addMessage('system', label)
      }

      const response = await socraticChatStream(
        action === 'end' ? '结束学习' : label,
        conversationId,
        action,
        threadId,
        controller.signal,
      )

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullReply = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop() || ''

        for (const part of parts) {
          if (!part.trim()) continue

          const lines = part.split('\n')
          let eventType = ''
          let dataStr = ''

          for (const line of lines) {
            if (line.startsWith('event: ')) {
              eventType = line.slice(7).trim()
            } else if (line.startsWith('data: ')) {
              dataStr += (dataStr ? '\n' : '') + line.slice(6)
            }
          }

          if (!dataStr) continue

          try {
            const data = JSON.parse(dataStr)

            switch (eventType || data.event) {
              case 'socratic_question':
              case 'socratic_hint':
              case 'socratic_feedback':
              case 'socratic_answer':
              case 'socratic_summary':
              case 'socratic_explain':
              case 'socratic_demo':
              case 'socratic_practice':
              case 'socratic_relate': {
                const socraticData = data.data || {}
                const content = socraticData.content || ''
                if (content) {
                  fullReply += content
                  const state = useChatStore.getState()
                  const msgs = [...state.messages]
                  const last = msgs[msgs.length - 1]
                  if (last && last.role === 'assistant') {
                    msgs[msgs.length - 1] = { ...last, content: fullReply }
                    useChatStore.setState({ messages: msgs })
                  }
                }
                if (socraticData.thread_id) {
                  useChatStore.getState().setSocraticThreadId(socraticData.thread_id)
                }
                // 如果会话结束，清除 threadId
                if (socraticData.ended) {
                  useChatStore.getState().setSocraticThreadId(null)
                }
                break
              }

              case 'mastery_update': {
                const masteryPayload = data.data || {}
                useChatStore.getState().setMasteryData({
                  mastery_level: masteryPayload.mastery_level || {},
                  changes: masteryPayload.changes || {},
                  current_stage: masteryPayload.current_stage || '',
                })
                window.dispatchEvent(new CustomEvent('learning-profile-dirty'))
                break
              }

              case 'socratic_end': {
                const endData = data.data || {}
                if (endData.conversation_id) {
                  useChatStore.setState({ currentConversationId: endData.conversation_id })
                }
                window.dispatchEvent(new CustomEvent('learning-profile-dirty'))
                break
              }

              case 'error': {
                const errData = data.data || {}
                throw new Error(typeof errData === 'string' ? errData : errData.error || '服务端错误')
              }
            }
          } catch (e: unknown) {
            if (e instanceof Error && !e.message.includes('JSON')) {
              throw e
            }
          }
        }
      }

      await useChatStore.getState().loadConversations()

    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        useChatStore.getState().addMessage('system', '已停止')
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        useChatStore.getState().addMessage('system', `错误：${msg}`)
      }
    } finally {
      useChatStore.getState().setStreaming(false)
      useChatStore.getState().setAbortController(null)
    }
  }, [])

  return { sendMessage, sendSocraticAction, error }
}
