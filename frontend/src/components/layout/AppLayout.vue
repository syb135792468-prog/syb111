<script setup>
import { useRoute } from 'vue-router'
import AppSidebar from './AppSidebar.vue'

const route = useRoute()
</script>

<template>
  <div class="flex h-screen bg-surface">
    <AppSidebar />
    <main class="flex-1 flex flex-col overflow-hidden bg-white">
      <router-view />
    </main>
  </div>
</template>
