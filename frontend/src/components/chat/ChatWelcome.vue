<script setup>
import { GraduationCap, Route, HelpCircle, PenTool, GitBranch } from 'lucide-vue-next'

const emit = defineEmits(['send'])

const actions = [
  {
    icon: Route,
    label: '规划学习路径',
    desc: '制定个性化学习计划',
    color: 'text-brand-500',
    message: '我想学习Python基础知识，请帮我规划学习路径',
  },
  {
    icon: HelpCircle,
    label: '提问答疑',
    desc: '解答Python疑问',
    color: 'text-green-500',
    message: 'Python的列表和元组有什么区别？',
  },
  {
    icon: PenTool,
    label: '生成练习题',
    desc: '针对性练习巩固',
    color: 'text-purple-500',
    message: '请给我出几道Python循环的练习题',
  },
  {
    icon: GitBranch,
    label: '思维导图',
    desc: '可视化知识结构',
    color: 'text-orange-500',
    message: '生成关于Python函数的思维导图',
  },
]
</script>

<template>
  <div class="h-full flex flex-col items-center justify-center px-6">
    <div class="w-16 h-16 rounded-2xl bg-brand-50 flex items-center justify-center mb-6">
      <GraduationCap class="w-8 h-8 text-brand-500" />
    </div>
    <h2 class="text-2xl font-bold text-gray-800 mb-2">Python 智能学习助手</h2>
    <p class="text-gray-500 text-center max-w-md mb-8">
      基于大模型的个性化资源生成与学习多智能体系统。我可以帮你答疑解惑、生成练习题、创建思维导图、规划学习路径。
    </p>

    <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-lg w-full">
      <button
        v-for="action in actions"
        :key="action.label"
        @click="emit('send', action.message)"
        class="flex items-start gap-3 px-4 py-3 rounded-xl border border-gray-200 bg-white hover:border-brand-300 hover:bg-brand-50 transition-all text-left group"
      >
        <component :is="action.icon" :class="['w-5 h-5 mt-0.5 flex-shrink-0', action.color]" />
        <div>
          <p class="text-sm font-medium text-gray-700 group-hover:text-brand-700">{{ action.label }}</p>
          <p class="text-xs text-gray-400">{{ action.desc }}</p>
        </div>
      </button>
    </div>
  </div>
</template>
