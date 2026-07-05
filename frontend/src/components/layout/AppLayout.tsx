import React from 'react'
import AppSidebar from './AppSidebar'
import RightPanel from './RightPanel'
import RobotPet from '../common/RobotPet'
import { useStudyTimer } from '../../composables/useStudyTimer'

interface AppLayoutProps {
  children?: React.ReactNode
}

const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  useStudyTimer()

  return (
    <>
      <div role="main" className="app-shell">
        <AppSidebar />
        <main aria-label="主内容区域" className="main-shell">
          {children}
        </main>
        <RightPanel />
      </div>
      <RobotPet />
    </>
  )
}

export default AppLayout
