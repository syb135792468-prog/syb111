<script setup>
import { computed, onMounted, ref, nextTick } from 'vue'
import { Bot } from 'lucide-vue-next'
import { renderMarkdown, highlightCodeBlocks } from '../../utils/markdown'

const props = defineProps({
  role: { type: String, required: true },
  content: { type: String, default: '' },
})

const contentRef = ref(null)

const isUser = computed(() => props.role === 'user')
const isSystem = computed(() => props.role === 'system')
const isAssistant = computed(() => props.role === 'assistant')

const renderedContent = computed(() => {
  if (isUser.value || isSystem.value) return ''
  return renderMarkdown(props.content)
})

onMounted(() => {
  if (contentRef.value && isAssistant.value) {
    nextTick(() => highlightCodeBlocks(contentRef.value))
  }
})

// Watch for content changes and re-highlight
import { watch } from 'vue'
watch(() => props.content, () => {
  if (contentRef.value && isAssistant.value) {
    nextTick(() => highlightCodeBlocks(contentRef.value))
  }
})
</script>

<template>
  <!-- User message -->
  <div v-if="isUser" class="flex justify-end msg-enter">
    <div class="max-w-[70%] px-4 py-2.5 bg-gradient-to-r from-brand-600 to-brand-700 text-white rounded-2xl rounded-br-md">
      <p class="text-sm whitespace-pre-wrap">{{ content }}</p>
    </div>
  </div>

  <!-- System message -->
  <div v-else-if="isSystem" class="flex justify-center msg-enter">
    <span class="text-xs text-gray-400 bg-gray-100 px-3 py-1 rounded-full">{{ content }}</span>
  </div>

  <!-- Assistant message -->
  <div v-else class="flex gap-3 msg-enter">
    <div class="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0 mt-1">
      <Bot class="w-4 h-4 text-brand-600" />
    </div>
    <div class="max-w-[75%] px-4 py-3 bg-gray-50 rounded-2xl rounded-bl-md">
      <div ref="contentRef" class="md-content text-sm" v-html="renderedContent"></div>
    </div>
  </div>
</template>
