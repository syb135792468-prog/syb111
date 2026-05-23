import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  {
    path: '/',
    redirect: '/chat',
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('../views/ChatView.vue'),
  },
  {
    path: '/profile',
    name: 'Profile',
    component: () => import('../views/ProfileView.vue'),
  },
  {
    path: '/resources',
    name: 'Resources',
    component: () => import('../views/ResourcesView.vue'),
  },
  {
    path: '/mindmap',
    name: 'Mindmap',
    component: () => import('../views/MindmapView.vue'),
  },
  {
    path: '/path',
    name: 'Path',
    component: () => import('../views/PathView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  if (!authStore.token) {
    authStore.showAuthModal = true
  }
})

export default router
