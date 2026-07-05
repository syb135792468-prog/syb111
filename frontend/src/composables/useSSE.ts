import { useState, useCallback } from 'react'
import { chatStream, deepChatStream, socraticChatStream } from '../api/chat'
import { useChatStore, ContentCardRef, ContentBlock, CardBlock } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useTaskStore } from '../stores/taskStore'
import { INTENT_MAP } from '../utils/constants'

const TASK_POLL_INTERVAL = 3000
const TASK_POLL_MAX_RETRIES = 60  // 最多 3 分钟
const STREAM_READ_TIMEOUT_MS = 30000  // 30秒无数据则判定连接卡死

// 防止 sendMessage 并发执行的模块级锁
let _sendMessageInFlight = false

// 记录 content_block_start 标记为 card 类型的 blockId，供 content_block_data 查表
const cardBlockIds = new Set<string>()

// 带超时的 stream read，防止 reader.read() 永久阻塞
function readWithTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  timeoutMs: number,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  return Promise.race([
    reader.read(),
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new Error(`stream_read_timeout_${timeoutMs}ms`)), timeoutMs)
    ),
  ])
}

async function pollTaskStatus(taskId: string, streamConvId: number | string | null) {
  let retries = 0
  const poll = async () => {
    try {
      const res = await fetch(`/api/tasks/${taskId}`)
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      if (data.status === 'pending') {
        if (++retries > TASK_POLL_MAX_RETRIES) {
          useTaskStore.getState().updateTask(taskId, { status: 'failed', error: '轮询超时' })
          return
        }
        setTimeout(poll, TASK_POLL_INTERVAL)
      } else if (data.status === 'completed') {
        useTaskStore.getState().updateTask(taskId, { status: 'completed', data: data.data })
        // 守卫：对话已切换时不追加卡片（资源已入库，可在资源库查看）
        if (useChatStore.getState().currentConversationId !== streamConvId) {
          useAppStore.getState().showToast('资源已生成，可在资源库查看', 'info')
          return
        }
        // 将完成的资源插入聊天卡片
        const task = useTaskStore.getState().tasks.find(t => t.taskId === taskId)
        if (task && data.data) {
          for (const item of data.data) {
            const card: ContentCardRef = {
              id: item.db_id?.toString() || crypto.randomUUID(),
              type: task.resourceType as ContentCardRef['type'],
              title: item.title || task.topic,
              data: item.content ? tryParseJSON(item.content) : item,
              collapsed: false,
            }
            useChatStore.getState().appendCardToLastAssistant(card)
          }
        }
        useAppStore.getState().showToast('资源生成完成', 'success')
      } else {
        useTaskStore.getState().updateTask(taskId, { status: 'failed', error: data.error })
        useAppStore.getState().showToast('资源生成失败', 'error')
      }
    } catch {
      if (++retries > TASK_POLL_MAX_RETRIES) {
        useTaskStore.getState().updateTask(taskId, { status: 'failed', error: '网络错误' })
        return
      }
      setTimeout(poll, TASK_POLL_INTERVAL)
    }
  }
  poll()
}

function tryParseJSON(str: string): any {
  try { return JSON.parse(str) } catch { return str }
}

