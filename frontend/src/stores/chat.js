import { defineStore } from 'pinia'
import { ref } from 'vue'
import { listConversations, getConversation, deleteConversation as apiDeleteConv } from '../api/conversation'
import { useAuthStore } from './auth'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const currentConversationId = ref(null)
  const conversations = ref([])
  const currentIntent = ref('')
  const lastLearningPath = ref(null)
  let abortController = null

  function startNewChat() {
    messages.value = []
    currentConversationId.value = null
    currentIntent.value = ''
    lastLearningPath.value = null
  }

  function addMessage(role, content) {
    messages.value.push({ role, content, created_at: new Date().toISOString() })
  }

  function appendToLastAssistant(text) {
    const last = messages.value[messages.value.length - 1]
    if (last && last.role === 'assistant') {
      last.content += text
    } else {
      messages.value.push({ role: 'assistant', content: text, created_at: new Date().toISOString() })
    }
  }

  function setStreaming(val) {
    isStreaming.value = val
  }

  function setAbortController(controller) {
    abortController = controller
  }

  function abort() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
  }

  async function loadConversations() {
    try {
      const resp = await listConversations()
      if (resp.code === 200) {
        conversations.value = resp.data || []
      }
    } catch (e) {
      console.error('Failed to load conversations:', e)
    }
  }

  async function switchConversation(conversationId) {
    if (isStreaming.value) return
    currentConversationId.value = conversationId
    messages.value = []
    currentIntent.value = ''

    try {
      const resp = await getConversation(conversationId)
      if (resp.code === 200 && resp.data.messages) {
        messages.value = resp.data.messages
      }
    } catch (e) {
      console.error('Failed to load conversation:', e)
    }
  }

  async function deleteConversation(conversationId) {
    try {
      const resp = await apiDeleteConv(conversationId)
      if (resp.code === 200) {
        if (currentConversationId.value === conversationId) {
          startNewChat()
        }
        await loadConversations()
        return true
      }
    } catch (e) {
      console.error('Failed to delete conversation:', e)
    }
    return false
  }

  return {
    messages, isStreaming, currentConversationId, conversations,
    currentIntent, lastLearningPath,
    startNewChat, addMessage, appendToLastAssistant,
    setStreaming, setAbortController, abort,
    loadConversations, switchConversation, deleteConversation,
  }
})
