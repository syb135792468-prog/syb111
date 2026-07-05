import { create } from 'zustand'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface Toast {
  id: number
  message: string
  type: ToastType
}

interface RightPanelEntry {
  id: string
  routeKey: string
  type: string | null
  data: Record<string, unknown>
  createdAt: number
  label: string
}

interface RightPanelState {
  isOpen: boolean
  isCollapsed: boolean
  width: number
  routeKey: string
  type: string | null
  data: Record<string, unknown>
  historyByRoute: Record<string, RightPanelEntry[]>
  currentIndexByRoute: Record<string, number>
}

interface ChatSelection {
  messageId: string | number
  text: string
  x: number
  y: number
}

interface AppState {
  sidebarOpen: boolean
  toasts: Toast[]
  rightPanel: RightPanelState
  chatSelection: ChatSelection | null
  toggleSidebar: () => void
  setSidebarOpen: (open: boolean) => void
  showToast: (message: string, type?: ToastType) => void
  removeToast: (id: number) => void
  setRightPanelRoute: (routeKey: string, defaultType?: string | null) => void
  openRightPanel: (type: string, data?: Record<string, unknown>) => void
  closeRightPanel: () => void
  updateRightPanelData: (data: Record<string, unknown>) => void
  navigateRightPanelHistory: (direction: 'prev' | 'next') => void
  setRightPanelHistoryIndex: (index: number) => void
  toggleRightPanelCollapse: () => void
  setRightPanelWidth: (width: number) => void
  setChatSelection: (sel: ChatSelection | null) => void
}

let toastId = 0
const RIGHT_PANEL_STORAGE_KEY = 'right-panel-session-v2'
const MAX_PANEL_HISTORY = 30

function sanitizeForStorage(value: unknown, seen = new WeakSet<object>()): unknown {
  if (
    value === null ||
    typeof value === 'string' ||
    typeof value === 'number' ||
    typeof value === 'boolean'
  ) {
    return value
  }

  if (value instanceof Date) {
    return value.toISOString()
  }

  if (typeof value === 'function' || typeof value === 'symbol' || typeof value === 'undefined') {
    return undefined
  }

  if (Array.isArray(value)) {
    return value
      .map((item) => sanitizeForStorage(item, seen))
      .filter((item) => item !== undefined)
  }

  if (typeof value === 'object') {
    if (seen.has(value as object)) return undefined
    seen.add(value as object)
    const result: Record<string, unknown> = {}
    Object.entries(value as Record<string, unknown>).forEach(([key, item]) => {
      const next = sanitizeForStorage(item, seen)
      if (next !== undefined) {
        result[key] = next
      }
    })
    return result
  }

  return undefined
}

function getPanelEntryLabel(type: string | null, data: Record<string, unknown>): string {
  const text = typeof data.text === 'string' ? data.text.trim() : ''
  const code = typeof data.code === 'string' ? data.code.trim() : ''
  const topic = typeof data.topic === 'string' ? data.topic.trim() : ''
  const nodeName = typeof data.nodeName === 'string' ? data.nodeName.trim() : ''
  const itemTitle = typeof (data.item as Record<string, unknown> | undefined)?.title === 'string'
    ? ((data.item as Record<string, unknown>).title as string).trim()
    : ''
  const resourceTitle = typeof (data.resource as Record<string, unknown> | undefined)?.title === 'string'
    ? ((data.resource as Record<string, unknown>).title as string).trim()
    : ''

  if (itemTitle) return itemTitle.slice(0, 22)
  if (resourceTitle) return resourceTitle.slice(0, 22)
  if (nodeName) return nodeName.slice(0, 22)
  if (topic) return topic.slice(0, 22)
  if (text) return text.replace(/\s+/g, ' ').slice(0, 22)
  if (code) return code.split('\n')[0].slice(0, 22)

  const typeLabels: Record<string, string> = {
    'chat-explain': '对话解释',
    'path-detail': '路径详情',
    'mindmap-detail': '导图详情',
    'error-detail': '错题详情',
    'analysis-detail': '分析记录',
    'code-explain': '代码解释',
    'challenge-solution': '解题思路',
    'resource-summary': '资源详情',
    'ai-suggestion': '学习建议',
    'animation-detail': '动画详情',
  }

  return type ? (typeLabels[type] || '辅助记录') : '辅助记录'
}

