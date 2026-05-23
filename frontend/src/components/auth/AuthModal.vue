<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { useChatStore } from '../../stores/chat'
import { GraduationCap } from 'lucide-vue-next'

const authStore = useAuthStore()
const chatStore = useChatStore()

const activeTab = ref('login')
const loginUsername = ref('')
const loginPassword = ref('')
const regUsername = ref('')
const regPassword = ref('')
const loginError = ref('')
const regError = ref('')
const loading = ref(false)

function switchTab(tab) {
  activeTab.value = tab
  loginError.value = ''
  regError.value = ''
}

async function handleLogin() {
  loginError.value = ''
  loading.value = true
  try {
    const result = await authStore.login(loginUsername.value, loginPassword.value)
    if (result.success) {
      chatStore.loadConversations()
    } else {
      loginError.value = result.message
    }
  } catch (e) {
    loginError.value = '网络错误，请重试'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  regError.value = ''
  if (regUsername.value.length < 2) {
    regError.value = '用户名至少2个字符'
    return
  }
  if (regPassword.value.length < 4) {
    regError.value = '密码至少4个字符'
    return
  }
  loading.value = true
  try {
    const result = await authStore.register(regUsername.value, regPassword.value)
    if (result.success) {
      chatStore.loadConversations()
    } else {
      regError.value = result.message
    }
  } catch (e) {
    regError.value = '网络错误，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 overflow-hidden">
      <!-- Brand header -->
      <div class="bg-gradient-to-r from-brand-600 to-brand-700 px-6 py-5 text-center">
        <div class="w-12 h-12 rounded-xl bg-white/20 flex items-center justify-center mx-auto mb-2">
          <GraduationCap class="w-6 h-6 text-white" />
        </div>
        <h2 class="text-white font-semibold text-lg">Python 智能学习助手</h2>
        <p class="text-brand-200 text-xs mt-1">登录后开始学习</p>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-gray-100">
        <button
          @click="switchTab('login')"
          :class="[
            'flex-1 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'login' ? 'text-brand-600 border-brand-600' : 'text-gray-400 border-transparent',
          ]"
        >
          登录
        </button>
        <button
          @click="switchTab('register')"
          :class="[
            'flex-1 py-3 text-sm font-medium border-b-2 transition-colors',
            activeTab === 'register' ? 'text-brand-600 border-brand-600' : 'text-gray-400 border-transparent',
          ]"
        >
          注册
        </button>
      </div>

      <!-- Login form -->
      <form v-if="activeTab === 'login'" @submit.prevent="handleLogin" class="px-6 py-5 space-y-4">
        <div>
          <label class="block text-xs text-gray-500 mb-1">用户名</label>
          <input
            v-model="loginUsername"
            type="text"
            required
            placeholder="请输入用户名"
            class="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">密码</label>
          <input
            v-model="loginPassword"
            type="password"
            required
            placeholder="请输入密码"
            class="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
        <p v-if="loginError" class="text-red-500 text-xs">{{ loginError }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors disabled:opacity-50"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <!-- Register form -->
      <form v-if="activeTab === 'register'" @submit.prevent="handleRegister" class="px-6 py-5 space-y-4">
        <div>
          <label class="block text-xs text-gray-500 mb-1">用户名</label>
          <input
            v-model="regUsername"
            type="text"
            required
            placeholder="2-50个字符，登录后不可修改"
            class="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
        <div>
          <label class="block text-xs text-gray-500 mb-1">密码</label>
          <input
            v-model="regPassword"
            type="password"
            required
            placeholder="4-100个字符"
            class="w-full px-3 py-2.5 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
          />
        </div>
        <p v-if="regError" class="text-red-500 text-xs">{{ regError }}</p>
        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 bg-brand-600 text-white rounded-lg text-sm font-medium hover:bg-brand-700 transition-colors disabled:opacity-50"
        >
          {{ loading ? '注册中...' : '注册并登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
