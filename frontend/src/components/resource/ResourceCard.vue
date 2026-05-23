<script setup>
import { computed } from 'vue'
import { FileText, Code, GitBranch, BookOpen, PlayCircle } from 'lucide-vue-next'

const props = defineProps({
  resource: { type: Object, required: true },
})

const emit = defineEmits(['click'])

const typeConfig = {
  quiz: { icon: FileText, gradient: 'from-purple-500 to-purple-600', label: '练习题', color: 'text-purple-600 bg-purple-50' },
  code: { icon: Code, gradient: 'from-blue-500 to-blue-600', label: '代码案例', color: 'text-blue-600 bg-blue-50' },
  mindmap: { icon: GitBranch, gradient: 'from-orange-500 to-orange-600', label: '思维导图', color: 'text-orange-600 bg-orange-50' },
  doc: { icon: BookOpen, gradient: 'from-green-500 to-green-600', label: '讲解文档', color: 'text-green-600 bg-green-50' },
  video: { icon: PlayCircle, gradient: 'from-red-500 to-red-600', label: '教学动画', color: 'text-red-600 bg-red-50' },
}

const config = computed(() => typeConfig[props.resource.resource_type] || typeConfig.doc)
</script>

<template>
  <div
    @click="emit('click')"
    class="resource-card bg-white rounded-xl border border-gray-100 overflow-hidden cursor-pointer shadow-sm"
  >
    <!-- Top gradient -->
    <div :class="['h-16 bg-gradient-to-r flex items-center justify-center', config.gradient]">
      <component :is="config.icon" class="w-8 h-8 text-white/90" />
    </div>
    <!-- Content -->
    <div class="p-4">
      <span :class="['text-xs px-2 py-0.5 rounded-full', config.color]">
        {{ config.label }}
      </span>
      <h3 class="text-sm font-medium text-gray-800 mt-2 line-clamp-2">
        {{ resource.title }}
      </h3>
      <p class="text-xs text-gray-400 mt-2">
        {{ resource.created_at ? new Date(resource.created_at).toLocaleDateString() : '' }}
      </p>
    </div>
  </div>
</template>

<style scoped>
.resource-card {
  transition: all 0.2s ease;
}
.resource-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
}
</style>
