import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useImperativeHandle,
  forwardRef,
} from 'react'
import MindElixir from 'mind-elixir'
import type { MindElixirData, NodeObj, MindElixirInstance } from 'mind-elixir'
import 'mind-elixir/style.css'

import { expandMindmapNode } from '../../api/resource'

// --- 类型定义 ---
interface NodeMetadata {
  definition: string
  syntax: string
  examples: string[]
  pitfalls: string[]
  advice: string
  depth?: number
}

interface DetailNode extends NodeMetadata {
  text: string
}

interface MindmapViewerProps {
  content?: string
  loading?: boolean
  resourceId?: number
  userId?: string | number
  onSelect?: (nodeObj: NodeObj) => void
}

export interface MindmapViewerHandle {
  zoomIn: () => void
  zoomOut: () => void
  resetView: () => void
  expandAll: () => void
  collapseAll: () => void
}

// --- 常量 ---
const THEME = {
  name: 'PythonHelper',
  palette: [
    '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b',
    '#ef4444', '#06b6d4', '#ec4899', '#84cc16',
  ],
  cssVar: {
    '--main-color': '#ffffff',
    '--main-bgcolor': '#7c3aed',
    '--main-bgcolor-transparent': 'rgba(124, 58, 237, 0.8)',
    '--color': '#1e293b',
    '--bgcolor': '#f8fafc',
    '--root-color': '#ffffff',
    '--root-bgcolor': '#1e40af',
    '--root-border-color': '#1e3a8a',
    '--root-radius': '14px',
    '--main-radius': '10px',
    '--selected': '#3b82f6',
    '--accent-color': '#3b82f6',
    '--node-gap-x': '20px',
    '--node-gap-y': '8px',
    '--main-gap-x': '60px',
    '--main-gap-y': '16px',
    '--topic-padding': '10px 18px',
    '--panel-color': '#1e293b',
    '--panel-bgcolor': '#ffffff',
    '--panel-border-color': '#e2e8f0',
    '--map-padding': '50px 80px',
  },
}

// Metadata backup: id → metadata (in case MindElixir strips custom fields)
const metadataMap = new Map<string, NodeMetadata>()

// --- 工具函数 ---
function detectContentType(text: string): string {
  if (!text) return 'empty'
  const trimmed = text.trim()
  if (trimmed.startsWith('{') && trimmed.includes('nodeData')) return 'json'
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed.nodeData) return 'json'
  } catch {}
  if (/^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|pie|gantt|erDiagram|mindmap)\b/i.test(trimmed)) return 'mermaid'
  if (/^#+\s/.test(trimmed) || /^-\s/m.test(trimmed)) return 'markdown'
  return 'unknown'
}

function convertNode(node: Record<string, unknown>, level: number): NodeObj {
  const id = (node.id as string) || `node_${Math.random().toString(36).slice(2, 9)}`
  const result: NodeObj = {
    id,
    topic: (node.topic as string) || (node.text as string) || '未命名',
    expanded: level < 2,
    children: [],
  } as NodeObj

  const meta: NodeMetadata = {
    definition: (node.definition as string) || '',
    syntax: (node.syntax as string) || '',
    examples: (node.examples as string[]) || [],
    pitfalls: (node.pitfalls as string[]) || [],
    advice: (node.advice as string) || '',
    depth: level,
  }
  result.metadata = meta
  metadataMap.set(id, meta)

  // ER 图专用样式：通过 definition 内容判断节点类型
  const defText = meta.definition || ''
  const topicText = (node.topic as string) || ''
  const isErRoot = level === 0 && (topicText.includes('ER图') || defText.includes('实体关系图'))
  const isErTable = defText.includes('业务用途') && defText.includes('数据量预估')
  const isErField = defText.includes('类型') && defText.includes('可为空')
  const isErFk = defText.includes('引用') && defText.includes('.')

  if (isErRoot) {
    result.style = { fontSize: '20', color: '#ffffff', background: '#0f766e', fontWeight: 'bold' }
  } else if (isErTable) {
    result.style = { fontSize: '15', color: '#ffffff', background: '#15803d', fontWeight: '600' }
    result.branchColor = '#4ade80'
  } else if (isErField) {
    result.style = {
      fontSize: '13', color: '#1e293b', background: '#fef9c3',
      fontWeight: '500', border: '1.5px solid #facc15',
    }
    result.branchColor = '#fde047'
  } else if (isErFk) {
    result.style = {
      fontSize: '13', color: '#1e293b', background: '#fee2e2',
      fontWeight: '500', border: '1.5px solid #f87171',
    }
    result.branchColor = '#fca5a5'
  } else if (level === 0) {
    result.style = { fontSize: '20', color: '#ffffff', background: '#1e40af', fontWeight: 'bold' }
  } else if (level === 1) {
    result.style = { fontSize: '15', color: '#ffffff', background: '#7c3aed', fontWeight: '600' }
    result.branchColor = '#a78bfa'
  } else if (level === 2) {
    result.style = {
      fontSize: '13', color: '#1e293b', background: '#ffffff',
      fontWeight: '500', border: '1.5px solid #e2e8f0',
    }
    result.branchColor = '#cbd5e1'
  } else {
    result.style = {
      fontSize: '12', color: '#475569', background: '#f8fafc',
      border: '1px solid #e2e8f0',
    }
    result.branchColor = '#e2e8f0'
  }

  if (node.children && (node.children as unknown[]).length > 0) {
    result.children = (node.children as Record<string, unknown>[]).map(c => convertNode(c, level + 1))
  }

  return result
}

