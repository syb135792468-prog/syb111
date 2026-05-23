<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import { loadProfile } from '../api/profile'
import {
  PROFILE_LEVEL_MAP, PROFILE_GOAL_MAP, PROFILE_MOTIVATION_MAP,
  PROFILE_STYLE_MAP, PROFILE_DURATION_MAP,
} from '../utils/constants'
import AppHeader from '../components/layout/AppHeader.vue'
import ProfileCards from '../components/profile/ProfileCards.vue'
import RadarChart from '../components/profile/RadarChart.vue'
import StyleChart from '../components/profile/StyleChart.vue'
import KnowledgeTags from '../components/profile/KnowledgeTags.vue'
import { RefreshCw } from 'lucide-vue-next'

const authStore = useAuthStore()

const profile = ref(null)
const loading = ref(true)

async function fetchProfile() {
  loading.value = true
  try {
    const resp = await loadProfile(authStore.userId)
    if (resp.code === 200) {
      profile.value = resp.data.profile
    }
  } catch (e) {
    console.error('Failed to load profile:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchProfile)
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 overflow-hidden">
    <AppHeader title="学习画像">
      <template #actions>
        <button
          @click="fetchProfile"
          class="text-gray-400 hover:text-gray-600 p-2 rounded-lg hover:bg-gray-50 transition-colors"
        >
          <RefreshCw class="w-4 h-4" />
        </button>
      </template>
    </AppHeader>

    <div class="flex-1 overflow-y-auto px-6 py-6">
      <div v-if="loading" class="flex items-center justify-center h-64">
        <div class="animate-spin rounded-full h-8 w-8 border-b-2 border-brand-600"></div>
      </div>

      <div v-else-if="profile" class="max-w-5xl mx-auto space-y-6">
        <!-- Overview cards -->
        <ProfileCards
          :level="PROFILE_LEVEL_MAP[profile.knowledge_level] || profile.knowledge_level"
          level-desc="根据你的学习表现自动评估"
          :goal="PROFILE_GOAL_MAP[profile.learning_goal] || profile.learning_goal"
          goal-desc="影响推荐资源的类型和难度"
          :motivation="PROFILE_MOTIVATION_MAP[profile.motivation_level] || profile.motivation_level"
          motivation-desc="基于你的学习频率和互动分析"
        />

        <!-- Charts -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <RadarChart
            :mastered="profile.mastered_points || []"
            :weak="profile.weak_points || []"
          />
          <StyleChart :style="profile.learning_style" />
        </div>

        <!-- Knowledge tags -->
        <KnowledgeTags
          :mastered="profile.mastered_points || []"
          :weak="profile.weak_points || []"
        />

        <!-- Details -->
        <div class="bg-white rounded-xl border border-gray-100 p-5 shadow-sm">
          <h3 class="text-sm font-semibold text-gray-700 mb-4">画像详情</h3>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p class="text-xs text-gray-400">学习风格</p>
              <p class="text-sm font-medium text-gray-700 mt-1">
                {{ PROFILE_STYLE_MAP[profile.learning_style] || profile.learning_style }}
              </p>
            </div>
            <div>
              <p class="text-xs text-gray-400">时长偏好</p>
              <p class="text-sm font-medium text-gray-700 mt-1">
                {{ PROFILE_DURATION_MAP[profile.duration_preference] || profile.duration_preference }}
              </p>
            </div>
            <div>
              <p class="text-xs text-gray-400">当前主题</p>
              <p class="text-sm font-medium text-gray-700 mt-1">{{ profile.current_topic || '未设定' }}</p>
            </div>
            <div>
              <p class="text-xs text-gray-400">最后学习</p>
              <p class="text-sm font-medium text-gray-700 mt-1">
                {{ profile.last_study_at ? new Date(profile.last_study_at).toLocaleDateString() : '暂无记录' }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
