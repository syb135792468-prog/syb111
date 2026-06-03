import React from 'react'
import { Menu } from 'lucide-react'
import { useAppStore } from '../../stores/app'

// --- 类型定义 ---
interface AppHeaderProps {
  title: string
  children?: React.ReactNode
}

// --- 组件 ---
const AppHeader: React.FC<AppHeaderProps> = ({ title, children }) => {
  const appStore = useAppStore()

  return (
    <header style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '0 64px', height: 56, borderBottom: '1px solid #f3f4f6', flexShrink: 0,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <button
          onClick={() => appStore.toggleSidebar()}
          style={{ color: '#9ca3af', background: 'none', border: 'none', cursor: 'pointer', display: 'none' }}
          className="md:!flex"
        >
          <Menu style={{ width: 20, height: 20 }} />
        </button>
        <h2 style={{ fontSize: 15, fontWeight: 600, color: '#111827', margin: 0 }}>{title}</h2>
        {children}
      </div>
    </header>
  )
}

export default AppHeader
