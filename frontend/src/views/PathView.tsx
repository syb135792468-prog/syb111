import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatStore } from '../stores/chat'
import { useAppStore } from '../stores/app'
import { useLearningCenterStore } from '../stores/learningCenter'
import AppHeader from '../components/layout/AppHeader'
import PathTimeline from '../components/path/PathTimeline'
import RecommendedPath from '../components/path/RecommendedPath'
import { PathNodeData } from '../components/path/PathStep'
import {
  listLearningPaths, getLearningPath, generateLearningPath,
  getNodeResources, completePathNode, deleteLearningPath, reorderPath,
  evaluatePath, createAdvancePath,
  type LearningPathData, type PathNode, type PathEvaluation,
} from '../api/learningPath'
import {
  Route, MessageCircle, Plus, Trash2, ChevronRight,
  Clock, CheckCircle, Target, Loader2, RefreshCw, AlertCircle, X, Shuffle, Award, Sparkles, ArrowRight
} from 'lucide-react'

// --- 类型转换：后端PathNode -> 前端PathNodeData ---
function toStepData(node: PathNode): PathNodeData {
  return {
    id: node.id,
    order: node.order,
    type: node.node_type,
    node_type: node.node_type,
    knowledge_point: node.knowledge_point,
    estimated_time: node.estimated_time,
    estimated_time_min: node.estimated_time,
    status: node.status,
    mastery: node.mastery,
    mastery_threshold: node.mastery_threshold,
    progress: node.progress,
    difficulty: node.difficulty,
    prerequisites: node.prerequisites,
    resources: node.resources,
  }
}

// 画像 knowledge_level 中文映射（与后端 PathAgent 保持一致）
const KNOWLEDGE_LEVEL_LABELS: Record<string, string> = {
  beginner: '零基础',
  intermediate: '有基础',
  advanced: '进阶',
}

// --- 学习方向定义 ---
const DIRECTIONS = [
  {
    label: 'Python 基础入门',
    topic: 'Python基础',
    description: '系统学习全部基础知识',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断（if/elif/else）', '循环（for/while）',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '面向对象基础', '类与对象', '继承与多态', '异常处理', '文件操作', '模块与包',
    ],
  },
  {
    label: '数据处理与分析',
    topic: '数据分析',
    description: '文件读写、数据结构、字符串处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断（if/elif/else）', '循环（for/while）',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '文件操作', '模块与包',
    ],
  },
  {
    label: '自动化脚本',
    topic: '自动化',
    description: '条件循环、函数封装、异常处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断（if/elif/else）', '循环（for/while）',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '异常处理', '文件操作', '模块与包',
    ],
  },
  {
    label: '面向对象编程',
    topic: '面向对象',
    description: '类、继承、多态、异常处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断（if/elif/else）', '循环（for/while）',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合',
      '面向对象基础', '类与对象', '继承与多态', '异常处理', '模块与包',
    ],
  },
]

