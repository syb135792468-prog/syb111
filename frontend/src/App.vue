<script setup>
import { onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import AppLayout from './components/layout/AppLayout.vue'
import AuthModal from './components/auth/AuthModal.vue'
import ToastContainer from './components/common/Toast.vue'

const authStore = useAuthStore()
const chatStore = useChatStore()

onMounted(async () => {
  const ok = await authStore.checkAuth()
  if (ok) {
    chatStore.loadConversations()
  }
})
</script>

<template>
  <AppLayout />
  <AuthModal v-if="authStore.showAuthModal" />
  <ToastContainer />
</template>
