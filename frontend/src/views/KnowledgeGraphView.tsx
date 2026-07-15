import React from 'react'
import AppHeader from '../components/layout/AppHeader'
import KnowledgeGraph from '../components/knowledge/KnowledgeGraph'

const KnowledgeGraphView: React.FC = () => {
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="Python 知识图谱" />
      <div className="page-scroll-area">
        <div className="page-content max-w-7xl mx-auto">
          <KnowledgeGraph mode="full" />
        </div>
      </div>
    </div>
  )
}

export default KnowledgeGraphView
