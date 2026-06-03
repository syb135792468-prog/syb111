import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { createPortal } from 'react-dom'
import { X, PenTool, Code, GitBranch, FileText, Video, ChevronDown } from 'lucide-react'

// --- 类型定义 ---
type ResourceType = 'quiz' | 'code' | 'mindmap' | 'doc' | 'video'

interface QuizConfig {
  questionTypes: string[]
  questionCount: number
  difficulty: string
  includeExplanation: boolean
  customPrompt?: string
}

interface GeneratePayload {
  topic: string
  type: ResourceType
  config: Record<string, unknown>
}

interface GenerateModalProps {
  show?: boolean
  onClose: () => void
  onGenerate: (payload: GeneratePayload) => void
}

// --- 常量 ---
const TYPES = [
  { value: 'quiz' as ResourceType, label: '练习题', icon: PenTool },
  { value: 'code' as ResourceType, label: '代码案例', icon: Code },
  { value: 'mindmap' as ResourceType, label: '思维导图', icon: GitBranch },
  { value: 'doc' as ResourceType, label: '讲解文档', icon: FileText },
  { value: 'video' as ResourceType, label: '教学动画', icon: Video },
]

const QUESTION_TYPE_OPTIONS = [
  { value: 'choice', label: '选择题' },
  { value: 'fill', label: '填空题' },
  { value: 'code', label: '编程题' },
]

const DIFFICULTY_OPTIONS = [
  { value: 'auto', label: '自动' },
  { value: 'easy', label: '简单' },
  { value: 'medium', label: '中等' },
  { value: 'hard', label: '困难' },
]

function getDefaultConfig(type: ResourceType): Partial<QuizConfig> {
  switch (type) {
    case 'quiz':
      return { questionTypes: ['choice'], questionCount: 5, difficulty: 'auto', includeExplanation: true }
    default:
      return {}
  }
}

