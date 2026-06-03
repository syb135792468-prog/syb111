import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useChatStore } from '../stores/chat'
import AppHeader from '../components/layout/AppHeader'
import PathTimeline from '../components/path/PathTimeline'
import { PathNodeData } from '../components/path/PathStep'
import {
  listLearningPaths, getLearningPath, generateLearningPath,
  getNodeResources, completePathNode,
  type LearningPathData, type PathNode,
} from '../api/learningPath'
import {
  Route, MessageCircle, Plus, Trash2, ChevronRight,
  Clock, CheckCircle, Target, Loader2, RefreshCw
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

// --- 学习方向定义 ---
const DIRECTIONS = [
  {
    label: 'Python 基础入门',
    topic: 'Python基础',
    description: '系统学习全部基础知识',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断', '循环',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '面向对象基础', '类与对象', '继承与多态', '异常处理', '文件操作', '模块与包',
    ],
  },
  {
    label: '数据处理与分析',
    topic: '数据分析',
    description: '文件读写、数据结构、字符串处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断', '循环',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '文件操作', '模块与包',
    ],
  },
  {
    label: '自动化脚本',
    topic: '自动化',
    description: '条件循环、函数封装、异常处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断', '循环',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合', '字符串操作',
      '异常处理', '文件操作', '模块与包',
    ],
  },
  {
    label: '面向对象编程',
    topic: '面向对象',
    description: '类、继承、多态、异常处理',
    kp: [
      '变量与数据类型', '运算符与表达式', '条件判断', '循环',
      '函数定义与调用', '函数参数与返回值', '列表与元组', '字典与集合',
      '面向对象基础', '类与对象', '继承与多态', '异常处理', '模块与包',
    ],
  },
]

