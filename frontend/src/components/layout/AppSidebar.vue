<script setup>
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'
import { useAppStore } from '../../stores/app'
import { GraduationCap, Plus, MessageCircle, User, BookOpen, GitBranch, Route, LogOut, Trash2 } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const chatStore = useChatStore()
const appStore = useAppStore()

const navItems = [
  { name: 'Chat', path: '/chat', label: '智能对话', icon: MessageCircle, color: 'text-[#4285f4]' },
  { name: 'Profile', path: '/profile', label: '学习画像', icon: User, color: 'text-[#ea4335]' },
  { name: 'Resources', path: '/resources', label: '学习资源', icon: BookOpen, color: 'text-[#34a853]' },
  { name: 'Mindmap', path: '/mindmap', label: '思维导图', icon: GitBranch, color: 'text-[#fbbc04]' },
  { name: 'Path', path: '/path', label: '学习路径', icon: Route, color: 'text-[#4285f4]' },
]

function navigateTo(path) {
  router.push(path)
  if (window.innerWidth < 768) {
    appStore.sidebarOpen = false
  }
}

function startNewChat() {
  chatStore.startNewChat()
  router.push('/chat')
}

function handleLogout() {
  if (chatStore.isStreaming) return
  authStore.logout()
  chatStore.startNewChat()
  chatStore.conversations = []
}

async function handleDeleteConversation(e, id) {
  e.stopPropagation()
  await chatStore.deleteConversation(id)
}
</script>

<template>
  <aside
    :class="[
      'w-64 flex flex-col flex-shrink-0 transition-all duration-200 z-40 border-r border-[#dadce0] bg-[#f8f9fa]',
      appStore.sidebarOpen ? 'translate-x-0' : '-translate-x-full absolute h-full',
    ]"
  >
    <!-- Brand -->
    <div class="p-4 flex items-center gap-3">
      <div class="w-9 h-9 rounded-lg bg-gradient-to-br from-[#4285f4] to-[#34a853] flex items-center justify-center shadow-sm">
        <GraduationCap class="w-5 h-5 text-white" />
      </div>
      <div>
        <h1 class="text-[#202124] font-semibold text-sm leading-tight">Python 学习助手</h1>
        <p class="text-[#9aa0a6] text-xs">软件杯 A3 赛题</p>
      </div>
    </div>

    <!-- New Chat -->
    <div class="px-3 mb-2">
      <button
        @click="startNewChat"
        class="w-full flex items-center gap-2 px-3 py-2.5 rounded-full border border-[#dadce0] text-[#1a73e8] hover:bg-[#e8f0fe] hover:border-[#a8c7fa] transition-all text-sm font-medium"
      >
        <Plus class="w-4 h-4" />
        <span>新建对话</span>
      </button>
    </div>

    <!-- Conversation List -->
    <div class="px-3 mb-3 overflow-y-auto" style="max-height: 35vh">
      <div
        v-for="conv in chatStore.conversations"
        :key="conv.id"
        @click="chatStore.switchConversation(conv.id); router.push('/chat')"
        :class="[
          'group flex items-center gap-2 px-3 py-2 rounded-full cursor-pointer transition-all text-sm mb-0.5',
          chatStore.currentConversationId === conv.id
            ? 'bg-[#e8f0fe] text-[#1a73e8] font-medium'
            : 'text-[#5f6368] hover:bg-[#f1f3f4] hover:text-[#202124]',
        ]"
      >
        <MessageCircle class="w-4 h-4 flex-shrink-0" />
        <span class="flex-1 truncate">{{ conv.title }}</span>
        <button
          @click="handleDeleteConversation($event, conv.id)"
          class="opacity-0 group-hover:opacity-100 text-[#9aa0a6] hover:text-[#ea4335] transition-all"
        >
          <Trash2 class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <!-- Divider -->
    <div class="mx-3 border-t border-[#e0e0e0]"></div>

    <!-- Navigation -->
    <nav class="flex-1 px-3 py-2 space-y-0.5 overflow-y-auto">
      <button
        v-for="item in navItems"
        :key="item.name"
        @click="navigateTo(item.path)"
        :class="[
          'w-full flex items-center gap-3 px-3 py-2.5 rounded-full text-sm transition-all',
          route.path === item.path
            ? 'bg-[#e8f0fe] text-[#1a73e8] font-medium'
            : 'text-[#5f6368] hover:bg-[#f1f3f4] hover:text-[#202124]',
        ]"
      >
        <component :is="item.icon" :class="['w-5 h-5', route.path === item.path ? 'text-[#1a73e8]' : item.color]" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <!-- User Info -->
    <div class="p-3 border-t border-[#e0e0e0]">
      <div class="flex items-center gap-3 px-2">
        <div class="w-8 h-8 rounded-full bg-gradient-to-br from-[#4285f4] to-[#34a853] flex items-center justify-center">
          <User class="w-4 h-4 text-white" />
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-[#202124] text-sm font-medium truncate">{{ authStore.username || '学习者' }}</p>
          <p class="text-[#34a853] text-xs flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full bg-[#34a853] inline-block"></span>
            在线
          </p>
        </div>
        <button
          @click="handleLogout"
          class="text-[#9aa0a6] hover:text-[#ea4335] transition-colors p-1.5 rounded-full hover:bg-[#fce8e6]"
          title="退出登录"
        >
          <LogOut class="w-4 h-4" />
        </button>
      </div>
    </div>
  </aside>

  <!-- Mobile overlay -->
  <div
    v-if="appStore.sidebarOpen"
    @click="appStore.sidebarOpen = false"
    class="fixed inset-0 bg-black/30 z-30 md:hidden"
  />
</template>
