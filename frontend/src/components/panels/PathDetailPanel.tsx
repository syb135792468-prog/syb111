import React, { useState, useEffect, useCallback } from 'react'
import { useAppStore } from '../../stores/app'
import { getNodeResources } from '../../api/learningPath'
import MarkdownText from '../common/MarkdownText'
import {
  Clock, BookOpen, GitBranch, Loader2, CheckCircle,
  FileText, HelpCircle, Code, PlayCircle, AlertCircle, Flag, Compass
} from 'lucide-react'

interface NodeDetail {
  pathId?: number
  nodeId: number
  nodeName: string
  description?: string
  difficulty?: number
  estimatedTime?: number
  prerequisites?: string[]
  mastery?: number
  masteryThreshold?: number
  status?: string
  nodeType?: string
  progress?: number
  order?: number
  totalNodes?: number
  pathTitle?: string
  pathGoal?: string
  pathProgressPercent?: number
  completedNodes?: number
  remainingNodes?: number
  pathTimeLeft?: number
  previousNodeName?: string
  previousNodeStatus?: string
  nextNodeId?: number | null
  nextNodeName?: string
  nextNodeStatus?: string
  resources?: Array<{
    id: number
    resource_type: string
    title: string
    status: string
    is_cached: boolean
  }>
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
  mindmap: '思维导图',
  code: '代码练习',
  video: '教学视频',
}

const STATUS_LABELS: Record<string, { label: string; color: string }> = {
  not_started: { label: '未开始', color: 'text-gray-500' },
  in_progress: { label: '学习中', color: 'text-blue-600' },
  completed: { label: '已完成', color: 'text-green-600' },
  needs_review: { label: '需复习', color: 'text-amber-600' },
  skipped: { label: '已跳过', color: 'text-gray-400' },
}

const PathDetailPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const node = data as unknown as NodeDetail
  // eslint-disable-next-line no-console
  console.log('[path-panel-debug] PathDetailPanel render', {
    nodeId: node?.nodeId,
    nodeName: node?.nodeName,
    dataKeys: Object.keys(data || {}),
    hasNodeId: !!node?.nodeId,
  })
  const [loadingResources, setLoadingResources] = useState(false)
  const [resources, setResources] = useState(node?.resources || [])
  const [guidance, setGuidance] = useState<string>('')
  const [loadingGuidance, setLoadingGuidance] = useState(false)
  const [guidanceMode, setGuidanceMode] = useState<'default' | 'detail' | 'next'>('default')

  const statusInfo = STATUS_LABELS[node?.status || 'not_started'] || STATUS_LABELS.not_started
  const mastery = node?.mastery ?? 0
  const masteryThreshold = node?.masteryThreshold ?? 0.7
  const nodeTypeLabel = node?.nodeType === 'review' ? '复习节点' : '新学节点'
  const currentStepLabel = node?.order && node?.totalNodes ? `第 ${node.order} / ${node.totalNodes} 步` : '当前学习节点'
  const anchorDependency = node?.prerequisites && node.prerequisites.length > 0
    ? `建立在「${node.prerequisites.slice(0, 2).join('」「')}」之上，需要先确认这些基础已掌握`
    : node?.previousNodeName
      ? `承接上一站「${node.previousNodeName}」的知识，是路径中的自然延伸`
      : '这是当前路径的起始节点，没有强前置依赖'
  const anchorNext = node?.nextNodeName
    ? `学好本节后，才能顺利进入「${node.nextNodeName}」的学习`
    : '掌握本节点后，路径中的核心知识体系就基本搭建完成'
  const anchorPractice = node?.nodeType === 'review'
    ? '复习节点用来确认前面学过的内容是否真正掌握，避免学了就忘'
    : `「${node.nodeName}」是编程中的基础能力点，实际开发中会频繁用到`
  const RESOURCE_TIME: Record<string, number> = { doc: 15, video: 10, mindmap: 8, quiz: 10, code: 15 }
  const sortedResources = [...resources].sort((a, b) => {
    const priority: Record<string, number> = { doc: 0, video: 1, mindmap: 2, quiz: 3, code: 4 }
    return (priority[a.resource_type] ?? 99) - (priority[b.resource_type] ?? 99)
  })
  const resourceSteps = sortedResources.map(r => {
    const label = RESOURCE_LABELS[r.resource_type] || r.resource_type
    const time = RESOURCE_TIME[r.resource_type] || 10
    return r.is_cached
      ? `完成「${label}」资源（约 ${time} 分钟），${r.title}`
      : `生成并学习「${label}」资源（约 ${time} 分钟）`
  })
  const actionSteps = [
    node?.prerequisites && node.prerequisites.length > 0
      ? `先快速确认前置知识：${node.prerequisites.slice(0, 3).join('、')}`
      : '先花 2-3 分钟确认你对这个知识点的已有基础',
    ...(resourceSteps.length > 0
      ? resourceSteps
      : ['还没有资源，点击下方”生成资源”补齐学习动作']),
    mastery < masteryThreshold
      ? `当前掌握度 ${Math.round(mastery * 100)}%，建议完成以上步骤后再推进`
      : `当前掌握度 ${Math.round(mastery * 100)}%，完成后可以准备进入下一步`,
  ].filter(Boolean)
  const completionChecks = [
    `掌握度至少达到 ${Math.round(masteryThreshold * 100)}%`,
    node?.nodeType === 'review' ? '能回忆关键点并独立完成至少一次复盘/练习' : '能复述核心概念，并完成一次基础练习或例题',
    node?.nextNodeName ? `完成后进入「${node.nextNodeName}」前，不再对当前节点感到明显生疏` : '完成后可以进入总结或回顾阶段',
  ]
  const nextStepAdvice = node?.nextNodeName
    ? `完成当前节点后，建议直接衔接到「${node.nextNodeName}」，避免中断路径节奏。`
    : '当前节点后没有明确下一站，可以把重点放在复习总结和查漏补缺。'
  // 获取/生成节点资源
  const handleLoadResources = useCallback(async () => {
    if (!node?.nodeId) return
    setLoadingResources(true)
    try {
      const resp = await getNodeResources(node.nodeId)
      if (resp.code === 200 && resp.data) {
        setResources(resp.data.resources || [])
      }
    } catch (e) {
      console.error('加载资源失败:', e)
    } finally {
      setLoadingResources(false)
    }
  }, [node?.nodeId])

  // 生成学习指导
  const handleGenerateGuidance = useCallback(async (
    mode: 'default' | 'detail' | 'next' = 'default',
  ) => {
    if (!node?.nodeName) return
    setLoadingGuidance(true)
    setGuidanceMode(mode)
    try {
      const { explainText } = await import('../../api/chat')
      const extraInstruction = mode === 'detail'
        ? '用户表示还没看懂，请把当前节点该怎么学拆得更细一点，步骤更具体。'
        : mode === 'next'
          ? '请重点说明当前节点完成后下一步该做什么，以及怎么判断可以进入下一节点。'
          : '请给出整体规划建议。'
      const resp = await explainText(
        node.nodeName,
        undefined,
        undefined,
        [
          '这是学习路径页面的右侧规划面板，请输出“规划型”内容，而不是单纯解释型内容。',
          `当前节点：${node.nodeName}`,
          node.pathTitle ? `所属路径：${node.pathTitle}` : '',
          node.pathGoal ? `路径目标：${node.pathGoal}` : '',
          node.order && node.totalNodes ? `当前处于第 ${node.order}/${node.totalNodes} 步` : '',
          node.previousNodeName ? `上一节点：${node.previousNodeName}` : '',
          node.nextNodeName ? `下一节点：${node.nextNodeName}` : '',
          node.prerequisites && node.prerequisites.length > 0 ? `前置知识：${node.prerequisites.join('、')}` : '',
          extraInstruction,
          `请给出：1) 当前节点的学习目标 2) 推荐学习顺序 3) 本节点完成标准 4) 做完后下一步怎么走`,
        ].filter(Boolean).join('\n'),
      )
      if (resp.code === 200 && resp.data) {
        setGuidance(typeof resp.data === 'string' ? resp.data : (resp.data as any).explanation || '')
      }
    } catch (e) {
      console.error('生成学习指导失败:', e)
    } finally {
      setLoadingGuidance(false)
      setGuidanceMode('default')
    }
  }, [node])

  useEffect(() => {
    setResources(node?.resources || [])
    setGuidance('')
  }, [node?.pathId, node?.nodeId])

  if (!node?.nodeId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm px-6">
        <AlertCircle className="w-5 h-5 mb-2" />
        <p className="text-center">点击学习路径中的知识点节点，右侧会展示该知识点的详情、资源和学习指导</p>
      </div>
    )
  }

  return (
    <div className="p-4 pb-20 space-y-4 text-sm">
      <div>
        <h3 className="text-base font-semibold text-gray-800 mb-1">{node.nodeName}</h3>
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <span className="text-xs px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 border border-brand-200">
            {currentStepLabel}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-violet-50 text-violet-700 border border-violet-200">
            {nodeTypeLabel}
          </span>
          <span className={`text-xs font-medium ${statusInfo.color}`}>{statusInfo.label}</span>
          {node.difficulty !== undefined && (
            <span className="text-xs text-gray-400">
              难度: {node.difficulty <= 0.3 ? '入门' : node.difficulty <= 0.6 ? '进阶' : '高级'}
            </span>
          )}
          {node.estimatedTime !== undefined && (
            <span className="text-xs text-gray-400 flex items-center gap-0.5">
              <Clock className="w-3 h-3" />
              {node.estimatedTime}分钟
            </span>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white p-3">
        <div className="flex items-center gap-2 mb-2 text-gray-700">
          <Compass className="w-4 h-4 text-brand-500" />
          <p className="text-xs font-semibold">这一步为什么在这里</p>
        </div>
        <div className="space-y-2.5 text-xs text-gray-700 leading-6">
          <div>
            <span className="text-[11px] font-medium text-brand-600">前置依赖</span>
            <p className="mt-0.5">{anchorDependency}</p>
          </div>
          <div>
            <span className="text-[11px] font-medium text-brand-600">后续作用</span>
            <p className="mt-0.5">{anchorNext}</p>
          </div>
          <div>
            <span className="text-[11px] font-medium text-brand-600">实战价值</span>
            <p className="mt-0.5">{anchorPractice}</p>
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white p-3">
        <div className="flex items-center gap-2 mb-2 text-gray-700">
          <Flag className="w-4 h-4 text-amber-500" />
          <p className="text-xs font-semibold">现在该怎么推进</p>
        </div>
        <ol className="space-y-2">
          {actionSteps.map((item, index) => (
            <li key={`${item}-${index}`} className="text-xs text-gray-700 leading-6 flex gap-2">
              <span className="w-4 h-4 rounded-full bg-brand-50 text-brand-700 flex items-center justify-center text-[10px] flex-shrink-0 mt-0.5">
                {index + 1}
              </span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="rounded-xl border border-gray-100 bg-white p-3">
        <div className="flex items-center gap-2 mb-2 text-gray-700">
          <GitBranch className="w-4 h-4 text-violet-500" />
          <p className="text-xs font-semibold">通过标准与衔接</p>
        </div>
        {node.prerequisites && node.prerequisites.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 mb-3">
            {node.prerequisites.map((pre, i) => (
              <span key={i} className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                {pre}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400 mb-3">当前节点没有强依赖前置知识，可以直接推进。</p>
        )}
        <ul className="space-y-2 mb-3">
          {completionChecks.map((item, index) => (
            <li key={`${item}-${index}`} className="text-xs text-gray-700 leading-6 flex gap-2">
              <span className="text-violet-500 flex-shrink-0">-</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
        <div className="rounded-lg border border-violet-100 bg-violet-50/50 px-3 py-3 text-xs text-gray-700 leading-6">
          {nextStepAdvice}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-xs font-medium text-gray-600 flex items-center gap-1">
            <BookOpen className="w-3 h-3" />资源动作
          </p>
          <button
            onClick={handleLoadResources}
            disabled={loadingResources}
            className="text-xs text-brand-600 hover:text-brand-700 disabled:opacity-50"
          >
            {loadingResources ? (
              <Loader2 className="w-3 h-3 animate-spin inline" />
            ) : (
              resources.length > 0 ? '刷新资源' : '生成资源'
            )}
          </button>
        </div>
        {sortedResources.length > 0 ? (
          <div className="space-y-1.5">
            {sortedResources.map((res, index) => (
              <div
                key={res.id}
                className="flex items-center gap-2 px-2.5 py-2 rounded-lg border border-gray-100 hover:border-gray-200 transition-colors"
              >
                <span className="text-gray-400">{RESOURCE_ICONS[res.resource_type] || <FileText className="w-3.5 h-3.5" />}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-gray-700 truncate">
                    {index === 0 ? '优先：' : ''}{RESOURCE_LABELS[res.resource_type] || res.resource_type}
                  </p>
                  <p className="text-[11px] text-gray-400 truncate">{res.title}</p>
                </div>
                {res.is_cached ? (
                  <CheckCircle className="w-3 h-3 text-green-400 flex-shrink-0" />
                ) : (
                  <span className="text-xs text-gray-400">待生成</span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-400">还没有可执行的学习资源，点击“生成资源”补齐本节点动作</p>
        )}
      </div>

      <div>
        <div className="flex items-center justify-between mb-1.5">
          <p className="text-xs font-medium text-gray-600">AI 路径建议</p>
          <button
            onClick={() => handleGenerateGuidance()}
            disabled={loadingGuidance}
            className="text-xs text-brand-600 hover:text-brand-700 disabled:opacity-50"
          >
            {loadingGuidance ? (
              <Loader2 className="w-3 h-3 animate-spin inline" />
            ) : (
              guidance ? '重新生成' : 'AI 生成指导'
            )}
          </button>
        </div>
        {loadingGuidance ? (
          <div className="flex items-center gap-2 text-xs text-gray-400 py-3">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            <span>
              {guidanceMode === 'detail'
                ? 'AI 正在把当前节点的学习步骤拆得更细...'
                : guidanceMode === 'next'
                  ? 'AI 正在补充下一步学习安排...'
                  : 'AI 正在生成本节点的学习规划...'}
            </span>
          </div>
        ) : guidance ? (
          <div className="space-y-2">
            <div className="text-xs text-gray-600 leading-relaxed bg-gray-50 rounded-lg p-3">
              <MarkdownText content={guidance} />
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={() => handleGenerateGuidance('detail')}
                className="px-2.5 py-1 text-[11px] rounded-full border border-brand-200 bg-white text-brand-700 hover:bg-brand-50 transition-colors"
              >
                没看懂，再细一点
              </button>
              <button
                onClick={() => handleGenerateGuidance('next')}
                className="px-2.5 py-1 text-[11px] rounded-full border border-brand-200 bg-white text-brand-700 hover:bg-brand-50 transition-colors"
              >
                下一步怎么学
              </button>
            </div>
          </div>
        ) : (
          <p className="text-xs text-gray-400">点击“AI 生成指导”查看这一步该怎么推进，以及什么时候进入下一步</p>
        )}
      </div>
    </div>
  )
}

export default PathDetailPanel
