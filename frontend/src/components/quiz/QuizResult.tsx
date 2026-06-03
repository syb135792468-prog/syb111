import React, { useMemo } from 'react'
import { CheckCircle, XCircle } from 'lucide-react'

// --- 类型定义 ---
interface ResultData {
  is_correct: boolean
  score?: number
  spent_time?: number
  correct_answer?: string
  explanation?: string
}

interface Question {
  [key: string]: unknown
}

interface QuizResultProps {
  result: ResultData
  question: Question
  type: string
}

// --- 工具函数 ---
function formatTime(seconds: number): string {
  if (!seconds && seconds !== 0) return ''
  if (seconds < 60) return `${seconds}秒`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
}

// --- 组件 ---
const QuizResultView: React.FC<QuizResultProps> = ({ result }) => {
  return (
    <div className="space-y-4 mt-6">
      {/* 正确/错误指示 */}
      <div className={`flex items-center gap-3 px-4 py-3 rounded-xl ${
        result.is_correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
      }`}>
        {result.is_correct ? (
          <CheckCircle className="w-6 h-6 text-green-500" />
        ) : (
          <XCircle className="w-6 h-6 text-red-500" />
        )}
        <div>
          <p className={`font-semibold text-sm ${result.is_correct ? 'text-green-700' : 'text-red-700'}`}>
            {result.is_correct ? '回答正确!' : '回答错误'}
          </p>
          {result.score !== undefined && (
            <p className="text-xs text-gray-500 mt-0.5">
              得分: {result.score}
              {result.spent_time !== undefined && ` | 用时: ${formatTime(result.spent_time)}`}
            </p>
          )}
        </div>
      </div>

      {/* 正确答案（答错时显示） */}
      {!result.is_correct && result.correct_answer && (
        <div className="px-4 py-3 bg-gray-50 rounded-xl">
          <p className="text-xs text-gray-500 mb-1">正确答案</p>
          <p className="text-sm font-medium text-gray-800">{result.correct_answer}</p>
        </div>
      )}

      {/* 答案解析 */}
      {result.explanation && (
        <div className="px-4 py-3 bg-gray-50 rounded-xl">
          <p className="text-xs text-gray-500 mb-1">答案解析</p>
          <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">{result.explanation}</p>
        </div>
      )}
    </div>
  )
}

export default QuizResultView
