import React, { useEffect, lazy, useMemo } from 'react'
import { useLocation } from 'react-router-dom'
import { useAuthStore } from './stores/auth'
import { useChatStore } from './stores/chat'
import { useAppStore } from './stores/app'
import AppLayout from './components/layout/AppLayout'
import AppRoutes from './router'
import AuthModal from './components/auth/AuthModal'
import ToastContainer from './components/common/Toast'

// 路由 → 右侧面板类型映射
const ROUTE_PANEL_MAP: Record<string, string> = {
  '/mindmap': 'mindmap-detail',
  '/error-book': 'error-detail',
  '/multimodal': 'analysis-detail',
  '/playground': 'code-explain',
  '/resources': 'resource-summary',
  '/profile': 'ai-suggestion',
  '/path': 'path-detail',
  '/animation': 'animation-detail',
}

const ChatView = lazy(() => import('./views/ChatView'))

// --- 组件 ---
const App: React.FC = () => {
  const location = useLocation()
  const checkAuth = useAuthStore((state) => state.checkAuth)
  const login = useAuthStore((state) => state.login)
  const register = useAuthStore((state) => state.register)
  const showAuthModal = useAuthStore((state) => state.showAuthModal)
  const loadConversations = useChatStore((state) => state.loadConversations)
  const restoreSocraticSession = useChatStore((state) => state.restoreSocraticSession)
  const isStreaming = useChatStore(s => s.isStreaming)
  const isChatPage = location.pathname === '/chat'
  const authStore = useMemo(() => ({ login, register }), [login, register])
  const chatStore = useMemo(() => ({ loadConversations }), [loadConversations])

  // 路由变化时自动切换右侧面板
  useEffect(() => {
    const panelType = ROUTE_PANEL_MAP[location.pathname]
    useAppStore.getState().setRightPanelRoute(location.pathname, panelType)
  }, [location.pathname])

  // 路由守卫：检查登录状态
  useEffect(() => {
    const init = async () => {
      const ok = await checkAuth()
      if (ok) {
        loadConversations()
        // 恢复未完成的苏格拉底会话
        restoreSocraticSession()
      }
    }
    init()
  }, [checkAuth, loadConversations, restoreSocraticSession])

  // ChatView 渲染决策：
  // - 聊天页：正常显示
  // - 流式期间切到其他页：保持挂载，用 opacity:0 隐藏（保留布局占位，浏览器不会节流网络）
  // - 非流式切到其他页：不渲染
  const showChat = isChatPage || isStreaming

  return (
    <>
      <AppLayout>
        {/* ChatView：流式期间始终保持在 DOM 中，opacity:0 对浏览器保持"可见" */}
        {showChat && (
          <div style={{
            flex: 1, minHeight: 0, display: 'flex',
            opacity: isChatPage ? 1 : 0,
            pointerEvents: isChatPage ? 'auto' : 'none',
            position: isChatPage ? 'relative' : 'absolute',
            overflow: isChatPage ? 'visible' : 'hidden',
            // 绝对定位时占满父容器
            ...(isChatPage ? {} : { top: 0, left: 0, right: 0, bottom: 0 }),
          }}>
            <ChatView />
          </div>
        )}
        {/* 其他页面走正常路由 */}
        {!isChatPage && <AppRoutes />}
      </AppLayout>
      {showAuthModal && (
        <AuthModal authStore={authStore} chatStore={chatStore} />
      )}
      <ToastContainer />
    </>
  )
}

export default App
