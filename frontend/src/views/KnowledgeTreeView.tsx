import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'

import AppHeader from '../components/layout/AppHeader'
import KnowledgeGraph from '../components/knowledge/KnowledgeGraph'

const KnowledgeTreeView: React.FC = () => {
  const navigate = useNavigate()
  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="Python 树形知识图谱">
        <button
          onClick={() => navigate('/profile')}
          className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          返回学习画像
        </button>
      </AppHeader>
      <div className="page-scroll-area">
        <div className="page-content max-w-7xl mx-auto">
          <KnowledgeGraph mode="tree" />
        </div>
      </div>
    </div>
  )
}

export default KnowledgeTreeView
