import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  const sidebarOpen = ref(true)
  const toasts = ref([])
  let toastId = 0

  function toggleSidebar() {
    sidebarOpen.value = !sidebarOpen.value
  }

  function showToast(message, type = 'info') {
    const id = ++toastId
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, 3000)
  }

  function removeToast(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  return { sidebarOpen, toasts, toggleSidebar, showToast, removeToast }
})
