<script setup>
import { ref, nextTick } from 'vue'
import { Send, Square } from 'lucide-vue-next'

const props = defineProps({
  isStreaming: { type: Boolean, default: false },
})

const emit = defineEmits(['send', 'abort'])

const message = ref('')
const textareaRef = ref(null)

function handleSend() {
  const text = message.value.trim()
  if (!text || props.isStreaming) return
  emit('send', text)
  message.value = ''
  nextTick(() => adjustHeight())
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function adjustHeight() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 128) + 'px'
}
</script>

<template>
  <div class="px-6 py-4 border-t border-gray-100">
    <form @submit.prevent="handleSend" class="flex items-end gap-3">
      <textarea
        ref="textareaRef"
        v-model="message"
        @keydown="handleKeydown"
        @input="adjustHeight"
        placeholder="输入你的问题... (Shift+Enter 换行)"
        rows="1"
        class="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent overflow-y-auto"
        style="max-height: 128px"
      />
      <button
        v-if="isStreaming"
        @click="emit('abort')"
        type="button"
        class="p-2.5 bg-red-500 text-white rounded-xl hover:bg-red-600 transition-colors"
      >
        <Square class="w-5 h-5" />
      </button>
      <button
        v-else
        type="submit"
        :disabled="!message.trim()"
        class="p-2.5 bg-brand-600 text-white rounded-xl hover:bg-brand-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Send class="w-5 h-5" />
      </button>
    </form>
    <p class="text-xs text-gray-400 mt-2 text-center">
      按 Enter 发送，Shift+Enter 换行。系统会自动识别你的学习意图并调用对应的智能体。
    </p>
  </div>
</template>