function getPanelEntryIdentity(type: string | null, data: Record<string, unknown>): string {
  if (!type) return ''

  const nodeId = typeof data.nodeId === 'number' || typeof data.nodeId === 'string'
    ? String(data.nodeId)
    : ''
  const pathId = typeof data.pathId === 'number' || typeof data.pathId === 'string'
    ? String(data.pathId)
    : ''
  const topic = typeof data.topic === 'string' ? data.topic.trim() : ''
  const nodeName = typeof data.nodeName === 'string' ? data.nodeName.trim() : ''
  const messageId = typeof data.messageId === 'number' ? String(data.messageId) : ''
  const text = typeof data.text === 'string' ? data.text.trim() : ''
  const itemId = typeof (data.item as Record<string, unknown> | undefined)?.id === 'number'
    ? String((data.item as Record<string, unknown>).id)
    : ''

  switch (type) {
    case 'mindmap-detail':
      return nodeId ? `${type}:${nodeId}` : `${type}:${topic}`
    case 'path-detail':
      return pathId && nodeId ? `${type}:${pathId}:${nodeId}` : nodeId ? `${type}:${nodeId}` : `${type}:${nodeName}`
    case 'chat-explain':
      return `${type}:${messageId}:${text}`
    case 'animation-detail':
      return itemId ? `${type}:${itemId}` : `${type}:${topic}`
    default:
      return ''
  }
}

function findLastPanelEntryIndex(
  entries: RightPanelEntry[],
  matcher: (entry: RightPanelEntry) => boolean,
): number {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    if (matcher(entries[index])) return index
  }
  return -1
}

function createPanelEntry(routeKey: string, type: string | null, data: Record<string, unknown>): RightPanelEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    routeKey,
    type,
    data,
    createdAt: Date.now(),
    label: getPanelEntryLabel(type, data),
  }
}

function getSerializableRightPanel(state: RightPanelState) {
  return sanitizeForStorage(state) as RightPanelState
}

function persistRightPanelState(state: RightPanelState) {
  if (typeof window === 'undefined') return
  try {
    window.sessionStorage.setItem(
      RIGHT_PANEL_STORAGE_KEY,
      JSON.stringify(getSerializableRightPanel(state))
    )
  } catch {
    // ignore storage errors
  }
}

function loadPersistedRightPanelState(): RightPanelState | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.sessionStorage.getItem(RIGHT_PANEL_STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw) as RightPanelState
  } catch {
    return null
  }
}

function buildCurrentPanelState(panel: RightPanelState, routeKey: string): RightPanelState {
  const entries = panel.historyByRoute[routeKey] || []
  const currentIndex = panel.currentIndexByRoute[routeKey]
  const safeIndex = entries.length === 0
    ? -1
    : Math.min(Math.max(currentIndex ?? entries.length - 1, 0), entries.length - 1)
  const currentEntry = safeIndex >= 0 ? entries[safeIndex] : null

  return {
    ...panel,
    routeKey,
    type: currentEntry?.type || null,
    data: currentEntry?.data || {},
    currentIndexByRoute: {
      ...panel.currentIndexByRoute,
      [routeKey]: safeIndex,
    },
  }
}

const isDesktopAtBoot = typeof window !== 'undefined' && window.innerWidth >= 768

const persistedRightPanel = loadPersistedRightPanelState()
const initialRightPanel: RightPanelState = persistedRightPanel
  ? {
      ...persistedRightPanel,
      width: 440,
    }
  : {
      isOpen: isDesktopAtBoot,
      isCollapsed: false,
      width: 440,
      routeKey: '/chat',
      type: null,
      data: {},
      historyByRoute: {},
      currentIndexByRoute: {},
    }

