<script setup>
defineProps({
  step: { type: Object, required: true },
  isLast: { type: Boolean, default: false },
})
</script>

<template>
  <div class="flex gap-4">
    <!-- Timeline dot -->
    <div class="flex flex-col items-center">
      <div
        :class="[
          'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0',
          step.type === 'review' ? 'bg-orange-400' : 'bg-brand-500',
        ]"
      >
        {{ step.order }}
      </div>
      <div v-if="!isLast" class="w-0.5 flex-1 bg-gray-200 mt-1"></div>
    </div>

    <!-- Content -->
    <div class="pb-6 flex-1">
      <div class="bg-white rounded-xl border border-gray-100 p-4 shadow-sm">
        <div class="flex items-center gap-2 mb-1">
          <h4 class="text-sm font-medium text-gray-800">{{ step.knowledge_point }}</h4>
          <span
            :class="[
              'text-xs px-2 py-0.5 rounded-full',
              step.type === 'review'
                ? 'bg-orange-50 text-orange-600 border border-orange-200'
                : 'bg-brand-50 text-brand-600 border border-brand-200',
            ]"
          >
            {{ step.type === 'review' ? '复习' : '新学' }}
          </span>
        </div>
        <p class="text-xs text-gray-400 mt-1">
          预计学习时间：{{ step.estimated_time_min }} 分钟
        </p>
      </div>
    </div>
  </div>
</template>
