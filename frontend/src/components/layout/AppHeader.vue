<script setup>
import { Menu } from 'lucide-vue-next'
import { useAppStore } from '../../stores/app'

defineProps({
  title: { type: String, required: true },
})

const appStore = useAppStore()
</script>

<template>
  <header class="flex items-center justify-between px-6 py-3 border-b border-gray-100">
    <div class="flex items-center gap-3">
      <button
        @click="appStore.toggleSidebar()"
        class="text-gray-400 hover:text-gray-600 md:hidden"
      >
        <Menu class="w-5 h-5" />
      </button>
      <h2 class="text-base font-semibold text-gray-800">{{ title }}</h2>
      <slot name="badge" />
    </div>
    <div class="flex items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
