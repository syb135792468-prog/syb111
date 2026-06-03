import { useState, useCallback, useRef } from 'react'

export function useScroll(containerRef: React.RefObject<HTMLElement | null>) {
  const [userScrolledUp, setUserScrolledUp] = useState(false)
  const scrolledUpRef = useRef(false)

  const scrollToBottom = useCallback((force = false) => {
    if (!containerRef.current) return
    if (!force && scrolledUpRef.current) return
    requestAnimationFrame(() => {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight
      }
    })
  }, [containerRef])

  const onScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isScrolledUp = scrollHeight - scrollTop - clientHeight > 80
    scrolledUpRef.current = isScrolledUp
    setUserScrolledUp(isScrolledUp)
  }, [containerRef])

  const resetScrollState = useCallback(() => {
    scrolledUpRef.current = false
    setUserScrolledUp(false)
  }, [])

  return { userScrolledUp, scrollToBottom, onScroll, resetScrollState }
}
