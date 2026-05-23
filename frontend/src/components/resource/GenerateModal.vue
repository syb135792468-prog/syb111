<script setup>
import { ref } from 'vue'
import { X, PenTool, Code, GitBranch, FileText, Video } from 'lucide-vue-next'

const props = defineProps({
  show: { type: Boolean, default: false },
})

const emit = defineEmits(['close', 'generate'])

const topic = ref('')
const selectedType = ref('quiz')
const loading = ref(false)

const types = [
  { value: 'quiz', label: '练习题', icon: PenTool },
  { value: 'code', label: '代码案例', icon: Code },
  { value: 'mindmap', label: '思维导图', icon: GitBranch },
  { value: 'doc', label: '讲解文档', icon: FileText },
  { value: 'video', label: '教学动画', icon: Video },
]

async function handleGenerate() {
  if (!topic.value.trim()) return
  loading.value = true
  emit('generate', { topic: topic.value.trim(), type: selectedType.value })
}
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" @click.self="emit('close')">
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4">
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 class="text-base font-semibold text-gray-800">生成学习资源</h3>
          <button @click="emit('close')" class="text-gray-400 hover:text-gray-600 p-1">
            <X class="w-5 h-5" />
          </button>
        </div>

        <div class="px-6 py-5 space-y-4">
          <div>
            <label class="block text-xs text-gray-500 mb-1">知识点主题</label>
            <input
              v-model="topic"
              type="text"
              placeholder="例如：循环、函数、列表"
              class="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>

          <div>
            <label class="block text-xs text-gray-500 mb-2">资源类型</label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="t in types"
                :key="t.value"
                @click="selectedType = t.value"
                :class="[
                  'flex flex-col items-center gap-1.5 px-3 py-3 rounded-lg border text-sm transition-colors',
                  selectedType === t.value
                    ? 'border-brand-500 bg-brand-50 text-brand-700'
                    : 'border-gray-200 text-gray-500 hover:border-gray-300',
                ]"
              >
                <component :is="t.icon" class="w-5 h-5" />
                <span class="text-xs">{{ t.label }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="flex justify-end gap-3 px-6 py-4 border-t border-gray-100">
          <button
            @click="emit('close')"
            class="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
          >
            取消
          </button>
          <button
            @click="handleGenerate"
            :disabled="!topic.trim() || loading"
            class="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50"
          >
            {{ loading ? '生成中...' : '开始生成' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
