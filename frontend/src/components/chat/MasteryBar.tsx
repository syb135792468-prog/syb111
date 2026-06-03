import React, { useEffect, useState } from 'react'
import { useChatStore } from '../../stores/chat'

const STAGE_LABELS: Record<string, string> = {
  concept_check: '概念理解',
  application: '应用实践',
  advanced_application: '进阶应用',
  extension: '拓展延伸',
  summary: '学习总结',
  ask_question: '提问中',
  explain_concept: '讲解中',
  code_demo: '代码演示',
  practice_exercise: '巩固练习',
  rephrase_question: '换角度提问',
  relate_knowledge: '关联知识',
  teaching_decision: '思考中',
}

const ENCOURAGEMENTS = [
  '太棒了！',
  '完全正确！',
  '很好！继续加油！',
  '你已经掌握了！',
  '进步明显！',
]

export function MasteryBar() {
  const masteryData = useChatStore((s) => s.masteryData)
  const [animatingKp, setAnimatingKp] = useState<string | null>(null)
  const [encouragement, setEncouragement] = useState<string | null>(null)

  useEffect(() => {
    if (!masteryData?.changes || Object.keys(masteryData.changes).length === 0) return

    // 找到变化最大的知识点
    let maxChange = 0
    let maxKp = ''
    for (const [kp, change] of Object.entries(masteryData.changes)) {
      const diff = change.to - change.from
      if (diff > maxChange) {
        maxChange = diff
        maxKp = kp
      }
    }

    if (maxKp) {
      setAnimatingKp(maxKp)
      // 显示鼓励语
      const randomEncouragement = ENCOURAGEMENTS[Math.floor(Math.random() * ENCOURAGEMENTS.length)]
      setEncouragement(randomEncouragement)

      // 动画结束后清除
      const timer = setTimeout(() => {
        setAnimatingKp(null)
        setEncouragement(null)
      }, 2000)

      return () => clearTimeout(timer)
    }
  }, [masteryData])

  if (!masteryData || Object.keys(masteryData.mastery_level).length === 0) {
    return null
  }

  const { mastery_level, changes, current_stage } = masteryData

  return (
    <div className="px-4 py-3 border-t border-gray-100 bg-gradient-to-r from-blue-50 to-indigo-50">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-gray-500">
          {(() => {
            // 动态阶段格式: "主题-动作"，提取动作部分查表
            const parts = current_stage.split('-')
            const action = parts.length > 1 ? parts[parts.length - 1] : current_stage
            return STAGE_LABELS[action] || STAGE_LABELS[current_stage] || action
          })()}
        </span>
        <div className="flex items-center gap-2">
          {encouragement && (
            <span className="text-xs text-green-600 animate-fade-in font-medium">
              {encouragement}
            </span>
          )}
          <span className="text-xs text-gray-400">掌握度</span>
        </div>
      </div>
      <div className="space-y-2">
        {Object.entries(mastery_level).map(([kp, score]) => {
          const change = changes[kp]
          const percent = Math.round(score * 100)
          const prevPercent = change ? Math.round(change.from * 100) : null
          const isAnimating = animatingKp === kp
          const isMastered = percent >= 80

          return (
            <div key={kp} className={`group ${isAnimating ? 'animate-pulse-once' : ''}`}>
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs text-gray-700 truncate max-w-[60%]" title={kp}>
                  {isMastered && <span className="text-green-500 mr-1">✓</span>}
                  {kp}
                </span>
                <span className="text-xs font-mono">
                  {change && prevPercent !== null ? (
                    <>
                      <span className="text-gray-400">{prevPercent}%</span>
                      <span className="text-gray-400 mx-0.5">&rarr;</span>
                      <span className={`transition-all duration-300 ${
                        isAnimating ? 'scale-110 font-bold' : ''
                      } ${isMastered ? 'text-green-600' : percent >= 50 ? 'text-blue-600' : 'text-amber-600'}`}>
                        {percent}%
                      </span>
                    </>
                  ) : (
                    <span className={isMastered ? 'text-green-600' : percent >= 50 ? 'text-blue-600' : 'text-amber-600'}>
                      {percent}%
                    </span>
                  )}
                </span>
              </div>
              <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ease-out ${
                    isAnimating ? 'animate-shimmer' : ''
                  } ${isMastered ? 'bg-green-500' : percent >= 50 ? 'bg-blue-500' : 'bg-amber-500'}`}
                  style={{ width: `${percent}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
