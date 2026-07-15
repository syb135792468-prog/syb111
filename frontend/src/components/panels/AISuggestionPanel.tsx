import React, { useState, useCallback } from 'react'
import { useAuthStore } from '../../stores/auth'
import { fetchAISuggestions } from '../../api/learningProfile'
import MarkdownText from '../common/MarkdownText'
import { Loader2, RefreshCw, Lightbulb } from 'lucide-react'

const AISuggestionPanel: React.FC = () => {
  const userId = useAuthStore((s) => s.userId)

  const [suggestions, setSuggestions] = useState('')
  const [profileSummary, setProfileSummary] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const generateSuggestions = useCallback(async () => {
    if (!userId) return
    setLoading(true)
    setError('')
    try {
      const result = await fetchAISuggestions(userId)
      setSuggestions(result.suggestions || '')
      setProfileSummary(result.profile_summary || '')
    } catch (e) {
      setError('生成建议失败，请稍后重试')
    } finally {
      setLoading(false)
    }
  }, [userId])

  // 仅在用户点击按钮时生成，不自动调用

  if (!userId) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400 px-6">
        <Lightbulb className="w-8 h-8 mb-3 opacity-30" />
        <p className="text-sm text-center">请先登录以获取 AI 学习建议</p>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto px-4 py-3 space-y-4">
      {/* 空态：未生成时提示用户主动点击 */}
      {!suggestions && !loading && !error && (
        <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
          <Lightbulb className="w-8 h-8 mb-3 text-amber-400" />
          <p className="text-sm text-gray-600 mb-1">点击下方按钮生成 AI 学习建议</p>
          <p className="text-xs text-gray-400 mb-4">基于你的学习画像、薄弱点和近期表现</p>
          <button
            onClick={generateSuggestions}
            className="flex items-center gap-1.5 px-4 py-2 text-xs font-medium text-amber-700 border border-amber-200 bg-amber-50 rounded-lg hover:bg-amber-100 transition-colors"
          >
            <Lightbulb className="w-3.5 h-3.5" />
            生成建议
          </button>
        </div>
      )}

      {/* 画像摘要 */}
      {profileSummary && (
        <div>
          <p className="text-xs font-semibold text-gray-500 mb-1.5 uppercase tracking-wide">你的学习画像</p>
          <div className="text-xs text-gray-600 bg-gray-50 border border-gray-100 rounded-lg p-3 leading-relaxed">
            <MarkdownText content={profileSummary} />
          </div>
        </div>
      )}

      {/* 加载中 */}
      {loading && (
        <div className="flex flex-col items-center justify-center py-8 text-gray-400">
          <Loader2 className="w-5 h-5 animate-spin mb-2" />
          <p className="text-xs">AI 正在分析你的学习画像...</p>
        </div>
      )}

      {/* 错误 */}
      {error && (
        <div className="text-xs text-red-500 bg-red-50 border border-red-100 rounded-lg p-3">
          {error}
        </div>
      )}

      {/* 建议内容 */}
      {suggestions && !loading && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-1.5 text-amber-600">
              <Lightbulb className="w-3.5 h-3.5" />
              <span className="text-xs font-semibold uppercase tracking-wide">AI 学习建议</span>
            </div>
            <button
              onClick={generateSuggestions}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              <RefreshCw className="w-3 h-3" />
              重新生成
            </button>
          </div>
          <div className="text-xs text-gray-700 leading-relaxed bg-amber-50 border border-amber-100 rounded-lg p-3">
            <MarkdownText content={suggestions} />
          </div>
        </div>
      )}
    </div>
  )
}

export default AISuggestionPanel