function jsonToMindElixir(jsonStr: string): NodeObj | null {
  try {
    const data = JSON.parse(jsonStr.trim())
    const nodeData = data.nodeData || data
    return convertNode(nodeData, 0)
  } catch {
    return null
  }
}

function mermaidToMindElixir(mermaidStr: string): NodeObj | null {
  const lines = mermaidStr.split('\n').filter(l => {
    const t = l.trim()
    return t && !t.startsWith('graph') && !t.startsWith('flowchart') && !t.startsWith('%%')
  })

  const nodeText = new Map<string, string>()
  const childrenMap = new Map<string, Set<string>>()
  const allChildren = new Set<string>()
  const allParents = new Set<string>()
  const lineOrder: string[] = []

  function ensureId(id: string) {
    if (!lineOrder.includes(id)) lineOrder.push(id)
  }

  for (const line of lines) {
    const arrowRe = /(\w+)(?:\["?([^"\]]*)"?\])?\s*(?:-->|-->>|-\.-|--)\s*(\w+)(?:\["?([^"\]]*)"?\])?/g
    let m: RegExpExecArray | null
    while ((m = arrowRe.exec(line)) !== null) {
      const [, fromId, fromLabel, toId, toLabel] = m
      if (fromLabel) nodeText.set(fromId, fromLabel)
      if (toLabel) nodeText.set(toId, toLabel)
      if (!childrenMap.has(fromId)) childrenMap.set(fromId, new Set())
      childrenMap.get(fromId)!.add(toId)
      allParents.add(fromId)
      allChildren.add(toId)
      ensureId(fromId)
      ensureId(toId)
    }
    const labelRe = /^\s*(\w+)\s*\["?([^"\]]*)"?\]\s*$/
    const lm = labelRe.exec(line)
    if (lm) {
      const [, id, text] = lm
      if (text) nodeText.set(id, text)
      ensureId(id)
    }
  }

  let rootId: string | null = null
  for (const id of lineOrder) {
    if (allParents.has(id) && !allChildren.has(id)) {
      rootId = id
      break
    }
  }
  if (!rootId && lineOrder.length > 0) rootId = lineOrder[0]
  if (!rootId) return null

  const visited = new Set<string>()
  function buildNode(id: string, level: number): NodeObj | null {
    if (visited.has(id)) return null
    visited.add(id)
    const text = nodeText.get(id) || id
    const childIds = childrenMap.get(id)
    const children: NodeObj[] = []
    if (childIds) {
      for (const cid of childIds) {
        const child = buildNode(cid, level + 1)
        if (child) children.push(child)
      }
    }

    const result = { id, topic: text, expanded: level < 2, children } as NodeObj
    result.metadata = { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' }

    if (level === 0) {
      result.style = { fontSize: '20', color: '#ffffff', background: '#1e40af', fontWeight: 'bold' }
    } else if (level === 1) {
      result.style = { fontSize: '15', color: '#ffffff', background: '#7c3aed', fontWeight: '600' }
      result.branchColor = '#a78bfa'
    } else {
      result.style = {
        fontSize: '13', color: '#1e293b', background: '#ffffff',
        fontWeight: '500', border: '1.5px solid #e2e8f0',
      }
      result.branchColor = '#cbd5e1'
    }

    return result
  }

  return buildNode(rootId, 0)
}

