<script setup>
import { BookOpen, Target, Zap } from 'lucide-vue-next'

defineProps({
  level: { type: String, default: '初学者' },
  levelDesc: { type: String, default: '' },
  goal: { type: String, default: '兴趣学习' },
  goalDesc: { type: String, default: '' },
  motivation: { type: String, default: '状态适中' },
  motivationDesc: { type: String, default: '' },
})

const cards = [
  { key: 'level', icon: BookOpen, gradient: 'from-blue-500 to-blue-600', bg: 'bg-blue-50' },
  { key: 'goal', icon: Target, gradient: 'from-purple-500 to-purple-600', bg: 'bg-purple-50' },
  { key: 'motivation', icon: Zap, gradient: 'from-green-500 to-green-600', bg: 'bg-green-50' },
]
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
    <div
      v-for="card in cards"
      :key="card.key"
      class="rounded-xl overflow-hidden shadow-sm"
    >
      <div :class="['bg-gradient-to-r px-5 py-4 text-white', card.gradient]">
        <div class="flex items-center gap-2 mb-1">
          <component :is="card.icon" class="w-4 h-4" />
          <span class="text-xs opacity-80">
            {{ card.key === 'level' ? '知识水平' : card.key === 'goal' ? '学习目标' : '学习动力' }}
          </span>
        </div>
        <p class="text-lg font-semibold">
          {{ card.key === 'level' ? level : card.key === 'goal' ? goal : motivation }}
        </p>
      </div>
      <div :class="['px-5 py-3', card.bg]">
        <p class="text-xs text-gray-500">
          {{ card.key === 'level' ? levelDesc : card.key === 'goal' ? goalDesc : motivationDesc }}
        </p>
      </div>
    </div>
  </div>
</template>
