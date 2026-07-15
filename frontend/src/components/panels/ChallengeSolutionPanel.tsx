import React from 'react'
import { useAppStore } from '../../stores/app'
import MarkdownText from '../common/MarkdownText'
import { CheckCircle2, XCircle, BookOpen, Lightbulb, Code2 } from 'lucide-react'

const DIFFICULTY_MAP: Record<string, { label: string; color: string }> = {
  easy: { label: '简单', color: 'bg-green-100 text-green-700' },
  medium: { label: '中等', color: 'bg-amber-100 text-amber-700' },
  hard: { label: '困难', color: 'bg-red-100 text-red-700' },
}

const ChallengeSolutionPanel: React.FC = () => {
  const { data } = useAppStore((s) => s.rightPanel)
  const challenge = data?.challenge as Record<string, unknown> | undefined
  const submitResult = data?.submitResult as Record<string, unknown> | undefined
  const code = (data?.code as string) || ''
  const hints = (data?.hints as string[]) || []

  if (!submitResult) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <BookOpen className="w-8 h-8 mb-3 opacity-30" />
        <p className="text-sm text-center">提交答案后查看解题思路</p>
      </div>
    )
  }

  const isCorrect = submitResult.is_correct as boolean
  const correctAnswer = (submitResult.correct_answer as string) || ''
  const explanation = (submitResult.explanation as string) || ''
  const feedback = (submitResult.feedback as string) || ''
  const title = (challenge?.title as string) || ''
  const difficulty = (challenge?.difficulty as string) || ''
  const knowledgePoint = (challenge?.knowledge_point as string) || ''
  const diffConfig = DIFFICULTY_MAP[difficulty]

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      {/* 结果状态 */}
      <div className={`flex items-center gap-3 p-3 rounded-lg ${
        isCorrect ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
      }`}>
        {isCorrect ? (
          <CheckCircle2 className="w-6 h-6 text-green-500 flex-shrink-0" />
        ) : (
          <XCircle className="w-6 h-6 text-red-500 flex-shrink-0" />
        )}
        <div>
          <p className={`text-sm font-semibold ${isCorrect ? 'text-green-700' : 'text-red-700'}`}>
            {isCorrect ? '回答正确！' : '回答错误'}
          </p>
          {feedback && (
            <p className="text-xs text-gray-600 mt-0.5">{feedback}</p>
          )}
        </div>
      </div>

      {/* 题目信息 */}
      {(title || difficulty || knowledgePoint) && (
        <div className="pb-3 border-b border-gray-100">
          {title && <p className="text-sm font-medium text-gray-800 mb-1.5">{title}</p>}
          <div className="flex items-center gap-2 flex-wrap">
            {diffConfig && (
              <span className={`text-xs px-2 py-0.5 rounded-full ${diffConfig.color}`}>
                {diffConfig.label}
              </span>
            )}
            {knowledgePoint && (
              <span className="text-xs text-gray-400">{knowledgePoint}</span>
            )}
          </div>
        </div>
      )}

      {/* 你的代码 */}
      {code && (
        <Section icon={<Code2 className="w-3.5 h-3.5" />} label="你的代码" color="text-gray-600">
          <pre className="text-xs bg-gray-900 text-gray-100 rounded-lg p-2.5 overflow-x-auto font-mono leading-relaxed">
            {code}
          </pre>
        </Section>
      )}

      {/* 正确答案 */}
      {correctAnswer && !isCorrect && (
        <Section icon={<CheckCircle2 className="w-3.5 h-3.5" />} label="正确答案" color="text-green-600">
          <pre className="text-xs bg-green-50 text-green-800 border border-green-100 rounded-lg p-2.5 overflow-x-auto font-mono leading-relaxed">
            {correctAnswer}
          </pre>
        </Section>
      )}

      {/* 解题思路 */}
      {explanation && (
        <Section icon={<Lightbulb className="w-3.5 h-3.5" />} label="解题思路" color="text-blue-600">
          <div className="text-xs text-blue-800 bg-blue-50 border border-blue-100 rounded-lg p-3 leading-relaxed">
            <MarkdownText content={explanation} />
          </div>
        </Section>
      )}

      {/* 使用的提示 */}
      {hints.length > 0 && (
        <Section icon={<Lightbulb className="w-3.5 h-3.5" />} label="使用的提示" color="text-amber-600">
          <div className="space-y-1.5">
            {hints.map((h, i) => (
              <div key={i} className="text-xs text-amber-800 bg-amber-50 border border-amber-100 rounded-lg px-3 py-2">
                <span className="text-amber-500 font-medium">提示 {i + 1}：</span>{h}
              </div>
            ))}
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
}> = ({ icon, label, color, children }) => (
  <div>
    <div className={`flex items-center gap-1.5 mb-2 ${color}`}>
      {icon}
      <span className="text-xs font-semibold uppercase tracking-wide">{label}</span>
    </div>
    {children}
  </div>
)

export default ChallengeSolutionPanel
