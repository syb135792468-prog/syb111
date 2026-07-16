import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Minus, Plus, Scan } from 'lucide-react'

import type { GraphNode, GraphSnapshot } from '../../api/graph'

interface KnowledgeTreeProps {
  snapshot: GraphSnapshot
  nodes: GraphNode[]
  onNodeSelect: (code: string) => void
}

interface Viewport {
  x: number
  y: number
  scale: number
}

const CANVAS_WIDTH = 1680
const CANVAS_HEIGHT = 940
const ROOT_X = CANVAS_WIDTH / 2
const ROOT_Y = 76
const MODULE_Y = 210
const NODE_START_Y = 334
const MODULE_GAP = 180
const MODULE_START_X = 120

const DOT_MASTERED = '#10b981'
const DOT_UNMASTERED = '#3b82f6'

export default function KnowledgeTree({ snapshot, nodes, onNodeSelect }: KnowledgeTreeProps) {
  const [viewport, setViewport] = useState<Viewport>({ x: 0, y: 0, scale: 0.72 })
  const [dragStart, setDragStart] = useState<{ x: number; y: number; originX: number; originY: number } | null>(null)

  const modules = useMemo(() => Object.keys(snapshot.modules)
    .filter((module) => nodes.some((node) => node.module === module))
    .sort((a, b) => (snapshot.modules[a]?.order ?? 99) - (snapshot.modules[b]?.order ?? 99)), [snapshot, nodes])

  const groupedNodes = useMemo(() => nodes.reduce<Record<string, GraphNode[]>>((groups, node) => {
    groups[node.module] = [...(groups[node.module] || []), node]
    return groups
  }, {}), [nodes])

  const resetView = useCallback(() => setViewport({ x: 0, y: 0, scale: 0.72 }), [])
  const zoom = useCallback((factor: number) => {
    setViewport((current) => ({ ...current, scale: Math.min(1.8, Math.max(0.35, current.scale * factor)) }))
  }, [])

  const svgRef = useRef<SVGSVGElement>(null)
  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    const handler = (event: WheelEvent) => {
      event.preventDefault()
      const bounds = svg.getBoundingClientRect()
      const cursorX = event.clientX - bounds.left
      const cursorY = event.clientY - bounds.top
      const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12
      setViewport((current) => {
        const scale = Math.min(1.8, Math.max(0.35, current.scale * factor))
        const ratio = scale / current.scale
        return {
          scale,
          x: cursorX - (cursorX - current.x) * ratio,
          y: cursorY - (cursorY - current.y) * ratio,
        }
      })
    }
    svg.addEventListener('wheel', handler, { passive: false })
    return () => svg.removeEventListener('wheel', handler)
  }, [])

  return (
    <div className="knowledge-tree relative h-[780px] overflow-hidden bg-slate-50">
      <svg
        ref={svgRef}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onPointerDown={(event) => {
          if (event.button !== 0) return
          event.currentTarget.setPointerCapture(event.pointerId)
          setDragStart({ x: event.clientX, y: event.clientY, originX: viewport.x, originY: viewport.y })
        }}
        onPointerMove={(event) => {
          if (!dragStart) return
          setViewport((current) => ({
            ...current,
            x: dragStart.originX + event.clientX - dragStart.x,
            y: dragStart.originY + event.clientY - dragStart.y,
          }))
        }}
        onPointerUp={(event) => {
          setDragStart(null)
          event.currentTarget.releasePointerCapture(event.pointerId)
        }}
        onPointerCancel={() => setDragStart(null)}
      >
        <g transform={`translate(${viewport.x} ${viewport.y}) scale(${viewport.scale})`}>
          {modules.map((module, index) => {
            const x = MODULE_START_X + index * MODULE_GAP
            return (
              <line
                key={`root-${module}`}
                x1={ROOT_X}
                y1={ROOT_Y + 27}
                x2={x}
                y2={MODULE_Y - 22}
                stroke={snapshot.modules[module].color}
                strokeWidth={2}
                strokeOpacity={0.42}
              />
            )
          })}

          <circle cx={ROOT_X} cy={ROOT_Y} r={27} fill="#1e3a5f" />
          <text x={ROOT_X} y={ROOT_Y + 4} textAnchor="middle" fontSize={13} fontWeight={700} fill="white">Python</text>

          {modules.map((module, index) => {
            const moduleMeta = snapshot.modules[module]
            const x = MODULE_START_X + index * MODULE_GAP
            const members = (groupedNodes[module] || [])
              .slice()
              .sort((a, b) => a.level - b.level || a.code.localeCompare(b.code))

            return (
              <g key={module}>
                {members.map((node, nodeIndex) => {
                  const y = NODE_START_Y + nodeIndex * 44
                  const isMastered = node.state === 'mastered'
                  const dotColor = isMastered ? DOT_MASTERED : DOT_UNMASTERED
                  return (
                    <g
                      key={node.code}
                      className="cursor-pointer"
                      onPointerDown={(event) => event.stopPropagation()}
                      onClick={() => onNodeSelect(node.code)}
                    >
                      <title>{`${node.name} - ${isMastered ? '已掌握' : '未掌握'} · 掌握度 ${node.mastery_score}%`}</title>
                      <line
                        x1={x}
                        y1={MODULE_Y + 18}
                        x2={x}
                        y2={y - 8}
                        stroke={moduleMeta.color}
                        strokeWidth={1.2}
                        strokeOpacity={0.26}
                      />
                      <circle cx={x} cy={y} r={7} fill={dotColor} />
                      <text x={x + 14} y={y + 4} fontSize={12} fill="#334155">
                        {node.name}
                      </text>
                    </g>
                  )
                })}
                <circle cx={x} cy={MODULE_Y} r={20} fill={moduleMeta.color} />
                <text x={x} y={MODULE_Y + 4} textAnchor="middle" fontSize={10} fontWeight={700} fill="white">
                  {moduleMeta.name.slice(0, 4)}
                </text>
                <text x={x} y={MODULE_Y + 36} textAnchor="middle" fontSize={11} fontWeight={600} fill="#334155">
                  {moduleMeta.name}
                </text>
              </g>
            )
          })}
        </g>
      </svg>

      <div className="absolute right-3 bottom-3 flex items-center rounded-md border border-slate-200 bg-white shadow-sm">
        <button type="button" onClick={() => zoom(1 / 1.16)} title="缩小" className="p-2 text-slate-600 hover:bg-slate-50">
          <Minus className="h-4 w-4" />
        </button>
        <button type="button" onClick={resetView} title="适应画布" className="border-x border-slate-200 p-2 text-slate-600 hover:bg-slate-50">
          <Scan className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => zoom(1.16)} title="放大" className="p-2 text-slate-600 hover:bg-slate-50">
          <Plus className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
