import React, { useState } from 'react'

interface Question {
  id?: string
  type: 'single' | 'multiple' | 'fill' | 'code'
  question: string
  options?: string[]
  correctAnswer?: string | string[]
  explanation?: string
}

interface FullscreenQuizProps {
  data: {
    questions?: Question[]
    [key: string]: any
  }
}

const FullscreenQuiz: React.FC<FullscreenQuizProps> = ({ data }) => {
  const questions: Question[] = data?.questions || []
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState<Record<number, boolean>>({})
  const [results, setResults] = useState<Record<number, boolean>>({})
  const [showSummary, setShowSummary] = useState(false)

  if (questions.length === 0) {
    return <div style={{ color: '#9ca3af', fontSize: 15, textAlign: 'center', padding: 40 }}>暂无题目</div>
  }

  const q = questions[currentIndex]
  const currentAnswer = answers[currentIndex] || ''
  const isSubmitted = submitted[currentIndex]

  const handleSelect = (option: string) => {
    if (isSubmitted) return
    setAnswers(prev => ({ ...prev, [currentIndex]: option }))
  }

  const handleSubmit = () => {
    if (!currentAnswer) return
    const correct = q.correctAnswer
    let isCorrect = false
    if (Array.isArray(correct)) {
      isCorrect = correct.includes(currentAnswer)
    } else if (correct) {
      isCorrect = currentAnswer.trim().toLowerCase() === correct.trim().toLowerCase()
    }
    setSubmitted(prev => ({ ...prev, [currentIndex]: true }))
    setResults(prev => ({ ...prev, [currentIndex]: isCorrect }))
  }

  const handleNext = () => {
    if (currentIndex < questions.length - 1) {
      setCurrentIndex(currentIndex + 1)
    } else {
      setShowSummary(true)
    }
  }

  const handlePrev = () => {
    if (currentIndex > 0) setCurrentIndex(currentIndex - 1)
  }

  const answeredCount = Object.keys(submitted).length
  const correctCount = Object.values(results).filter(Boolean).length

  if (showSummary) {
    return (
      <div style={{ textAlign: 'center', padding: '40px 0' }}>
        <div style={{ fontSize: 64, marginBottom: 16 }}>
          {correctCount === questions.length ? '🏆' : correctCount >= questions.length / 2 ? '👍' : '💪'}
        </div>
        <div style={{ fontSize: 32, fontWeight: 700, color: '#111827', marginBottom: 8 }}>
          {correctCount}/{questions.length}
        </div>
        <div style={{ fontSize: 16, color: '#6b7280', marginBottom: 24 }}>
          正确率 {questions.length > 0 ? Math.round(correctCount / questions.length * 100) : 0}%
        </div>
        <button
          onClick={() => { setCurrentIndex(0); setAnswers({}); setSubmitted({}); setResults({}); setShowSummary(false) }}
          style={{
            background: '#8b5cf6', color: '#fff', border: 'none', borderRadius: 10,
            padding: '12px 32px', fontSize: 15, cursor: 'pointer', fontWeight: 600,
          }}
        >
          重新作答
        </button>
      </div>
    )
  }

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      {/* Progress bar */}
      <div style={{
        height: 6, background: '#e5e7eb', borderRadius: 3, marginBottom: 24,
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%', background: '#8b5cf6', borderRadius: 3,
          width: `${((currentIndex + (isSubmitted ? 1 : 0)) / questions.length) * 100}%`,
          transition: 'width 0.3s ease',
        }} />
      </div>

      {/* Question header */}
      <div style={{ fontSize: 13, color: '#8b5cf6', fontWeight: 600, marginBottom: 8 }}>
        第 {currentIndex + 1}/{questions.length} 题 · {
          q.type === 'single' ? '单选' : q.type === 'multiple' ? '多选' : q.type === 'fill' ? '填空' : '代码'
        }
      </div>

      {/* Question text */}
      <div style={{ fontSize: 17, color: '#111827', marginBottom: 20, lineHeight: 1.7 }}>
        {q.question}
      </div>

      {/* Options */}
      {(q.type === 'single' || q.type === 'multiple') && q.options && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 20 }}>
          {q.options.map((opt, oi) => {
            const letter = String.fromCharCode(65 + oi)
            const selected = currentAnswer === opt
            const isCorrectOpt = isSubmitted && (Array.isArray(q.correctAnswer) ? q.correctAnswer.includes(opt) : q.correctAnswer === opt)
            const isWrong = isSubmitted && selected && !isCorrectOpt

            return (
              <button
                key={oi}
                onClick={() => handleSelect(opt)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 14,
                  padding: '14px 18px', borderRadius: 10, fontSize: 15,
                  border: isCorrectOpt ? '2px solid #10b981' : isWrong ? '2px solid #ef4444' : selected ? '2px solid #8b5cf6' : '1px solid #e5e7eb',
                  background: isCorrectOpt ? '#f0fdf4' : isWrong ? '#fef2f2' : selected ? '#f5f3ff' : '#fff',
                  cursor: isSubmitted ? 'default' : 'pointer',
                  textAlign: 'left', transition: 'all 0.15s',
                }}
              >
                <span style={{
                  width: 28, height: 28, borderRadius: '50%', fontSize: 13, fontWeight: 600,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: selected ? '#8b5cf6' : '#f3f4f6',
                  color: selected ? '#fff' : '#6b7280',
                  flexShrink: 0,
                }}>
                  {letter}
                </span>
                <span style={{ color: '#374151' }}>{opt}</span>
              </button>
            )
          })}
        </div>
      )}

      {/* Fill type */}
      {q.type === 'fill' && (
        <input
          value={currentAnswer}
          onChange={(e) => !isSubmitted && setAnswers(prev => ({ ...prev, [currentIndex]: e.target.value }))}
          disabled={isSubmitted}
          placeholder="输入你的答案..."
          style={{
            width: '100%', padding: '12px 16px', borderRadius: 10, fontSize: 15,
            border: isSubmitted
              ? (results[currentIndex] ? '2px solid #10b981' : '2px solid #ef4444')
              : '1px solid #e5e7eb',
            outline: 'none', boxSizing: 'border-box', marginBottom: 20,
          }}
        />
      )}

      {/* Explanation after submit */}
      {isSubmitted && q.explanation && (
        <div style={{
          padding: '14px 18px', borderRadius: 10, marginBottom: 20,
          background: results[currentIndex] ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${results[currentIndex] ? '#bbf7d0' : '#fecaca'}`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: results[currentIndex] ? '#16a34a' : '#dc2626', marginBottom: 6 }}>
            {results[currentIndex] ? '✅ 回答正确' : '❌ 回答错误'}
          </div>
          <div style={{ fontSize: 14, color: '#374151', lineHeight: 1.7 }}>{q.explanation}</div>
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
        {currentIndex > 0 && (
          <button onClick={handlePrev} style={{
            background: '#f3f4f6', border: 'none', borderRadius: 10,
            padding: '10px 20px', fontSize: 14, cursor: 'pointer', color: '#374151',
          }}>
            上一题
          </button>
        )}
        {!isSubmitted ? (
          <button onClick={handleSubmit} disabled={!currentAnswer} style={{
            background: currentAnswer ? '#8b5cf6' : '#d1d5db', color: '#fff', border: 'none',
            borderRadius: 10, padding: '10px 20px', fontSize: 14, cursor: currentAnswer ? 'pointer' : 'default',
          }}>
            提交
          </button>
        ) : (
          <button onClick={handleNext} style={{
            background: '#8b5cf6', color: '#fff', border: 'none',
            borderRadius: 10, padding: '10px 20px', fontSize: 14, cursor: 'pointer',
          }}>
            {currentIndex < questions.length - 1 ? '下一题' : '查看结果'}
          </button>
        )}
      </div>
    </div>
  )
}

export default FullscreenQuiz
