import React, { useMemo } from 'react'
import { BookOpen, Target, Zap } from 'lucide-react'

// --- 类型定义 ---
interface ProfileCardsProps {
  level?: string
  levelDesc?: string
  goal?: string
  goalDesc?: string
  motivation?: string
  motivationDesc?: string
  motivationValue?: number
}

interface CardDef {
  key: 'level' | 'goal' | 'motivation'
  icon: React.FC<{ className?: string }>
  gradient: string
  bg: string
  label: string
}

// --- 常量 ---
const CARDS: CardDef[] = [
  { key: 'level', icon: BookOpen, gradient: 'from-blue-500 to-blue-600', bg: 'bg-blue-50', label: '知识水平' },
  { key: 'goal', icon: Target, gradient: 'from-purple-500 to-purple-600', bg: 'bg-purple-50', label: '学习目标' },
  { key: 'motivation', icon: Zap, gradient: 'from-green-500 to-green-600', bg: 'bg-green-50', label: '学习动力' },
]

// --- 组件 ---
const ProfileCards: React.FC<ProfileCardsProps> = ({
  level = '初学者',
  levelDesc = '',
  goal = '兴趣学习',
  goalDesc = '',
  motivation = '适中',
  motivationDesc = '',
  motivationValue = 50,
}) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {CARDS.map(card => {
        const Icon = card.icon
        const value = card.key === 'level' ? level : card.key === 'goal' ? goal : motivation
        const desc = card.key === 'level' ? levelDesc : card.key === 'goal' ? goalDesc : motivationDesc

        return (
          <div key={card.key} className="rounded-xl overflow-hidden shadow-sm">
            <div className={`bg-gradient-to-r px-5 py-4 text-white ${card.gradient}`}>
              <div className="flex items-center gap-2 mb-1">
                <Icon className="w-4 h-4" />
                <span className="text-xs opacity-80">{card.label}</span>
              </div>
              <p className="text-lg font-semibold">{value}</p>
            </div>
            <div className={`px-5 py-3 ${card.bg}`}>
              <p className="text-xs text-gray-500">{desc}</p>
              {/* 学习动力进度条 */}
              {card.key === 'motivation' && (
                <div className="mt-2">
                  {motivationValue > 0 ? (
                    <>
                      <div className="w-full h-1.5 bg-green-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-green-500 rounded-full transition-all duration-700 ease-out"
                          style={{ width: `${motivationValue}%` }}
                        />
                      </div>
                      <p className="text-[10px] text-green-600 mt-1">{motivationValue}/100</p>
                    </>
                  ) : (
                    <p className="text-[10px] text-gray-400">暂无学习记录</p>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ProfileCards
