import React from 'react'
import { useAppStore } from '../../stores/app'
import { CheckCircle, XCircle, AlertTriangle, Info } from 'lucide-react'

// --- 类型定义 ---
type ToastType = 'success' | 'error' | 'warning' | 'info'

// --- 常量 ---
const ICONS: Record<ToastType, React.FC<{ className?: string; style?: React.CSSProperties }>> = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
}

const COLORS: Record<ToastType, string> = {
  success: 'bg-green-50 border-green-200 text-green-800',
  error: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-yellow-50 border-yellow-200 text-yellow-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
}

const ICON_COLORS: Record<ToastType, string> = {
  success: 'text-green-500',
  error: 'text-red-500',
  warning: 'text-yellow-500',
  info: 'text-blue-500',
}

// --- 组件 ---
const Toast: React.FC = () => {
  const appStore = useAppStore()

  return (
    <div className="fixed top-4 right-4 z-50 space-y-2">
      {appStore.toasts.map((toast) => {
        const Icon = ICONS[toast.type] || Info
        return (
          <div
            key={toast.id}
            className={`flex items-center gap-3 px-4 py-3 rounded-lg border shadow-lg min-w-[280px] ${COLORS[toast.type] || COLORS.info}`}
            style={{ animation: 'toastIn 0.3s ease-out' }}
          >
            <Icon className={`w-5 h-5 flex-shrink-0 ${ICON_COLORS[toast.type] || ''}`} />
            <span className="text-sm">{toast.message}</span>
          </div>
        )
      })}
      <style>{`
        @keyframes toastIn {
          from { opacity: 0; transform: translateX(20px); }
          to { opacity: 1; transform: translateX(0); }
        }
        @keyframes toastOut {
          from { opacity: 1; transform: translateX(0); }
          to { opacity: 0; transform: translateX(20px); }
        }
      `}</style>
    </div>
  )
}

export default Toast
