import React, { useMemo, useCallback } from 'react'
import { FileText, Code, GitBranch, BookOpen, PlayCircle, Trash2, Bookmark } from 'lucide-react'

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
  onDelete?: () => void
  onSave?: () => void
  saved?: boolean
}

interface TypeConfig {
  icon: React.FC<{ className?: string }>
  gradient: string
  label: string
  color: string
  iconColor: string
}

// --- 常量 ---
const TYPE_CONFIG: Record<string, TypeConfig> = {
  quiz: { icon: FileText, gradient: 'bg-violet-50', label: '练习题', color: 'text-violet-700 bg-white/86 border-violet-100', iconColor: 'text-violet-500' },
  code: { icon: Code, gradient: 'bg-blue-50', label: '代码案例', color: 'text-blue-700 bg-white/86 border-blue-100', iconColor: 'text-blue-500' },
  mindmap: { icon: GitBranch, gradient: 'bg-amber-50', label: '思维导图', color: 'text-orange-700 bg-white/86 border-orange-100', iconColor: 'text-orange-500' },
  doc: { icon: BookOpen, gradient: 'bg-emerald-50', label: '讲解文档', color: 'text-emerald-700 bg-white/86 border-emerald-100', iconColor: 'text-emerald-500' },
  video: { icon: PlayCircle, gradient: 'bg-rose-50', label: '教学动画', color: 'text-rose-700 bg-white/86 border-rose-100', iconColor: 'text-rose-500' },
  slides: { icon: PlayCircle, gradient: 'bg-indigo-50', label: '幻灯片', color: 'text-indigo-700 bg-white/86 border-indigo-100', iconColor: 'text-indigo-500' },
}

// --- 组件 ---
const ResourceCard: React.FC<ResourceCardProps> = ({ resource, onClick, onDelete, onSave, saved }) => {
  const config = useMemo(() => TYPE_CONFIG[resource.resource_type] || TYPE_CONFIG.doc, [resource.resource_type])
  const Icon = config.icon

  const thumbnail = useMemo(() => {
    const meta = resource.extra_metadata as Record<string, unknown> | undefined
    return (meta?.thumbnail as string) || ''
  }, [resource.extra_metadata])

  const dateStr = useMemo(() => {
    if (!resource.created_at) return ''
    return new Date(resource.created_at).toLocaleDateString()
  }, [resource.created_at])

  return (
    <div
      onClick={onClick}
      className="resource-card overflow-hidden cursor-pointer"
    >
      {/* Top: thumbnail or gradient */}
      {thumbnail ? (
        <div className="h-36 bg-slate-100 relative">
          <img
            src={thumbnail}
            alt={resource.title}
            className="w-full h-full object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
          />
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/5 transition-colors">
            <div className="rounded-xl border border-gray-200 bg-white/90 p-3 opacity-0 hover:opacity-100 transition-opacity shadow-sm">
              <Icon className={`w-6 h-6 ${config.iconColor}`} />
            </div>
          </div>
        </div>
      ) : (
        <div className={`h-24 flex items-center justify-center border-b border-slate-200/80 ${config.gradient}`}>
          <div className="flex h-12 w-12 items-center justify-center rounded-xl border border-gray-200 bg-white shadow-sm">
            <Icon className={`w-6 h-6 ${config.iconColor}`} />
          </div>
        </div>
      )}
      {/* Content */}
      <div className="p-5">
        <span className={`inline-flex items-center text-[11px] px-2.5 py-1 rounded-full border ${config.color}`}>
          {config.label}
        </span>
        <h3 className="text-[15px] font-semibold text-slate-800 mt-3 line-clamp-2 leading-6">
          {resource.title}
        </h3>
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-slate-400">{dateStr}</p>
          <div className="flex items-center gap-1.5">
            {onSave && (
              <button
                onClick={e => { e.stopPropagation(); onSave() }}
                className={`flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-xl transition-colors ${
                  saved
                    ? 'text-emerald-700 bg-emerald-50/80 border border-emerald-100 hover:bg-emerald-100/80'
                    : 'text-amber-700 bg-amber-50/80 border border-amber-100 hover:bg-amber-100/80'
                }`}
                title={saved ? '取消收藏' : '收藏到资源库'}
              >
                <Bookmark className={`w-3 h-3 ${saved ? 'fill-current' : ''}`} />
                {saved ? '已收藏' : '收藏'}
              </button>
            )}
            {onDelete && (
              <button
                onClick={e => { e.stopPropagation(); onDelete() }}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-rose-600 bg-rose-50/80 border border-rose-100 hover:bg-rose-100/80 rounded-xl transition-colors"
                title="删除"
              >
                <Trash2 className="w-3 h-3" />
                删除
              </button>
            )}
          </div>
        </div>
      </div>
      <style>{`
        .resource-card {
          background: #fff;
          border: 1px solid #e5e7eb;
          border-radius: 14px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.04);
          transition: box-shadow 0.2s ease, transform 0.2s ease;
        }
        .resource-card:hover {
          transform: translateY(-1px);
          box-shadow: 0 4px 12px rgba(0,0,0,0.06);
        }
      `}</style>
    </div>
  )
}

export default ResourceCard
