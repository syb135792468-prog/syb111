import React, { useMemo, useCallback } from 'react'
import { FileText, Code, GitBranch, BookOpen, PlayCircle } from 'lucide-react'

// --- 类型定义 ---
interface Resource {
  id: number | string
  title: string
  resource_type: string
  created_at?: string
  [key: string]: unknown
}

interface ResourceCardProps {
  resource: Resource
  onClick?: () => void
}

interface TypeConfig {
  icon: React.FC<{ className?: string }>
  gradient: string
  label: string
  color: string
}

// --- 常量 ---
const TYPE_CONFIG: Record<string, TypeConfig> = {
  quiz: { icon: FileText, gradient: 'from-purple-500 to-purple-600', label: '练习题', color: 'text-purple-600 bg-purple-50' },
  code: { icon: Code, gradient: 'from-blue-500 to-blue-600', label: '代码案例', color: 'text-blue-600 bg-blue-50' },
  mindmap: { icon: GitBranch, gradient: 'from-orange-500 to-orange-600', label: '思维导图', color: 'text-orange-600 bg-orange-50' },
  doc: { icon: BookOpen, gradient: 'from-green-500 to-green-600', label: '讲解文档', color: 'text-green-600 bg-green-50' },
  video: { icon: PlayCircle, gradient: 'from-red-500 to-red-600', label: '教学动画', color: 'text-red-600 bg-red-50' },
}

// --- 组件 ---
const ResourceCard: React.FC<ResourceCardProps> = ({ resource, onClick }) => {
  const config = useMemo(() => TYPE_CONFIG[resource.resource_type] || TYPE_CONFIG.doc, [resource.resource_type])
  const Icon = config.icon

  const dateStr = useMemo(() => {
    if (!resource.created_at) return ''
    return new Date(resource.created_at).toLocaleDateString()
  }, [resource.created_at])

  return (
    <div
      onClick={onClick}
      className="resource-card bg-white rounded-xl border border-gray-100 overflow-hidden cursor-pointer shadow-sm"
    >
      {/* Top gradient */}
      <div className={`h-16 bg-gradient-to-r flex items-center justify-center ${config.gradient}`}>
        <Icon className="w-8 h-8 text-white/90" />
      </div>
      {/* Content */}
      <div className="p-4">
        <span className={`text-xs px-2 py-0.5 rounded-full ${config.color}`}>
          {config.label}
        </span>
        <h3 className="text-sm font-medium text-gray-800 mt-2 line-clamp-2">
          {resource.title}
        </h3>
        <p className="text-xs text-gray-400 mt-2">{dateStr}</p>
      </div>
      <style>{`
        .resource-card { transition: all 0.2s ease; }
        .resource-card:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.1); }
      `}</style>
    </div>
  )
}

export default ResourceCard
