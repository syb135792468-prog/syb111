import React, { useCallback } from 'react'

// --- 类型定义 ---
interface ModeAction {
  key: string
  placeholder: string
  guide: string
  label: string
  desc?: string
}

interface ChatWelcomeProps {
  onSelectMode: (mode: ModeAction) => void
}

// --- 常量 ---
const ACTIONS: ModeAction[] = [
  {
    label: '规划学习路径',
    desc: '制定个性化学习计划',
    key: 'path',
    placeholder: '请描述你的Python基础和学习目标',
    guide: '好的，我来为你规划个性化的Python学习路径。请告诉我你的基础情况和想要达成的目标。',
  },
  {
    label: '提问答疑',
    desc: '解答Python疑问',
    key: 'qa',
    placeholder: '请输入你的Python问题',
    guide: '好的，我来帮你解答Python问题。请在下方输入你的疑问。',
  },
  {
    label: '生成练习题',
    desc: '针对性练习巩固',
    key: 'quiz',
    placeholder: '请输入你想练习的知识点',
    guide: '好的，我来为你生成针对性的练习题。请告诉我你想练习哪个知识点。',
  },
  {
    label: '思维导图',
    desc: '可视化知识结构',
    key: 'mindmap',
    placeholder: '请输入你想梳理的知识主题',
    guide: '好的，我来为你创建知识思维导图。请输入你想梳理的主题。',
  },
]

// --- 组件 ---
const ChatWelcome: React.FC<ChatWelcomeProps> = ({ onSelectMode }) => {
  const handleClick = useCallback((action: ModeAction) => {
    onSelectMode({
      key: action.key,
      placeholder: action.placeholder,
      guide: action.guide,
      label: action.label,
    })
  }, [onSelectMode])

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', padding: '0 64px',
    }}>
      <h2 style={{ fontSize: 18, fontWeight: 600, color: '#111827', margin: '0 0 8px' }}>
        Python 智能学习助手
      </h2>
      <p style={{
        color: '#6b7280', textAlign: 'center', maxWidth: 480,
        margin: '0 0 40px', fontSize: 14, lineHeight: 1.6,
      }}>
        基于大模型的个性化资源生成与学习多智能体系统。我可以帮你答疑解惑、生成练习题、创建思维导图、规划学习路径。
      </p>

      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)',
        gap: 12, maxWidth: 480, width: '100%',
      }}>
        {ACTIONS.map(action => (
          <button
            key={action.label}
            onClick={() => handleClick(action)}
            style={{
              display: 'flex', flexDirection: 'column', gap: 4,
              padding: 16, borderRadius: 8, border: '1px solid #e5e7eb',
              background: '#ffffff', cursor: 'pointer', textAlign: 'left',
              transition: 'background 0.15s ease, border-color 0.15s ease',
            }}
            onMouseEnter={e => {
              e.currentTarget.style.background = '#f9fafb'
              e.currentTarget.style.borderColor = '#d1d5db'
            }}
            onMouseLeave={e => {
              e.currentTarget.style.background = '#ffffff'
              e.currentTarget.style.borderColor = '#e5e7eb'
            }}
          >
            <p style={{ fontSize: 14, fontWeight: 500, color: '#111827', margin: 0 }}>{action.label}</p>
            <p style={{ fontSize: 13, color: '#9ca3af', margin: 0 }}>{action.desc}</p>
          </button>
        ))}
      </div>
    </div>
  )
}

export default ChatWelcome
