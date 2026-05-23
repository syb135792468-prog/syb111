<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { listResources, generateResource } from '../api/resource'
import AppHeader from '../components/layout/AppHeader.vue'
import ResourceCard from '../components/resource/ResourceCard.vue'
import ResourceDetail from '../components/resource/ResourceDetail.vue'
import GenerateModal from '../components/resource/GenerateModal.vue'
import { BookOpen, Filter, Plus } from 'lucide-vue-next'

const authStore = useAuthStore()
const appStore = useAppStore()

const resources = ref([])
const loading = ref(true)
const typeFilter = ref('')
const showGenerate = ref(false)
const showDetail = ref(false)
const detailResource = ref({})

async function fetchResources() {
  loading.value = true
  try {
    const resp = await listResources(authStore.userId, { resourceType: typeFilter.value || undefined })
    if (resp.code === 200) {
      resources.value = resp.data.resources || []
    }
  } catch (e) {
    console.error('Failed to load resources:', e)
  } finally {
    loading.value = false
  }
}

function openDetail(r) {
  detailResource.value = r
  showDetail.value = true
}

async function handleGenerate({ topic, type }) {
  try {
    const resp = await generateResource(authStore.userId, topic, type)
    if (resp.code === 200) {
      appStore.showToast('资源生成成功', 'success')
      showGenerate.value = false
      fetchResources()
    } else {
      appStore.showToast(resp.message || '生成失败', 'error')
    }
  } catch (e) {
    appStore.showToast('生成失败：' + e.message, 'error')
  }
}

onMounted(fetchResources)
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <AppHeader title="学习资源">
      <template #actions>
        <select
          v-model="typeFilter"
          @change="fetchResources"
          class="text-sm border border-gray-200 rounded-lg px-3 py-1.5 text-gray-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">全部类型</option>
          <option value="quiz">练习题</option>
          <option value="code">代码案例</option>
          <option value="mindmap">思维导图</option>
          <option value="doc">讲解文档</option>
          <option value="video">教学动画</option>
        </select>
        <button
          @click="showGenerate = true"
          class="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700 transition-colors"
        >
          <Plus class="w-4 h-4" />
          生成资源
        </button>
      </template>
    </AppHeader>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center h-64">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
      </div>

      <!-- Empty -->
      <div v-else-if="resources.length === 0" class="flex flex-col items-center justify-center h-64 text-gray-400">
        <BookOpen class="w-12 h-12 mb-3 opacity-40" />
        <p class="text-sm">暂无学习资源</p>
        <button
          @click="showGenerate = true"
          class="mt-3 text-sm text-brand-600 hover:text-brand-700"
        >
          生成第一个资源
        </button>
      </div>

      <!-- Grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 max-w-5xl mx-auto">
        <ResourceCard
          v-for="r in resources"
          :key="r.id"
          :resource="r"
          @click="openDetail(r)"
        />
      </div>
    </div>

    <!-- Modals -->
    <GenerateModal
      :show="showGenerate"
      @close="showGenerate = false"
      @generate="handleGenerate"
    />
    <ResourceDetail
      :show="showDetail"
      :title="detailResource.title"
      :content="detailResource.content"
      :type="detailResource.resource_type"
      @close="showDetail = false"
    />
  </div>
</template>
