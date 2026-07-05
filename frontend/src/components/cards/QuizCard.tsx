import React, { useState } from 'react'

interface Question {
  id?: string
  type: 'single' | 'multiple' | 'fill' | 'code'
  question: string
  options?: string[]
  correctAnswer?: string | string[]
  explanation?: string
}

interface QuizCardProps {
  data: {
    questions?: Question[]
    [key: string]: any
  }
}

const QuizCard: React.FC<QuizCardProps> = ({ data }) => {
  const questions: Question[] = data?.questions || []
  const [currentIndex, setCurrentIndex] = useState(0)
  const [answers, setAnswers] = useState<Record<number, string | string[]>>({})
  const [submitted, setSubmitted] = useState<Record<number, boolean>>({})
  const [results, setResults] = useState<Record<number, boolean>>({})
  const [showSummary, setShowSummary] = useState(false)

  if (questions.length === 0) {
    return <div style={{ color: '#9ca3af', fontSize: 13, textAlign: 'center', padding: 12 }}>暂无题目</div>
  }

  const q = questions[currentIndex]
  const isMultiple = q.type === 'multiple'
  const rawAnswer = answers[currentIndex]
  const currentAnswer: string | string[] = isMultiple
    ? (Array.isArray(rawAnswer) ? rawAnswer : rawAnswer ? [rawAnswer] : [])
    : (typeof rawAnswer === 'string' ? rawAnswer : '')
  const isSubmitted = submitted[currentIndex]

  const handleSelect = (option: string) => {
    if (isSubmitted) return
    if (isMultiple) {
      setAnswers(prev => {
        const prevArr = Array.isArray(prev[currentIndex]) ? prev[currentIndex] as string[] : []
        const next = prevArr.includes(option)
          ? prevArr.filter(o => o !== option)
          : [...prevArr, option]
        return { ...prev, [currentIndex]: next }
      })
    } else {
      setAnswers(prev => ({ ...prev, [currentIndex]: option }))
    }
  }

  const handleSubmit = () => {
    const hasAnswer = isMultiple ? (currentAnswer as string[]).length > 0 : !!currentAnswer
    if (!hasAnswer) return
    const correct = q.correctAnswer
    let isCorrect = false
    if (isMultiple && Array.isArray(correct)) {
      const selected = (currentAnswer as string[]).map(a => a.trim().toLowerCase())
      const expected = correct.map(c => c.trim().toLowerCase())
      isCorrect = selected.length === expected.length && expected.every(c => selected.includes(c))
    } else if (Array.isArray(correct)) {
      isCorrect = correct.includes(currentAnswer as string)
    } else if (correct) {
      isCorrect = (currentAnswer as string).trim().toLowerCase() === correct.trim().toLowerCase()
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

  // Summary view
  if (showSummary) {
    return (
      <div style={{ textAlign: 'center', padding: '12px 0' }}>
        <div style={{ fontSize: 36, marginBottom: 8 }}>
          {correctCount === questions.length ? '🏆' : correctCount >= questions.length / 2 ? '👍' : '💪'}
        </div>
        <div style={{ fontSize: 18, fontWeight: 700, color: '#111827', marginBottom: 4 }}>
          {correctCount}/{questions.length}
        </div>
        <div style={{ fontSize: 13, color: '#6b7280', marginBottom: 12 }}>
          正确率 {questions.length > 0 ? Math.round(correctCount / questions.length * 100) : 0}%
        </div>
        <button
          onClick={() => { setCurrentIndex(0); setAnswers({}); setSubmitted({}); setResults({}); setShowSummary(false) }}
          style={{
            background: '#8b5cf6', color: '#fff', border: 'none', borderRadius: 8,
            padding: '8px 20px', fontSize: 13, cursor: 'pointer', fontWeight: 500,
          }}
        >
          重新作答
        </button>
      </div>
    )
  }

  // Progress dots
  const progressDots = (
    <div style={{ display: 'flex', gap: 4, justifyContent: 'center', marginBottom: 12, flexWrap: 'wrap' }}>
      {questions.map((_, idx) => (
        <div
          key={idx}
          style={{
            width: 8, height: 8, borderRadius: '50%',
            background: idx === currentIndex ? '#8b5cf6' : submitted[idx] ? (results[idx] ? '#10b981' : '#ef4444') : '#e5e7eb',
            transition: 'background 0.2s',
          }}
        />
      ))}
    </div>
  )

  return (
    <div>
      {progressDots}

      {/* Question header */}
      <div style={{ fontSize: 12, color: '#8b5cf6', fontWeight: 600, marginBottom: 6 }}>
        第 {currentIndex + 1}/{questions.length} 题 · {
          q.type === 'single' ? '单选' : q.type === 'multiple' ? '多选' : q.type === 'fill' ? '填空' : '代码'
        }
      </div>

      {/* Question text */}
      <div style={{ fontSize: 14, color: '#111827', marginBottom: 12, lineHeight: 1.6 }}>
        {q.question}
      </div>

      {/* Options for choice type */}
      {(q.type === 'single' || q.type === 'multiple') && q.options && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginBottom: 12 }}>
          {q.options.map((opt, oi) => {
            const letter = String.fromCharCode(65 + oi)
            const selected = isMultiple ? (currentAnswer as string[]).includes(opt) : currentAnswer === opt
            const isCorrectOpt = isSubmitted && (Array.isArray(q.correctAnswer) ? q.correctAnswer.includes(opt) : q.correctAnswer === opt)
            const isWrong = isSubmitted && selected && !isCorrectOpt

            return (
              <button
                key={oi}
                onClick={() => handleSelect(opt)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 12px', borderRadius: 8, fontSize: 13,
                  border: isCorrectOpt ? '2px solid #10b981' : isWrong ? '2px solid #ef4444' : selected ? '2px solid #8b5cf6' : '1px solid #e5e7eb',
                  background: isCorrectOpt ? '#f0fdf4' : isWrong ? '#fef2f2' : selected ? '#f5f3ff' : '#fff',
                  cursor: isSubmitted ? 'default' : 'pointer',
                  textAlign: 'left', transition: 'all 0.15s',
                  minHeight: 44, /* touch-friendly height */
                }}
              >
                <span style={{
                  width: 22, height: 22, borderRadius: isMultiple ? 4 : '50%', fontSize: 11, fontWeight: 600,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: selected ? '#8b5cf6' : '#f3f4f6',
                  color: selected ? '#fff' : '#6b7280',
                  flexShrink: 0,
                }}>
                  {selected ? '✓' : letter}
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
            width: '100%', padding: '8px 12px', borderRadius: 8, fontSize: 13,
            border: isSubmitted
              ? (results[currentIndex] ? '2px solid #10b981' : '2px solid #ef4444')
              : '1px solid #e5e7eb',
            outline: 'none', boxSizing: 'border-box', marginBottom: 12,
          }}
        />
      )}

      {/* Code type */}
      {q.type === 'code' && (
        <textarea
          value={currentAnswer}
          onChange={(e) => !isSubmitted && setAnswers(prev => ({ ...prev, [currentIndex]: e.target.value }))}
          disabled={isSubmitted}
          placeholder="编写你的代码..."
          rows={4}
          style={{
            width: '100%', padding: '8px 12px', borderRadius: 8, fontSize: 13,
            fontFamily: 'Consolas, Monaco, monospace',
            border: '1px solid #e5e7eb', outline: 'none', boxSizing: 'border-box',
            resize: 'vertical', marginBottom: 12,
          }}
        />
      )}

      {/* Explanation after submit */}
      {isSubmitted && q.explanation && (
        <div style={{
          padding: '10px 12px', borderRadius: 8, marginBottom: 12,
          background: results[currentIndex] ? '#f0fdf4' : '#fef2f2',
          border: `1px solid ${results[currentIndex] ? '#bbf7d0' : '#fecaca'}`,
        }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: results[currentIndex] ? '#16a34a' : '#dc2626', marginBottom: 4 }}>
            {results[currentIndex] ? '✅ 回答正确' : '❌ 回答错误'}
          </div>
          <div style={{ fontSize: 12, color: '#374151', lineHeight: 1.6 }}>{q.explanation}</div>
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        {currentIndex > 0 && (
          <button onClick={handlePrev} style={{
            background: '#f3f4f6', border: 'none', borderRadius: 8,
            padding: '8px 14px', fontSize: 12, cursor: 'pointer', color: '#374151',
            minHeight: 36,
          }}>
            上一题
          </button>
        )}
        {!isSubmitted ? (
          <button onClick={handleSubmit} disabled={isMultiple ? (currentAnswer as string[]).length === 0 : !currentAnswer} style={{
            background: isMultiple ? (currentAnswer as string[]).length > 0 ? '#8b5cf6' : '#d1d5db' : currentAnswer ? '#8b5cf6' : '#d1d5db', color: '#fff', border: 'none',
            borderRadius: 8, padding: '8px 14px', fontSize: 12, cursor: isMultiple ? (currentAnswer as string[]).length > 0 ? 'pointer' : 'default' : currentAnswer ? 'pointer' : 'default',
            minHeight: 36,
          }}>
            提交
          </button>
        ) : (
          <button onClick={handleNext} style={{
            background: '#8b5cf6', color: '#fff', border: 'none',
            borderRadius: 8, padding: '8px 14px', fontSize: 12, cursor: 'pointer',
            minHeight: 36,
          }}>
            {currentIndex < questions.length - 1 ? '下一题' : '查看结果'}
          </button>
        )}
      </div>
    </div>
  )
}

export default QuizCard