// --- 组件 ---
const PathView: React.FC = () => {
  const navigate = useNavigate()
  const chatStore = useChatStore()

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

  // 加载路径列表
  const loadPaths = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listLearningPaths()
      if (resp.code === 200 && resp.data) {
        setPaths(resp.data.paths || [])
        if (resp.data.paths.length > 0 && !activePathId) {
          setActivePathId(resp.data.paths[0].id)
        }
      }
    } catch (e) {
      console.error('加载路径失败:', e)
    } finally {
      setLoading(false)
    }
  }, [activePathId])

  useEffect(() => {
    loadPaths()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // 同步 chatStore 中的 SSE 路径数据到本地状态
  useEffect(() => {
    const ssePath = chatStore.lastLearningPath as LearningPathData | null
    if (ssePath && ssePath.id && !paths.find(p => p.id === ssePath.id)) {
      setPaths(prev => [ssePath, ...prev])
      setActivePathId(ssePath.id)
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
    const completed = activePath.nodes.filter(n => n.status === 'completed').length
    const total = activePath.total_nodes || activePath.nodes.length
    const timeLeft = activePath.nodes
      .filter(n => n.status !== 'completed')
      .reduce((sum, n) => sum + n.estimated_time, 0)
    return {
      completed,
      total,
      timeLeft,
      percent: activePath.progress_percent || (total > 0 ? Math.round((completed / total) * 100) : 0),
    }
  }, [activePath])

  // 生成新路径
  const handleGenerate = useCallback(async () => {
    setGenerating(true)
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
        setPaths(prev => [resp.data!, ...prev])
        setActivePathId(resp.data!.id)
        setShowNewForm(false)
        setMasteredPoints(new Set())
        setDirectionIdx(null)
        setCustomKpInput('')
      }
    } catch (e) {
      console.error('生成路径失败:', e)
    } finally {
      setGenerating(false)
    }
  }, [newTopic, formTab, directionIdx, masteredPoints])

  // 点击节点：加载资源
  const handleNodeClick = useCallback(async (nodeId: number) => {
    if (!activePath) return
    const node = activePath.nodes.find(n => n.id === nodeId)
    if (!node || (node.resources && node.resources.length > 0)) return

    try {
      const resp = await getNodeResources(nodeId)
      if (resp.code === 200 && resp.data) {
        // 更新本地路径数据中的节点资源
        setPaths(prev => prev.map(p => {
          if (p.id !== activePathId) return p
          return {
            ...p,
            nodes: p.nodes.map(n =>
              n.id === nodeId ? { ...n, resources: resp.data!.resources } : n
            ),
          }
        }))
      }
    } catch (e) {
      console.error('加载节点资源失败:', e)
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

  // 重新规划：跳转到对话
  const requestPath = useCallback(() => {
    chatStore.startNewChat()
    navigate('/chat')
  }, [chatStore, navigate])

  return (
    <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
      <AppHeader title="学习路径">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewForm(prev => !prev)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            新建路径
          </button>
          <button
            onClick={requestPath}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition-colors"
          >
            <MessageCircle className="w-4 h-4" />
            对话规划
          </button>
        </div>
      </AppHeader>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        {/* 新建路径表单 */}
        {showNewForm && (
          <div className="max-w-2xl mx-auto mb-6 p-4 bg-white rounded-xl border border-gray-100 shadow-sm">
            {/* Tab 切换 */}
            <div className="flex gap-1 mb-4 bg-gray-100 rounded-lg p-0.5">
              <button
                onClick={() => setFormTab('quick')}
                className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
                  formTab === 'quick' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'
                }`}
              >
                快速生成
              </button>
              <button
                onClick={() => setFormTab('survey')}
                className={`flex-1 py-1.5 text-sm rounded-md transition-colors ${
                  formTab === 'survey' ? 'bg-white text-gray-800 shadow-sm' : 'text-gray-500'
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
                  className="flex-1 px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:border-brand-400"
                />
              </div>
            )}

            {/* 问卷模式 */}
            {formTab === 'survey' && (
              <div className="space-y-4">
                {/* Step 1: 选择方向 */}
                <div>
                  <p className="text-xs font-medium text-gray-600 mb-2">1. 选择学习方向</p>
                  <div className="grid grid-cols-2 gap-2">
                    {DIRECTIONS.map((dir, i) => (
                      <button
                        key={dir.topic}
                        onClick={() => {
                          setDirectionIdx(i)
                          setMasteredPoints(new Set())
                        }}
                        className={`text-left p-3 rounded-lg border transition-colors ${
                          directionIdx === i
                            ? 'border-brand-400 bg-brand-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <p className={`text-sm font-medium ${directionIdx === i ? 'text-brand-700' : 'text-gray-700'}`}>
                          {dir.label}
                        </p>
                        <p className="text-xs text-gray-400 mt-0.5">{dir.description}</p>
                      </button>
                    ))}
                  </div>
                </div>

                {/* Step 2: 勾选已掌握的知识点 */}
                {directionIdx !== null && (
                  <div>
                    <p className="text-xs font-medium text-gray-600 mb-2">
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
                          className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
                            masteredPoints.has(kp)
                              ? 'bg-green-50 border-green-300 text-green-700'
                              : 'bg-white border-gray-200 text-gray-600 hover:border-gray-300'
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
                          if (e.key === 'Enter' && customKpInput.trim()) {
                            e.preventDefault()
                            setMasteredPoints(prev => new Set(prev).add(customKpInput.trim()))
                            setCustomKpInput('')
                          }
                        }}
                        placeholder="输入自定义知识点，回车添加"
                        className="flex-1 px-3 py-1.5 text-xs border border-gray-200 rounded-lg focus:outline-none focus:border-brand-400"
                      />
                      <button
                        onClick={() => {
                          if (customKpInput.trim()) {
                            setMasteredPoints(prev => new Set(prev).add(customKpInput.trim()))
                            setCustomKpInput('')
                          }
                        }}
                        className="px-3 py-1.5 text-xs bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 transition-colors"
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
              className="mt-4 flex items-center gap-1.5 px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {generating ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Route className="w-4 h-4" />
              )}
              {generating ? '生成中...' : '生成学习路径'}
            </button>
          </div>
        )}

        {/* Loading state */}
        {loading ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <Loader2 className="w-8 h-8 mb-3 animate-spin text-brand-400" />
            <p className="text-sm">加载学习路径...</p>
          </div>
        ) : paths.length === 0 ? (
          /* Empty state */
          <div className="flex flex-col items-center justify-center h-64 text-gray-400">
            <Route className="w-12 h-12 mb-3 opacity-40" />
            <p className="text-sm font-medium mb-1">暂无学习路径</p>
            <p className="text-xs text-gray-400 mb-4">生成一条新路径，或在对话中让 AI 为你规划</p>
            <div className="flex gap-3">
              <button
                onClick={() => setShowNewForm(true)}
                className="flex items-center gap-2 px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                新建路径
              </button>
              <button
                onClick={requestPath}
                className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 text-sm rounded-lg hover:bg-gray-200 transition-colors"
              >
                <MessageCircle className="w-4 h-4" />
                去对话中规划
              </button>
            </div>
          </div>
        ) : (
          <div className="max-w-2xl mx-auto">
            {/* 路径切换标签 */}
            {paths.length > 1 && (
              <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
                {paths.map(p => (
                  <button
                    key={p.id}
                    onClick={() => setActivePathId(p.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg whitespace-nowrap transition-colors ${
                      p.id === activePathId
                        ? 'bg-brand-600 text-white'
                        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                    }`}
                  >
                    {p.title}
                    <span className="text-xs opacity-70">
                      {Math.round(p.progress_percent)}%
                    </span>
                  </button>
                ))}
              </div>
            )}

            {/* 路径概览卡片 */}
            {activePath && (
              <div className="mb-6 p-4 bg-white rounded-xl border border-gray-100 shadow-sm">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-lg font-semibold text-gray-800">{activePath.title}</h3>
                    {activePath.description && (
                      <p className="text-xs text-gray-500 mt-0.5">{activePath.description}</p>
                    )}
                  </div>
                  <button
                    onClick={loadPaths}
                    className="p-1.5 text-gray-400 hover:text-gray-600 transition-colors"
                    title="刷新"
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                </div>

                {/* 进度条 */}
                <div className="mb-3">
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1">
                    <span>学习进度</span>
                    <span>{stats.completed}/{stats.total} 知识点</span>
                  </div>
                  <div className="w-full h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-brand-500 rounded-full transition-all duration-500"
                      style={{ width: `${stats.percent}%` }}
                    />
                  </div>
                </div>

                {/* 统计数据 */}
                <div className="flex gap-4 text-xs text-gray-500">
                  <span className="flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                    已完成 {stats.completed}
                  </span>
                  <span className="flex items-center gap-1">
                    <Target className="w-3.5 h-3.5 text-brand-500" />
                    剩余 {stats.total - stats.completed}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5 text-gray-400" />
                    预计还需 {stats.timeLeft} 分钟
                  </span>
                </div>
              </div>
            )}

            {/* 学习路径时间线 */}
            <PathTimeline
              steps={pathSteps}
              onNodeClick={handleNodeClick}
              onResourceClick={handleResourceClick}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default PathView
