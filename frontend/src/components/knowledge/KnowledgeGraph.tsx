import React, { useState, useEffect, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  X, Loader2, RefreshCw, Target, AlertCircle, CheckCircle2, Lock,
  BookOpen, ChevronRight, Maximize2,
} from 'lucide-react'
import {
  getGraphSnapshot, getNodeDetail, getNodePractice,
  type GraphSnapshot, type NodeDetail, type NodePractice,
  type GraphNode,
} from '../../api/graph'

interface KnowledgeGraphProps {
  refreshKey?: number
  mode?: 'profile' | 'local' | 'full'
}

interface PositionedNode extends GraphNode {
  x: number
  y: number
}

const COL_WIDTH = 130
const ROW_HEIGHT = 48
const PAD_TOP = 30
const NODE_RADIUS = 17
const EXPLORER_WIDTH = 1280
const EXPLORER_HEIGHT = 720

const FALLBACK_STATE_COLORS: Record<string, string> = {
  locked: '#cbd5e1',
  available: '#3b82f6',
  learning: '#f59e0b',
  mastered: '#10b981',
}
const FALLBACK_STATE_NAMES: Record<string, string> = {
  locked: '未解锁',
  available: '可学习',
  learning: '学习中',
  mastered: '已掌握',
}

// 节点内状态图标（SVG path，圆心为 0,0）
function StatusGlyph({ state, masteryScore, radius }: {
  state: string
  masteryScore: number
  radius: number
}) {
  if (state === 'locked') {
    const s = radius * 0.55
    return (
      <g>
        <path
          d={`M ${-s * 0.55} ${-s * 0.2} V ${-s * 0.7} A ${s * 0.55} ${s * 0.55} 0 0 1 ${s * 0.55} ${-s * 0.7} V ${-s * 0.2}`}
          fill="none"
          stroke="white"
          strokeWidth={s * 0.28}
          strokeLinecap="round"
        />
        <rect
          x={-s * 0.7}
          y={-s * 0.2}
          width={s * 1.4}
          height={s}
          rx={s * 0.15}
          fill="white"
        />
      </g>
    )
  }
  if (state === 'mastered') {
    const s = radius * 0.45
    return (
      <path
        d={`M ${-s} 0 L ${-s * 0.25} ${s * 0.7} L ${s} ${-s * 0.5}`}
        fill="none"
        stroke="white"
        strokeWidth={s * 0.4}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    )
  }
  if (state === 'learning') {
    return (
      <path
        d={`M ${-radius * 0.4} 0 H ${radius * 0.4}`}
        fill="none"
        stroke="white"
        strokeWidth={2.4}
        strokeLinecap="round"
      />
    )
  }
  // available: 空心圆由外层渲染，不画图标
  return null
}

