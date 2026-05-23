<script setup>
import { CheckCircle, AlertTriangle } from 'lucide-vue-next'

defineProps({
  mastered: { type: Array, default: () => [] },
  weak: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
    <!-- Mastered -->
    <div class="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
      <div class="flex items-center gap-2 mb-3">
        <CheckCircle class="w-4 h-4 text-green-500" />
        <h3 class="text-sm font-semibold text-gray-700">已掌握知识点</h3>
      </div>
      <div v-if="mastered.length" class="flex flex-wrap gap-2">
        <span
          v-for="p in mastered"
          :key="p"
          class="px-3 py-1 bg-green-50 text-green-700 text-xs rounded-full border border-green-200"
        >
          {{ p }}
        </span>
      </div>
      <p v-else class="text-xs text-gray-400">暂无已掌握的知识点</p>
    </div>

    <!-- Weak -->
    <div class="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
      <div class="flex items-center gap-2 mb-3">
        <AlertTriangle class="w-4 h-4 text-orange-500" />
        <h3 class="text-sm font-semibold text-gray-700">薄弱知识点</h3>
      </div>
      <div v-if="weak.length" class="flex flex-wrap gap-2">
        <span
          v-for="p in weak"
          :key="p"
          class="px-3 py-1 bg-orange-50 text-orange-700 text-xs rounded-full border border-orange-200"
        >
          {{ p }}
        </span>
      </div>
      <p v-else class="text-xs text-gray-400">暂无薄弱知识点，继续保持！</p>
    </div>
  </div>
</template>
