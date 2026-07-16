import React, { useCallback, useEffect, useMemo, useRef } from 'react'
import MindElixir from 'mind-elixir'
import type { MindElixirData, MindElixirInstance, NodeObj } from 'mind-elixir'
import { Minus, Plus, Scan } from 'lucide-react'
import 'mind-elixir/style.css'

import type { GraphNode, GraphSnapshot } from '../../api/graph'

interface KnowledgeMindmapProps {
  snapshot: GraphSnapshot
  nodes: GraphNode[]
  onNodeSelect: (code: string) => void
  layout?: 'mindmap' | 'tree'
}

const NODE_COLORS: Record<string, { background: string; border: string; color: string }> = {
  locked: { background: '#f8fafc', border: '#cbd5e1', color: '#94a3b8' },
  available: { background: '#eff6ff', border: '#93c5fd', color: '#1d4ed8' },
  learning: { background: '#fff7ed', border: '#fcd34d', color: '#b45309' },
  mastered: { background: '#059669', border: '#047857', color: '#ffffff' },
}

function buildMindmap(snapshot: GraphSnapshot, nodes: GraphNode[], layout: 'mindmap' | 'tree'): MindElixirData {
  const nodesByModule = nodes.reduce<Record<string, GraphNode[]>>((groups, node) => {
    groups[node.module] = [...(groups[node.module] || []), node]
    return groups
  }, {})

  const modules = Object.keys(snapshot.modules)
    .filter((module) => nodesByModule[module]?.length)
    .sort((a, b) => (snapshot.modules[a]?.order ?? 99) - (snapshot.modules[b]?.order ?? 99))

  const root = {
    id: 'knowledge-root',
    topic: 'Python Knowledge Map',
    expanded: true,
    style: {
      background: '#1e3a5f',
      color: '#ffffff',
      fontSize: '17',
      fontWeight: '700',
      border: '1px solid #1e3a5f',
      borderRadius: '8px',
    },
    children: modules.map((module) => {
      const meta = snapshot.modules[module]
      return {
        id: `module:${module}`,
        topic: meta.name,
        expanded: true,
        branchColor: meta.color,
        style: {
          background: meta.color,
          color: '#ffffff',
          fontSize: '13',
          fontWeight: '650',
          border: `1px solid ${meta.color}`,
          borderRadius: '6px',
        },
        children: nodesByModule[module]
          .slice()
          .sort((a, b) => a.level - b.level || a.code.localeCompare(b.code))
          .map((node) => {
            const style = NODE_COLORS[node.state] || NODE_COLORS.locked
            return {
              id: `node:${node.code}`,
              topic: node.name,
              expanded: true,
              branchColor: meta.color,
              style: {
                background: style.background,
                color: style.color,
                fontSize: '12',
                fontWeight: '500',
                border: `1px solid ${style.border}`,
                borderRadius: '5px',
              },
              children: [],
            }
          }),
      }
    }),
  } as unknown as NodeObj

  return { nodeData: root, direction: layout === 'tree' ? 1 : 2 } as unknown as MindElixirData
}

export default function KnowledgeMindmap({
  snapshot,
  nodes,
  onNodeSelect,
  layout = 'mindmap',
}: KnowledgeMindmapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mindRef = useRef<MindElixirInstance | null>(null)
  const selectHandlerRef = useRef<((selected: NodeObj[]) => void) | null>(null)
  const data = useMemo(() => buildMindmap(snapshot, nodes, layout), [snapshot, nodes, layout])

  const resetView = useCallback(() => {
    if (!mindRef.current) return
    mindRef.current.toCenter()
    mindRef.current.scaleFit()
  }, [])

  const zoomIn = useCallback(() => {
    if (mindRef.current) mindRef.current.scale(mindRef.current.scaleVal * 1.16)
  }, [])

  const zoomOut = useCallback(() => {
    if (mindRef.current) mindRef.current.scale(mindRef.current.scaleVal / 1.16)
  }, [])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const mind = new MindElixir({
      el: container,
      direction: layout === 'tree' ? 1 : 2,
      toolBar: false,
      keypress: false,
      editable: false,
      contextMenu: false,
      overflowHidden: false,
      allowUndo: false,
      theme: {
        name: 'KnowledgeMap',
        palette: ['#3b82f6', '#10b981', '#f59e0b', '#6366f1'],
        cssVar: {
          '--node-gap-x': '18px',
          '--node-gap-y': '8px',
          '--main-gap-x': '58px',
          '--main-gap-y': '22px',
          '--main-color': '#ffffff',
          '--main-bgcolor': '#3b82f6',
          '--main-bgcolor-transparent': 'rgba(59, 130, 246, 0.12)',
          '--color': '#334155',
          '--bgcolor': '#f8fafc',
          '--selected': '#2563eb',
          '--accent-color': '#2563eb',
          '--root-color': '#ffffff',
          '--root-bgcolor': '#0f172a',
          '--root-border-color': '#0f172a',
          '--root-radius': '10px',
          '--main-radius': '8px',
          '--topic-padding': '7px 12px',
          '--panel-color': '#334155',
          '--panel-bgcolor': '#ffffff',
          '--panel-border-color': '#e2e8f0',
          '--map-padding': '64px 96px',
        },
      },
    })

    mindRef.current = mind
    mind.init(data)
    selectHandlerRef.current = (selected: NodeObj[]) => {
      const node = selected?.[0]
      const id = String(node?.id || '')
      if (id.startsWith('node:')) onNodeSelect(id.slice(5))
    }
    mind.bus.addListener('selectNodes', selectHandlerRef.current)

    const frame = requestAnimationFrame(resetView)
    return () => {
      cancelAnimationFrame(frame)
      if (selectHandlerRef.current) mind.bus.removeListener('selectNodes', selectHandlerRef.current)
      mind.destroy()
      if (mindRef.current === mind) mindRef.current = null
    }
  }, [data, layout, onNodeSelect, resetView])

  return (
    <div className="knowledge-mindmap relative h-[780px] overflow-hidden bg-slate-50">
      <div ref={containerRef} className="h-full w-full" />
      <div className="absolute right-3 bottom-3 flex items-center rounded-md border border-slate-200 bg-white shadow-sm">
        <button type="button" onClick={zoomOut} title="缩小" className="p-2 text-slate-600 hover:bg-slate-50">
          <Minus className="h-4 w-4" />
        </button>
        <button type="button" onClick={resetView} title="适应画布" className="border-x border-slate-200 p-2 text-slate-600 hover:bg-slate-50">
          <Scan className="h-4 w-4" />
        </button>
        <button type="button" onClick={zoomIn} title="放大" className="p-2 text-slate-600 hover:bg-slate-50">
          <Plus className="h-4 w-4" />
        </button>
      </div>
      <style>{`
        .knowledge-mindmap .map-container { background: #f8fafc !important; cursor: grab; }
        .knowledge-mindmap .map-container:active { cursor: grabbing; }
        .knowledge-mindmap .topic { box-shadow: none !important; cursor: pointer; }
      `}</style>
    </div>
  )
}
