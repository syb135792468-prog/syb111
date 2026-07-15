import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAppStore } from '../../stores/app'
import { explainText } from '../../api/chat'
import MarkdownText from '../common/MarkdownText'
import {
  BookOpen,
  Lightbulb,
  FileText,
  Loader2,
  Sparkles,
  RotateCcw,
  GitBranch,
} from 'lucide-react'

type PromptMode = 'default' | 'refine' | 'example'

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
}

function clampText(text: string, maxLength: number): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) return ''
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
}

function buildContext(params: {
  topic: string
  parentTopic: string
  childTopics: string[]
  relationTrail: string[]
  definition: string
  syntax: string
  examples: string[]
  pitfalls: string[]
  advice: string
  resourceId?: number
  nodeId: string
  promptMode: PromptMode
}) {
  const promptInstruction = params.promptMode === 'refine'
    ? '请把解释讲得更细一点，更白话一点，假设用户第一次没有完全看懂。'
    : params.promptMode === 'example'
      ? '请重点补充一个非常具体的小例子，并指出最容易混淆的地方。'
      : '请保持解释简洁清楚，突出知识点之间的关系。'

  return [
    '这是思维导图页面右侧的知识点详情面板。',
    '请用中文输出解释型内容，不要输出学习计划或任务拆解。',
    '请重点说明：1. 这个知识点是什么 2. 它和上下级节点的关系 3. 学习时先抓什么 4. 常见误区 5. 一个简短例子。',
    promptInstruction,
    `知识点：${params.topic}`,
    params.parentTopic ? `上一级节点：${params.parentTopic}` : '',
    params.childTopics.length > 0 ? `下一级节点：${params.childTopics.slice(0, 6).join('、')}` : '',
    params.relationTrail.length > 0 ? `当前位置链路：${params.relationTrail.join(' > ')}` : '',
    params.definition ? `定义：${clampText(params.definition, 320)}` : '',
    params.syntax ? `语法：${clampText(params.syntax, 220)}` : '',
    params.examples.length > 0 ? `示例：${clampText(params.examples[0], 260)}` : '',
    params.pitfalls.length > 0 ? `常见坑点：${params.pitfalls.slice(0, 3).join('；')}` : '',
    params.advice ? `学习建议：${clampText(params.advice, 160)}` : '',
    params.resourceId ? `资源ID：${params.resourceId}` : '',
    params.nodeId ? `节点ID：${params.nodeId}` : '',
  ].filter(Boolean).join('\n\n')
}

