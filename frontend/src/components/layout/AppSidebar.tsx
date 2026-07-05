import React, { useCallback, useMemo } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Plus,
  LogOut,
  Trash2,
  MessageSquare,
  User,
  BookOpen,
  GitBranch,
  AlertCircle,
  Code,
  Play,
  ScanSearch,
  Presentation,
  Compass,
  Sparkles,
} from 'lucide-react'
import { useIsMobile } from '../../hooks/useIsMobile'
import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'
import { useAppStore } from '../../stores/app'
import { useTaskStore } from '../../stores/taskStore'

interface NavItem {
  name: string
  path: string
  label: string
  group: 'core' | 'tools' | 'growth'
  icon: React.ReactNode
}

const NAV_ITEMS: NavItem[] = [
  { name: 'Chat', path: '/chat', label: '智能对话', group: 'core', icon: <MessageSquare style={{ width: 17, height: 17 }} /> },
  { name: 'Path', path: '/path', label: '学习路径', group: 'core', icon: <Compass style={{ width: 17, height: 17 }} /> },
  { name: 'Playground', path: '/playground', label: '编程练习', group: 'core', icon: <Code style={{ width: 17, height: 17 }} /> },
  { name: 'Resources', path: '/resources', label: '学习资源', group: 'tools', icon: <BookOpen style={{ width: 17, height: 17 }} /> },
  { name: 'Mindmap', path: '/mindmap', label: '思维导图', group: 'tools', icon: <GitBranch style={{ width: 17, height: 17 }} /> },
  { name: 'ErrorBook', path: '/error-book', label: '错题本', group: 'tools', icon: <AlertCircle style={{ width: 17, height: 17 }} /> },
  { name: 'Animation', path: '/animation', label: '教学动画', group: 'tools', icon: <Play style={{ width: 17, height: 17 }} /> },
  { name: 'Multimodal', path: '/multimodal', label: '代码识别', group: 'tools', icon: <ScanSearch style={{ width: 17, height: 17 }} /> },
  { name: 'Slides', path: '/slides', label: '演示幻灯片', group: 'tools', icon: <Presentation style={{ width: 17, height: 17 }} /> },
  { name: 'Profile', path: '/profile', label: '学习画像', group: 'growth', icon: <User style={{ width: 17, height: 17 }} /> },
]

const NAV_GROUPS: Array<{ key: NavItem['group']; label: string }> = [
  { key: 'core', label: '核心流程' },
  { key: 'tools', label: '学习工具' },
  { key: 'growth', label: '成长反馈' },
]