export function useSSE() {
  const [error, setError] = useState<string | null>(null)

  const sendMessage = useCallback(async (message: string, mode: 'fast' | 'deep' | 'socratic' = 'fast', images?: string[]) => {
    if (_sendMessageInFlight) { console.warn('[SSE] sendMessage already in flight, skipping'); return }
    _sendMessageInFlight = true
    setError(null)
    const store = useChatStore.getState()
    const conversationId = store.currentConversationId
    const streamConvId = conversationId  // 捕获当前对话 ID，后续用于守卫

    // 如果只有图片没有文字，使用默认提示词
    const effectiveMessage = message.trim() || (images && images.length > 0 ? '请分析这张图片' : message)

    // Clear thinking steps for new message
    store.clearThinkingSteps()

    // Add user message
    store.addMessage('user', message || (images && images.length > 0 ? '[图片]' : ''), images)

    // Prepare streaming
    store.setStreaming(true, streamConvId)
    const controller = new AbortController()
    store.setAbortController(controller)

    // Add empty assistant message for streaming
    store.addMessage('assistant', '')

    try {
      let response: Response

      if (mode === 'socratic') {
        const threadId = store.socraticThreadId
        const action: 'start' | 'answer' = threadId ? 'answer' : 'start'
        response = await socraticChatStream(effectiveMessage, conversationId, action, threadId, controller.signal, images)
      } else {
        response = mode === 'deep'
          ? await deepChatStream(effectiveMessage, conversationId, controller.signal, images)
          : await chatStream(effectiveMessage, conversationId, controller.signal, images)
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }
      const reader = response.body!.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let fullReply = ''

      while (true) {
        let readResult: ReadableStreamReadResult<Uint8Array>
        try {
          readResult = await readWithTimeout(reader, STREAM_READ_TIMEOUT_MS)
        } catch (readErr) {
          // 读取超时：连接可能已卡死，主动中止
          console.error('[SSE] Stream read timed out, aborting')
          controller.abort()
          useAppStore.getState().showToast('连接超时，请重试', 'error')
          break
        }
        const { done, value } = readResult
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

          // 守卫：对话已切换（新建/切换到其他对话），忽略旧流的数据
          const curConvId = useChatStore.getState().currentConversationId
          if (curConvId !== streamConvId) break

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
                  cardBlockIds.add(blockId)
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

                // card block 的 delta 是完整 JSON，由 start 事件的 block_type 标记
                if (cardBlockIds.has(d.block_id)) {
                  try {
                    const parsed = JSON.parse(delta)
                    const cardBlock: CardBlock = {
                      type: 'card',
                      card_type: parsed.card_type,
                      card_id: parsed.card_id,
                      title: parsed.title || '',
                      data: parsed.data,
                    }
                    store.startContentBlock(cardBlock)
                  } catch { /* card delta 解析失败，丢弃，不当 text 处理 */ }
                  break
                }

                // text/thinking block delta
                store.appendBlockDelta(d.block_id, delta)
                // 同时更新 content 字段（兼容旧逻辑）
                fullReply += delta
                break
              }

              case 'content_block_stop': {
                cardBlockIds.delete(data.data?.block_id)
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
                // 提前保存 conversation_id（后端在首个 thinking 事件中附带）
                if (data.data?.conversation_id) {
                  useChatStore.setState({ currentConversationId: data.data.conversation_id })
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
                  useChatStore.getState().appendToLastAssistant(content)
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

              case 'task_started': {
                const taskData = data.data || {}
                const { task_id, resource_type, topic } = taskData
                if (task_id) {
                  useTaskStore.getState().addTask({
                    taskId: task_id,
                    resourceType: resource_type || 'unknown',
                    topic: topic || '',
                    status: 'pending',
                    createdAt: Date.now(),
                  })
                  pollTaskStatus(task_id, streamConvId)
                }
                break
              }

              case 'end': {
                const endData = data.data || {}
                if (endData.conversation_id) {
                  // 守卫：仅在对话未切换时更新 conversationId
                  const s = useChatStore.getState()
                  if (s.currentConversationId === streamConvId) {
                    useChatStore.setState({ currentConversationId: endData.conversation_id })
                  }
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

      // Final update（仅在对话未切换时写入）
      const finalConvId = useChatStore.getState().currentConversationId
      if (finalConvId === streamConvId) {
        const state = useChatStore.getState()
        const finalMsg = state.messages[state.messages.length - 1]
        if (finalMsg && finalMsg.role === 'assistant' && fullReply) {
          const msgs = [...state.messages]
          msgs[msgs.length - 1] = { ...finalMsg, content: fullReply }
          useChatStore.setState({ messages: msgs })
        }
        await useChatStore.getState().loadConversations()
      }

    } catch (e: unknown) {
      if (e instanceof Error && e.name === 'AbortError') {
        if (useChatStore.getState().currentConversationId === streamConvId) {
          useChatStore.getState().addMessage('system', '已停止生成')
        }
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        if (useChatStore.getState().currentConversationId === streamConvId) {
          useChatStore.getState().addMessage('system', `错误：${msg}`)
        }
      }
    } finally {
      _sendMessageInFlight = false
      // 无条件清除流式状态，确保不会卡在"正在生成"
      useChatStore.getState().setStreaming(false)
      useChatStore.getState().setAbortController(null)
    }
  }, [])

  const sendSocraticAction = useCallback(async (action: 'hint' | 'give_up' | 'end' | 'confused') => {
    setError(null)
    const store = useChatStore.getState()
    const threadId = store.socraticThreadId
    const conversationId = store.currentConversationId
    const streamConvId = conversationId

    if (!threadId) {
      setError('没有活跃的苏格拉底会话')
      return
    }

    store.setStreaming(true, streamConvId)
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
        let readResult: ReadableStreamReadResult<Uint8Array>
        try {
          readResult = await readWithTimeout(reader, STREAM_READ_TIMEOUT_MS)
        } catch (readErr) {
          console.error('[SSE] Socratic stream read timed out, aborting')
          controller.abort()
          useAppStore.getState().showToast('连接超时，请重试', 'error')
          break
        }
        const { done, value } = readResult
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

          // 守卫：对话已切换，忽略旧流的数据
          const curConvId = useChatStore.getState().currentConversationId
          if (curConvId !== streamConvId) break

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
                  useChatStore.getState().appendToLastAssistant(content)
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
                  const s = useChatStore.getState()
                  if (s.currentConversationId === streamConvId) {
                    useChatStore.setState({ currentConversationId: endData.conversation_id })
                  }
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
        if (useChatStore.getState().currentConversationId === streamConvId) {
          useChatStore.getState().addMessage('system', '已停止')
        }
      } else {
        const msg = e instanceof Error ? e.message : String(e)
        setError(msg)
        if (useChatStore.getState().currentConversationId === streamConvId) {
          useChatStore.getState().addMessage('system', `错误：${msg}`)
        }
      }
    } finally {
      useChatStore.getState().setStreaming(false)
      useChatStore.getState().setAbortController(null)
    }
  }, [])

  return { sendMessage, sendSocraticAction, error }
}