// --- 组件 ---
const PathView: React.FC = () => {
  const navigate = useNavigate()
  const chatStore = useChatStore()
  const syncPaths = useLearningCenterStore((state) => state.syncPaths)
  const pathStatsById = useLearningCenterStore((state) => state.pathStatsById)
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)

  const [paths, setPaths] = useState<LearningPathData[]>([])
  const [activePathId, setActivePathId] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [showNewForm, setShowNewForm] = useState(false)
  const [newTopic, setNewTopic] = useState('Python基础')
  const [formTab, setFormTab] = useState<'quick' | 'survey'>('quick')
  const [directionIdx, setDirectionIdx] = useState<number | null>(null)
  const [masteredPoints, setMasteredPoints] = useState<Set<string>>(new Set())
  const [customKpInput, setCustomKpInput] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [reordering, setReordering] = useState(false)
  const [evaluation, setEvaluation] = useState<PathEvaluation | null>(null)
  const [evaluating, setEvaluating] = useState(false)
  const [advancingTopic, setAdvancingTopic] = useState<string | null>(null)

  // 加载路径列表
  const loadPaths = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listLearningPaths()
      if (resp.code === 200 && resp.data) {
        const loadedPaths = resp.data.paths || []
        setPaths(loadedPaths)
        // 自动选中最新路径（如果没有当前选中的，或当前选中不存在）
        setActivePathId(prev => {
          if (prev && loadedPaths.find(p => p.id === prev)) return prev
          return loadedPaths.length > 0 ? loadedPaths[0].id : null
        })
      }
    } catch (e) {
      console.error('加载路径失败:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadPaths()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    syncPaths(paths)
  }, [paths, syncPaths])

  // 切换路径时清空评估结果
  useEffect(() => {
    setEvaluation(null)
  }, [activePathId])

  // 当 chatStore 收到 SSE 路径事件时，重新从 API 加载路径列表（确保数据已持久化）
  useEffect(() => {
    if (chatStore.lastLearningPath) {
      loadPaths()
    }
  }, [chatStore.lastLearningPath]) // eslint-disable-line react-hooks/exhaustive-deps

  // 当前选中的路径
  const activePath = useMemo(
    () => paths.find(p => p.id === activePathId) || paths[0] || null,
    [paths, activePathId]
  )

  // 转换为时间线步骤数据
  const pathSteps = useMemo((): PathNodeData[] => {
    if (!activePath?.nodes) return []
    return activePath.nodes.map(toStepData)
  }, [activePath])

  // 统计数据
  const stats = useMemo(() => {
    if (!activePath) return { completed: 0, total: 0, timeLeft: 0, percent: 0 }
    const syncedStats = pathStatsById[activePath.id]
    const completed = activePath.nodes.filter(n => n.status === 'completed').length
    const total = activePath.total_nodes || activePath.nodes.length
    const timeLeft = activePath.nodes
      .filter(n => n.status !== 'completed')
      .reduce((sum, n) => sum + n.estimated_time, 0)
    return {
      completed: syncedStats?.completedNodes ?? completed,
      total: syncedStats?.totalNodes ?? total,
      timeLeft: syncedStats?.timeLeft ?? timeLeft,
      percent: syncedStats?.pathProgress ?? activePath.progress_percent ?? (total > 0 ? Math.round((completed / total) * 100) : 0),
    }
  }, [activePath, pathStatsById])

  // 生成新路径
  const handleGenerate = useCallback(async () => {
    setGenerating(true)
    setError(null)
    try {
      const req: Record<string, unknown> = {}
      if (formTab === 'survey' && directionIdx !== null) {
        req.topic = DIRECTIONS[directionIdx].topic
        if (masteredPoints.size > 0) {
          req.mastered_points = Array.from(masteredPoints)
        }
      } else {
        req.topic = newTopic
      }
      const resp = await generateLearningPath(req)
      if (resp.code === 200 && resp.data) {
        // 重新加载路径列表（确保从 DB 获取完整数据）
        await loadPaths()
        setActivePathId(resp.data!.id)
        setShowNewForm(false)
        setMasteredPoints(new Set())
        setDirectionIdx(null)
        setCustomKpInput('')
        setError(null)
      } else {
        setError(resp.message || '生成失败，请稍后重试')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '网络错误，请检查连接后重试'
      setError(msg)
      console.error('生成路径失败:', e)
    } finally {
      setGenerating(false)
    }
  }, [newTopic, formTab, directionIdx, masteredPoints, loadPaths])

  // 点击节点：加载资源 + 打开右侧详情面板
  const handleNodeClick = useCallback(async (nodeId: number) => {
    if (!activePath) return
    const node = activePath.nodes.find(n => n.id === nodeId)
    if (!node) return
    const sortedNodes = [...activePath.nodes].sort((a, b) => a.order - b.order)
    const currentIndex = sortedNodes.findIndex((n) => n.id === nodeId)
    const previousNode = currentIndex > 0 ? sortedNodes[currentIndex - 1] : null
    const nextNode = currentIndex >= 0 && currentIndex < sortedNodes.length - 1 ? sortedNodes[currentIndex + 1] : null
    const remainingNodes = sortedNodes.filter((n) => n.order > node.order && n.status !== 'completed').length
    const completedNodes = sortedNodes.filter((n) => n.status === 'completed').length
    const pathTimeLeft = sortedNodes
      .filter((n) => n.status !== 'completed')
      .reduce((sum, n) => sum + n.estimated_time, 0)

    // 打开右侧知识点详情面板
    const panelData = {
      pathId: activePath.id,
      nodeId: node.id,
      nodeName: node.knowledge_point,
      description: node.description,
      difficulty: node.difficulty,
      estimatedTime: node.estimated_time,
      prerequisites: node.prerequisites,
      mastery: node.mastery,
      masteryThreshold: node.mastery_threshold,
      status: node.status,
      resources: node.resources,
      nodeType: node.node_type,
      progress: node.progress,
      order: node.order,
      totalNodes: sortedNodes.length,
      pathTitle: activePath.title,
      pathGoal: activePath.goal || activePath.description || activePath.topic,
      pathProgressPercent: pathStatsById[activePath.id]?.pathProgress ?? activePath.progress_percent,
      completedNodes,
      remainingNodes,
      pathTimeLeft,
      previousNodeName: previousNode?.knowledge_point || '',
      previousNodeStatus: previousNode?.status || '',
      nextNodeId: nextNode?.id || null,
      nextNodeName: nextNode?.knowledge_point || '',
      nextNodeStatus: nextNode?.status || '',
    }
    // eslint-disable-next-line no-console
    console.log('[path-panel-debug] handleNodeClick', {
      nodeId: node.id,
      pathId: activePath.id,
      routeKey: useAppStore.getState().rightPanel.routeKey,
      isCollapsed: useAppStore.getState().rightPanel.isCollapsed,
      isOpen: useAppStore.getState().rightPanel.isOpen,
      panelDataKeys: Object.keys(panelData),
    })
    useAppStore.getState().openRightPanel('path-detail', panelData)
    // eslint-disable-next-line no-console
    console.log('[path-panel-debug] after openRightPanel', {
      routeKey: useAppStore.getState().rightPanel.routeKey,
      type: useAppStore.getState().rightPanel.type,
      dataNodeId: (useAppStore.getState().rightPanel.data as Record<string, unknown>).nodeId,
      isCollapsed: useAppStore.getState().rightPanel.isCollapsed,
      isOpen: useAppStore.getState().rightPanel.isOpen,
    })

    // 如果没有资源，异步加载
    if (!node.resources || node.resources.length === 0) {
      try {
        const resp = await getNodeResources(nodeId)
        if (resp.code === 200 && resp.data) {
          setPaths(prev => prev.map(p => {
            if (p.id !== activePathId) return p
            return {
              ...p,
              nodes: p.nodes.map(n =>
                n.id === nodeId ? { ...n, resources: resp.data!.resources } : n
              ),
            }
          }))
          // 同步更新面板数据
          useAppStore.getState().updateRightPanelData({ resources: resp.data!.resources })
        }
      } catch (e) {
        console.error('加载节点资源失败:', e)
      }
    }
  }, [activePath, activePathId])

  // 点击资源：跳转到对应页面
  const handleResourceClick = useCallback((nodeId: number, resourceType: string) => {
    // 根据资源类型跳转到对应页面
    if (resourceType === 'quiz') navigate('/resources')
    else if (resourceType === 'mindmap') navigate('/mindmap')
    else if (resourceType === 'code') navigate('/playground')
    else navigate('/resources')
  }, [navigate])

  // 标记节点完成
  const handleNodeComplete = useCallback(async (nodeId: number) => {
    try {
      const resp = await completePathNode(nodeId)
      if (resp.code === 200 && resp.data) {
        recordLearningEvent({
          sourcePage: 'path',
          actionType: 'path_node_completed',
          topic: resp.data.nodes.find((node) => node.id === nodeId)?.knowledge_point,
          knowledgePoint: resp.data.nodes.find((node) => node.id === nodeId)?.knowledge_point,
          pathId: resp.data.id,
          nodeId,
        })
        // 更新本地路径数据
        setPaths(prev => prev.map(p => {
          if (p.id !== resp.data!.id) return p
          return resp.data!
        }))
      }
    } catch (e) {
      console.error('标记节点完成失败:', e)
    }
  }, [recordLearningEvent])

  // 路径数据更新（前置测试答对跳过 / 取消跳过 触发）
  const handlePathUpdated = useCallback((path: LearningPathData) => {
    setPaths(prev => prev.map(p => p.id === path.id ? path : p))
  }, [])

  // 删除路径
  const handleDeletePath = useCallback(async (pathId: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('确定要删除这条学习路径吗？')) return
    try {
      const resp = await deleteLearningPath(pathId)
      if (resp.code === 200) {
        setPaths(prev => {
          const next = prev.filter(p => p.id !== pathId)
          // 如果删除的是当前选中的路径，切换到第一条
          if (pathId === activePathId && next.length > 0) {
            setActivePathId(next[0].id)
          } else if (next.length === 0) {
            setActivePathId(null)
          }
          return next
        })
      }
    } catch (e) {
      console.error('删除路径失败:', e)
    }
  }, [activePathId])

  // 重新规划：跳转到对话
  const requestPath = useCallback(() => {
    chatStore.startNewChat()
    navigate('/chat')
  }, [chatStore, navigate])

  // 规则重排路径 NOT_STARTED 节点
  const handleReorderPath = useCallback(async (pathId: number) => {
    if (reordering) return
    setReordering(true)
    try {
      const resp = await reorderPath(pathId)
      if (resp.code === 200 && resp.data) {
        setPaths(prev => prev.map(p => p.id === pathId ? resp.data! : p))
        const info = resp.data.reorder_info
        const msg = info && info.reordered_count > 0
          ? `已重排 ${info.reordered_count} 个未学节点${info.weak_points_prioritized.length > 0 ? '（薄弱点已优先）' : ''}`
          : '暂无可重排的未学节点'
        setError(msg)
        setTimeout(() => setError(null), 3000)
      } else {
        setError(resp.message || '重排失败')
      }
    } catch (e) {
      console.error('路径重排失败:', e)
      setError('重排失败，请稍后重试')
    } finally {
      setReordering(false)
    }
  }, [reordering])

  const useRecommendedPath = useCallback((topic: string) => {
    setNewTopic(topic)
    setFormTab('quick')
    setShowNewForm(true)
  }, [])

  // 评估路径完成度（偏差 F 评估闭环）
  const handleEvaluate = useCallback(async (pathId: number) => {
    if (evaluating) return
    setEvaluating(true)
    setError(null)
    try {
      const resp = await evaluatePath(pathId)
      if (resp.code === 200 && resp.data) {
        setEvaluation(resp.data)
        // 评估后路径 status 变 completed，重新加载路径列表
        await loadPaths()
      } else {
        setError(resp.message || '评估失败')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '评估失败，请稍后重试'
      setError(msg)
      console.error('路径评估失败:', e)
    } finally {
      setEvaluating(false)
    }
  }, [evaluating, loadPaths])

  // 一键创建进阶路径
  const handleCreateAdvance = useCallback(async (pathId: number, topic: string, reason: string) => {
    if (advancingTopic) return
    setAdvancingTopic(topic)
    setError(null)
    try {
      const resp = await createAdvancePath(pathId, topic, reason)
      if (resp.code === 200 && resp.data) {
        await loadPaths()
        setActivePathId(resp.data!.id)
        setEvaluation(null)
        setError(`已创建进阶路径：${resp.data!.title}`)
        setTimeout(() => setError(null), 3000)
      } else {
        setError(resp.message || '进阶路径创建失败')
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '创建失败，请稍后重试'
      setError(msg)
      console.error('进阶路径创建失败:', e)
    } finally {
      setAdvancingTopic(null)
    }
  }, [advancingTopic, loadPaths])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="学习路径">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewForm(prev => !prev)}
            className="btn-primary"
          >
            <Plus className="w-4 h-4" />
            新建路径
          </button>
          <button
            onClick={requestPath}
            className="btn-secondary"
          >
            <MessageCircle className="w-4 h-4" />
            对话规划
          </button>
        </div>
      </AppHeader>

      <div className="page-scroll-area">
        <RecommendedPath onUse={useRecommendedPath} />
        {/* 新建路径表单 */}
        {showNewForm && (
          <div className="page-panel max-w-2xl mx-auto mb-6 p-5">
            {/* Tab 切换 */}
            <div className="flex gap-1 mb-5 rounded-xl border border-brand-100 bg-white p-1">
              <button
                onClick={() => setFormTab('quick')}
                className={`flex-1 py-2 text-sm rounded-lg transition-all ${
                  formTab === 'quick' ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                快速生成
              </button>
              <button
                onClick={() => setFormTab('survey')}
                className={`flex-1 py-2 text-sm rounded-lg transition-all ${
                  formTab === 'survey' ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                问卷生成
              </button>
            </div>

            {/* 快速模式：主题输入 */}
            {formTab === 'quick' && (
              <div className="flex gap-3 mb-3">
                <input
                  type="text"
                  value={newTopic}
                  onChange={(e) => setNewTopic(e.target.value)}
                  placeholder="输入学习主题（如：Python基础、数据分析）"
                  className="input flex-1"
                />
              </div>
            )}

            {/* 问卷模式 */}
            {formTab === 'survey' && (
              <div className="space-y-4">
                {/* Step 1: 选择方向 */}
                <div>
                  <p className="text-xs font-medium text-slate-600 mb-2">1. 选择学习方向</p>
                  <div className="grid grid-cols-2 gap-2">
                    {DIRECTIONS.map((dir, i) => (
                      <button
                        key={dir.topic}
                        onClick={() => {
                          setDirectionIdx(i)
                          setMasteredPoints(new Set())
                        }}
                        className={`text-left p-3.5 rounded-xl border transition-all ${
                          directionIdx === i
                            ? 'border-brand-500 bg-brand-50'
                            : 'border-slate-200 bg-white hover:border-brand-300'
                        }`}
                      >
                        <p className={`text-sm font-medium ${directionIdx === i ? 'text-brand-700' : 'text-slate-700'}`}>
                          {dir.label}
                        </p>
                        <p className="text-xs text-slate-400 mt-0.5">{dir.description}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Step 2: 勾选已掌握的知识点 */}
                {directionIdx !== null && (
                  <div>
                    <p className="text-xs font-medium text-slate-600 mb-2">
                      2. 勾选你已掌握的知识点（可跳过）
                    </p>
                    <div className="flex flex-wrap gap-1.5 mb-3">
                      {DIRECTIONS[directionIdx].kp.map(kp => (
                        <button
                          key={kp}
                          onClick={() => setMasteredPoints(prev => {
                            const next = new Set(prev)
                            next.has(kp) ? next.delete(kp) : next.add(kp)
                            return next
                          })}
                        className={`text-xs px-2.5 py-1 rounded-md border transition-colors ${
                            masteredPoints.has(kp)
                              ? 'bg-brand-50 border-brand-500 text-brand-700'
                              : 'bg-white border-slate-200 text-slate-600 hover:border-brand-300'
                          }`}
                        >
                          {masteredPoints.has(kp) ? '✓ ' : ''}{kp}
                        </button>
                      ))}
                    </div>

                    {/* 自定义知识点输入 */}
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={customKpInput}
                        onChange={(e) => setCustomKpInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.nativeEvent.isComposing) return
                          if (e.key === 'Enter' && customKpInput.trim()) {
                            e.preventDefault()
                            setMasteredPoints(prev => new Set(prev).add(customKpInput.trim()))
                            setCustomKpInput('')
                          }
                        }}
                        placeholder="输入自定义知识点，回车添加"
                        className="input flex-1 text-xs"
                      />
                      <button
                        onClick={() => {
                          if (customKpInput.trim()) {
                            setMasteredPoints(prev => new Set(prev).add(customKpInput.trim()))
                            setCustomKpInput('')
                          }
                        }}
                        className="btn-secondary px-3 py-1.5 text-xs"
                      >
                        添加
                      </button>
                    </div>

                    {masteredPoints.size > 0 && (
                      <p className="text-xs text-gray-400 mt-2">
                        已选 {masteredPoints.size} 个知识点将被跳过
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* 生成按钮 */}
            <button
              onClick={handleGenerate}
              disabled={generating || (formTab === 'quick' ? !newTopic.trim() : directionIdx === null)}
              className="btn-primary mt-4 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Route className="w-4 h-4" />
              )}
              {generating ? '生成中...' : '生成学习路径'}
            </button>

            {/* 生成过程中的进度提示 */}
            {generating && (
              <div className="mt-3 flex items-center gap-2 text-xs text-brand-600">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>AI 正在根据你的知识掌握情况规划学习路径，预计需要 10-30 秒</span>
              </div>
            )}

            {/* 错误提示 */}
            {error && (
              <div className="mt-3 flex items-start gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700">
                <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="font-medium">生成失败</p>
                  <p className="mt-0.5 text-red-600">{error}</p>
                </div>
                <button onClick={() => setError(null)} className="text-red-400 hover:text-red-600">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>
        )}

        {/* Loading state */}
        {loading ? (
          <div className="page-content flex flex-col items-center justify-center h-64 text-slate-400">
            <Loader2 className="w-7 h-7 mb-3 animate-spin text-brand-500" />
            <p className="text-sm text-slate-500">加载学习路径...</p>
          </div>
        ) : paths.length === 0 ? (
          /* Empty state */
          <div className="page-content">
            <div className="page-panel flex flex-col items-center justify-center h-72 text-slate-400">
            <Route className="w-10 h-10 mb-3 opacity-30" />
            <p className="text-sm font-medium mb-1 text-slate-700">还没有学习路径</p>
            <p className="text-xs text-slate-400 mb-4">生成一条新路径，或在对话中让 AI 为你规划</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowNewForm(true)}
                className="btn-primary"
              >
                <Plus className="w-4 h-4" />
                新建路径
              </button>
              <button
                onClick={requestPath}
                className="btn-secondary"
              >
                <MessageCircle className="w-4 h-4" />
                去对话中规划
              </button>
            </div>
            </div>
          </div>
        ) : (
          <div className="page-content max-w-2xl mx-auto">
            {/* 路径切换标签 */}
            {paths.length > 1 && (
              <div className="flex gap-2 mb-5 overflow-x-auto pb-1">
                {paths.map(p => (
                  <div
                    key={p.id}
                    className={`flex items-center gap-1 rounded-lg whitespace-nowrap transition-all border ${
                      p.id === activePathId
                        ? 'bg-brand-50 text-brand-700 border-brand-200'
                        : 'bg-white text-slate-600 border-slate-200 hover:border-brand-300'
                    }`}
                  >
                    <button
                      onClick={() => setActivePathId(p.id)}
                      className="flex items-center gap-1.5 pl-3 pr-1.5 py-1.5 text-sm"
                    >
                      {p.title}
                      <span className="text-xs font-mono opacity-70">
                        {pathStatsById[p.id]?.pathProgress ?? Math.round(p.progress_percent)}%
                      </span>
                    </button>
                    <button
                      onClick={(e) => handleDeletePath(p.id, e)}
                      className={`p-1 mr-1 rounded transition-colors ${
                        p.id === activePathId
                          ? 'text-brand-400 hover:text-brand-700 hover:bg-brand-100'
                          : 'text-slate-400 hover:text-red-500 hover:bg-red-50'
                      }`}
                      title="删除路径"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* 路径概览卡片 */}
            {activePath && (
              <div className="page-panel mb-6 p-5">
                <div className="flex items-start justify-between mb-4 gap-3">
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <h3 className="text-lg font-semibold text-slate-800" style={{ fontFamily: 'var(--font-display)' }}>
                      {activePath.title}
                    </h3>
                    {activePath.description && (
                      <p className="text-xs text-slate-500 mt-1">{activePath.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    {stats.percent >= 100 && activePath.status === 'active' && (
                      <button
                        onClick={() => handleEvaluate(activePath.id)}
                        disabled={evaluating}
                        className="btn-primary text-xs px-3 py-1.5"
                        style={{ opacity: evaluating ? 0.7 : 1, cursor: evaluating ? 'wait' : 'pointer' }}
                        title="评估路径完成度，生成评估报告和进阶推荐"
                      >
                        {evaluating
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Award className="w-3.5 h-3.5" />}
                        {evaluating ? '评估中...' : '完成评估'}
                      </button>
                    )}
                    <button
                      onClick={() => handleReorderPath(activePath.id)}
                      disabled={reordering}
                      className="icon-button"
                      title="根据学习进展重排未学节点（薄弱点优先）"
                      style={{ opacity: reordering ? 0.5 : 1, cursor: reordering ? 'wait' : 'pointer' }}
                    >
                      {reordering
                        ? <Loader2 className="w-4 h-4 animate-spin" />
                        : <Shuffle className="w-4 h-4" />}
                    </button>
                    <button
                      onClick={loadPaths}
                      className="icon-button"
                      title="刷新"
                    >
                      <RefreshCw className="w-4 h-4" />
                    </button>
                    <button
                      onClick={(e) => handleDeletePath(activePath.id, e)}
                      className="icon-button hover:!text-rose-600"
                      title="删除路径"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* 进度条 */}
                <div className="mb-3">
                  <div className="flex items-center justify-between text-xs text-slate-500 mb-1.5">
                    <span>学习进度</span>
                    <span className="font-mono">{stats.completed} / {stats.total} · {stats.percent}%</span>
                  </div>
                  <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-500 rounded-full transition-all duration-500"
                      style={{ width: `${stats.percent}%` }}
                    />
                  </div>
                </div>

                {/* 统计数据 */}
                <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-slate-500">
                  <span className="flex items-center gap-1.5">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-500" />
                    已完成 <span className="font-semibold text-emerald-600">{stats.completed}</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Target className="w-3.5 h-3.5 text-brand-500" />
                    剩余 <span className="font-semibold text-brand-700">{stats.total - stats.completed}</span>
                  </span>
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    预计还需 <span className="font-semibold text-slate-700">{stats.timeLeft}</span> 分钟
                  </span>
                </div>
              </div>
            )}

            {/* 评估报告（偏差 F 评估闭环） */}
            {evaluation && (
              <div className="page-panel mb-6 p-5">
                {/* 顶部：达成度评分 + 升级横幅 */}
                <div className="flex items-center gap-4 mb-4 pb-4 border-b border-slate-100">
                  <div className="flex-shrink-0 w-20 h-20 rounded-full bg-gradient-to-br from-brand-50 to-brand-100 flex flex-col items-center justify-center">
                    <span className="text-2xl font-bold text-brand-700 font-mono">
                      {evaluation.achievement_score}
                    </span>
                    <span className="text-[10px] text-slate-500">达成度</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Award className="w-4 h-4 text-amber-500" />
                      <h4 className="text-sm font-semibold text-slate-800">路径完成评估报告</h4>
                    </div>
                    <p className="text-xs text-slate-500">
                      掌握度均值 {evaluation.mastery_stats.avg} · 完成率 {Math.round(evaluation.completion_rate * 100)}%
                    </p>
                    {evaluation.level_upgraded && (
                      <div className="mt-2 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-amber-50 border border-amber-200 text-xs text-amber-700">
                        <Sparkles className="w-3 h-3" />
                        知识水平升级：{KNOWLEDGE_LEVEL_LABELS[evaluation.level_upgraded.from] || evaluation.level_upgraded.from} → {KNOWLEDGE_LEVEL_LABELS[evaluation.level_upgraded.to] || evaluation.level_upgraded.to}
                      </div>
                    )}
                  </div>
                </div>

                {/* 目标达成度 */}
                {evaluation.report.goal_achievement && (
                  <div className="mb-3">
                    <span className="text-xs font-medium text-slate-600">目标达成度：</span>
                    <span className={`ml-1.5 text-xs font-semibold px-2 py-0.5 rounded ${
                      evaluation.report.goal_achievement === 'high' ? 'bg-emerald-50 text-emerald-700' :
                      evaluation.report.goal_achievement === 'medium' ? 'bg-amber-50 text-amber-700' :
                      'bg-rose-50 text-rose-700'
                    }`}>
                      {evaluation.report.goal_achievement === 'high' ? '高度达成' :
                       evaluation.report.goal_achievement === 'medium' ? '部分达成' : '达成不足'}
                    </span>
                  </div>
                )}

                {/* 目标分析 */}
                {evaluation.report.goal_analysis && (
                  <div className="mb-3 text-xs text-slate-600 leading-relaxed bg-slate-50 p-3 rounded-lg">
                    {evaluation.report.goal_analysis}
                  </div>
                )}

                {/* 强项 / 弱项 */}
                <div className="grid grid-cols-2 gap-3 mb-3">
                  <div>
                    <p className="text-xs font-medium text-emerald-600 mb-1.5">💪 强项</p>
                    <div className="flex flex-wrap gap-1">
                      {evaluation.report.strengths.length > 0 ? evaluation.report.strengths.map((s, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                          {s}
                        </span>
                      )) : <span className="text-xs text-slate-400">暂无</span>}
                    </div>
                  </div>
                  <div>
                    <p className="text-xs font-medium text-rose-600 mb-1.5">⚠️ 弱项</p>
                    <div className="flex flex-wrap gap-1">
                      {evaluation.report.weaknesses.length > 0 ? evaluation.report.weaknesses.map((w, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                          {w}
                        </span>
                      )) : <span className="text-xs text-slate-400">暂无</span>}
                    </div>
                  </div>
                </div>

                {/* 建议 */}
                {evaluation.report.suggestions.length > 0 && (
                  <div className="mb-4">
                    <p className="text-xs font-medium text-slate-600 mb-1.5">📝 学习建议</p>
                    <ul className="space-y-1">
                      {evaluation.report.suggestions.map((s, i) => (
                        <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                          <span className="text-brand-500 mt-0.5">•</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* 进阶推荐 */}
                {evaluation.recommendations.length > 0 && (
                  <div className="pt-4 border-t border-slate-100">
                    <p className="text-xs font-medium text-slate-600 mb-2">🚀 进阶学习推荐</p>
                    <div className="space-y-2">
                      {evaluation.recommendations.map((rec, i) => (
                        <div key={i} className="flex items-start gap-2 p-2.5 rounded-lg border border-slate-200 hover:border-brand-300 transition-colors">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 mb-0.5">
                              <span className="text-sm font-medium text-slate-800">{rec.topic}</span>
                              <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                                rec.difficulty === 'advanced' ? 'bg-rose-50 text-rose-600' : 'bg-amber-50 text-amber-600'
                              }`}>
                                {rec.difficulty === 'advanced' ? '进阶' : '中级'}
                              </span>
                            </div>
                            <p className="text-xs text-slate-500">{rec.reason}</p>
                          </div>
                          <button
                            onClick={() => activePath && handleCreateAdvance(activePath.id, rec.topic, rec.reason)}
                            disabled={advancingTopic !== null}
                            className="btn-secondary text-xs px-2.5 py-1 flex-shrink-0"
                            style={{ opacity: advancingTopic ? 0.5 : 1 }}
                          >
                            {advancingTopic === rec.topic
                              ? <Loader2 className="w-3 h-3 animate-spin" />
                              : <ArrowRight className="w-3 h-3" />}
                            创建
                          </button>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 学习路径时间线 */}
            <PathTimeline
              steps={pathSteps}
              onNodeClick={handleNodeClick}
              onResourceClick={handleResourceClick}
              onComplete={handleNodeComplete}
              onPathUpdated={handlePathUpdated}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default PathView
