import React, { useMemo } from 'react'

// --- 类型定义 ---
interface Question {
  title?: string
  questionText?: string
  [key: string]: unknown
}

interface QuizQuestionProps {
  question: Question
  type: string
  children?: React.ReactNode
}

// --- 常量 ---
const TYPE_LABELS: Record<string, string> = { choice: '选择题', fill: '填空题', code: '编程题' }

// --- 组件 ---
const QuizQuestion: React.FC<QuizQuestionProps> = ({ question, type, children }) => {
  const typeLabel = useMemo(() => TYPE_LABELS[type] || '练习题', [type])

  return (
    <div className="space-y-4">
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-brand-50 text-brand-600">
        {typeLabel}
      </span>
      <h3 className="text-base font-semibold text-gray-800">{question.title}</h3>
      <div className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{question.questionText}</div>
      {children}
    </div>
  )
}

export default QuizQuestion
