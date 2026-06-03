import React, { useCallback } from 'react'
import { useCodeTextarea } from '../../composables/useCodeTextarea'

// --- 类型定义 ---
interface QuizAnswerProps {
  type: string
  options?: string[]
  disabled?: boolean
  value: string
  onChange: (val: string) => void
}

// --- 组件 ---
const QuizAnswer: React.FC<QuizAnswerProps> = ({
  type,
  options = [],
  disabled = false,
  value,
  onChange,
}) => {
  const selectOption = useCallback((opt: string) => {
    if (disabled) return
    onChange(opt.charAt(0))
  }, [disabled, onChange])

  const { handleKeyDown } = useCodeTextarea(value, onChange)

  // 选择题
  if (type === 'choice') {
    return (
      <div className="grid grid-cols-1 gap-3">
        {options.map((opt, idx) => {
          const letter = opt.charAt(0)
          const isSelected = letter === value
          return (
            <button
              key={idx}
              onClick={() => selectOption(opt)}
              className={`text-left px-4 py-3 rounded-xl border-2 transition-all text-sm ${
                isSelected
                  ? 'border-brand-500 bg-brand-50 shadow-md'
                  : 'border-gray-200 hover:border-gray-300 hover:shadow-sm'
              } ${disabled ? 'cursor-not-allowed opacity-70' : ''}`}
            >
              <span className="font-medium text-brand-600 mr-2">{letter}.</span>
              <span className="text-gray-700">{opt.slice(opt.indexOf('.') + 1).trim()}</span>
            </button>
          )
        })}
      </div>
    )
  }

  // 填空题
  if (type === 'fill') {
    return (
      <div className="flex items-center gap-2">
        <input
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={disabled}
          type="text"
          placeholder="输入你的答案..."
          className="flex-1 px-0 py-2 border-0 border-b-2 border-gray-300 text-sm
            focus:outline-none focus:border-brand-500 transition-colors
            disabled:bg-transparent disabled:cursor-not-allowed font-mono"
        />
      </div>
    )
  }

  // 编程题
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      onKeyDown={handleKeyDown}
      disabled={disabled}
      rows={8}
      placeholder="在此编写代码..."
      className="w-full px-4 py-3 border border-gray-200 rounded-xl text-sm
        font-mono leading-relaxed resize-y
        focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent
        disabled:bg-gray-50 disabled:cursor-not-allowed"
    />
  )
}

export default QuizAnswer
