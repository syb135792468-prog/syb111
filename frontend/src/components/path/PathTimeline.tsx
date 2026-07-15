import React from 'react'
import PathStep, { PathNodeData } from './PathStep'
import type { LearningPathData } from '../../api/learningPath'

// --- 类型定义 ---
interface PathTimelineProps {
  steps?: PathNodeData[]
  onNodeClick?: (nodeId: number) => void
  onResourceClick?: (nodeId: number, resourceType: string) => void
  onComplete?: (nodeId: number) => void
  onPathUpdated?: (path: LearningPathData) => void
}

// --- 组件 ---
const PathTimeline: React.FC<PathTimelineProps> = ({ steps = [], onNodeClick, onResourceClick, onComplete, onPathUpdated }) => {
  return (
    <div className="space-y-0">
      {steps.map((step, i) => (
        <PathStep
          key={step.id || step.order}
          step={step}
          isLast={i === steps.length - 1}
          onNodeClick={onNodeClick}
          onResourceClick={onResourceClick}
          onComplete={onComplete}
          onPathUpdated={onPathUpdated}
        />
      ))}
    </div>
  )
}

export default PathTimeline