// --- 组件 ---
const GenerateModal: React.FC<GenerateModalProps> = ({ show = false, onClose, onGenerate }) => {
  // --- 表单状态 ---
  const [topic, setTopic] = useState('')
  const [type, setType] = useState<ResourceType>('quiz')
  const [config, setConfig] = useState<QuizConfig>({
    questionTypes: ['choice'],
    questionCount: 5,
    difficulty: 'auto',
    includeExplanation: true,
    customPrompt: '',
  })
  const [loading, setLoading] = useState(false)
  const [topicError, setTopicError] = useState('')
  const [quizTypeError, setQuizTypeError] = useState('')
  const [showAdvanced, setShowAdvanced] = useState(false)

  // --- 类型切换时重置配置 ---
  useEffect(() => {
    setConfig(prev => ({
      ...prev,
      ...getDefaultConfig(type),
    }))
    setQuizTypeError('')
  }, [type])

  // --- 打开弹窗时重置 ---
  useEffect(() => {
    if (show) {
      setLoading(false)
      setTopicError('')
      setQuizTypeError('')
    }
  }, [show])

  // --- 切换题型 ---
  const toggleQuestionType = useCallback((val: string) => {
    setConfig(prev => {
      const idx = prev.questionTypes.indexOf(val)
      const newTypes = [...prev.questionTypes]
      if (idx >= 0) {
        if (newTypes.length > 1) newTypes.splice(idx, 1)
      } else {
        newTypes.push(val)
      }
      return { ...prev, questionTypes: newTypes }
    })
  }, [])

  // --- 验证 ---
  const validate = useCallback((): boolean => {
    setTopicError('')
    setQuizTypeError('')
    let valid = true

    if (!topic.trim()) {
      setTopicError('请输入知识点主题')
      valid = false
    }
    if (type === 'quiz' && config.questionTypes.length === 0) {
      setQuizTypeError('至少选择一种题型')
      valid = false
    }
    return valid
  }, [topic, type, config.questionTypes])

  // --- 生成 ---
  const handleGenerate = useCallback(() => {
    if (!validate()) return
    setLoading(true)

    const genConfig: Record<string, unknown> = { ...config }
    if (!(genConfig.customPrompt as string)?.trim()) delete genConfig.customPrompt

    onGenerate({
      topic: topic.trim(),
      type,
      config: genConfig,
    })
  }, [validate, topic, type, config, onGenerate])

  // --- 关闭 ---
  const handleClose = useCallback(() => {
    setLoading(false)
    onClose()
  }, [onClose])

  // --- ESC 关闭 ---
  useEffect(() => {
    if (!show) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') handleClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [show, handleClose])

  if (!show) return null

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={handleClose}
    >
      <div
        className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 max-h-[90vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
          <h3 className="text-base font-semibold text-gray-800">生成学习资源</h3>
          <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
          {/* 知识点主题 */}
          <div>
            <label className="block text-xs text-gray-500 mb-1">知识点主题</label>
            <input
              type="text"
              value={topic}
              onChange={e => { setTopic(e.target.value); setTopicError('') }}
              placeholder="例如：循环、函数、列表"
              className={`w-full px-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition-colors ${
                topicError ? 'border-red-400' : 'border-gray-200'
              }`}
            />
            {topicError && <p className="text-xs text-red-500 mt-1">{topicError}</p>}
          </div>

          {/* 资源类型 */}
          <div>
            <label className="block text-xs text-gray-500 mb-2">资源类型</label>
            <div className="grid grid-cols-3 gap-2">
              {TYPES.map(t => {
                const Icon = t.icon
                return (
                  <button
                    key={t.value}
                    onClick={() => setType(t.value)}
                    className={`flex flex-col items-center gap-1.5 px-3 py-3 rounded-lg border text-sm transition-colors ${
                      type === t.value
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                    <span className="text-xs">{t.label}</span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 动态配置区 */}
          <div key={type} className="space-y-4 pt-2 border-t border-gray-100">
            {type === 'quiz' ? (
              <>
                {/* 题型 */}
                <div>
                  <label className="block text-xs text-gray-500 mb-2">题型</label>
                  <div className="flex flex-wrap gap-2">
                    {QUESTION_TYPE_OPTIONS.map(qt => (
                      <button
                        key={qt.value}
                        onClick={() => toggleQuestionType(qt.value)}
                        className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                          config.questionTypes.includes(qt.value)
                            ? 'border-brand-500 bg-brand-50 text-brand-700'
                            : 'border-gray-200 text-gray-500 hover:border-gray-300'
                        }`}
                      >
                        {qt.label}
                      </button>
                    ))}
                  </div>
                  {quizTypeError && <p className="text-xs text-red-500 mt-1">{quizTypeError}</p>}
                </div>

                {/* 题目数量 */}
                <div>
                  <label className="block text-xs text-gray-500 mb-1">题目数量</label>
                  <input
                    type="number"
                    value={config.questionCount}
                    onChange={e => setConfig(prev => ({ ...prev, questionCount: Number(e.target.value) }))}
                    min={1}
                    max={20}
                    className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
                  />
                </div>

                {/* 难度等级 */}
                <div>
                  <label className="block text-xs text-gray-500 mb-2">难度等级</label>
                  <div className="flex gap-2">
                    {DIFFICULTY_OPTIONS.map(d => (
                      <button
                        key={d.value}
                        onClick={() => setConfig(prev => ({ ...prev, difficulty: d.value }))}
                        className={`px-4 py-1.5 rounded-lg border text-sm transition-colors ${
                          config.difficulty === d.value
                            ? 'border-brand-500 bg-brand-50 text-brand-700'
                            : 'border-gray-200 text-gray-500 hover:border-gray-300'
                        }`}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* 包含答案和解析 */}
                <div className="flex items-center justify-between">
                  <label className="text-xs text-gray-500">包含答案和解析</label>
                  <button
                    onClick={() => setConfig(prev => ({ ...prev, includeExplanation: !prev.includeExplanation }))}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      config.includeExplanation ? 'bg-brand-600' : 'bg-gray-300'
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                        config.includeExplanation ? 'translate-x-5' : 'translate-x-0.5'
                      }`}
                    />
                  </button>
                </div>
              </>
            ) : (
              <p className="text-xs text-gray-400 text-center py-2">暂无额外配置，直接生成即可</p>
            )}
          </div>

          {/* 高级选项 */}
          <div className="border-t border-gray-100 pt-3">
            <button
              onClick={() => setShowAdvanced(prev => !prev)}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showAdvanced ? 'rotate-180' : ''}`} />
              高级选项
            </button>
            <div className={`overflow-hidden transition-all duration-300 ${showAdvanced ? 'max-h-48 mt-3 opacity-100' : 'max-h-0 opacity-0'}`}>
              <div>
                <label className="block text-xs text-gray-500 mb-1">自定义要求/提示词</label>
                <textarea
                  value={config.customPrompt || ''}
                  onChange={e => setConfig(prev => ({ ...prev, customPrompt: e.target.value }))}
                  rows={3}
                  placeholder="在这里输入你对生成内容的特殊要求，AI会严格按照你的要求生成。例如：题目要侧重考察边界条件，错误选项要有迷惑性"
                  className="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent resize-none"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-3 px-6 py-4 border-t border-gray-100 flex-shrink-0">
          <button onClick={handleClose} className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800">
            取消
          </button>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="px-4 py-2 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors disabled:opacity-50"
          >
            {loading ? '生成中...' : '开始生成'}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

export default GenerateModal