function markdownToMindElixir(md: string): NodeObj {
  const lines = md.split('\n').filter(l => l.trim())
  let idCounter = 0
  const root = {
    id: 'root', topic: '', expanded: true, children: [] as NodeObj[],
    metadata: { definition: '', syntax: '', examples: [] as string[], pitfalls: [] as string[], advice: '' },
  } as NodeObj
  const stack: NodeObj[] = [root]

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/)
    const bulletMatch = line.match(/^(\s*)[-*]\s+(.+)/)

    if (headingMatch) {
      const level = headingMatch[1].length
      const text = headingMatch[2].trim()
      const node = {
        id: `md_${idCounter++}`,
        topic: text,
        expanded: level <= 2,
        children: [] as NodeObj[],
        metadata: { definition: '', syntax: '', examples: [] as string[], pitfalls: [] as string[], advice: '' },
        _level: level,
      } as NodeObj & { _level: number }
      while (stack.length > 1 && ((stack[stack.length - 1] as NodeObj & { _level?: number })._level || 0) >= level) stack.pop()
      ;(stack[stack.length - 1].children as NodeObj[]).push(node)
      stack.push(node)
    } else if (bulletMatch) {
      const text = bulletMatch[2].trim()
      ;(stack[stack.length - 1].children as NodeObj[]).push({
        id: `md_${idCounter++}`,
        topic: text,
        expanded: true,
        children: [],
        metadata: { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' },
      } as NodeObj)
    }
  }

  if (!root.topic && root.children && (root.children as NodeObj[]).length > 0) {
    const first = (root.children as NodeObj[])[0]
    root.topic = first.topic
    root.children = [...(first.children as NodeObj[]), ...(root.children as NodeObj[]).slice(1)]
  }
  return root
}

function setExpandAll(node: NodeObj, expanded: boolean) {
  if (node.children && node.children.length > 0) {
    node.expanded = expanded
    node.children.forEach(c => setExpandAll(c, expanded))
  }
}

