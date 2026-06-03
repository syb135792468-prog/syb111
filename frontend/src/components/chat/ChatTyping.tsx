import React from 'react'
import { Bot } from 'lucide-react'

// --- 组件 ---
const ChatTyping: React.FC = () => {
  return (
    <div className="msg-enter" style={{ display: 'flex', paddingLeft: 64 }}>
      <div style={{
        width: 32, height: 32, borderRadius: '50%', background: '#f3f4f6',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0, marginRight: 16,
      }}>
        <Bot style={{ width: 16, height: 16, color: '#6b7280' }} />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 0' }}>
        <div className="typing-dot" style={{ width: 6, height: 6, background: '#9ca3af', borderRadius: '50%' }} />
        <div className="typing-dot" style={{ width: 6, height: 6, background: '#9ca3af', borderRadius: '50%' }} />
        <div className="typing-dot" style={{ width: 6, height: 6, background: '#9ca3af', borderRadius: '50%' }} />
      </div>
      {/* typing-dot 动画由全局 CSS 或 main.css 提供 */}
    </div>
  )
}

export default ChatTyping
