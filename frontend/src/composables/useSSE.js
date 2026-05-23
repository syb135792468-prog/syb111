import { ref } from 'vue'
import { chatStream } from '../api/chat'
import { useChatStore } from '../stores/chat'
import { INTENT_MAP } from '../utils/constants'

export function useSSE() {
  const chatStore = useChatStore()
  const error = ref(null)

  async function sendMessage(message) {
    error.value = null
    const conversationId = chatStore.currentConversationId

    // Add user message
    chatStore.addMessage('user', message)

    // Prepare streaming
    chatStore.setStreaming(true)
    const controller = new AbortController()
    chatStore.setAbortController(controller)

    // Add empty assistant message for streaming
    chatStore.addMessage('assistant', '')

    try {
      const response = await chatStream(message, conversationId, controller.signal)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body.getReader()
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
              dataStr = line.slice(6)
            }
          }

          if (!dataStr) continue

          try {
            const data = JSON.parse(dataStr)

            switch (eventType || data.event) {
              case 'token': {
                fullReply += data.data || ''
                const tMsg = chatStore.messages[chatStore.messages.length - 1]
                if (tMsg && tMsg.role === 'assistant') {
                  tMsg.content = fullReply
                }
                break
              }

              case 'tutor': {
                if (!fullReply && data.data) {
                  fullReply = data.data
                  const uMsg = chatStore.messages[chatStore.messages.length - 1]
                  if (uMsg && uMsg.role === 'assistant') {
                    uMsg.content = fullReply
                  }
                }
                break
              }

              case 'intent':
                chatStore.currentIntent = INTENT_MAP[data.data] || data.data || ''
                break

              case 'path':
                chatStore.lastLearningPath = data.data
                break

              case 'profile':
                // Profile updated silently
                break

              case 'end': {
                const endData = data.data || {}
                if (endData.conversation_id) {
                  chatStore.currentConversationId = endData.conversation_id
                }
                break
              }

              case 'error': {
                const errData = data.data || {}
                throw new Error(typeof errData === 'string' ? errData : errData.error || errData.detail || '服务端错误')
              }
            }
          } catch (e) {
            if (e.message && !e.message.includes('JSON')) {
              throw e
            }
          }
        }
      }

      // Final update
      const finalMsg = chatStore.messages[chatStore.messages.length - 1]
      if (finalMsg && finalMsg.role === 'assistant' && fullReply) {
        finalMsg.content = fullReply
      }

      // Reload conversations
      await chatStore.loadConversations()

    } catch (e) {
      if (e.name === 'AbortError') {
        chatStore.addMessage('system', '已停止生成')
      } else {
        error.value = e.message
        chatStore.addMessage('system', `错误：${e.message}`)
      }
    } finally {
      chatStore.setStreaming(false)
      chatStore.setAbortController(null)
    }
  }

  return { sendMessage, error }
}
