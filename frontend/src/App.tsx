import React, { useEffect } from 'react'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import AppLayout from './components/layout/AppLayout'
import AppRoutes from './router'
import AuthModal from './components/auth/AuthModal'
import ToastContainer from './components/common/Toast'

// --- 组件 ---
const App: React.FC = () => {
  const authStore = useAuthStore()
  const chatStore = useChatStore()

  // 路由守卫：检查登录状态
  useEffect(() => {
    const init = async () => {
      const ok = await authStore.checkAuth()
      if (ok) {
        chatStore.loadConversations()
        // 恢复未完成的苏格拉底会话
        chatStore.restoreSocraticSession()
      }
    }
    init()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <AppLayout>
        <AppRoutes />
      </AppLayout>
      {authStore.showAuthModal && (
        <AuthModal authStore={authStore} chatStore={chatStore} />
      )}
      <ToastContainer />
    </>
  )
}

export default App
