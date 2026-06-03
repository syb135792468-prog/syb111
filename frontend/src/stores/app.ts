import { create } from 'zustand'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  message: string
  type: ToastType
}

interface AppState {
  sidebarOpen: boolean
  toasts: Toast[]
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  showToast: (message: string, type?: ToastType) => void
  removeToast: (id: number) => void
}

let toastId = 0

export const useAppStore = create<AppState>((set) => ({
  sidebarOpen: true,
  toasts: [],

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  showToast: (message, type = 'info') => {
    const id = ++toastId
    set((state) => ({
      toasts: [...state.toasts, { id, message, type }].slice(-5),
    }))
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }))
    }, 3000)
  },

  removeToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}))
