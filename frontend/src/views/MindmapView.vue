<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { generateResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader.vue'
import MindmapViewer from '../components/mindmap/MindmapViewer.vue'
import { Search, GitBranch, FileText, Zap } from 'lucide-vue-next'

const STORAGE_KEY = 'mindmap_cache'

const authStore = useAuthStore()
const appStore = useAppStore()

const topic = ref('')
const content = ref('')
const loading = ref(false)
const lastTitle = ref('')

// Restore from localStorage on mount
onMounted(() => {
  try {
    const cached = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (cached && cached.content) {
      content.value = cached.content
      lastTitle.value = cached.lastTitle || ''
      topic.value = cached.topic || ''
    }
  } catch {}
})

const presets = [
  { label: '变量与数据类型', icon: '📦' },
  { label: '控制流', icon: '🔀' },
  { label: '函数', icon: '⚡' },
  { label: '面向对象', icon: '🏗️' },
  { label: '文件操作', icon: '📁' },
  { label: '异常处理', icon: '🛡️' },
]

async function generate(t) {
  const target = t || topic.value.trim()
  if (!target) {
    appStore.showToast('请输入知识点主题', 'warning')
    return
  }
  if (!authStore.userId) {
    authStore.showAuthModal = true
    appStore.showToast('请先登录', 'warning')
    return
  }
  topic.value = target
  loading.value = true
  content.value = ''
  lastTitle.value = ''
  // 清除旧缓存
  try { localStorage.removeItem(STORAGE_KEY) } catch {}
  try {
    const resp = await generateResource(authStore.userId, target, 'mindmap')
    if (resp.code === 200) {
      content.value = resp.data.content || ''
      lastTitle.value = resp.data.title || target
      // Persist to localStorage so it survives view switches
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify({
          content: content.value,
          lastTitle: lastTitle.value,
          topic: topic.value,
        }))
      } catch {}
      appStore.showToast('思维导图生成成功', 'success')
    } else {
      appStore.showToast(resp.message || '生成失败', 'error')
    }
  } catch (e) {
    appStore.showToast('生成失败：' + e.message, 'error')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <AppHeader title="思维导图">
      <template #actions>
        <div class="flex items-center gap-2">
          <div class="relative">
            <input
              v-model="topic"
              type="text"
              placeholder="输入知识点名称..."
              @keydown.enter="generate()"
              class="w-64 px-3 py-1.5 pr-9 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent bg-white"
            />
            <Search class="absolute right-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          </div>
          <button
            @click="generate()"
            :disabled="loading || !topic.trim()"
            class="flex items-center gap-1.5 px-4 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
          >
            <GitBranch class="w-4 h-4" />
            {{ loading ? '生成中...' : '生成导图' }}
          </button>
        </div>
      </template>
    </AppHeader>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <div class="max-w-5xl mx-auto">
        <!-- Preset buttons (shown when no content) -->
        <div v-if="!content && !loading" class="mb-6">
          <p class="text-sm text-gray-500 mb-3">快速选择知识点：</p>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="p in presets"
              :key="p.label"
              @click="generate(p.label)"
              class="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 rounded-full text-sm text-gray-700 hover:border-brand-400 hover:text-brand-600 hover:bg-brand-50 transition-all shadow-sm"
            >
              <span>{{ p.icon }}</span>
              <span>{{ p.label }}</span>
            </button>
          </div>
        </div>

        <!-- Title bar (shown when content exists) -->
        <div v-if="lastTitle && !loading" class="mb-4 flex items-center justify-between">
          <div class="flex items-center gap-2">
            <GitBranch class="w-5 h-5 text-brand-600" />
            <h2 class="text-lg font-semibold text-gray-800">{{ lastTitle }}</h2>
          </div>
          <button
            @click="generate()"
            :disabled="loading"
            class="text-sm text-gray-400 hover:text-gray-600 transition-colors disabled:opacity-50"
          >
            重新生成
          </button>
        </div>

        <!-- Mindmap viewer -->
        <div style="height: 600px;">
          <MindmapViewer :content="content" :loading="loading" />
        </div>
      </div>
    </div>
  </div>
</template>