const AppSidebar: React.FC = () => {
  const navigate = useNavigate()
  const location = useLocation()
  const username = useAuthStore((state) => state.username)
  const logout = useAuthStore((state) => state.logout)
  const conversations = useChatStore((state) => state.conversations)
  const currentConversationId = useChatStore((state) => state.currentConversationId)
  const isStreaming = useChatStore((state) => state.isStreaming)
  const startNewChatAction = useChatStore((state) => state.startNewChat)
  const switchConversation = useChatStore((state) => state.switchConversation)
  const deleteConversation = useChatStore((state) => state.deleteConversation)
  const sidebarOpen = useAppStore((state) => state.sidebarOpen)
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen)
  const tasks = useTaskStore((state) => state.tasks)
  const isMobile = useIsMobile()

  const pendingTasks = useMemo(() => tasks.filter((task) => task.status === 'pending'), [tasks])
  const userInitial = useMemo(() => (username || '学')[0], [username])

  const groupedItems = useMemo(
    () =>
      NAV_GROUPS.map((group) => ({
        ...group,
        items: NAV_ITEMS.filter((item) => item.group === group.key),
      })),
    [],
  )

  const navigateTo = useCallback(
    (path: string) => {
      navigate(path)
      if (isMobile) setSidebarOpen(false)
    },
    [navigate, setSidebarOpen, isMobile],
  )

  const startNewChat = useCallback(() => {
    startNewChatAction()
    navigate('/chat')
  }, [startNewChatAction, navigate])

  const handleLogout = useCallback(() => {
    if (isStreaming) return
    logout()
    startNewChatAction()
  }, [isStreaming, logout, startNewChatAction])

  const handleDeleteConversation = useCallback(
    async (event: React.MouseEvent, id: string | number) => {
      event.stopPropagation()
      if (!window.confirm('确定要删除这段对话吗？')) return
      await deleteConversation(id)
    },
    [deleteConversation],
  )

  return (
    <>
      <aside
        aria-label="侧边导航栏"
        className={`sidebar-shell flex flex-col flex-shrink-0 transition-all duration-200 z-40 ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full absolute h-full'
        }`}
        style={{ width: 216 }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '14px 12px 12px' }}>
          <div className="rail-card" style={{ padding: '14px 14px 12px', marginBottom: 10 }}>
            <h1
              style={{
                margin: 0,
                color: 'var(--ink)',
                fontSize: 20,
                lineHeight: 1.08,
                letterSpacing: '-0.04em',
                fontFamily: 'var(--font-display)',
                fontWeight: 700,
              }}
            >
              Python 学习助手
            </h1>

            <p style={{ margin: '6px 0 0', color: 'var(--mute)', fontSize: 11.5, lineHeight: 1.65 }}>
              面向学习者和评委都更容易理解的学习工作台。
            </p>
          </div>

          <button
            onClick={startNewChat}
            className="rail-primary-button btn-click-feedback"
            aria-label="开始新会话"
            style={{ marginBottom: 12 }}
          >
            <Plus style={{ width: 15, height: 15 }} />
            开始新会话
          </button>

          <div className="rail-card" style={{ padding: '10px 9px', marginBottom: 10 }}>
            <div className="rail-section-label">最近对话</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: '22vh', overflowY: 'auto' }}>
              {conversations.length === 0 && (
                <div className="rail-empty">
                  暂无历史对话
                </div>
              )}

              {conversations.map((conversation) => {
                const active = currentConversationId === conversation.id
                return (
                  <div
                    key={conversation.id}
                    className={`rail-thread-item ${active ? 'rail-thread-item-active' : ''}`}
                    onClick={() => {
                      switchConversation(conversation.id)
                      navigate('/chat')
                    }}
                  >
                    <MessageSquare style={{ width: 14, height: 14, flexShrink: 0 }} />
                    <span
                      style={{
                        flex: 1,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        fontSize: 13,
                      }}
                    >
                      {conversation.title}
                    </span>
                    <button
                      onClick={(event) => handleDeleteConversation(event, conversation.id)}
                      className="rail-thread-delete"
                      title="删除对话"
                    >
                      <Trash2 style={{ width: 12, height: 12 }} />
                    </button>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="rail-card" style={{ padding: '10px 9px', flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ overflowY: 'auto', flex: 1, paddingRight: 2 }}>
              {groupedItems.map((group) => (
                <div key={group.key} style={{ marginBottom: 12 }}>
                  <div className="rail-section-label">{group.label}</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {group.items.map((item) => {
                      const active = location.pathname === item.path
                      return (
                        <button
                          key={item.name}
                          onClick={() => navigateTo(item.path)}
                          aria-label={item.label}
                          aria-current={active ? 'page' : undefined}
                          className={`rail-nav-item btn-click-feedback ${active ? 'rail-nav-item-active' : ''}`}
                        >
                          {item.icon}
                          <span>{item.label}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 10 }}>
            {pendingTasks.length > 0 && (
              <div className="rail-card" style={{ padding: '9px 11px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-soft)', fontSize: 12, fontWeight: 600 }}>
                  <Sparkles style={{ width: 13, height: 13, color: 'var(--py-blue)' }} />
                  正在处理 {pendingTasks.length} 个任务
                </div>
              </div>
            )}

            <div className="rail-card" style={{ padding: '9px 11px', display: 'flex', alignItems: 'center', gap: 10 }}>
              <div className="rail-user-avatar">{userInitial}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    color: 'var(--ink)',
                    fontSize: 13,
                    fontWeight: 600,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {username || '学习者'}
                </div>
                <div style={{ color: 'var(--mute)', fontSize: 11 }}>学习状态已同步</div>
              </div>
              <button onClick={handleLogout} title="退出登录" className="rail-icon-button">
                <LogOut style={{ width: 15, height: 15 }} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.18)',
            backdropFilter: 'blur(3px)',
            zIndex: 30,
          }}
          className="md:hidden"
        />
      )}
    </>
  )
}

export default AppSidebar
