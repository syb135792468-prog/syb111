import React, { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import LoadingSpinner from '../components/common/LoadingSpinner'

// 懒加载页面组件
const ProfileView = lazy(() => import('../views/ProfileView'))
const ResourcesView = lazy(() => import('../views/ResourcesView'))
const MindmapView = lazy(() => import('../views/MindmapView'))
const PathView = lazy(() => import('../views/PathView'))
const ErrorBookView = lazy(() => import('../views/ErrorBookView'))
const CodePlaygroundView = lazy(() => import('../views/CodePlaygroundView'))
const TeachingAnimationView = lazy(() => import('../views/TeachingAnimationView'))
const MultimodalView = lazy(() => import('../views/MultimodalView'))
const SlidesView = lazy(() => import('../views/SlidesView'))
const KnowledgeGraphView = lazy(() => import('../views/KnowledgeGraphView'))
const CourseView = lazy(() => import('../views/CourseView'))

// 加载占位
const PageLoading: React.FC = () => (
  <div className="flex items-center justify-center h-full">
    <LoadingSpinner />
  </div>
)

// 路由配置（ChatView 由 App.tsx 直接渲染，不走路由）
const AppRoutes: React.FC = () => {
  return (
    <Suspense fallback={<PageLoading />}>
      <Routes>
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/course" element={<CourseView />} />
        <Route path="/profile" element={<ProfileView />} />
        <Route path="/resources" element={<ResourcesView />} />
        <Route path="/mindmap" element={<MindmapView />} />
        <Route path="/path" element={<PathView />} />
        <Route path="/error-book" element={<ErrorBookView />} />
        <Route path="/playground" element={<CodePlaygroundView />} />
        <Route path="/animation" element={<TeachingAnimationView />} />
        <Route path="/multimodal" element={<MultimodalView />} />
        <Route path="/slides" element={<SlidesView />} />
        <Route path="/knowledge-graph" element={<KnowledgeGraphView />} />
      </Routes>
    </Suspense>
  )
}

export default AppRoutes
