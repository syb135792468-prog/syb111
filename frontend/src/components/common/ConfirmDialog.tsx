import React, { useCallback, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, Trash2, Info, X } from 'lucide-react'

// --- 类型定义 ---
type DangerLevel = 'warning' | 'danger' | 'info'

interface ConfirmDialogProps {
  show?: boolean
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  dangerLevel?: DangerLevel
  isLoading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

// --- 组件 ---
const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  show = false,
  title = '确认操作',
  message = '',
  confirmText = '确认',
  cancelText = '取消',
  dangerLevel = 'warning',
  isLoading = false,
  onConfirm,
  onCancel,
}) => {
  const handleCancel = useCallback(() => {
    if (isLoading) return
    onCancel()
  }, [isLoading, onCancel])

  const handleConfirm = useCallback(() => {
    if (isLoading) return
    onConfirm()
  }, [isLoading, onConfirm])

  // ESC 键关闭（仅 info 级别）
  useEffect(() => {
    const handleKeydown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && show && dangerLevel === 'info') handleCancel()
    }
    document.addEventListener('keydown', handleKeydown)
    return () => document.removeEventListener('keydown', handleKeydown)
  }, [show, dangerLevel, handleCancel])

  // 背景点击关闭（仅 info 级别）
  const handleBackdrop = useCallback(() => {
    if (dangerLevel === 'info' && !isLoading) handleCancel()
  }, [dangerLevel, isLoading, handleCancel])

  if (!show) return null

  return createPortal(
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/40 backdrop-blur-sm"
      onClick={handleBackdrop}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="px-5 pt-5 pb-3 flex items-start gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
            dangerLevel === 'danger' ? 'bg-red-100' : dangerLevel === 'warning' ? 'bg-amber-100' : 'bg-blue-100'
          }`}>
            {dangerLevel === 'danger' ? (
              <Trash2 className="w-5 h-5 text-red-600" />
            ) : dangerLevel === 'warning' ? (
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            ) : (
              <Info className="w-5 h-5 text-blue-600" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-gray-800">{title}</h3>
            <p className="text-sm text-gray-500 mt-1 leading-relaxed whitespace-pre-line">{message}</p>
          </div>
          <button
            onClick={handleCancel}
            disabled={isLoading}
            className="text-gray-300 hover:text-gray-500 p-1 -mr-1 transition-colors disabled:opacity-40"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Actions */}
        <div className="px-5 pb-5 flex items-center justify-end gap-2">
          <button
            onClick={handleCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-40"
          >
            {cancelText}
          </button>
          <button
            onClick={handleConfirm}
            disabled={isLoading}
            className={`px-4 py-2 text-sm font-medium rounded-lg transition-all flex items-center gap-1.5 disabled:opacity-60 ${
              dangerLevel === 'danger'
                ? 'bg-red-600 text-white hover:bg-red-700'
                : dangerLevel === 'warning'
                ? 'bg-amber-500 text-white hover:bg-amber-600'
                : 'bg-brand-600 text-white hover:bg-brand-700'
            }`}
          >
            {isLoading && (
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {isLoading ? '处理中...' : confirmText}
          </button>
        </div>
      </div>
    </div>,
    document.body
  )
}

export default ConfirmDialog
