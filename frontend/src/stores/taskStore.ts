import { create } from 'zustand'

export interface BackgroundTask {
  taskId: string
  resourceType: string
  topic: string
  status: 'pending' | 'completed' | 'failed'
  data?: any
  error?: string
  createdAt: number
  progress?: number
  stage?: string
  message?: string
}

interface TaskState {
  tasks: BackgroundTask[]
  addTask: (task: BackgroundTask) => void
  updateTask: (taskId: string, update: Partial<BackgroundTask>) => void
  removeTask: (taskId: string) => void
  getPendingTasks: () => BackgroundTask[]
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: [],

  addTask: (task) => {
    set((state) => ({
      tasks: [...state.tasks.filter(t => t.taskId !== task.taskId), task],
    }))
  },

  updateTask: (taskId, update) => {
    set((state) => ({
      tasks: state.tasks.map(t => t.taskId === taskId ? { ...t, ...update } : t),
    }))
  },

  removeTask: (taskId) => {
    set((state) => ({
      tasks: state.tasks.filter(t => t.taskId !== taskId),
    }))
  },

  getPendingTasks: () => get().tasks.filter(t => t.status === 'pending'),
}))
