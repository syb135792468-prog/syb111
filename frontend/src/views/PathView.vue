<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '../stores/chat'
import AppHeader from '../components/layout/AppHeader.vue'
import PathTimeline from '../components/path/PathTimeline.vue'
import { Route, MessageCircle } from 'lucide-vue-next'

const router = useRouter()
const chatStore = useChatStore()

const pathSteps = computed(() => {
  const path = chatStore.lastLearningPath
  if (!path) return []
  if (Array.isArray(path)) return path
  if (path.learning_path) return path.learning_path
  return []
})

function requestPath() {
  chatStore.startNewChat()
  router.push('/chat')
  // The user can send the message from chat
}
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <AppHeader title="学习路径">
      <template #actions>
        <button
          @click="requestPath"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Route class="w-4 h-4" />
          重新规划
        </button>
      </template>
    </AppHeader>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <!-- Empty state -->
      <div v-if="pathSteps.length === 0" class="flex flex-col items-center justify-center h-64 text-gray-400">
        <Route class="w-12 h-12 mb-3 opacity-40" />
        <p class="text-sm font-medium mb-1">暂无学习路径</p>
        <p class="text-xs text-gray-400 mb-4">在对话中让 AI 为你规划个性化学习路径</p>
        <button
          @click="requestPath"
          class="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          <MessageCircle class="w-4 h-4" />
          去对话中规划
        </button>
      </div>

      <!-- Timeline -->
      <div v-else class="max-w-2xl mx-auto">
        <div class="mb-6">
          <h3 class="text-lg font-semibold text-gray-800">你的个性化学习路径</h3>
          <p class="text-sm text-gray-500 mt-1">共 {{ pathSteps.length }} 个知识点，按推荐顺序学习</p>
        </div>
        <PathTimeline :steps="pathSteps" />
      </div>
    </div>
  </div>
</template>
