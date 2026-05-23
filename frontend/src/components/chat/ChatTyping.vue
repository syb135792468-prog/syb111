<script setup>
import { Bot } from 'lucide-vue-next'
</script>

<template>
  <div class="flex gap-3 msg-enter">
    <div class="w-8 h-8 rounded-lg bg-brand-100 flex items-center justify-center flex-shrink-0">
      <Bot class="w-4 h-4 text-brand-600" />
    </div>
    <div class="px-4 py-3 bg-gray-50 rounded-2xl rounded-bl-md">
      <div class="flex items-center gap-1.5">
        <div class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
        <div class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
        <div class="typing-dot w-2 h-2 bg-gray-400 rounded-full"></div>
      </div>
    </div>
  </div>
</template>
