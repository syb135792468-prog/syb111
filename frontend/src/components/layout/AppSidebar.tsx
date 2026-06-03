import React, { useCallback, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'
import { useAppStore } from '../../stores/app'
import { Plus, LogOut, Trash2 } from 'lucide-react'

// --- 类型定义 ---
interface NavItem {
  name: string
  path: string
  label: string
}

// --- 常量 ---
const NAV_ITEMS: NavItem[] = [
  { name: 'Chat', path: '/chat', label: '智能对话' },
  { name: 'Profile', path: '/profile', label: '学习画像' },
  { name: 'Resources', path: '/resources', label: '学习资源' },
  { name: 'Mindmap', path: '/mindmap', label: '思维导图' },
  { name: 'Path', path: '/path', label: '学习路径' },
  { name: 'ErrorBook', path: '/error-book', label: '错题本' },
  { name: 'Playground', path: '/playground', label: '代码练习' },
  { name: 'Animation', path: '/animation', label: '教学动画' },
]

// --- 组件 ---
const AppSidebar: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const authStore = useAuthStore()
  const chatStore = useChatStore()
  const appStore = useAppStore()

  // --- 导航 ---
  const navigateTo = useCallback((path: string) => {
    navigate(path)
    if (window.innerWidth < 768) {
      appStore.setSidebarOpen(false)
    }
  }, [navigate, appStore])

  // --- 新建对话 ---
  const startNewChat = useCallback(() => {
    chatStore.startNewChat()
    navigate('/chat')
  }, [chatStore, navigate])

  // --- 退出登录 ---
  const handleLogout = useCallback(() => {
    if (chatStore.isStreaming) return
    authStore.logout()
    chatStore.startNewChat()
  }, [authStore, chatStore])

  // --- 删除对话 ---
  const handleDeleteConversation = useCallback(async (e: React.MouseEvent, id: string | number) => {
    e.stopPropagation()
    if (!window.confirm('确定要删除这个对话吗？')) return
    await chatStore.deleteConversation(id)
  }, [chatStore])

  // --- 用户名首字母 ---
  const userInitial = useMemo(() => (authStore.username || '学')[0], [authStore.username])

  return (
    <>
      <aside
        className={`flex flex-col flex-shrink-0 transition-all duration-200 z-40 ${
          appStore.sidebarOpen ? 'translate-x-0' : '-translate-x-full absolute h-full'
        }`}
        style={{ width: 260, background: '#f9fafb' }}
      >
        {/* Brand */}
        <div style={{ padding: '16px 16px 12px' }}>
          <h1 style={{ fontSize: 15, fontWeight: 600, color: '#111827', margin: 0 }}>Python 学习助手</h1>
        </div>

        {/* New Chat */}
        <div style={{ padding: '0 12px 8px' }}>
          <button
            onClick={startNewChat}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: 8,
              padding: '8px 12px', background: '#ffffff', border: '1px solid #e5e7eb',
              borderRadius: 8, color: '#374151', fontSize: 14, cursor: 'pointer',
              transition: 'background 0.15s ease',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = '#f3f4f6')}
            onMouseLeave={e => (e.currentTarget.style.background = '#ffffff')}
          >
            <Plus style={{ width: 16, height: 16 }} />
            <span>新建对话</span>
          </button>
        </div>

        {/* Conversation List */}
        <div style={{ padding: '0 12px', overflowY: 'auto', maxHeight: '35vh', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {chatStore.conversations.map(conv => (
            <div
              key={conv.id}
              className="conv-item"
              onClick={() => { chatStore.switchConversation(conv.id); navigate('/chat') }}
              style={{
                padding: '8px 12px', borderRadius: 6, cursor: 'pointer', fontSize: 14,
                transition: 'background 0.15s ease', display: 'flex', alignItems: 'center', gap: 8,
                background: chatStore.currentConversationId === conv.id ? '#e5e7eb' : 'transparent',
                color: chatStore.currentConversationId === conv.id ? '#111827' : '#374151',
                fontWeight: chatStore.currentConversationId === conv.id ? 500 : 400,
              }}
              onMouseEnter={e => {
                if (chatStore.currentConversationId !== conv.id) {
                  (e.currentTarget as HTMLElement).style.background = '#f3f4f6'
                }
              }}
              onMouseLeave={e => {
                if (chatStore.currentConversationId !== conv.id) {
                  (e.currentTarget as HTMLElement).style.background = 'transparent'
                }
              }}
            >
              <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {conv.title}
              </span>
              <button
                onClick={e => handleDeleteConversation(e, conv.id)}
                className="conv-delete-btn"
                title="删除对话"
                style={{
                  background: 'none', border: 'none', color: '#9ca3af',
                  cursor: 'pointer', padding: 2, transition: 'color 0.15s',
                }}
                onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                onMouseLeave={e => (e.currentTarget.style.color = '#9ca3af')}
              >
                <Trash2 style={{ width: 12, height: 12 }} />
              </button>
            </div>
          ))}
        </div>

        {/* Divider */}
        <div style={{ margin: '8px 12px', borderTop: '1px solid #e5e7eb' }} />

        {/* Navigation */}
        <nav style={{ flex: 1, padding: '4px 12px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 2 }}>
          {NAV_ITEMS.map(item => (
            <button
              key={item.name}
              onClick={() => navigateTo(item.path)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center',
                padding: '8px 12px', borderRadius: 6, fontSize: 14,
                border: 'none', cursor: 'pointer', transition: 'background 0.15s ease',
                height: 40,
                background: location.pathname === item.path ? '#e5e7eb' : 'transparent',
                color: location.pathname === item.path ? '#111827' : '#374151',
                fontWeight: location.pathname === item.path ? 500 : 400,
              }}
              onMouseEnter={e => {
                if (location.pathname !== item.path) {
                  (e.currentTarget as HTMLElement).style.background = '#f3f4f6'
                }
              }}
              onMouseLeave={e => {
                if (location.pathname !== item.path) {
                  (e.currentTarget as HTMLElement).style.background = 'transparent'
                }
              }}
            >
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        {/* User Info */}
        <div style={{ padding: 12, borderTop: '1px solid #e5e7eb' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 8px' }}>
            <div style={{
              width: 28, height: 28, borderRadius: '50%', background: '#10b981',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ color: '#ffffff', fontSize: 12, fontWeight: 600 }}>{userInitial}</span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <p style={{
                fontSize: 14, fontWeight: 500, color: '#111827', margin: 0,
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {authStore.username || '学习者'}
              </p>
            </div>
            <button
              onClick={handleLogout}
              style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: 4, transition: 'color 0.15s' }}
              onMouseEnter={e => (e.currentTarget.style.color = '#374151')}
              onMouseLeave={e => (e.currentTarget.style.color = '#9ca3af')}
              title="退出登录"
            >
              <LogOut style={{ width: 16, height: 16 }} />
            </button>
          </div>
        </div>
      </aside>

      {/* Mobile overlay */}
      {appStore.sidebarOpen && (
        <div
          onClick={() => appStore.setSidebarOpen(false)}
          style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.3)', zIndex: 30 }}
          className="md:hidden"
        />
      )}

      {/* Scoped style for conversation delete button hover */}
      <style>{`
        .conv-delete-btn {
          visibility: hidden;
        }
        .conv-item:hover .conv-delete-btn {
          visibility: visible;
        }
      `}</style>
    </>
  )
}

export default AppSidebar