const MindmapDetailPanel: React.FC = () => {
  const { data } = useAppStore((state) => state.rightPanel)
  const updateRightPanelData = useAppStore((state) => state.updateRightPanelData)

  const nodeId = typeof data?.nodeId === 'string' || typeof data?.nodeId === 'number'
    ? String(data.nodeId)
    : ''
  const resourceId = typeof data?.resourceId === 'number' ? data.resourceId : undefined
  const topic = typeof data?.topic === 'string' ? data.topic : ''
  const definition = typeof data?.definition === 'string' ? data.definition : ''
  const syntax = typeof data?.syntax === 'string' ? data.syntax : ''
  const examples = asStringArray(data?.examples)
  const pitfalls = asStringArray(data?.pitfalls)
  const advice = typeof data?.advice === 'string' ? data.advice : ''
  const depth = typeof data?.depth === 'number' ? data.depth : 0
  const parentTopic = typeof data?.parentTopic === 'string' ? data.parentTopic : ''
  const childTopics = asStringArray(data?.childTopics)
  const ancestorTopics = asStringArray(data?.ancestorTopics)
  const cachedDeepExplanation = typeof data?.deepExplanation === 'string' ? data.deepExplanation : ''

  const [deepExplanation, setDeepExplanation] = useState(cachedDeepExplanation)
  const [loadingExplanation, setLoadingExplanation] = useState(false)
  const [explanationError, setExplanationError] = useState('')
  const [activePrompt, setActivePrompt] = useState<PromptMode>('default')

  const requestKeyRef = useRef('')
  const autoRequestedNodeRef = useRef('')

  const nodeKey = `${nodeId}::${topic}`
  const relationTrail = useMemo(
    () => [...ancestorTopics.slice(0, -1), topic].filter(Boolean),
    [ancestorTopics, topic],
  )

  const levelLabel = depth <= 0
    ? '根主题'
    : depth === 1
      ? '一级知识点'
      : depth === 2
        ? '二级知识点'
        : '细分知识点'

  const learningHints = useMemo(
    () => [advice, pitfalls[0] ? `易错点：${pitfalls[0]}` : ''].filter(Boolean),
    [advice, pitfalls],
  )

  const generateDeepExplanation = useCallback(async (
    force = false,
    promptMode: PromptMode = 'default',
  ) => {
    if (!topic) return

    if (!force && cachedDeepExplanation) {
      setDeepExplanation(cachedDeepExplanation)
      setExplanationError('')
      return
    }

    const requestKey = `${nodeKey}:${promptMode}:${Date.now()}`
    requestKeyRef.current = requestKey

    setLoadingExplanation(true)
    setExplanationError('')
    setActivePrompt(promptMode)

    try {
      const context = buildContext({
        topic,
        parentTopic,
        childTopics,
        relationTrail,
        definition,
        syntax,
        examples,
        pitfalls,
        advice,
        resourceId,
        nodeId,
        promptMode,
      })

      const resp = await explainText(`请深入解释知识点：${topic}`, 0, undefined, context)
      if (requestKeyRef.current !== requestKey) return

      const explanation = resp.code === 200 && resp.data
        ? (typeof resp.data === 'string' ? resp.data : resp.data.explanation || '').trim()
        : ''

      if (explanation) {
        setDeepExplanation(explanation)

        const currentPanelData = useAppStore.getState().rightPanel.data
        if (
          String(currentPanelData?.nodeId || '') === nodeId &&
          String(currentPanelData?.topic || '') === topic
        ) {
          updateRightPanelData({ deepExplanation: explanation })
        }
      } else {
        setExplanationError(resp.message || '生成讲解失败')
      }
    } catch {
      if (requestKeyRef.current !== requestKey) return
      setExplanationError('生成讲解失败，请稍后重试')
    } finally {
      if (requestKeyRef.current !== requestKey) return
      setLoadingExplanation(false)
      setActivePrompt('default')
    }
  }, [
    topic,
    cachedDeepExplanation,
    nodeKey,
    parentTopic,
    childTopics,
    relationTrail,
    definition,
    syntax,
    examples,
    pitfalls,
    advice,
    resourceId,
    nodeId,
    updateRightPanelData,
  ])

  useEffect(() => {
    requestKeyRef.current = ''
    autoRequestedNodeRef.current = ''
    setDeepExplanation(cachedDeepExplanation)
    setLoadingExplanation(false)
    setExplanationError('')
    setActivePrompt('default')
  }, [nodeKey, cachedDeepExplanation])

  useEffect(() => {
    if (!topic) return
    if (cachedDeepExplanation) return
    if (autoRequestedNodeRef.current === nodeKey) return

    autoRequestedNodeRef.current = nodeKey
    generateDeepExplanation()
  }, [topic, cachedDeepExplanation, nodeKey, generateDeepExplanation])

  if (!topic) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <BookOpen className="w-8 h-8 mb-3 opacity-30" />
        <p className="text-sm text-center">点击思维导图中的节点查看知识点详情</p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      <div className="pb-3 border-b border-gray-100 space-y-2">
        <h3 className="text-base font-semibold text-gray-800">{topic}</h3>
        <div className="flex flex-wrap gap-2">
          <span className="px-2 py-1 rounded-full bg-indigo-50 text-indigo-600 text-[11px] font-medium">
            {levelLabel}
          </span>
          {parentTopic && (
            <span className="px-2 py-1 rounded-full bg-emerald-50 text-emerald-600 text-[11px] font-medium">
              上级：{parentTopic}
            </span>
          )}
          {childTopics.length > 0 && (
            <span className="px-2 py-1 rounded-full bg-amber-50 text-amber-700 text-[11px] font-medium">
              下级：{childTopics.length} 项
            </span>
          )}
        </div>
      </div>

      <Section icon={<BookOpen className="w-3.5 h-3.5" />} label="节点解释" color="text-blue-600">
        {definition ? (
          <div className="rounded-lg border border-blue-100 bg-blue-50/60 px-3 py-3 text-xs text-gray-700 leading-6">
            <MarkdownText content={definition} />
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-3 text-xs text-gray-400">
            当前节点没有现成定义，下面会由 AI 自动补充解释。
          </div>
        )}
        {examples.length > 0 && (
          <div className="mt-3">
            <p className="text-[11px] text-gray-400 mb-1.5">代码速览</p>
            <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-3 overflow-x-auto font-mono whitespace-pre-wrap border border-gray-800">
              {examples[0]}
            </pre>
          </div>
        )}
      </Section>

      {relationTrail.length > 1 && (
        <Section icon={<GitBranch className="w-3.5 h-3.5" />} label="知识路径" color="text-violet-600">
          <div className="rounded-lg border border-violet-100 bg-violet-50/50 px-3 py-2.5">
            <div className="flex flex-wrap items-center gap-1 text-xs">
              {relationTrail.map((item, index) => (
                <React.Fragment key={`${item}-${index}`}>
                  {index > 0 && <span className="text-violet-300 mx-0.5">/</span>}
                  <span className={index === relationTrail.length - 1 ? 'text-violet-700 font-medium' : 'text-violet-500'}>
                    {item}
                  </span>
                </React.Fragment>
              ))}
            </div>
          </div>
        </Section>
      )}

      {learningHints.length > 0 && (
        <Section icon={<Lightbulb className="w-3.5 h-3.5" />} label="学习提醒" color="text-emerald-600">
          <div className="rounded-lg border border-emerald-100 bg-emerald-50/50 px-3 py-3">
            <ul className="space-y-2">
              {learningHints.map((hint, index) => (
                <li key={`${hint}-${index}`} className="text-xs text-gray-700 leading-6 flex gap-2">
                  <span className="text-emerald-500 flex-shrink-0">-</span>
                  <span>{hint}</span>
                </li>
              ))}
            </ul>
          </div>
        </Section>
      )}

      <Section
        icon={<Sparkles className="w-3.5 h-3.5" />}
        label="进一步解释"
        color="text-emerald-600"
        action={(
          <button
            onClick={() => generateDeepExplanation(true)}
            disabled={loadingExplanation}
            className="inline-flex items-center gap-1 text-[11px] text-emerald-600 hover:text-emerald-700 disabled:opacity-50"
          >
            {loadingExplanation ? <Loader2 className="w-3 h-3 animate-spin" /> : <RotateCcw className="w-3 h-3" />}
            {deepExplanation ? '重新生成' : '生成讲解'}
          </button>
        )}
      >
        {loadingExplanation ? (
          <div className="rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-3 text-xs text-emerald-700">
            <div className="flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>
                {activePrompt === 'refine'
                  ? '正在把这个知识点讲得更细一点...'
                  : activePrompt === 'example'
                    ? '正在补充更具体的例子...'
                    : '正在补充这个知识点的通俗解释和上下级关系...'}
              </span>
            </div>
          </div>
        ) : deepExplanation ? (
          <>
            <div className="text-xs text-gray-700 leading-6 rounded-lg border border-emerald-100 bg-emerald-50/40 p-3">
              <MarkdownText content={deepExplanation} />
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <button
                onClick={() => generateDeepExplanation(true, 'refine')}
                className="px-2.5 py-1 text-[11px] rounded-full border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50 transition-colors"
              >
                没看懂，再细一点
              </button>
              <button
                onClick={() => generateDeepExplanation(true, 'example')}
                className="px-2.5 py-1 text-[11px] rounded-full border border-emerald-200 bg-white text-emerald-700 hover:bg-emerald-50 transition-colors"
              >
                给我一个例子
              </button>
            </div>
          </>
        ) : explanationError ? (
          <div className="rounded-lg border border-red-100 bg-red-50 px-3 py-3 text-xs text-red-600">
            {explanationError}
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-gray-200 bg-gray-50 px-3 py-3 text-xs text-gray-400">
            点击节点后，右侧会自动补充更通俗的解释。
          </div>
        )}
      </Section>

      {(examples.length > 1 || pitfalls.length > 0) && (
        <Section icon={<FileText className="w-3.5 h-3.5" />} label="更多示例 / 易错点" color="text-amber-600">
          <div className="space-y-3">
            {examples.length > 1 && (
              <div className="space-y-2">
                {examples.slice(1).map((example, index) => (
                  <pre key={index} className="text-xs bg-gray-50 border border-gray-100 rounded-lg p-3 overflow-x-auto font-mono text-gray-800 whitespace-pre-wrap">
                    {example}
                  </pre>
                ))}
              </div>
            )}

            {pitfalls.length > 0 && (
              <ul className="space-y-1.5">
                {pitfalls.map((item, index) => (
                  <li key={index} className="text-xs text-gray-700 leading-relaxed flex gap-2">
                    <span className="text-amber-500 flex-shrink-0">-</span>
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </Section>
      )}
    </div>
  )
}

const Section: React.FC<{
  icon: React.ReactNode
  label: string
  color: string
  children: React.ReactNode
  action?: React.ReactNode
}> = ({ icon, label, color, children, action }) => (
  <div>
    <div className={`flex items-center justify-between gap-2 mb-2 ${color}`}>
      <div className="flex items-center gap-1.5 min-w-0">
        {icon}
        <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
      </div>
      {action}
    </div>
    {children}
  </div>
)

export default MindmapDetailPanel