// --- 组件 ---
const MindmapViewer = forwardRef<MindmapViewerHandle, MindmapViewerProps>(
  ({ content = '', loading = false, resourceId, userId, onSelect }, ref) => {
    const mapRef = useRef<HTMLDivElement>(null)
    const mindRef = useRef<MindElixirInstance | null>(null)
    const selectHandlerRef = useRef<((nodeObj: NodeObj) => void) | null>(null)
    const expandHandlerRef = useRef<((nodeObj: NodeObj) => void) | null>(null)
    const scaleHandlerRef = useRef<((scale: number) => void) | null>(null)

    const [zoomLevel, setZoomLevel] = useState(100)
    const [detailNode, setDetailNode] = useState<DetailNode | null>(null)
    const [showDetail, setShowDetail] = useState(false)
    const [renderError, setRenderError] = useState('')
    const [expandingNodes, setExpandingNodes] = useState<Set<string>>(new Set())

    // --- 解析内容 ---
    const parseContent = useCallback((): MindElixirData | null => {
      if (!content) return null
      const type = detectContentType(content)
      const trimmed = content.trim()

      let nodeData: NodeObj | null = null
      switch (type) {
        case 'json': nodeData = jsonToMindElixir(trimmed); break
        case 'mermaid': nodeData = mermaidToMindElixir(trimmed); break
        case 'markdown': nodeData = markdownToMindElixir(trimmed); break
        default:
          try { nodeData = jsonToMindElixir(trimmed) } catch {}
          if (!nodeData) nodeData = mermaidToMindElixir(trimmed)
          if (!nodeData) nodeData = markdownToMindElixir(trimmed)
      }

      if (!nodeData) {
        setRenderError(`解析失败 (类型: ${type}, 长度: ${trimmed.length}, 开头: ${trimmed.substring(0, 50)})`)
        return null
      }
      return { nodeData, direction: 1 } as unknown as MindElixirData
    }, [content])

    // --- 展开第四级节点 ---
    const expandNode = useCallback(async (nodeObj: NodeObj) => {
      if (!resourceId || !userId) return
      if (expandingNodes.has(nodeObj.id)) return

      const meta = (nodeObj.metadata as NodeMetadata) || metadataMap.get(nodeObj.id)
      if (!meta) return

      setExpandingNodes(prev => new Set(prev).add(nodeObj.id))

      try {
        const resp = await expandMindmapNode({
          userId,
          resourceId,
          nodeId: nodeObj.id,
          nodeTopic: nodeObj.topic,
          nodeDefinition: meta.definition,
          nodeSyntax: meta.syntax,
          nodeExamples: meta.examples,
          nodePitfalls: meta.pitfalls,
          nodeAdvice: meta.advice,
        })

        const respData = resp.data as { children?: Record<string, unknown>[] } | undefined
        if (resp.code === 200 && respData?.children) {
          const children = respData.children
          const convertedChildren = children.map(c => convertNode(c, 4))

          // Update metadataMap for new children
          const updateMeta = (nodes: NodeObj[]) => {
            for (const n of nodes) {
              if (n.metadata) metadataMap.set(n.id, n.metadata as NodeMetadata)
              if (n.children) updateMeta(n.children as NodeObj[])
            }
          }
          updateMeta(convertedChildren)

          // Attach to parent node and refresh
          nodeObj.children = convertedChildren
          nodeObj.expanded = true
          if (mindRef.current) {
            const data = mindRef.current.getData()
            mindRef.current.refresh(data)
          }
        }
      } catch (e) {
        console.warn('节点展开失败:', e)
      } finally {
        setExpandingNodes(prev => {
          const next = new Set(prev)
          next.delete(nodeObj.id)
          return next
        })
      }
    }, [resourceId, userId, expandingNodes])

    // --- 初始化 MindElixir ---
    const initMindElixir = useCallback(() => {
      if (!mapRef.current) return

      let retries = 0
      function tryInit() {
        if (!mapRef.current) return
        const container = mapRef.current

        if (container.offsetWidth === 0 || container.offsetHeight === 0) {
          retries++
          if (retries < 20) {
            setTimeout(tryInit, 50)
          }
          return
        }

        if (mindRef.current) {
          mindRef.current.destroy()
          mindRef.current = null
        }

        try {
          mindRef.current = new MindElixir({
            el: container,
            direction: 1,
            toolBar: true,
            keypress: false,
            editable: false,
            contextMenu: false,
            overflowHidden: false,
            allowUndo: false,
            theme: THEME,
          })
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e)
          setRenderError('MindElixir 初始化失败: ' + msg)
          return
        }

        const data = parseContent()
        if (!data) return

        try {
          const err = mindRef.current.init(data)
          if (err) {
            setRenderError('MindElixir init 错误: ' + String(err))
          }
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : String(e)
          setRenderError('渲染失败: ' + msg)
        }

        // 监听节点点击
        selectHandlerRef.current = (nodeObj: NodeObj) => {
          const meta = (nodeObj.metadata as NodeMetadata) || metadataMap.get(nodeObj.id) || null
          setDetailNode(meta ? { text: nodeObj.topic, ...meta } : {
            text: nodeObj.topic,
            definition: '', syntax: '', examples: [], pitfalls: [], advice: '',
          })
          setShowDetail(true)
          onSelect?.(nodeObj)

          // 自动展开：depth>=2 且无子节点的叶子节点
          if (meta?.depth !== undefined && meta.depth >= 2 && (!nodeObj.children || nodeObj.children.length === 0)) {
            expandNode(nodeObj)
          }
        }

        expandHandlerRef.current = () => {}

        scaleHandlerRef.current = (scale: number) => {
          setZoomLevel(Math.round(scale * 100))
        }

        mindRef.current.bus.addListener('selectNewNode', selectHandlerRef.current)
        mindRef.current.bus.addListener('expandNode', expandHandlerRef.current)
        mindRef.current.bus.addListener('scale', scaleHandlerRef.current)
      }

      requestAnimationFrame(() => tryInit())
    }, [parseContent, onSelect, expandNode])

    // --- 关闭详情面板 ---
    const closeDetail = useCallback(() => {
      setShowDetail(false)
      setDetailNode(null)
      if (mindRef.current) mindRef.current.clearSelection()
    }, [])

    // --- 工具栏方法 ---
    const zoomIn = useCallback(() => {
      if (mindRef.current) mindRef.current.scale(mindRef.current.scaleVal * 1.2)
    }, [])

    const zoomOut = useCallback(() => {
      if (mindRef.current) mindRef.current.scale(mindRef.current.scaleVal / 1.2)
    }, [])

    const resetView = useCallback(() => {
      if (mindRef.current) {
        mindRef.current.toCenter()
        mindRef.current.scaleFit()
      }
    }, [])

    const expandAll = useCallback(() => {
      if (mindRef.current) {
        const data = mindRef.current.getData()
        if (data.nodeData) {
          setExpandAll(data.nodeData, true)
          mindRef.current.refresh(data)
        }
      }
    }, [])

    const collapseAll = useCallback(() => {
      if (mindRef.current) {
        const data = mindRef.current.getData()
        if (data.nodeData) {
          setExpandAll(data.nodeData, false)
          data.nodeData.expanded = true
          mindRef.current.refresh(data)
        }
      }
    }, [])

    // --- 暴露方法 ---
    useImperativeHandle(ref, () => ({
      zoomIn,
      zoomOut,
      resetView,
      expandAll,
      collapseAll,
    }), [zoomIn, zoomOut, resetView, expandAll, collapseAll])

    // --- content 变化时重新渲染（含首次挂载） ---
    useEffect(() => {
      setShowDetail(false)
      setDetailNode(null)
      setRenderError('')
      metadataMap.clear()
      if (content) {
        requestAnimationFrame(() => initMindElixir())
      }
    }, [content, initMindElixir])

    // --- 卸载时清理 ---
    useEffect(() => {
      return () => {
        if (mindRef.current) {
          if (selectHandlerRef.current) mindRef.current.bus.removeListener('selectNewNode', selectHandlerRef.current)
          if (expandHandlerRef.current) mindRef.current.bus.removeListener('expandNode', expandHandlerRef.current)
          if (scaleHandlerRef.current) mindRef.current.bus.removeListener('scale', scaleHandlerRef.current)
          mindRef.current.destroy()
          mindRef.current = null
        }
      }
    }, [])

    // --- 渲染 ---
    return (
      <div className="mm-wrapper">
        {/* 加载动画 */}
        {loading ? (
          <div className="mm-loading">
            <div className="mm-spinner" />
            <p>正在生成思维导图...</p>
          </div>
        ) : !content ? (
          /* 空状态 */
          <div className="mm-empty">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="1.5">
              <path d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l5.447 2.724A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
            </svg>
            <p>输入知识点，生成思维导图</p>
          </div>
        ) : (
          <>
            {/* 错误回退 */}
            {renderError ? (
              <div className="mm-empty" style={{ color: '#ef4444' }}>
                <p>{renderError}</p>
                <p style={{ fontSize: 12, color: '#94a3b8' }}>请刷新页面重试</p>
              </div>
            ) : (
              <div className="mm-canvas-area">
                <div ref={mapRef} className="mm-map" />
              </div>
            )}

            {/* 右侧详情面板 */}
            {showDetail && detailNode && (
              <div className="mm-panel mm-panel-slide-in">
                <div className="mm-panel-header">
                  <h3 className="mm-panel-title">{detailNode.text}</h3>
                  <button className="mm-panel-close" onClick={closeDetail}>
                    <svg width="18" height="18" viewBox="0 0 18 18">
                      <path d="M5 5l8 8M13 5l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                    </svg>
                  </button>
                </div>
                <div className="mm-panel-body">
                  {detailNode.definition && (
                    <div className="mm-panel-section">
                      <div className="mm-panel-label">定义</div>
                      <p className="mm-panel-text">{detailNode.definition}</p>
                    </div>
                  )}
                  {detailNode.syntax && (
                    <div className="mm-panel-section">
                      <div className="mm-panel-label">语法</div>
                      <pre className="mm-panel-code">{detailNode.syntax}</pre>
                    </div>
                  )}
                  {detailNode.examples && detailNode.examples.length > 0 && (
                    <div className="mm-panel-section">
                      <div className="mm-panel-label">示例</div>
                      {detailNode.examples.map((ex, i) => (
                        <pre key={i} className="mm-panel-code">{ex}</pre>
                      ))}
                    </div>
                  )}
                  {detailNode.pitfalls && detailNode.pitfalls.length > 0 && (
                    <div className="mm-panel-section">
                      <div className="mm-panel-label">常见坑点</div>
                      <ul className="mm-panel-list">
                        {detailNode.pitfalls.map((p, i) => (
                          <li key={i}>{p}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {detailNode.advice && (
                    <div className="mm-panel-section">
                      <div className="mm-panel-label">学习建议</div>
                      <p className="mm-panel-text mm-panel-advice">{detailNode.advice}</p>
                    </div>
                  )}
                  {!detailNode.definition &&
                    !detailNode.syntax &&
                    (!detailNode.examples || detailNode.examples.length === 0) &&
                    (!detailNode.pitfalls || detailNode.pitfalls.length === 0) &&
                    !detailNode.advice && (
                      <div className="mm-panel-empty">该节点无详细内容</div>
                    )}
                  {expandingNodes.size > 0 && (
                    <div className="mm-panel-expanding">
                      <div className="mm-spinner-small" />
                      <span>正在展开子节点...</span>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}

        <style>{`
          .mm-wrapper {
            position: relative;
            width: 100%;
            height: 100%;
            min-height: 500px;
            background: #f8fafc;
            border-radius: 16px;
            border: 1px solid #e2e8f0;
            box-sizing: border-box;
          }
          .mm-canvas-area {
            width: 100%;
            height: 100%;
            min-height: 500px;
          }
          .mm-map {
            width: 100%;
            height: 100%;
            min-height: 500px;
          }
          .mm-map .map-container {
            background: #f8fafc !important;
          }
          .mm-panel {
            position: absolute;
            top: 0; right: 0;
            width: 340px;
            height: 100%;
            background: #fff;
            border-left: 1px solid #e2e8f0;
            box-shadow: -4px 0 24px rgba(0,0,0,0.06);
            z-index: 500;
            display: flex;
            flex-direction: column;
            overflow: hidden;
          }
          .mm-panel-slide-in {
            animation: mm-slide-in 0.3s ease forwards;
          }
          @keyframes mm-slide-in {
            from { transform: translateX(100%); opacity: 0; }
            to { transform: translateX(0); opacity: 1; }
          }
          .mm-panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 16px 20px;
            border-bottom: 1px solid #f1f5f9;
            flex-shrink: 0;
          }
          .mm-panel-title {
            font-size: 16px;
            font-weight: 700;
            color: #1e293b;
            margin: 0;
          }
          .mm-panel-close {
            width: 28px; height: 28px;
            border: none; border-radius: 6px;
            display: flex; align-items: center; justify-content: center;
            cursor: pointer; color: #94a3b8;
            background: transparent;
            transition: all 0.15s;
          }
          .mm-panel-close:hover { background: #f1f5f9; color: #64748b; }
          .mm-panel-body {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
          }
          .mm-panel-section { margin-bottom: 16px; }
          .mm-panel-label {
            font-size: 11px;
            font-weight: 600;
            color: #7c3aed;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 6px;
          }
          .mm-panel-text {
            font-size: 13px;
            color: #475569;
            line-height: 1.6;
            margin: 0;
          }
          .mm-panel-code {
            font-size: 12px;
            color: #1e293b;
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 0 0 6px 0;
            overflow-x: auto;
            font-family: 'SF Mono', 'Fira Code', monospace;
            line-height: 1.5;
            white-space: pre-wrap;
          }
          .mm-panel-list {
            margin: 0;
            padding: 0 0 0 16px;
            font-size: 13px;
            color: #475569;
            line-height: 1.8;
          }
          .mm-panel-list li { margin-bottom: 2px; }
          .mm-panel-advice {
            background: linear-gradient(135deg, #eff6ff, #f0fdf4);
            border: 1px solid #dbeafe;
            border-radius: 8px;
            padding: 10px 12px;
            font-size: 13px;
            color: #1e40af;
          }
          .mm-panel-empty {
            text-align: center;
            color: #94a3b8;
            font-size: 13px;
            padding: 32px 0;
          }
          .mm-panel-expanding {
            display: flex;
            align-items: center;
            gap: 8px;
            justify-content: center;
            color: #3b82f6;
            font-size: 12px;
            padding: 12px 0;
            margin-top: 8px;
            border-top: 1px solid #f1f5f9;
          }
          .mm-spinner-small {
            width: 14px; height: 14px;
            border: 2px solid #e2e8f0;
            border-top-color: #3b82f6;
            border-radius: 50%;
            animation: mm-spin 0.8s linear infinite;
          }
          .mm-loading {
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100%; gap: 16px;
            color: #94a3b8; font-size: 14px;
          }
          .mm-spinner {
            width: 36px; height: 36px;
            border: 3px solid #e2e8f0;
            border-top-color: #3b82f6;
            border-radius: 50%;
            animation: mm-spin 0.8s linear infinite;
          }
          @keyframes mm-spin { to { transform: rotate(360deg); } }
          .mm-empty {
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            height: 100%; gap: 12px;
            color: #94a3b8; font-size: 14px;
          }
        `}</style>
      </div>
    )
  }
)

MindmapViewer.displayName = 'MindmapViewer'

export default MindmapViewer
