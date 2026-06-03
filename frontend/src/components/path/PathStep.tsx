import React, { useState, useCallback } from 'react'
import {
  CheckCircle, Clock, AlertTriangle, SkipForward, ChevronDown, ChevronUp,
  FileText, HelpCircle, GitBranch, Code, PlayCircle, Loader2
} from 'lucide-react'

// --- 类型定义 ---
export interface PathNodeResource {
  id: number
  resource_type: string
  title: string
  status: string
  is_cached: boolean
  duration?: number
  description?: string
  content?: string
  resource_id?: number
  difficulty?: number
  created_at?: string
  updated_at?: string
}

export interface PathNodeData {
  id?: number
  order: number
  type: string
  node_type?: string
  knowledge_point: string
  estimated_time?: number
  estimated_time_min?: number
  status?: string
  mastery?: number
  mastery_threshold?: number
  progress?: number
  difficulty?: number
  prerequisites?: string[]
  resources?: PathNodeResource[]
  [key: string]: unknown
}

interface PathStepProps {
  step: PathNodeData
  isLast?: boolean
  onNodeClick?: (nodeId: number) => void
  onResourceClick?: (nodeId: number, resourceType: string) => void
}

// --- 常量 ---
const STATUS_CONFIG: Record<string, { color: string; bg: string; border: string; icon: React.ReactNode; label: string }> = {
  not_started: {
    color: 'text-gray-500',
    bg: 'bg-gray-100',
    border: 'border-gray-200',
    icon: <Clock className="w-3.5 h-3.5" />,
    label: '未开始',
  },
  in_progress: {
    color: 'text-blue-600',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
    icon: <Loader2 className="w-3.5 h-3.5 animate-spin" />,
    label: '学习中',
  },
  completed: {
    color: 'text-green-600',
    bg: 'bg-green-50',
    border: 'border-green-200',
    icon: <CheckCircle className="w-3.5 h-3.5" />,
    label: '已完成',
  },
  needs_review: {
    color: 'text-amber-600',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: <AlertTriangle className="w-3.5 h-3.5" />,
    label: '需复习',
  },
  skipped: {
    color: 'text-gray-400',
    bg: 'bg-gray-50',
    border: 'border-gray-100',
    icon: <SkipForward className="w-3.5 h-3.5" />,
    label: '已跳过',
  },
}

const RESOURCE_ICONS: Record<string, React.ReactNode> = {
  doc: <FileText className="w-3.5 h-3.5" />,
  quiz: <HelpCircle className="w-3.5 h-3.5" />,
  mindmap: <GitBranch className="w-3.5 h-3.5" />,
  code: <Code className="w-3.5 h-3.5" />,
  video: <PlayCircle className="w-3.5 h-3.5" />,
}

const RESOURCE_LABELS: Record<string, string> = {
  doc: '文档',
  quiz: '练习',
  mindmap: '导图',
  code: '代码',
  video: '视频',
}