export const useAppStore = create<AppState>((set, get) => ({
  sidebarOpen: isDesktopAtBoot,
  toasts: [],
  rightPanel: initialRightPanel,
  chatSelection: null,

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

  setRightPanelRoute: (routeKey, defaultType = null) => {
    set((state) => {
      const currentPanel = state.rightPanel
      const routeHistory = currentPanel.historyByRoute[routeKey] || []
      let nextPanel = { ...currentPanel, routeKey, isOpen: true }

      if (routeHistory.length === 0 && defaultType) {
        const entry = createPanelEntry(routeKey, defaultType, {})
        nextPanel = {
          ...nextPanel,
          historyByRoute: {
            ...nextPanel.historyByRoute,
            [routeKey]: [entry],
          },
          currentIndexByRoute: {
            ...nextPanel.currentIndexByRoute,
            [routeKey]: 0,
          },
        }
      }

      const resolvedPanel = buildCurrentPanelState(nextPanel, routeKey)
      persistRightPanelState(resolvedPanel)
      return { rightPanel: resolvedPanel }
    })
  },

  openRightPanel: (type, data = {}) => {
    set((state) => {
      const routeKey = state.rightPanel.routeKey || '/chat'
      const routeHistory = [...(state.rightPanel.historyByRoute[routeKey] || [])]
      const lastEntry = routeHistory[routeHistory.length - 1]
      const incomingIdentity = getPanelEntryIdentity(type, data)
      const incomingComparable = JSON.stringify(sanitizeForStorage(data) || {})
      const lastComparable = lastEntry
        ? JSON.stringify(sanitizeForStorage({ type: lastEntry.type, data: lastEntry.data }) || {})
        : ''

      let nextHistory = routeHistory
      let nextIndex = routeHistory.length - 1
      const existingIdentityIndex = incomingIdentity
        ? findLastPanelEntryIndex(routeHistory, (entry) => entry.type === type && getPanelEntryIdentity(entry.type, entry.data) === incomingIdentity)
        : -1

      if (existingIdentityIndex >= 0) {
        const existingEntry = routeHistory[existingIdentityIndex]
        const mergedData = { ...existingEntry.data, ...data }
        routeHistory[existingIdentityIndex] = {
          ...existingEntry,
          data: mergedData,
          label: getPanelEntryLabel(type, mergedData),
        }
        nextHistory = routeHistory
        nextIndex = existingIdentityIndex
      } else if (
        lastEntry &&
        lastEntry.type === type &&
        lastComparable === JSON.stringify(sanitizeForStorage({ type, data }) || {})
      ) {
        nextIndex = routeHistory.length - 1
      } else {
        const entry = createPanelEntry(routeKey, type, data)
        nextHistory = [...routeHistory, entry].slice(-MAX_PANEL_HISTORY)
        nextIndex = nextHistory.length - 1
      }

      const nextPanel = buildCurrentPanelState({
        ...state.rightPanel,
        isOpen: true,
        routeKey,
        historyByRoute: {
          ...state.rightPanel.historyByRoute,
          [routeKey]: nextHistory,
        },
        currentIndexByRoute: {
          ...state.rightPanel.currentIndexByRoute,
          [routeKey]: nextIndex,
        },
      }, routeKey)
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },
  closeRightPanel: () => {
    set((state) => {
      const nextPanel = { ...state.rightPanel, isOpen: false }
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },
  updateRightPanelData: (data) => {
    set((state) => ({
      rightPanel: (() => {
        const routeKey = state.rightPanel.routeKey || '/chat'
        const routeHistory = [...(state.rightPanel.historyByRoute[routeKey] || [])]
        const currentIndex = state.rightPanel.currentIndexByRoute[routeKey]

        if (currentIndex === undefined || currentIndex < 0 || !routeHistory[currentIndex]) {
          const entry = createPanelEntry(routeKey, state.rightPanel.type, { ...state.rightPanel.data, ...data })
          const nextPanel = buildCurrentPanelState({
            ...state.rightPanel,
            historyByRoute: {
              ...state.rightPanel.historyByRoute,
              [routeKey]: [...routeHistory, entry].slice(-MAX_PANEL_HISTORY),
            },
            currentIndexByRoute: {
              ...state.rightPanel.currentIndexByRoute,
              [routeKey]: Math.min(routeHistory.length, MAX_PANEL_HISTORY - 1),
            },
          }, routeKey)
          persistRightPanelState(nextPanel)
          return nextPanel
        }

        const updatedData = { ...routeHistory[currentIndex].data, ...data }
        routeHistory[currentIndex] = {
          ...routeHistory[currentIndex],
          data: updatedData,
          label: getPanelEntryLabel(routeHistory[currentIndex].type, updatedData),
        }

        const nextPanel = buildCurrentPanelState({
          ...state.rightPanel,
          historyByRoute: {
            ...state.rightPanel.historyByRoute,
            [routeKey]: routeHistory,
          },
        }, routeKey)
        persistRightPanelState(nextPanel)
        return nextPanel
      })(),
    }))
  },

  navigateRightPanelHistory: (direction) => {
    set((state) => {
      const routeKey = state.rightPanel.routeKey || '/chat'
      const routeHistory = state.rightPanel.historyByRoute[routeKey] || []
      if (routeHistory.length === 0) return state

      const currentIndex = state.rightPanel.currentIndexByRoute[routeKey] ?? (routeHistory.length - 1)
      const nextIndex = direction === 'prev'
        ? Math.max(0, currentIndex - 1)
        : Math.min(routeHistory.length - 1, currentIndex + 1)

      const nextPanel = buildCurrentPanelState({
        ...state.rightPanel,
        isOpen: true,
        currentIndexByRoute: {
          ...state.rightPanel.currentIndexByRoute,
          [routeKey]: nextIndex,
        },
      }, routeKey)
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },

  setRightPanelHistoryIndex: (index) => {
    set((state) => {
      const routeKey = state.rightPanel.routeKey || '/chat'
      const routeHistory = state.rightPanel.historyByRoute[routeKey] || []
      if (routeHistory.length === 0) return state

      const nextIndex = Math.min(Math.max(index, 0), routeHistory.length - 1)
      const nextPanel = buildCurrentPanelState({
        ...state.rightPanel,
        isOpen: true,
        currentIndexByRoute: {
          ...state.rightPanel.currentIndexByRoute,
          [routeKey]: nextIndex,
        },
      }, routeKey)
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },

  toggleRightPanelCollapse: () => {
    set((state) => {
      const nextPanel = { ...state.rightPanel, isCollapsed: !state.rightPanel.isCollapsed }
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },

  setRightPanelWidth: (width) => {
    set((state) => {
      const clamped = Math.min(440, Math.max(300, width))
      const nextPanel = { ...state.rightPanel, width: clamped }
      persistRightPanelState(nextPanel)
      return { rightPanel: nextPanel }
    })
  },

  setChatSelection: (sel) => set({ chatSelection: sel }),
}))
