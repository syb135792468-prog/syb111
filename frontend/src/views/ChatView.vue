<script setup>
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useSSE } from '../composables/useSSE'
import { useScroll } from '../composables/useScroll'
import { clearChatHistory } from '../api/chat'
import AppHeader from '../components/layout/AppHeader.vue'
import ChatWelcome from '../components/chat/ChatWelcome.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatTyping from '../components/chat/ChatTyping.vue'
import ChatInput from '../components/chat/ChatInput.vue'
import { Trash2 } from 'lucide-vue-next'

const chatStore = useChatStore()
const appStore = useAppStore()
const { sendMessage } = useSSE()

const messagesContainer = ref(null)
const { scrollToBottom, onScroll, resetScrollState } = useScroll(messagesContainer)

const showTyping = ref(false)

function handleSend(text) {
  resetScrollState()
  showTyping.value = true
  sendMessage(text).finally(() => {
    showTyping.value = false
  })
}

function handleAbort() {
  chatStore.abort()
}

async function clearChat() {
  try {
    await clearChatHistory()
  } catch (e) {
    // ignore
  }
  chatStore.startNewChat()
  appStore.showToast('对话已清空', 'success')
}

// Auto-scroll when messages change
watch(
  () => chatStore.messages.length,
  () => {
    nextTick(() => scrollToBottom(true))
  }
)

// Auto-scroll during streaming
watch(
  () => {
    const last = chatStore.messages[chatStore.messages.length - 1]
    return last?.role === 'assistant' ? last.content : ''
  },
  () => {
    nextTick(() => scrollToBottom())
  }
)
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <!-- Header -->
    <AppHeader title="智能对话">
      <template #badge>
        <span
          v-if="chatStore.currentIntent"
          class="text-xs text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full"
        >
          {{ chatStore.currentIntent }}
        </span>
      </template>
      <template #actions>
        <button
          @click="clearChat"
          class="text-gray-400 hover:text-gray-600 p-2 rounded-lg hover:bg-gray-50 transition-colors"
          title="清空对话"
        >
          <Trash2 class="w-4 h-4" />
        </button>
      </template>
    </AppHeader>

    <!-- Messages -->
    <div
      ref="messagesContainer"
      @scroll="onScroll"
      class="flex-1 overflow-y-auto px-6 py-4"
    >
      <!-- Welcome -->
      <ChatWelcome
        v-if="chatStore.messages.length === 0"
        @send="handleSend"
      />

      <!-- Messages -->
      <div v-else class="max-w-3xl mx-auto space-y-4">
        <ChatMessage
          v-for="(msg, i) in chatStore.messages"
          :key="i"
          :role="msg.role"
          :content="msg.content"
        />
        <ChatTyping v-if="showTyping && !chatStore.messages.some(m => m.role === 'assistant' && m.content)" />
      </div>
    </div>

    <!-- Input -->
    <ChatInput
      :is-streaming="chatStore.isStreaming"
      @send="handleSend"
      @abort="handleAbort"
    />
  </div>
</template>
