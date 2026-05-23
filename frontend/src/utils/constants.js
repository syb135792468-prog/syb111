export const API_BASE = '/api'

export const RESOURCE_TYPES = [
  { value: 'quiz', label: '练习题', icon: 'pencil', color: 'purple' },
  { value: 'code', label: '代码案例', icon: 'code', color: 'blue' },
  { value: 'mindmap', label: '思维导图', icon: 'git-branch', color: 'orange' },
  { value: 'doc', label: '讲解文档', icon: 'file-text', color: 'green' },
  { value: 'video', label: '教学动画', icon: 'play-circle', color: 'red' },
]

export const PYTHON_KNOWLEDGE_POINTS = [
  '变量与数据类型', '运算符与表达式', '条件判断', '循环',
  '函数定义', '列表与元组', '字典与集合', '字符串操作',
  '面向对象基础', '类与继承', '异常处理', '文件操作',
  '模块与包', '列表推导式', '装饰器',
]

export const PROFILE_LEVEL_MAP = {
  beginner: '初学者',
  intermediate: '中级',
  advanced: '高级',
}

export const PROFILE_GOAL_MAP = {
  exam: '考试备考',
  interest: '兴趣学习',
  employment: '就业求职',
  competition: '竞赛提升',
}

export const PROFILE_MOTIVATION_MAP = {
  high: '动力十足',
  medium: '状态适中',
  low: '需要鼓励',
}

export const PROFILE_STYLE_MAP = {
  visual: '视觉型',
  auditory: '听觉型',
  kinesthetic: '动手型',
  mixed: '混合型',
}

export const PROFILE_DURATION_MAP = {
  short: '短时高效',
  medium: '适中节奏',
  long: '深度沉浸',
}

export const INTENT_MAP = {
  start_learning: '开始学习',
  ask_question: '提问',
  do_quiz: '练习',
  view_path: '学习路径',
  generate_resource: '生成资源',
  tutoring: '辅导',
  evaluate: '评估',
}