// --- 组件 ---
const PathStep: React.FC<PathStepProps> = ({ step, isLast = false, onNodeClick, onResourceClick }) => {
  const [expanded, setExpanded] = useState(false)

  const isReview = (step.type || step.node_type) === 'review'
  const status = step.status || 'not_started'
  const statusCfg = STATUS_CONFIG[status] || STATUS_CONFIG.not_started
  const mastery = step.mastery ?? 0
  const masteryThreshold = step.mastery_threshold ?? 0.7
  const estimatedTime = step.estimated_time ?? step.estimated_time_min ?? 15
  const resources = step.resources || []

  const handleToggle = useCallback(() => {
    setExpanded(prev => !prev)
    if (onNodeClick && step.id) {
      onNodeClick(step.id)
    }
  }, [onNodeClick, step.id])

  // 圆点颜色：优先用状态色，复习用橙色
  const dotColor = status === 'completed'
    ? 'bg-green-500'
    : status === 'in_progress'
      ? 'bg-blue-500'
      : status === 'needs_review'
        ? 'bg-amber-500'
        : isReview
          ? 'bg-orange-400'
          : 'bg-gray-300'

  return (
    <div className="flex gap-4">
      {/* Timeline dot */}
      <div className="flex flex-col items-center">
        <div
          className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold text-white flex-shrink-0 transition-colors ${dotColor}`}
        >
          {status === 'completed' ? (
            <CheckCircle className="w-4 h-4" />
          ) : (
            step.order
          )}
        </div>
        {!isLast && <div className="w-0.5 flex-1 bg-gray-200 mt-1" />}
      </div>

      {/* Content */}
      <div className="pb-6 flex-1 min-w-0">
        <div
          className={`rounded-xl border p-4 shadow-sm cursor-pointer transition-all hover:shadow-md ${
            status === 'completed'
              ? 'bg-green-50/50 border-green-100'
              : status === 'in_progress'
                ? 'bg-blue-50/50 border-blue-100'
                : 'bg-white border-gray-100'
          }`}
          onClick={handleToggle}
        >
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 min-w-0">
              <h4 className="text-sm font-medium text-gray-800 truncate">
                {step.knowledge_point}
              </h4>
              <span
                className={`text-xs px-2 py-0.5 rounded-full flex items-center gap-1 flex-shrink-0 ${
                  isReview
                    ? 'bg-orange-50 text-orange-600 border border-orange-200'
                    : 'bg-brand-50 text-brand-600 border border-brand-200'
                }`}
              >
                {isReview ? '复习' : '新学'}
              </span>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={`text-xs flex items-center gap-1 ${statusCfg.color}`}>
                {statusCfg.icon}
                {statusCfg.label}
              </span>
              {expanded ? (
                <ChevronUp className="w-4 h-4 text-gray-400" />
              ) : (
                <ChevronDown className="w-4 h-4 text-gray-400" />
              )}
            </div>
          </div>

          {/* Mastery bar */}
          {mastery > 0 && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                <span>掌握度</span>
                <span>{Math.round(mastery * 100)}%</span>
              </div>
              <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    mastery >= masteryThreshold ? 'bg-green-500' : 'bg-blue-400'
                  }`}
                  style={{ width: `${Math.min(100, mastery * 100)}%` }}
                />
              </div>
            </div>
          )}

          {/* Meta info */}
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {estimatedTime} 分钟
            </span>
            {step.difficulty !== undefined && (
              <span>
                难度: {step.difficulty <= 0.3 ? '入门' : step.difficulty <= 0.6 ? '进阶' : '高级'}
              </span>
            )}
            {resources.length > 0 && (
              <span className="flex items-center gap-1">
                {resources.filter(r => r.is_cached).length}/{resources.length} 资源
              </span>
            )}
          </div>

          {/* Expanded details */}
          {expanded && (
            <div className="mt-3 pt-3 border-t border-gray-100">
              {/* Prerequisites */}
              {step.prerequisites && step.prerequisites.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs text-gray-500 mb-1">前置知识：</p>
                  <div className="flex flex-wrap gap-1">
                    {step.prerequisites.map((pre, i) => (
                      <span key={i} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                        {pre}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Resources */}
              {resources.length > 0 && (
                <div>
                  <p className="text-xs text-gray-500 mb-2">学习资源：</p>
                  <div className="flex flex-wrap gap-2">
                    {resources.map((res) => (
                      <button
                        key={res.id}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (onResourceClick && step.id) {
                            onResourceClick(step.id, res.resource_type)
                          }
                        }}
                        className={`flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg border transition-colors ${
                          res.is_cached
                            ? 'bg-white border-gray-200 text-gray-700 hover:border-brand-300 hover:text-brand-600'
                            : 'bg-gray-50 border-gray-100 text-gray-400'
                        }`}
                      >
                        {RESOURCE_ICONS[res.resource_type] || <FileText className="w-3.5 h-3.5" />}
                        {RESOURCE_LABELS[res.resource_type] || res.resource_type}
                        {res.status === 'generating' && (
                          <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
                        )}
                        {res.is_cached && (
                          <CheckCircle className="w-3 h-3 text-green-400" />
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default PathStep
