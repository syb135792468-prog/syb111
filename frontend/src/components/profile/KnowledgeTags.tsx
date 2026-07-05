import React from 'react'
import { CheckCircle, AlertTriangle } from 'lucide-react'

// --- 类型定义 ---
interface KnowledgePoint {
  id: string
  name: string
  mastery: number
}

interface KnowledgeTagsProps {
  mastered?: KnowledgePoint[]
  weak?: KnowledgePoint[]
}

// --- 组件 ---
const KnowledgeTags: React.FC<KnowledgeTagsProps> = ({ mastered = [], weak = [] }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* Mastered */}
      <div className="page-panel p-5">
        <div className="flex items-center gap-2 mb-3">
          <CheckCircle className="w-4 h-4 text-green-500" />
          <h3 className="text-sm font-semibold text-slate-700">已掌握知识点</h3>
        </div>
        {mastered.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {mastered.map(p => (
              <span
                key={p.id}
                className="px-3 py-1.5 bg-emerald-50/90 text-emerald-700 text-xs rounded-full border border-emerald-200 transition-all duration-300"
              >
                {p.name} ({p.mastery}%)
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400">暂无已掌握的知识点</p>
        )}
      </div>

      {/* Weak */}
      <div className="page-panel p-5">
        <div className="flex items-center gap-2 mb-3">
          <AlertTriangle className="w-4 h-4 text-orange-500" />
          <h3 className="text-sm font-semibold text-slate-700">薄弱知识点</h3>
        </div>
        {weak.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {weak.map(p => (
              <span
                key={p.id}
                className="px-3 py-1.5 bg-orange-50/90 text-orange-700 text-xs rounded-full border border-orange-200 transition-all duration-300"
              >
                {p.name} ({p.mastery}%)
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400">暂无薄弱知识点，继续保持！</p>
        )}
      </div>
    </div>
  )
}

export default KnowledgeTags
