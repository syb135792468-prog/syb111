<script setup>
import { useAppStore } from '../../stores/app'
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-vue-next'

const appStore = useAppStore()

const icons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const colors = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
}

const iconColors = {
  success: 'text-green-500',
  error: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
}
</script>

<template>
  <div class="fixed top-4 right-4 z-50 space-y-2">
    <TransitionGroup name="toast">
      <div
        v-for="toast in appStore.toasts"
        :key="toast.id"
        :class="[
          'flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg min-w-[280px]',
          colors[toast.type] || colors.info,
        ]"
        style="animation: toastIn 0.3s ease-out"
      >
        <component :is="icons[toast.type] || Info" :class="['w-5 h-5 flex-shrink-0', iconColors[toast.type]]" />
        <span class="text-sm">{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active { animation: toastIn 0.3s ease-out; }
.toast-leave-active { animation: toastOut 0.3s ease-in; }
</style>
