import { ref, nextTick } from 'vue'

export function useScroll(containerRef) {
  const userScrolledUp = ref(false)

  function scrollToBottom(force = false) {
    if (!containerRef.value) return
    if (!force && userScrolledUp.value) return
    nextTick(() => {
      containerRef.value.scrollTop = containerRef.value.scrollHeight
    })
  }

  function onScroll() {
    if (!containerRef.value) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.value
    userScrolledUp.value = scrollHeight - scrollTop - clientHeight > 80
  }

  function resetScrollState() {
    userScrolledUp.value = false
  }

  return { userScrolledUp, scrollToBottom, onScroll, resetScrollState }
}