export default function KnowledgeGraph({ refreshKey = 0, mode = 'full' }: KnowledgeGraphProps) {
  const navigate = useNavigate()
  const [snapshot, setSnapshot] = useState<GraphSnapshot | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [moduleFilter, setModuleFilter] = useState<string>('')
  const [stateFilter, setStateFilter] = useState<string>('')
  const [selectedNode, setSelectedNode] = useState<string | null>(null)
  const [nodeDetail, setNodeDetail] = useState<NodeDetail | null>(null)
  const [practice, setPractice] = useState<NodePractice | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  const isProfile = mode === 'profile'
  const isLocal = mode === 'local'
  const canvasWidth = isLocal ? 960 : (isProfile ? 1180 : EXPLORER_WIDTH)
  const canvasHeight = isLocal ? 440 : (isProfile ? 660 : EXPLORER_HEIGHT)

  const fetchSnapshot = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: { module?: string; state?: string } = {}
      if (!isLocal) {
        if (moduleFilter) params.module = moduleFilter
        if (stateFilter) params.state = stateFilter
      }
      const res = await getGraphSnapshot(params)
      if (res.code === 200) {
        setSnapshot(res.data as GraphSnapshot)
      } else {
        setError(res.message || '获取图谱失败')
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '获取图谱失败')
    } finally {
      setLoading(false)
    }
  }, [moduleFilter, stateFilter, isLocal])

  useEffect(() => {
    fetchSnapshot()
  }, [fetchSnapshot, refreshKey])

  // 状态颜色/名称（优先用 backend 返回的 meta）
  const stateColorMap: Record<string, string> = useMemo(() => {
    if (!snapshot?.states) return FALLBACK_STATE_COLORS
    const m: Record<string, string> = { ...FALLBACK_STATE_COLORS }
    for (const k in snapshot.states) m[k] = snapshot.states[k].color
    return m
  }, [snapshot])

  const stateNames: Record<string, string> = useMemo(() => {
    if (!snapshot?.states) return FALLBACK_STATE_NAMES
    const m: Record<string, string> = { ...FALLBACK_STATE_NAMES }
    for (const k in snapshot.states) m[k] = snapshot.states[k].name
    return m
  }, [snapshot])

  // 推荐节点（下一步）
  const recommendedNode = useMemo<GraphNode | null>(() => {
    if (!snapshot) return null
    const modules = snapshot.modules
    const sortByOrder = (a: GraphNode, b: GraphNode) =>
      (modules[a.module]?.order ?? 99) - (modules[b.module]?.order ?? 99) ||
      a.level - b.level ||
      a.code.localeCompare(b.code)
    const available = snapshot.nodes.filter(n => n.state === 'available').sort(sortByOrder)
    if (available.length) return available[0]
    const inProgress = snapshot.nodes
      .filter(n => n.state === 'learning' && n.mastery_score < 50)
      .sort(sortByOrder)
    if (inProgress.length) return inProgress[0]
    return null
  }, [snapshot])

  // 局部视图焦点节点（6 级优先链）
  const focusNodeCode = useMemo<string | null>(() => {
    if (!snapshot) return null
    if (selectedNode) return selectedNode
    const modules = snapshot.modules
    const sortByOrder = (a: GraphNode, b: GraphNode) =>
      (modules[a.module]?.order ?? 99) - (modules[b.module]?.order ?? 99) ||
      a.level - b.level ||
      a.code.localeCompare(b.code)

    // 2. 最近 7 天有证据的 learning 节点
    const sevenDaysAgo = Date.now() - 7 * 24 * 3600 * 1000
    const recent = snapshot.nodes
      .filter(n => n.state === 'learning' && n.last_evidence_at &&
                  new Date(n.last_evidence_at).getTime() > sevenDaysAgo)
      .sort((a, b) =>
        new Date(b.last_evidence_at!).getTime() - new Date(a.last_evidence_at!).getTime())
    if (recent.length) return recent[0].code

    // 3. 第一个 available
    const available = snapshot.nodes.filter(n => n.state === 'available').sort(sortByOrder)
    if (available.length) return available[0].code

    // 4. 到期需要复习（learning 且超 14 天无证据）
    const fourteenDaysAgo = Date.now() - 14 * 24 * 3600 * 1000
    const reviewDue = snapshot.nodes
      .filter(n => n.state === 'learning' && n.last_evidence_at &&
                  new Date(n.last_evidence_at).getTime() < fourteenDaysAgo)
      .sort((a, b) =>
        new Date(a.last_evidence_at!).getTime() - new Date(b.last_evidence_at!).getTime())
    if (reviewDue.length) return reviewDue[0].code

    // 5. 最近有学习证据的节点（不限 7 天）
    const anyRecent = snapshot.nodes
      .filter(n => n.last_evidence_at)
      .sort((a, b) =>
        new Date(b.last_evidence_at!).getTime() - new Date(a.last_evidence_at!).getTime())
    if (anyRecent.length) return anyRecent[0].code

    // 6. 根节点
    return 'py_intro'
  }, [snapshot, selectedNode])

  // 局部节点子集：focus ± 2 层 + 薄弱点
  const localNodeCodes = useMemo<Set<string> | null>(() => {
    if (!snapshot || !focusNodeCode) return null
    const all = new Set<string>([focusNodeCode])
    const edges = snapshot.edges.filter(e => e.edge_type === 'prerequisite')
    let frontier = [focusNodeCode]
    for (let depth = 0; depth < 2; depth++) {
      const next: string[] = []
      for (const code of frontier) {
        for (const e of edges) {
          if (e.source_code === code && !all.has(e.target_code)) {
            all.add(e.target_code); next.push(e.target_code)
          }
          if (e.target_code === code && !all.has(e.source_code)) {
            all.add(e.source_code); next.push(e.source_code)
          }
        }
      }
      frontier = next
    }
    return all
  }, [snapshot, focusNodeCode])

  const visibleNodes = useMemo<GraphNode[]>(() => {
    if (!snapshot) return []
    if (!isLocal) return snapshot.nodes
    if (!localNodeCodes) return []
    return snapshot.nodes.filter(n => localNodeCodes.has(n.code))
  }, [snapshot, isLocal, localNodeCodes])

  const visibleEdges = useMemo(() => {
    if (!snapshot) return []
    const visCodes = new Set(visibleNodes.map(n => n.code))
    return snapshot.edges.filter(e =>
      e.edge_type === 'prerequisite' &&
      visCodes.has(e.source_code) && visCodes.has(e.target_code))
  }, [snapshot, visibleNodes])

  const activeModules = useMemo<string[]>(() => {
    if (!snapshot) return []
    const present = new Set(visibleNodes.map(n => n.module))
    return Object.keys(snapshot.modules)
      .filter(m => present.has(m))
      .sort((a, b) =>
        (snapshot.modules[a]?.order ?? 99) - (snapshot.modules[b]?.order ?? 99))
  }, [snapshot, visibleNodes])

  // DAG 布局：桌面横向列式（每列内按 prerequisite 拓扑排序），移动端纵向行式（每模块一行）
  const positionedNodes = useMemo<PositionedNode[]>(() => {
    if (snapshot === null || activeModules.length === 0) return []
    const result: PositionedNode[] = []

    const moduleCount = activeModules.length
    const ringRadiusX = moduleCount <= 2 ? canvasWidth * 0.24 : canvasWidth * 0.33
    const ringRadiusY = moduleCount <= 2 ? canvasHeight * 0.18 : canvasHeight * 0.25

    activeModules.forEach((module, moduleIndex) => {
      const nodes = visibleNodes.filter((node) => node.module === module)
      const moduleAngle = -Math.PI / 2 + (Math.PI * 2 * moduleIndex) / moduleCount
      const centerX = moduleCount === 1
        ? canvasWidth / 2
        : canvasWidth / 2 + Math.cos(moduleAngle) * ringRadiusX
      const centerY = moduleCount === 1
        ? canvasHeight / 2
        : canvasHeight / 2 + Math.sin(moduleAngle) * ringRadiusY

      nodes.forEach((node, nodeIndex) => {
        const nodeAngle = nodeIndex * 2.399963229728653
        const nodeRadius = 26 + Math.sqrt(nodeIndex) * 19
        result.push({
          ...node,
          x: centerX + Math.cos(nodeAngle) * nodeRadius,
          y: centerY + Math.sin(nodeAngle) * nodeRadius,
        })
      })
    })

    return result

    /*

    // 每个模块内的节点按 prerequisite 拓扑排序（桌面/移动共用）
    const sortModuleNodes = (mod: string): GraphNode[] => {
      const colNodes = visibleNodes.filter(n => n.module === mod)
      if (colNodes.length === 0) return []
      const colCodes = new Set(colNodes.map(n => n.code))
      const inDeg: Record<string, number> = {}
      const adj: Record<string, string[]> = {}
      colCodes.forEach(c => { inDeg[c] = 0; adj[c] = [] })
      visibleEdges.forEach(e => {
        if (colCodes.has(e.source_code) && colCodes.has(e.target_code)) {
          adj[e.source_code].push(e.target_code)
          inDeg[e.target_code]++
        }
      })
      const queue = colNodes.map(n => n.code).filter(c => inDeg[c] === 0)
      const sorted: string[] = []
      while (queue.length) {
        const c = queue.shift()!
        sorted.push(c)
        ;(adj[c] || []).forEach(next => {
          inDeg[next]--
          if (inDeg[next] === 0) queue.push(next)
        })
      }
      colNodes.forEach(n => { if (!sorted.includes(n.code)) sorted.push(n.code) })
      return sorted.map(code => colNodes.find(x => x.code === code)!)
    }

    if (isMobile) {
      // 纵向：每个模块占一行，行内节点横向排布
      activeModules.forEach((mod, moduleIdx) => {
        const sortedNodes = sortModuleNodes(mod)
        sortedNodes.forEach((n, nodeIdx) => {
          result.push({
            ...n,
            x: nodeIdx * COL_WIDTH + COL_WIDTH / 2,
            y: PAD_TOP + moduleIdx * ROW_HEIGHT,
          })
        })
      })
    } else {
      // 横向：每个模块占一列，列内节点纵向排布
      activeModules.forEach((mod, colIdx) => {
        const sortedNodes = sortModuleNodes(mod)
        sortedNodes.forEach((n, rowIdx) => {
          result.push({
            ...n,
            x: colIdx * COL_WIDTH + COL_WIDTH / 2,
            y: PAD_TOP + rowIdx * ROW_HEIGHT,
          })
        })
      })
    }
    return result
    */
  }, [snapshot, activeModules, visibleNodes, canvasWidth, canvasHeight])

  const nodePosMap = useMemo(() => {
    const m: Record<string, PositionedNode> = {}
    for (const n of positionedNodes) m[n.code] = n
    return m
  }, [positionedNodes])

  const svgWidth = canvasWidth
  const svgHeight = canvasHeight

  /*

  const svgWidth = useMemo(() => {
    if (isMobile) {
      // 纵向：取每模块最大节点数 * COL_WIDTH
      const maxNodesInModule = activeModules.reduce((max, mod) => {
        const cnt = visibleNodes.filter(n => n.module === mod).length
        return Math.max(max, cnt)
      }, 0)
      return Math.max(maxNodesInModule * COL_WIDTH, COL_WIDTH)
    }
    return activeModules.length * COL_WIDTH
  }, [isMobile, activeModules, visibleNodes])

  const svgHeight = useMemo(() => {
    if (positionedNodes.length === 0) return 300
    const maxY = Math.max(...positionedNodes.map(n => n.y))
    return maxY + 40
  }, [positionedNodes])
  */

  // 持久标签节点：focus/推荐 + 选中 + 其 1 跳邻接
  const labeledNodes = useMemo<Set<string>>(() => {
    const s = new Set<string>()
    const focus = isLocal ? focusNodeCode : recommendedNode?.code
    if (focus) s.add(focus)
    if (selectedNode) s.add(selectedNode)
    const seeds = [...s]
    for (const code of seeds) {
      visibleEdges.forEach(e => {
        if (e.source_code === code) s.add(e.target_code)
        if (e.target_code === code) s.add(e.source_code)
      })
    }
    return s
  }, [isLocal, focusNodeCode, recommendedNode, selectedNode, visibleEdges])

  const handleNodeClick = useCallback(async (code: string) => {
    setSelectedNode(code)
    setDetailLoading(true)
    setNodeDetail(null)
    setPractice(null)
    try {
      const [detailRes, practiceRes] = await Promise.all([
        getNodeDetail(code),
        getNodePractice(code, 5),
      ])
      if (detailRes.code === 200) setNodeDetail(detailRes.data as NodeDetail)
      if (practiceRes.code === 200) setPractice(practiceRes.data as NodePractice)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载节点详情失败')
    } finally {
      setDetailLoading(false)
    }
  }, [])

  const renderNodes = () => {
    return positionedNodes.map(n => {
      const isSelected = selectedNode === n.code
      const isHovered = hoveredNode === n.code
      const isPrereqOfSelected = !!selectedNode && visibleEdges.some(
        e => e.target_code === selectedNode && e.source_code === n.code)
      const isTargetOfSelected = !!selectedNode && visibleEdges.some(
        e => e.source_code === selectedNode && e.target_code === n.code)
      const focusCode = isLocal ? focusNodeCode : recommendedNode?.code
      const isFocused = focusCode === n.code
      const showLabel = labeledNodes.has(n.code) || isHovered || isSelected
      const color = stateColorMap[n.state] || FALLBACK_STATE_COLORS[n.state]
      const dim = !!selectedNode && !isSelected && !isPrereqOfSelected && !isTargetOfSelected
      const progress = n.state === 'mastered' || n.state === 'locked'
        ? 1
        : Math.max(0.08, Math.min(1, n.mastery_score / 100))
      const ringCircumference = 2 * Math.PI * (NODE_RADIUS - 1)
      const labelWidth = Math.max(54, n.name.length * 11 + 16)

      return (
        <g
          key={n.code}
          transform={`translate(${n.x},${n.y})`}
          style={{ cursor: 'pointer' }}
          onClick={() => handleNodeClick(n.code)}
          onMouseEnter={() => setHoveredNode(n.code)}
          onMouseLeave={() => setHoveredNode(null)}
          opacity={dim ? 0.3 : 1}
        >
          <title>{`${n.name} - ${stateNames[n.state] || n.state} - 掌握度 ${n.mastery_score}%`}</title>
          {(isSelected || isPrereqOfSelected || isTargetOfSelected || isFocused) && (
            <circle
              r={NODE_RADIUS + 5}
              fill="none"
              stroke={isSelected ? '#0f172a' : isFocused ? '#3b82f6' : (isPrereqOfSelected ? '#f59e0b' : '#10b981')}
              strokeWidth={1.4}
              strokeDasharray={isPrereqOfSelected ? '2,2' : undefined}
            />
          )}
          <circle
            r={NODE_RADIUS}
            fill={color}
            fillOpacity={n.state === 'locked' ? 0.1 : 0.13}
            stroke={color}
            strokeOpacity={n.state === 'locked' ? 0.35 : 0.42}
            strokeWidth={1}
          />
          <circle
            r={NODE_RADIUS - 1}
            fill="none"
            stroke={color}
            strokeWidth={2.2}
            strokeOpacity={n.state === 'locked' ? 0.28 : 0.84}
            strokeLinecap="round"
            strokeDasharray={`${ringCircumference * progress} ${ringCircumference}`}
            transform="rotate(-90)"
          />
          <circle
            r={NODE_RADIUS - 5.5}
            fill={color}
            fillOpacity={n.state === 'locked' ? 0.68 : 1}
            stroke="white"
            strokeWidth={1.5}
          />
          <StatusGlyph state={n.state} masteryScore={n.mastery_score} radius={NODE_RADIUS - 5.5} />
          {showLabel && (
            <g transform={`translate(0, ${NODE_RADIUS + 10})`}>
              <rect
                x={-labelWidth / 2}
                y={-8}
                width={labelWidth}
                height={17}
                rx={4}
                fill="white"
                fillOpacity={0.94}
                stroke={isSelected ? color : '#e2e8f0'}
                strokeWidth={0.8}
              />
              <text
                y={4}
                textAnchor="middle"
                fontSize={10}
                fill="#1e293b"
                fontWeight={isFocused || isSelected ? 600 : 500}
              >
                {n.name}
              </text>
            </g>
          )}
        </g>
      )
    })
  }

  const renderEdges = () => {
    return visibleEdges.map((edge, idx) => {
      const s = nodePosMap[edge.source_code]
      const t = nodePosMap[edge.target_code]
      if (!s || !t) return null
      const isActive = selectedNode === edge.source_code || selectedNode === edge.target_code
      const isFaded = !!selectedNode && !isActive

      const sx = s.x + NODE_RADIUS
      const sy = s.y
      const tx = t.x - NODE_RADIUS
      const ty = t.y
      const dx = Math.max(Math.abs(tx - sx) * 0.5, 20)
      const path = `M ${sx} ${sy} C ${sx + dx} ${sy}, ${tx - dx} ${ty}, ${tx} ${ty}`

      return (
        <path
          key={`${edge.source_code}-${edge.target_code}-${idx}`}
          d={path}
          fill="none"
          stroke={isActive ? '#0f172a' : '#cbd5e1'}
          strokeWidth={isActive ? 1.5 : 0.8}
          opacity={isFaded ? 0.1 : (isActive ? 0.9 : 0.28)}
          markerEnd={isActive ? 'url(#arrow-active)' : 'url(#arrow)'}
        />
      )
    })
  }

  const renderModuleHeaders = () => {
    if (!snapshot) return null

    return activeModules.map((module) => {
      const meta = snapshot.modules[module]
      const members = positionedNodes.filter((node) => node.module === module)
      if (!meta || members.length === 0) return null
      const centerX = members.reduce((sum, node) => sum + node.x, 0) / members.length
      const topY = Math.min(...members.map((node) => node.y))
      return (
        <text
          key={module}
          x={centerX}
          y={topY - 28}
          textAnchor="middle"
          fontSize={12}
          fontWeight={600}
          fill={meta.color}
        >
          {meta.name}
        </text>
      )
    })

    /*
    return activeModules.map((mod, idx) => {
      const meta = snapshot.modules[mod]
      if (!meta) return null
      if (isMobile) {
        // 纵向：模块标题作为行标签，放在每行最左侧
        return (
          <text
            key={mod}
            x={4}
            y={PAD_TOP + idx * ROW_HEIGHT - 4}
            textAnchor="start"
            fontSize={10}
            fontWeight={600}
            fill={meta.color}
          >
            {meta.name}
          </text>
        )
      }
      // 横向：模块标题在每列顶部
      return (
        <text
          key={mod}
          x={idx * COL_WIDTH + COL_WIDTH / 2}
          y={14}
          textAnchor="middle"
          fontSize={11}
          fontWeight={600}
          fill={meta.color}
        >
          {meta.name}
        </text>
      )
    })
    */
  }

  const stats = snapshot?.stats

  return (
    <div className="page-panel p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-brand-500 mb-1">
            Knowledge Graph
          </p>
          <h3 className="text-base font-semibold text-slate-800">
            {isProfile ? 'Python 知识图谱' : `Python 知识图谱${isLocal ? ' · 当前学习上下文' : ''}`}
          </h3>
          <p className="text-xs text-gray-400 mt-1">
            {isProfile ? '完整展示你的 Python 知识网络，点击节点查看掌握证据与练习' : '点击节点查看详情与练习题'} · 共 {stats?.total ?? 0} 个知识点
            {isLocal && visibleNodes.length < (stats?.total ?? 0) &&
              ` · 当前展示 ${visibleNodes.length} 个`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {isLocal && !isProfile && (
            <button
              onClick={() => navigate('/knowledge-graph')}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-brand-600 border border-brand-200 rounded-lg hover:bg-brand-50 transition-colors"
            >
              <Maximize2 className="w-3 h-3" />
              查看完整图谱
            </button>
          )}
          <button
            onClick={fetchSnapshot}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {/* 下一步推荐卡片 */}
      {!isProfile && recommendedNode && (
        <div
          className="mb-4 p-3 rounded-lg border border-brand-200 bg-brand-50/40 flex items-center justify-between cursor-pointer hover:bg-brand-50/70 transition-colors"
          onClick={() => handleNodeClick(recommendedNode.code)}
        >
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-brand-500 text-white flex items-center justify-center text-[10px] font-bold">
              下一步
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-800">{recommendedNode.name}</div>
              <div className="text-xs text-gray-500 mt-0.5">
                预计 {recommendedNode.estimated_time} 分钟 ·
                {' '}{recommendedNode.state === 'available' ? '前置已满足' : '继续学习'}
              </div>
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-brand-500" />
        </div>
      )}

      {/* 筛选器（仅 full 模式）*/}
      {!isLocal && snapshot && (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="text-xs text-gray-400">模块:</span>
            <button
              onClick={() => setModuleFilter('')}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${moduleFilter === '' ? 'bg-slate-700 text-white border-slate-700' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
            >全部</button>
            {activeModules.map(m => {
              const meta = snapshot.modules[m]
              return (
                <button
                  key={m}
                  onClick={() => setModuleFilter(m)}
                  className={`px-2 py-0.5 text-xs rounded border transition-colors ${moduleFilter === m ? 'text-white border-transparent' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
                  style={moduleFilter === m ? { background: meta?.color } : {}}
                >{meta?.name ?? m}</button>
              )
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <span className="text-xs text-gray-400">状态:</span>
            <button
              onClick={() => setStateFilter('')}
              className={`px-2 py-0.5 text-xs rounded border transition-colors ${stateFilter === '' ? 'bg-slate-700 text-white border-slate-700' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
            >全部</button>
            {(['mastered', 'learning', 'available', 'locked'] as const).map(s => (
              <button
                key={s}
                onClick={() => setStateFilter(s)}
                className={`px-2 py-0.5 text-xs rounded border transition-colors ${stateFilter === s ? 'text-white border-transparent' : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'}`}
                style={stateFilter === s ? { background: stateColorMap[s] } : {}}
              >{stateNames[s]}</button>
            ))}
          </div>
        </>
      )}

      {/* SVG 容器 */}
      <div className="relative overflow-hidden border border-slate-100 rounded-lg bg-slate-50/60">
        {loading ? (
          <div className="flex items-center justify-center h-[440px]">
            <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center h-[440px] text-slate-400">
            <AlertCircle className="w-8 h-8 mb-2" />
            <p className="text-sm">{error}</p>
            <button onClick={fetchSnapshot} className="mt-2 text-xs text-brand-500 hover:underline">重试</button>
          </div>
        ) : positionedNodes.length === 0 ? (
          <div className="flex items-center justify-center h-[440px] text-slate-400 text-sm">暂无图谱数据</div>
        ) : (
          <>
            <div className="overflow-auto">
              <svg
                viewBox={`0 0 ${Math.max(svgWidth, 200)} ${Math.max(svgHeight, 200)}`}
                style={{ width: `${svgWidth}px`, height: `${svgHeight}px`, minWidth: `${svgWidth}px` }}
              >
                <defs>
                  <marker id="arrow" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                    <path d="M0,0 L6,3 L0,6 Z" fill="#cbd5e1" />
                  </marker>
                  <marker id="arrow-active" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
                    <path d="M0,0 L6,3 L0,6 Z" fill="#0f172a" />
                  </marker>
                </defs>
                {renderModuleHeaders()}
                {renderEdges()}
                {renderNodes()}
              </svg>
            </div>
            {/* 图例浮层 - 右上角 */}
            <div className="absolute top-2 right-2 bg-white/90 backdrop-blur rounded-lg p-2 text-xs space-y-1 shadow-sm border border-slate-100">
              {(['mastered', 'learning', 'available', 'locked'] as const).map(s => (
                <div key={s} className="flex items-center gap-1.5">
                  <svg width={14} height={14} viewBox="-7 -7 14 14">
                    <circle
                      r={5}
                      fill={s === 'available' ? 'white' : stateColorMap[s]}
                      stroke={stateColorMap[s]}
                      strokeWidth={s === 'available' ? 1.5 : 1}
                    />
                  </svg>
                  <span className="text-slate-600">{stateNames[s]}</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {selectedNode && (
        <NodeDetailDrawer
          detail={nodeDetail}
          practice={practice}
          loading={detailLoading}
          onClose={() => {
            setSelectedNode(null)
            setNodeDetail(null)
            setPractice(null)
          }}
          stateColors={stateColorMap}
          stateNames={stateNames}
        />
      )}
    </div>
  )
}

function NodeDetailDrawer({
  detail,
  practice,
  loading,
  onClose,
  stateColors,
  stateNames,
}: {
  detail: NodeDetail | null
  practice: NodePractice | null
  loading: boolean
  onClose: () => void
  stateColors: Record<string, string>
  stateNames: Record<string, string>
}) {
  const navigate = useNavigate()
  if (loading && !detail) {
    return (
      <div className="fixed inset-0 bg-black/30 z-50 flex items-center justify-center">
        <div className="bg-white rounded-xl p-6 flex items-center gap-3">
          <Loader2 className="w-5 h-5 animate-spin text-brand-500" />
          <span className="text-sm text-slate-600">加载节点详情...</span>
        </div>
      </div>
    )
  }
  if (!detail) return null

  const {
    node, mastery, effective_state, prerequisites, recent_evidences,
    threshold, evidence_threshold, error_count, related_paths,
  } = detail
  const effState = effective_state || mastery?.state || 'available'
  const stateColor = stateColors[effState] || FALLBACK_STATE_COLORS[effState]
  const stateName = stateNames[effState] || FALLBACK_STATE_NAMES[effState]
  const allPrereqMet = prerequisites.every(p => p.state === 'mastered')
  const canPractice = effState !== 'locked'
  const moduleMeta = detail.modules[node.module]
  const firstUntried = practice?.questions.find(q => !q.attempted) || practice?.questions[0]

  return (
    <div className="fixed inset-0 bg-black/30 z-50 flex justify-end" onClick={onClose}>
      <div
        className="bg-white w-full max-w-md h-full overflow-y-auto shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-slate-100 px-5 py-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 text-[10px] rounded-full text-white" style={{ background: stateColor }}>
                {stateName}
              </span>
              <span className="text-xs text-gray-400">
                {moduleMeta?.name ?? node.module} · L{node.level}
              </span>
            </div>
            <h2 className="text-lg font-semibold text-slate-800">{node.name}</h2>
            <p className="text-xs text-gray-400 mt-0.5">{node.code}</p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors">
            <X className="w-4 h-4 text-slate-500" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {node.description && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1.5">学习目标</h3>
              <p className="text-sm text-slate-600 leading-relaxed">{node.description}</p>
            </div>
          )}

          {mastery && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">掌握度</h3>
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-slate-600">分数</span>
                  <span className="text-sm font-semibold" style={{ color: stateColor }}>
                    {mastery.mastery_score} / 100
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{ width: `${Math.min(mastery.mastery_score, 100)}%`, background: stateColor }}
                  />
                </div>
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <span>掌握阈值 {threshold}</span>
                  <span>证据 {mastery.evidence_count} / {evidence_threshold}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2">
                  <div className="text-center py-1.5 rounded bg-slate-50">
                    <div className="text-sm font-semibold text-slate-700">
                      {mastery.quiz_correct_count}/{mastery.quiz_total_count}
                    </div>
                    <div className="text-[10px] text-gray-400">测验</div>
                  </div>
                  <div className="text-center py-1.5 rounded bg-slate-50">
                    <div className="text-sm font-semibold text-slate-700">{mastery.code_practice_count}</div>
                    <div className="text-[10px] text-gray-400">代码实践</div>
                  </div>
                  <div className="text-center py-1.5 rounded bg-slate-50">
                    <div className="text-sm font-semibold text-slate-700">{mastery.evidence_count}</div>
                    <div className="text-[10px] text-gray-400">总证据</div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {prerequisites.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">前置知识点</h3>
              <div className="space-y-1.5">
                {prerequisites.map(p => (
                  <div key={p.code} className="flex items-center justify-between py-1.5 px-2 rounded bg-slate-50">
                    <div className="flex items-center gap-2">
                      {p.state === 'mastered' ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      ) : p.state === 'locked' ? (
                        <Lock className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <AlertCircle className="w-3.5 h-3.5 text-amber-500" />
                      )}
                      <span className="text-sm text-slate-700">{p.name}</span>
                    </div>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{ background: `${stateColors[p.state] || '#999'}20`, color: stateColors[p.state] || '#999' }}
                    >
                      {stateNames[p.state] || p.state}
                    </span>
                  </div>
                ))}
              </div>
              {!allPrereqMet && (
                <p className="text-xs text-amber-600 mt-2 flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  需先掌握前置知识点
                </p>
              )}
            </div>
          )}

          {/* 错题记录 */}
          {error_count > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">错题记录</h3>
              <div className="flex items-center justify-between py-2 px-3 rounded bg-red-50 border border-red-100">
                <div className="flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-red-500" />
                  <span className="text-sm text-slate-700">
                    该知识点累计 <span className="font-semibold text-red-600">{error_count}</span> 道错题
                  </span>
                </div>
                <button
                  onClick={() => navigate('/error-book')}
                  className="text-xs text-red-600 hover:underline"
                >去复习</button>
              </div>
            </div>
          )}

          {/* 关联学习路径 */}
          {related_paths.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">关联学习路径</h3>
              <div className="space-y-1.5">
                {related_paths.map(p => (
                  <button
                    key={`${p.path_id}-${p.node_id}`}
                    onClick={() => navigate('/path')}
                    className="w-full flex items-center justify-between py-2 px-3 rounded-lg border border-slate-100 hover:border-brand-300 hover:bg-brand-50/30 transition-colors text-left"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <BookOpen className="w-3.5 h-3.5 text-brand-500 flex-shrink-0" />
                      <span className="text-sm text-slate-700 truncate">{p.path_title}</span>
                    </div>
                    <span className={`text-xs ml-2 flex-shrink-0 ${p.node_status === 'completed' ? 'text-emerald-600' : 'text-gray-400'}`}>
                      {p.node_status === 'completed' ? '已完成' : p.node_status === 'in_progress' ? '学习中' : '未开始'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 推荐练习 */}
          {practice && practice.questions.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">推荐练习</h3>
                <span className="text-xs text-gray-400">{practice.total} 题</span>
              </div>
              <div className="space-y-1.5">
                {practice.questions.map((q, idx) => (
                  <button
                    key={`${q.resource_id}-${q.question_index}`}
                    type="button"
                    onClick={() => navigate(`/resources?quiz=${q.resource_id}`)}
                    className="w-full flex items-center justify-between py-2 px-3 rounded-lg border border-slate-100 hover:border-brand-300 hover:bg-brand-50/30 transition-colors group text-left"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs text-gray-400 w-4">{idx + 1}</span>
                      {q.attempted ? (
                        q.last_correct ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                        ) : (
                          <AlertCircle className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
                        )
                      ) : (
                        <Target className="w-3.5 h-3.5 text-slate-300 flex-shrink-0 group-hover:text-brand-500" />
                      )}
                      <span className="text-sm text-slate-700 truncate">{q.title}</span>
                    </div>
                    <span className="text-xs text-gray-400 ml-2 flex-shrink-0">
                      {q.attempted ? (q.last_correct ? '已答对' : '需复习') : '未做'}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 最近学习记录 */}
          {recent_evidences.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">最近学习记录</h3>
              <div className="space-y-1.5">
                {recent_evidences.slice(0, 5).map(ev => (
                  <div key={ev.id} className="flex items-center justify-between text-xs py-1.5 px-2 rounded bg-slate-50">
                    <div className="flex items-center gap-2">
                      <BookOpen className="w-3 h-3 text-slate-400" />
                      <span className="text-slate-600">
                        {ev.source_type === 'quiz_attempt' ? '测验' :
                         ev.source_type === 'code_run' ? '代码实践' :
                         ev.source_type === 'path_node' ? '路径节点' :
                         ev.source_type === 'review' ? '复习' : '其他'}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className={ev.score >= 60 ? 'text-emerald-600' : 'text-amber-600'}>{ev.score}分</span>
                      <span className="text-gray-400">
                        {new Date(ev.created_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {!mastery && (
            <div className="text-center py-6 text-sm text-gray-400">
              <BookOpen className="w-8 h-8 mx-auto mb-2 opacity-50" />
              尚未学习此知识点，完成前置后即可开始
            </div>
          )}
        </div>

        {/* 底部 CTA - 开始学习 */}
        {canPractice && firstUntried && (
          <div className="sticky bottom-0 bg-white border-t border-slate-100 px-5 py-3">
            <button
              onClick={() => navigate(`/resources?quiz=${firstUntried.resource_id}`)}
              className="w-full py-2 bg-brand-500 text-white text-sm font-medium rounded-lg hover:bg-brand-600 transition-colors flex items-center justify-center gap-1.5"
            >
              <Target className="w-3.5 h-3.5" />
              开始学习
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
