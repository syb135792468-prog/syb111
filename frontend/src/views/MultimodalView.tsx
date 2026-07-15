import React, { useState, useCallback, useRef, useEffect } from 'react'
import { Upload, Code, AlertTriangle, BookOpen, Loader2, Heart, MessageCircle, Copy, Check } from 'lucide-react'
import { useAppStore } from '../stores/app'
import { useAuthStore } from '../stores/auth'
import { useLearningCenterStore } from '../stores/learningCenter'
import { uploadImage, ImageUploadResult } from '../api/images'
import { analyzeCodeImage, saveAnalysisResult, getMultimodalHistory, toggleFavorite, MultimodalAnalysisResult, MultimodalHistoryItem, CodeProblem, Exercise } from '../api/multimodal'

type AnalysisStep = 'upload' | 'recognizing' | 'analyzing' | 'complete' | 'error'

const STORAGE_KEY = 'multimodal_analysis_state'

interface CodeSelection {
  text: string
  x: number
  y: number
}

function hasTextSelection() {
  const sel = window.getSelection()
  return !!sel && sel.toString().trim().length > 0
}

const MultimodalView: React.FC = () => {
  const authStore = useAuthStore()
  const recordLearningEvent = useLearningCenterStore((state) => state.recordEvent)
  const [step, setStep] = useState<AnalysisStep>('upload')
  const [imageUrl, setImageUrl] = useState<string>('')
  const [previewUrl, setPreviewUrl] = useState<string>('')
  const [result, setResult] = useState<MultimodalAnalysisResult | null>(null)
  const [error, setError] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [currentResourceId, setCurrentResourceId] = useState<number | null>(null)
  const [historyItems, setHistoryItems] = useState<MultimodalHistoryItem[]>([])
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [historyHasMore, setHistoryHasMore] = useState(false)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [codeSelection, setCodeSelection] = useState<CodeSelection | null>(null)
  const [copiedCode, setCopiedCode] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const codeBlockRef = useRef<HTMLPreElement>(null)

  const abortControllerRef = useRef<AbortController | null>(null)
  const uploadAreaRef = useRef<HTMLDivElement>(null)

  // 从 sessionStorage 恢复状态
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY)
      if (saved) {
        const state = JSON.parse(saved)
        if (state.step === 'complete' && state.result) {
          setStep(state.step)
          setImageUrl(state.imageUrl || '')
          setPreviewUrl(state.previewUrl || '')
          setResult(state.result)
          setSaved(state.saved || false)
        }
      }
    } catch {}
  }, [])

  // 状态变化时保存到 sessionStorage
  useEffect(() => {
    if (step === 'complete' && result) {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
        step, imageUrl, previewUrl, result, saved,
      }))
    }
  }, [step, imageUrl, previewUrl, result, saved])

  // 加载历史列表
  const loadHistory = useCallback(async (offset = 0, append = false) => {
    setLoadingHistory(true)
    try {
      const data = await getMultimodalHistory(10, offset)
      setHistoryItems(prev => append ? [...prev, ...data.items] : data.items)
      setHistoryHasMore(data.has_more)
      setHistoryOffset(offset + data.items.length)
    } catch {
      // 静默失败，不影响主流程
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  // 上传页加载历史
  useEffect(() => {
    if (step === 'upload') {
      loadHistory()
    }
  }, [step, loadHistory])

  const handleFileSelect = useCallback(async (file: File) => {
    // 验证文件
    const allowedTypes = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
    if (!allowedTypes.includes(file.type)) {
      setError(`不支持的文件类型: ${file.type}，支持 PNG/JPG/GIF/WebP`)
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      setError('文件太大，最大支持 10MB')
      return
    }

    setError('')
    setSaved(false)
    setPreviewUrl(prev => {
      if (prev.startsWith('blob:')) URL.revokeObjectURL(prev)
      return URL.createObjectURL(file)
    })
    setStep('recognizing')

    try {
      // 上传图片
      const uploadResult: ImageUploadResult = await uploadImage(file)
      setImageUrl(uploadResult.url)

      // 开始分析
      const abortController = new AbortController()
      abortControllerRef.current = abortController

      const analysisResult: MultimodalAnalysisResult = {
        code_text: '',
        explanation: '',
        problems: [],
        exercises: [],
        knowledge_points: [],
      }

      await analyzeCodeImage(
        uploadResult.url,
        (event, rawData) => {
          // SSE 数据是 StreamEvent 包装，实际内容在 rawData.data 里
          const data = rawData.data || rawData
          if (event === 'code_recognition') {
            analysisResult.code_text = data.code_text || ''
            analysisResult.recognition_warning = data.recognition_warning || null
            setStep('analyzing')
          } else if (event === 'multimodal_analysis') {
            analysisResult.explanation = data.explanation || ''
            analysisResult.problems = data.problems || []
            analysisResult.knowledge_points = data.knowledge_points || []
          } else if (event === 'multimodal_exercises') {
            analysisResult.exercises = data.exercises || []
          } else if (event === 'error') {
            throw new Error(data.error || '分析失败')
          }
        },
        abortController.signal
      )

      setResult(analysisResult)
      setStep('complete')
      recordLearningEvent({
        userId: authStore.userId,
        sourcePage: 'multimodal',
        actionType: 'multimodal_analyzed',
        topic: analysisResult.knowledge_points[0] || '多模态代码分析',
        knowledgePoint: analysisResult.knowledge_points[0] || undefined,
        knowledgePoints: analysisResult.knowledge_points,
      })
      // 右侧面板不自动弹出，等用户选中代码片段后主动点击"解释"
    } catch (err: any) {
      if (err.name === 'AbortError') {
        setError('分析已取消')
      } else {
        setError(err.message || '分析失败')
      }
      setStep('error')
    }
  }, [authStore.userId, recordLearningEvent])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFileSelect(files[0])
    }
  }, [handleFileSelect])

  const handleFileInput = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleFileSelect(files[0])
    }
  }, [handleFileSelect])

  // 粘贴图片处理
  const handlePaste = useCallback((e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items
    if (!items) return
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        e.preventDefault()
        const file = item.getAsFile()
        if (file) {
          const ext = item.type.split('/')[1] || 'png'
          const namedFile = new File([file], `clipboard_${Date.now()}.${ext}`, { type: item.type })
          handleFileSelect(namedFile)
        }
        return
      }
    }
  }, [handleFileSelect])

  // 点击历史条目恢复结果
  const handleHistoryClick = useCallback((item: MultimodalHistoryItem) => {
    const resultData = {
      code_text: item.code_text,
      explanation: item.explanation,
      problems: item.problems,
      exercises: item.exercises,
      knowledge_points: item.knowledge_points,
    }
    setResult(resultData)
    setImageUrl(item.image_url)
    setPreviewUrl(prev => {
      if (prev.startsWith('blob:')) URL.revokeObjectURL(prev)
      return item.image_url
    })
    setSaved(item.in_library)
    setCurrentResourceId(item.id)
    setStep('complete')
    recordLearningEvent({
      userId: authStore.userId,
      sourcePage: 'multimodal',
      actionType: 'resource_viewed',
      topic: item.title || item.knowledge_points[0] || '多模态分析记录',
      knowledgePoint: item.knowledge_points[0] || undefined,
      knowledgePoints: item.knowledge_points,
      resourceId: item.id,
    })
    // 右侧面板不自动弹出，等用户选中代码片段后主动点击"解释"
  }, [authStore.userId, recordLearningEvent])

  // 收藏/取消收藏历史条目
  const handleToggleFavorite = useCallback(async (e: React.MouseEvent, itemId: number) => {
    e.stopPropagation()
    try {
      const res = await toggleFavorite(itemId)
      setHistoryItems(prev => prev.map(h =>
        h.id === itemId ? { ...h, in_library: res.in_library } : h
      ))
    } catch {
      // 静默失败
    }
  }, [])

  const handleSave = useCallback(async () => {
    if (!result || !imageUrl) return
    setSaving(true)
    try {
      // 如果已有资源ID，直接收藏
      if (currentResourceId) {
        const res = await toggleFavorite(currentResourceId)
        setSaved(res.in_library)
      } else {
        // 新分析结果，保存并收藏
        const res = await saveAnalysisResult(imageUrl, result)
        setSaved(true)
        setCurrentResourceId(res.id)
      }
      loadHistory()
    } catch (err: any) {
      setError(err.message || '收藏失败')
    } finally {
      setSaving(false)
    }
  }, [result, imageUrl, currentResourceId, loadHistory])

  const handleCodeMouseUp = useCallback(() => {
    setTimeout(() => {
      const selection = window.getSelection()
      const text = selection?.toString().trim()
      if (text && text.length > 1 && selection && selection.rangeCount > 0) {
        const range = selection.getRangeAt(0)
        const rect = range.getBoundingClientRect()
        if (codeBlockRef.current && codeBlockRef.current.contains(selection.anchorNode)) {
          setCodeSelection({
            text,
            x: rect.left + rect.width / 2,
            y: rect.top,
          })
          setCopiedCode(false)
        }
      }
    }, 10)
  }, [])

  // 选区浮窗 dismiss：mousedown / scroll 时检查选区为空则清空
  useEffect(() => {
    if (!codeSelection) return
    const handleDismiss = () => {
      setTimeout(() => {
        const selection = window.getSelection()
        if (!selection || selection.toString().trim().length === 0) {
          setCodeSelection(null)
        }
      }, 200)
    }
    const handleScroll = () => {
      setCodeSelection(null)
      window.getSelection()?.removeAllRanges()
    }
    document.addEventListener('mousedown', handleDismiss)
    document.addEventListener('scroll', handleScroll, true)
    return () => {
      document.removeEventListener('mousedown', handleDismiss)
      document.removeEventListener('scroll', handleScroll, true)
    }
  }, [codeSelection])

  const handleExplainSelection = useCallback(() => {
    if (!codeSelection || !result) return
    const fullContext = `${result.code_text}\n\n整体解释：${result.explanation || ''}`
    useAppStore.getState().openRightPanel('analysis-detail', {
      selectedCode: codeSelection.text,
      fullContext,
    })
    setCodeSelection(null)
    window.getSelection()?.removeAllRanges()
  }, [codeSelection, result])

  const handleCopySelection = useCallback(() => {
    if (!codeSelection) return
    navigator.clipboard.writeText(codeSelection.text).then(() => {
      setCopiedCode(true)
      setTimeout(() => setCopiedCode(false), 1500)
    })
  }, [codeSelection])

  const handleHistoryExplain = useCallback((item: MultimodalHistoryItem) => {
    const fullContext = `${item.code_text}\n\n整体解释：${item.explanation || ''}`
    useAppStore.getState().openRightPanel('analysis-detail', {
      selectedCode: '',
      fullContext,
    })
  }, [])

  const handleReset = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    setStep('upload')
    setImageUrl('')
    setPreviewUrl(prev => {
      if (prev.startsWith('blob:')) URL.revokeObjectURL(prev)
      return ''
    })
    setResult(null)
    setError('')
    setSaved(false)
    setCurrentResourceId(null)
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  return (
    <div style={{ maxWidth: 900, margin: '0 auto', padding: 24, height: '100%', overflowY: 'auto' }}>
      <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8, color: '#111827' }}>
        📸 多模态代码分析
      </h1>
      <p style={{ color: '#6b7280', marginBottom: 24 }}>
        上传手写代码图片，AI 自动识别、解释、诊断问题并生成练习题
      </p>

      {/* 上传区域 */}
      {step === 'upload' && (
        <>
          <div
            ref={uploadAreaRef}
            tabIndex={0}
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            onPaste={handlePaste}
            style={{
              border: '2px dashed #d1d5db',
              borderRadius: 12,
              padding: 48,
              textAlign: 'center',
              cursor: 'pointer',
              transition: 'border-color 0.2s',
              background: '#f9fafb',
              outline: 'none',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#10b981')}
            onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#d1d5db')}
          >
            <Upload style={{ width: 48, height: 48, color: '#9ca3af', margin: '0 auto 16px' }} />
            <p style={{ fontSize: 16, fontWeight: 500, color: '#374151', marginBottom: 8 }}>
              点击、拖拽或 Ctrl+V 粘贴代码图片
            </p>
            <p style={{ fontSize: 14, color: '#9ca3af' }}>
              支持 PNG、JPG、GIF、WebP，最大 10MB
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              onChange={handleFileInput}
              style={{ display: 'none' }}
            />
          </div>

          {/* 分析历史 */}
          {historyItems.length > 0 && (
            <div style={{ marginTop: 32 }}>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: '#111827' }}>
                📋 最近分析
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {historyItems.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleHistoryClick(item)}
                    style={{
                      padding: '12px 16px',
                      borderRadius: 8,
                      border: '1px solid #e5e7eb',
                      background: '#fff',
                      cursor: 'pointer',
                      transition: 'border-color 0.15s, box-shadow 0.15s',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.borderColor = '#10b981'
                      e.currentTarget.style.boxShadow = '0 1px 4px rgba(16,185,129,0.15)'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.borderColor = '#e5e7eb'
                      e.currentTarget.style.boxShadow = 'none'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 }}>
                      <span style={{ fontSize: 14, fontWeight: 500, color: '#111827' }}>
                        {item.title || '未命名分析'}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleHistoryExplain(item)
                        }}
                        title="在右侧面板解释代码"
                        style={{
                          border: 'none',
                          background: 'none',
                          cursor: 'pointer',
                          padding: 2,
                          flexShrink: 0,
                          color: '#9ca3af',
                        }}
                      >
                        <MessageCircle style={{ width: 16, height: 16 }} />
                      </button>
                      <button
                        onClick={(e) => handleToggleFavorite(e, item.id)}
                        title={item.in_library ? '取消收藏' : '收藏'}
                        style={{
                          border: 'none',
                          background: 'none',
                          cursor: 'pointer',
                          padding: 2,
                          flexShrink: 0,
                          marginLeft: 4,
                        }}
                      >
                        <Heart
                          style={{ width: 16, height: 16 }}
                          fill={item.in_library ? '#ef4444' : 'none'}
                          color={item.in_library ? '#ef4444' : '#9ca3af'}
                        />
                      </button>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                        {item.knowledge_points.slice(0, 3).map((kp, i) => (
                          <span key={i} style={{
                            padding: '1px 8px',
                            borderRadius: 10,
                            background: '#dbeafe',
                            color: '#1d4ed8',
                            fontSize: 12,
                          }}>{kp}</span>
                        ))}
                      </div>
                      <span style={{ fontSize: 12, color: '#9ca3af' }}>
                        {item.created_at ? new Date(item.created_at).toLocaleDateString('zh-CN') : ''}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
              {historyHasMore && (
                <button
                  onClick={() => loadHistory(historyOffset, true)}
                  disabled={loadingHistory}
                  style={{
                    marginTop: 12,
                    padding: '6px 16px',
                    borderRadius: 6,
                    border: '1px solid #d1d5db',
                    background: '#f9fafb',
                    cursor: 'pointer',
                    fontSize: 13,
                    color: '#374151',
                    width: '100%',
                  }}
                >
                  {loadingHistory ? '加载中...' : '加载更多'}
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* 分析中 */}
      {(step === 'recognizing' || step === 'analyzing') && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          {previewUrl && (
            <img
              src={previewUrl}
              alt="预览"
              style={{
                maxWidth: 400,
                maxHeight: 300,
                borderRadius: 8,
                marginBottom: 24,
                border: '1px solid #e5e7eb',
              }}
            />
          )}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12 }}>
            <Loader2 style={{ width: 24, height: 24, color: '#10b981', animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: 16, color: '#374151' }}>
              {step === 'recognizing' ? '正在识别代码...' : '正在分析代码...'}
            </span>
          </div>
        </div>
      )}

      {/* 错误 */}
      {step === 'error' && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <AlertTriangle style={{ width: 48, height: 48, color: '#ef4444', margin: '0 auto 16px' }} />
          <p style={{ fontSize: 16, color: '#ef4444', marginBottom: 16 }}>{error}</p>
          <button
            onClick={handleReset}
            style={{
              padding: '8px 24px',
              borderRadius: 8,
              border: 'none',
              background: '#10b981',
              color: '#fff',
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            重新上传
          </button>
        </div>
      )}

      {/* 分析结果 */}
      {step === 'complete' && result && (
        <div>
          {/* 顶部操作栏 */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <button
              onClick={handleReset}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: '1px solid #d1d5db',
                background: '#fff',
                cursor: 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <Upload style={{ width: 16, height: 16 }} /> 重新上传
            </button>
            <button
              onClick={handleSave}
              disabled={saving || saved}
              style={{
                padding: '8px 16px',
                borderRadius: 8,
                border: 'none',
                background: saved ? '#d1d5db' : '#10b981',
                color: '#fff',
                cursor: saving || saved ? 'not-allowed' : 'pointer',
                fontSize: 14,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              {saving ? (
                <Loader2 style={{ width: 16, height: 16, animation: 'spin 1s linear infinite' }} />
              ) : saved ? (
                <Heart style={{ width: 16, height: 16, fill: '#ef4444', color: '#ef4444' }} />
              ) : (
                <Heart style={{ width: 16, height: 16 }} />
              )}
              {saving ? '收藏中...' : saved ? '已收藏' : '收藏到资源库'}
            </button>
          </div>

          {/* 上传的原图 + 识别出的代码 */}
          <div style={{ display: 'grid', gridTemplateColumns: previewUrl ? '1fr 1fr' : '1fr', gap: 16, marginBottom: 24 }}>
            {previewUrl && (
              <div>
                <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                  📷 上传的图片
                </h2>
                <img
                  src={previewUrl}
                  alt="上传的代码图片"
                  style={{
                    width: '100%',
                    maxHeight: 400,
                    objectFit: 'contain',
                    borderRadius: 8,
                    border: '1px solid #e5e7eb',
                    background: '#fff',
                  }}
                />
              </div>
            )}
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <Code style={{ width: 20, height: 20, color: '#10b981' }} /> 识别出的代码
              </h2>
              {result.recognition_warning && (
                <div style={{
                  background: '#fffbeb',
                  border: '1px solid #fed7aa',
                  borderRadius: 8,
                  padding: '10px 14px',
                  marginBottom: 12,
                  fontSize: 13,
                  color: '#92400e',
                  lineHeight: 1.6,
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8,
                }}>
                  <AlertTriangle style={{ width: 16, height: 16, color: '#d97706', flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <strong>识别可能有误：</strong>{result.recognition_warning}
                    <div style={{ marginTop: 4, color: '#78350f', fontSize: 12 }}>
                      下方分析基于识别结果，缩进/符号错位可能是识别误差而非代码本身的问题，请对照原图核对。
                    </div>
                  </div>
                </div>
              )}
              <p style={{ fontSize: 12, color: '#9ca3af', marginBottom: 8 }}>
                💡 选中代码片段后可点击"解释"查看逐行讲解
              </p>
              <pre
                ref={codeBlockRef}
                onMouseUp={handleCodeMouseUp}
                style={{
                  background: '#1f2937',
                  color: '#f9fafb',
                  padding: 16,
                  borderRadius: 8,
                  overflow: 'auto',
                  fontSize: 14,
                  lineHeight: 1.6,
                  maxHeight: 400,
                  userSelect: 'text',
                  cursor: 'text',
                }}
              >
                <code>{result.code_text || '未能识别到代码'}</code>
              </pre>
            </div>
          </div>

          {/* 选中代码浮动解释按钮 */}
          {codeSelection && (
            <div
              className="chat-selection-popup"
              style={{
                left: codeSelection.x,
                top: codeSelection.y < 110 ? codeSelection.y + 16 : codeSelection.y - 50,
              }}
            >
              <div style={{
                borderRadius: 12,
                background: 'rgba(255,255,255,0.98)',
                border: '1px solid rgba(112, 137, 175, 0.18)',
                boxShadow: '0 12px 32px rgba(23, 37, 61, 0.12)',
                padding: '6px 8px',
                display: 'flex',
                gap: 4,
              }}>
                <button
                  onClick={handleCopySelection}
                  style={{
                    border: 'none',
                    background: copiedCode ? 'rgba(16,185,129,0.12)' : 'transparent',
                    color: copiedCode ? '#10b981' : '#6b7280',
                    padding: '5px 10px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  {copiedCode ? <Check style={{ width: 13, height: 13 }} /> : <Copy style={{ width: 13, height: 13 }} />}
                  {copiedCode ? '已复制' : '复制'}
                </button>
                <button
                  onClick={handleExplainSelection}
                  style={{
                    border: 'none',
                    background: 'transparent',
                    color: '#10b981',
                    padding: '5px 10px',
                    borderRadius: 8,
                    cursor: 'pointer',
                    fontSize: 12,
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 4,
                  }}
                >
                  <MessageCircle style={{ width: 13, height: 13 }} />
                  解释
                </button>
              </div>
            </div>
          )}

          {/* 代码解释 */}
          <div style={{ marginBottom: 24 }}>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <BookOpen style={{ width: 20, height: 20, color: '#3b82f6' }} /> 代码解释
            </h2>
            <div style={{
              background: '#f0f9ff',
              border: '1px solid #bae6fd',
              borderRadius: 8,
              padding: 16,
              fontSize: 14,
              lineHeight: 1.8,
              whiteSpace: 'pre-wrap',
            }}>
              {result.explanation || '暂无解释'}
            </div>
          </div>

          {/* 问题诊断 */}
          {result.problems.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertTriangle style={{ width: 20, height: 20, color: '#f59e0b' }} /> 问题诊断
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {result.problems.map((problem, index) => (
                  <ProblemCard key={index} problem={problem} />
                ))}
              </div>
            </div>
          )}

          {/* 练习题 */}
          {result.exercises.length > 0 && (
            <div style={{ marginBottom: 24 }}>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                <BookOpen style={{ width: 20, height: 20, color: '#8b5cf6' }} /> 巩固练习
              </h2>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {result.exercises.map((exercise, index) => (
                  <ExerciseCard key={index} exercise={exercise} index={index} />
                ))}
              </div>
            </div>
          )}

          {/* 知识点 */}
          {result.knowledge_points.length > 0 && (
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 12 }}>📚 涉及知识点</h2>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {result.knowledge_points.map((kp, index) => (
                  <span
                    key={index}
                    style={{
                      padding: '4px 12px',
                      borderRadius: 16,
                      background: '#dbeafe',
                      color: '#1d4ed8',
                      fontSize: 13,
                    }}
                  >
                    {kp}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// 问题卡片组件
const ProblemCard: React.FC<{ problem: CodeProblem }> = ({ problem }) => {
  const typeColors: Record<string, { bg: string; border: string; text: string }> = {
    '语法错误': { bg: '#fef2f2', border: '#fecaca', text: '#dc2626' },
    '逻辑错误': { bg: '#fffbeb', border: '#fed7aa', text: '#d97706' },
    '最佳实践': { bg: '#f0fdf4', border: '#bbf7d0', text: '#16a34a' },
  }
  const colors = typeColors[problem.type] || typeColors['最佳实践']

  return (
    <div style={{
      background: colors.bg,
      border: `1px solid ${colors.border}`,
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{
          padding: '2px 8px',
          borderRadius: 4,
          background: colors.text,
          color: '#fff',
          fontSize: 12,
          fontWeight: 500,
        }}>
          {problem.type}
        </span>
        {problem.line && (
          <span style={{ fontSize: 12, color: '#6b7280' }}>第 {problem.line} 行</span>
        )}
      </div>
      <p style={{ fontSize: 14, color: '#374151', marginBottom: 8 }}>{problem.description}</p>
      <p style={{ fontSize: 13, color: '#059669' }}>💡 {problem.fix}</p>
    </div>
  )
}

// 练习题卡片组件
const ExerciseCard: React.FC<{ exercise: Exercise; index: number }> = ({ exercise, index }) => {
  const [userAnswer, setUserAnswer] = useState('')
  const [selectedOption, setSelectedOption] = useState<number | null>(null)
  const [submitted, setSubmitted] = useState(false)
  const [showAnswer, setShowAnswer] = useState(false)

  const typeLabels: Record<string, string> = {
    choice: '选择题',
    fill: '填空题',
    code: '编程题',
  }

  const isCorrect = (() => {
    if (!submitted) return null
    if (exercise.type === 'choice') {
      const answerLetter = exercise.answer.charAt(0).toUpperCase()
      const optionIndex = 'ABCD'.indexOf(answerLetter)
      return selectedOption === optionIndex
    }
    if (exercise.type === 'fill') {
      return userAnswer.trim().toLowerCase() === exercise.answer.trim().toLowerCase()
    }
    return null // 编程题不自动判对错
  })()

  const handleSubmit = () => {
    if (exercise.type === 'choice' && selectedOption === null) return
    if (exercise.type === 'fill' && !userAnswer.trim()) return
    setSubmitted(true)
  }

  const handleShowAnswer = () => {
    setShowAnswer(!showAnswer)
  }

  return (
    <div style={{
      background: '#fff',
      border: '1px solid #e5e7eb',
      borderRadius: 8,
      padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
        <span style={{
          padding: '2px 8px',
          borderRadius: 4,
          background: '#8b5cf6',
          color: '#fff',
          fontSize: 12,
          fontWeight: 500,
        }}>
          {typeLabels[exercise.type] || exercise.type}
        </span>
        <span style={{ fontSize: 14, fontWeight: 500, color: '#374151' }}>
          第 {index + 1} 题
        </span>
      </div>
      <p style={{ fontSize: 14, color: '#111827', marginBottom: 12, lineHeight: 1.6 }}>
        {exercise.question}
      </p>

      {/* 选择题：可点击选项 */}
      {exercise.type === 'choice' && exercise.options && (
        <div style={{ marginBottom: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {exercise.options.map((opt, i) => {
            const isSelected = selectedOption === i
            const answerLetter = exercise.answer.charAt(0).toUpperCase()
            const isAnswer = 'ABCD'.indexOf(answerLetter) === i
            let bg = '#fff'
            let border = '#e5e7eb'
            if (submitted) {
              if (isAnswer) { bg = '#f0fdf4'; border = '#22c55e' }
              else if (isSelected && !isAnswer) { bg = '#fef2f2'; border = '#ef4444' }
            } else if (isSelected) {
              bg = '#eff6ff'; border = '#3b82f6'
            }
            return (
              <div
                key={i}
                onClick={() => !submitted && setSelectedOption(i)}
                style={{
                  padding: '8px 12px',
                  borderRadius: 6,
                  border: `1px solid ${border}`,
                  background: bg,
                  cursor: submitted ? 'default' : 'pointer',
                  fontSize: 14,
                  color: '#374151',
                  transition: 'all 0.15s',
                }}
              >
                {opt}
              </div>
            )
          })}
        </div>
      )}

      {/* 填空题：输入框 */}
      {exercise.type === 'fill' && (
        <div style={{ marginBottom: 12 }}>
          <input
            type="text"
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            placeholder="输入你的答案..."
            disabled={submitted}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: 6,
              border: submitted
                ? isCorrect ? '1px solid #22c55e' : '1px solid #ef4444'
                : '1px solid #d1d5db',
              fontSize: 14,
              outline: 'none',
              background: submitted ? (isCorrect ? '#f0fdf4' : '#fef2f2') : '#fff',
              boxSizing: 'border-box',
            }}
          />
        </div>
      )}

      {/* 编程题：文本框 */}
      {exercise.type === 'code' && (
        <div style={{ marginBottom: 12 }}>
          <textarea
            value={userAnswer}
            onChange={(e) => setUserAnswer(e.target.value)}
            placeholder="在此编写你的代码..."
            disabled={submitted}
            rows={5}
            style={{
              width: '100%',
              padding: '8px 12px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              fontSize: 13,
              fontFamily: 'monospace',
              outline: 'none',
              resize: 'vertical',
              background: submitted ? '#f9fafb' : '#fff',
              boxSizing: 'border-box',
            }}
          />
        </div>
      )}

      {/* 按钮区 */}
      <div style={{ display: 'flex', gap: 8 }}>
        {!submitted && (
          <button
            onClick={handleSubmit}
            disabled={exercise.type === 'choice' && selectedOption === null}
            style={{
              padding: '6px 16px',
              borderRadius: 6,
              border: 'none',
              background: (exercise.type === 'choice' && selectedOption === null) ? '#d1d5db' : '#8b5cf6',
              color: '#fff',
              cursor: (exercise.type === 'choice' && selectedOption === null) ? 'not-allowed' : 'pointer',
              fontSize: 13,
              fontWeight: 500,
            }}
          >
            提交答案
          </button>
        )}
        {submitted && (
          <button
            onClick={handleShowAnswer}
            style={{
              padding: '6px 12px',
              borderRadius: 6,
              border: '1px solid #d1d5db',
              background: '#f9fafb',
              cursor: 'pointer',
              fontSize: 13,
              color: '#374151',
            }}
          >
            {showAnswer ? '隐藏解析' : '查看解析'}
          </button>
        )}
      </div>

      {/* 提交后反馈 */}
      {submitted && isCorrect !== null && (
        <div style={{
          marginTop: 12,
          padding: 12,
          borderRadius: 6,
          background: isCorrect ? '#f0fdf4' : '#fef2f2',
          border: isCorrect ? '1px solid #bbf7d0' : '1px solid #fecaca',
        }}>
          <p style={{ fontSize: 14, fontWeight: 500, color: isCorrect ? '#16a34a' : '#dc2626' }}>
            {isCorrect ? '✅ 回答正确！' : '❌ 回答错误'}
          </p>
        </div>
      )}

      {/* 解析 */}
      {showAnswer && (
        <div style={{
          marginTop: 12,
          padding: 12,
          background: '#f0fdf4',
          borderRadius: 6,
          border: '1px solid #bbf7d0',
        }}>
          <p style={{ fontSize: 14, fontWeight: 500, color: '#16a34a', marginBottom: 4 }}>
            ✅ 答案：{exercise.answer}
          </p>
          <p style={{ fontSize: 13, color: '#374151' }}>
            {exercise.explanation}
          </p>
        </div>
      )}
    </div>
  )
}

export default MultimodalView
