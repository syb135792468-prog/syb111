import React from 'react'
import AppSidebar from './AppSidebar'
import RobotPet from '../common/RobotPet'
import { useStudyTimer } from '../../composables/useStudyTimer'

interface AppLayoutProps {
  children?: React.ReactNode
}

// --- 组件 ---
const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  useStudyTimer()
  return (
    <>
      <div className="flex h-screen" style={{ background: '#ffffff' }}>
        <AppSidebar />
        <main className="flex-1 flex flex-col overflow-hidden" style={{ borderLeft: '1px solid #e5e7eb' }}>
          {children}
        </main>
      </div>
      <RobotPet />
    </>
  )
}

export default AppLayout
