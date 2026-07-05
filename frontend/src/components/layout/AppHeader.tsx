import React from 'react'
import { Menu } from 'lucide-react'
import { useAppStore } from '../../stores/app'

interface AppHeaderProps {
  title: string
  children?: React.ReactNode
}

const AppHeader: React.FC<AppHeaderProps> = ({ title, children }) => {
  const toggleSidebar = useAppStore((state) => state.toggleSidebar)

  return (
    <header role="banner" className="shell-page-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
        <button
          onClick={toggleSidebar}
          aria-label="切换侧边栏"
          className="shell-icon-button btn-click-feedback"
        >
          <Menu style={{ width: 18, height: 18 }} />
        </button>

        <div className="shell-page-title">
          <h2>{title}</h2>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexWrap: 'wrap',
          justifyContent: 'flex-end',
        }}
      >
        {children}
      </div>
    </header>
  )
}

export default AppHeader
