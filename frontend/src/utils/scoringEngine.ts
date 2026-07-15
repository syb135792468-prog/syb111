import { PYTHON_KNOWLEDGE_POINTS, BACKEND_TO_DISPLAY } from './constants'

// --- 类型定义 ---
export interface ProgressRecord {
  topic: string
  status: 'completed' | 'in_progress' | 'failed' | 'not_started'
  score?: number
  duration?: number
  updated_at?: string
}

export interface BackendProfile {
  learning_goal?: string
  learning_style?: string
  mastered_points?: string[]
  weak_points?: string[]
}

export interface KnowledgePoint {
  id: string
  name: string
  mastery: number
  category: string
}

export interface LearningStyleData {
  visual: number
  auditory: number
  kinesthetic: number
  mixed: number
  dominant: string
}

export interface LearningProfile {
  knowledgeLevel: string
  learningGoal: string
  learningMotivation: { status: string; value: number }
  radarData: KnowledgePoint[]
  learningStyle: LearningStyleData
  masteredPoints: KnowledgePoint[]
  weakPoints: KnowledgePoint[]
  timePreference: string
  lastStudyTime: string
  totalStudyHours: number
  accuracy: number
  dailyStudyTime: DailyStudyTime[]
}

// --- 知识点掌握度计算 ---
export function calcTopicMastery(records: ProgressRecord[]): number {
  if (!records || records.length === 0) return 0

  const scores = records.filter((r) => r.score != null).map((r) => r.score!)
  const bestScore = scores.length > 0 ? Math.max(...scores) : 0

  const latestRecord = [...records].sort(
    (a, b) => new Date(b.updated_at || 0).getTime() - new Date(a.updated_at || 0).getTime()
  )[0]
  const statusFloor: Record<string, number> = {
    completed: 80,
    in_progress: 0,
    failed: 0,
    not_started: 0,
  }
  const floor = statusFloor[latestRecord?.status] || 0

  // Scores are already evidence-based mastery values; avoid distorting them a second time.
  const mastery = Math.max(bestScore, floor)
  return Math.round(Math.min(100, Math.max(0, mastery)))
}

// --- 评分平滑（P2：消除单次答题的剧烈波动） ---
// 调整参数使掌握度变化更平缓
const SMOOTH_DECAY = 0.92          // 衰减系数，越大收敛越慢，变化越平滑
const SMOOTH_BASELINE_WEAK = 35    // 薄弱知识点基准分
const SMOOTH_BASELINE_MASTERED = 70 // 掌握知识点基准分
const SMOOTH_BASELINE_DEFAULT = 50  // 默认基准分（更接近中间值）
const MIN_ATTEMPTS_FOR_ADJUSTMENT = 2 // 最少答题次数才开始调整

/**
 * 基于答题次数的指数衰减平滑。
 * 答题次数越少，分数越靠近基准分；次数越多，越贴近原始得分。
 * 优化目标：减少单次答题导致的剧烈波动，使掌握度变化更加平缓。
 */
export function smoothKnowledgeScore(
  rawScore: number,
  attemptCount: number,
  isMastered: boolean,
  isWeak: boolean,
): number {
  // 答题次数少于阈值时，直接返回原始得分或基准分的平均值
  if (attemptCount < MIN_ATTEMPTS_FOR_ADJUSTMENT) {
    const baseLine = isMastered ? SMOOTH_BASELINE_MASTERED
      : isWeak ? SMOOTH_BASELINE_WEAK
      : SMOOTH_BASELINE_DEFAULT
    // 前两次答题只做轻微调整
    const weight = attemptCount === 0 ? 1 : 0.3 // 第一次答题权重30%
    return Math.round(baseLine * (1 - weight) + rawScore * weight)
  }
  
  const baseLine = isMastered ? SMOOTH_BASELINE_MASTERED
    : isWeak ? SMOOTH_BASELINE_WEAK
    : SMOOTH_BASELINE_DEFAULT
  // 使用更高的衰减系数，让熟练度增长更慢
  const proficiency = 1 - Math.pow(SMOOTH_DECAY, attemptCount)
  return Math.round(baseLine + (rawScore - baseLine) * proficiency)
}

// --- 知识水平等级 ---
export function calcKnowledgeLevel(avgMastery: number): string {
  if (avgMastery >= 75) return '精通者'
  if (avgMastery >= 55) return '进阶者'
  if (avgMastery >= 35) return '入门者'
  if (avgMastery >= 15) return '初学者'
  return '初学者'
}

// --- 学习动力 ---
export function calcMotivation(allRecords: ProgressRecord[]): { status: string; value: number } {
  const now = Date.now()
  const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000

  const recentRecords = allRecords.filter((r) => {
    if (!r.updated_at) return false
    return new Date(r.updated_at).getTime() >= sevenDaysAgo
  })

  if (recentRecords.length === 0) {
    return { status: '低迷', value: 0 }
  }

  const recentSeconds = recentRecords.reduce((sum, r) => sum + (r.duration || 0), 0)
  const recentHours = recentSeconds / 3600

  let value: number, status: string
  if (recentHours > 5) {
    value = Math.min(100, 85 + Math.round((recentHours - 5) * 3))
    status = '高涨'
  } else if (recentHours > 2) {
    value = 60 + Math.round(((recentHours - 2) / 3) * 25)
    status = '适中'
  } else if (recentHours > 0.5) {
    value = 30 + Math.round(((recentHours - 0.5) / 1.5) * 30)
    status = '适中'
  } else {
    value = Math.round(recentHours * 60)
    status = '低迷'
  }

  return { status, value: Math.round(Math.min(100, Math.max(0, value))) }
}

// --- 答题正确率 ---
export function calcAccuracy(allRecords: ProgressRecord[]): number {
  const completedWithScore = allRecords.filter(
    (r) => r.status === 'completed' && r.score != null
  )
  if (completedWithScore.length === 0) return 0

  const avg = completedWithScore.reduce((sum, r) => sum + r.score!, 0) / completedWithScore.length
  return Math.round(avg)
}

// --- 学习时间记录过滤 ---
function isStudyTimeRecord(r: ProgressRecord): boolean {
  return r.topic === '在线学习' || r.topic.startsWith('在线学习_') || r.topic.startsWith('智能对话_')
}

// --- 总学习时长 ---
export function calcTotalStudyHours(allRecords: ProgressRecord[]): number {
  const totalSeconds = allRecords.filter(isStudyTimeRecord).reduce((sum, r) => sum + (r.duration || 0), 0)
  return Math.round((totalSeconds / 3600) * 10) / 10
}

// --- 每日学习时长（最近7天） ---
export interface DailyStudyTime {
  date: string      // MM/DD 格式
  label: string     // 周几
  minutes: number
}

export function calcDailyStudyTime(allRecords: ProgressRecord[]): DailyStudyTime[] {
  const dayLabels = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
  const studyRecords = allRecords.filter(isStudyTimeRecord)
  const result: DailyStudyTime[] = []

  for (let i = 6; i >= 0; i--) {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() - i)

    const nextDay = new Date(d)
    nextDay.setDate(nextDay.getDate() + 1)

    const dayRecords = studyRecords.filter((r) => {
      if (!r.updated_at) return false
      const t = new Date(r.updated_at).getTime()
      return t >= d.getTime() && t < nextDay.getTime()
    })

    const seconds = dayRecords.reduce((sum, r) => sum + (r.duration || 0), 0)
    result.push({
      date: `${d.getMonth() + 1}/${d.getDate()}`,
      label: dayLabels[d.getDay()],
      minutes: Math.round(seconds / 60),
    })
  }

  return result
}

// --- 时长偏好 ---
export function calcTimePreference(allRecords: ProgressRecord[]): string {
  const recordsWithDuration = allRecords.filter((r) => r.duration && r.duration > 0)
  if (recordsWithDuration.length === 0) return '碎片化'

  const totalSeconds = recordsWithDuration.reduce((sum, r) => sum + r.duration!, 0)
  const avgSeconds = totalSeconds / recordsWithDuration.length

  if (avgSeconds >= 3600) return '长时段'
  if (avgSeconds >= 1800) return '适中节奏'
  return '碎片化'
}

// --- 最后学习时间 ---
export function calcLastStudyTime(allRecords: ProgressRecord[]): string {
  const dates = allRecords
    .filter((r) => r.updated_at)
    .map((r) => new Date(r.updated_at!))

  if (dates.length === 0) return '暂无记录'

  const latest = new Date(Math.max(...dates.map((d) => d.getTime())))
  return latest.toLocaleDateString('zh-CN')
}

// --- 学习风格 ---
export function calcLearningStyle(allRecords: ProgressRecord[], backendStyle = 'mixed'): LearningStyleData {
  const styleNames: Record<string, string> = {
    visual: '视觉型',
    auditory: '听觉型',
    kinesthetic: '动手型',
    mixed: '混合型',
  }

  if (backendStyle && backendStyle !== 'mixed' && styleNames[backendStyle]) {
    const active = backendStyle
    const distribution: Record<string, number> = { visual: 20, auditory: 20, kinesthetic: 20, mixed: 20 }
    distribution[active] = 40
    return { ...distribution, dominant: styleNames[active] } as LearningStyleData
  }

  const completedCount = allRecords.filter((r) => r.status === 'completed').length
  const inProgressCount = allRecords.filter((r) => r.status === 'in_progress').length
  const totalDuration = allRecords.reduce((s, r) => s + (r.duration || 0), 0)

  if (completedCount === 0 && inProgressCount === 0 && totalDuration === 0) {
    return { visual: 25, auditory: 25, kinesthetic: 25, mixed: 25, dominant: '混合型' }
  }

  // 用 in_progress 记录数补充 completed 记录数，让风格随交互变化
  const activeCount = completedCount + inProgressCount
  const kinesthetic = Math.min(50, 25 + activeCount * 3)
  const remaining = 100 - kinesthetic
  const visual = Math.round(remaining * 0.4)
  const auditory = Math.round(remaining * 0.3)
  const mixed = 100 - kinesthetic - visual - auditory

  const styles: Record<string, number> = { visual, auditory, kinesthetic, mixed }
  const dominantKey = Object.entries(styles).sort((a, b) => b[1] - a[1])[0][0]

  return { visual, auditory, kinesthetic, mixed, dominant: styleNames[dominantKey] }
}

// --- 聚合：从 progress + profile 合并计算完整画像 ---
export function buildProfileFromProgress(
  progressRecords: ProgressRecord[] = [],
  backendProfile: BackendProfile = {}
): LearningProfile {
  // 构建 topic -> records 映射（topic 现在是后端标准名称）
  const topicMap: Record<string, ProgressRecord[]> = {}
  for (const record of progressRecords) {
    if (!topicMap[record.topic]) topicMap[record.topic] = []
    topicMap[record.topic].push(record)
  }

  // 从 user_profiles 表获取声明的掌握/薄弱知识点（后端标准名称）
  const profileMastered = new Set(backendProfile.mastered_points || [])
  const profileWeak = new Set(backendProfile.weak_points || [])

  const radarData: KnowledgePoint[] = PYTHON_KNOWLEDGE_POINTS.map((backendName, index) => {
    const records = topicMap[backendName] || []
    let mastery = calcTopicMastery(records)

    // 如果 profile 中标记为掌握，取 progress 计算值和 80 的较大者
    if (profileMastered.has(backendName)) {
      mastery = Math.max(mastery, 80)
    }
    // 如果 progress 没有记录且 profile 标记为薄弱，给 20 分
    if (records.length === 0 && profileWeak.has(backendName)) {
      mastery = 20
    }

    const displayName = BACKEND_TO_DISPLAY[backendName] || backendName
    const categories: Record<string, string> = {
      '变量与数据类型': '基础语法', '运算符与表达式': '基础语法',
      '条件判断（if/elif/else）': '流程控制', '循环（for/while）': '流程控制',
      '函数定义与调用': '函数', '函数参数与返回值': '函数',
      '列表与元组': '数据结构', '字典与集合': '数据结构', '字符串操作': '数据结构',
      '面向对象基础': '面向对象', '类与对象': '面向对象', '继承与多态': '面向对象',
      '异常处理': '进阶特性', '文件操作': '进阶特性', '模块与包': '进阶特性',
    }

    return { id: `kp_${index}`, name: displayName, mastery, category: categories[backendName] || '其他' }
  })

  const avgMastery = radarData.length > 0
    ? radarData.reduce((sum, p) => sum + p.mastery, 0) / radarData.length
    : 0

  // 合并 progress 和 profile 两个数据源的 mastered/weak
  const progressMastered = radarData.filter((p) => p.mastery >= 80)
  const progressWeak = radarData.filter((p) => p.mastery <= 30 && p.mastery > 0)

  // 从 profile 声明中转换为 displayName 集合
  const profileMasteredDisplay = new Set(
    (backendProfile.mastered_points || []).map(bp => BACKEND_TO_DISPLAY[bp] || bp)
  )
  const profileWeakDisplay = new Set(
    (backendProfile.weak_points || []).map(bp => BACKEND_TO_DISPLAY[bp] || bp)
  )

  // 合并去重
  const masteredMap = new Map<string, KnowledgePoint>()
  for (const p of progressMastered) masteredMap.set(p.name, p)
  for (const p of radarData) {
    if (profileMasteredDisplay.has(p.name) && !masteredMap.has(p.name)) {
      masteredMap.set(p.name, { ...p, mastery: Math.max(p.mastery, 80) })
    }
  }
  const masteredPoints = Array.from(masteredMap.values()).sort((a, b) => b.mastery - a.mastery)

  const weakMap = new Map<string, KnowledgePoint>()
  for (const p of progressWeak) weakMap.set(p.name, p)
  for (const p of radarData) {
    if (profileWeakDisplay.has(p.name) && !weakMap.has(p.name) && !masteredMap.has(p.name)) {
      weakMap.set(p.name, { ...p, mastery: p.mastery || 20 })
    }
  }
  const weakPoints = Array.from(weakMap.values()).sort((a, b) => a.mastery - b.mastery)

  return {
    knowledgeLevel: calcKnowledgeLevel(avgMastery),
    learningGoal: ({
      interest: '兴趣学习', career: '职业发展', exam: '考试备考', hobby: '业余爱好', academic: '学术研究',
    } as Record<string, string>)[backendProfile.learning_goal || ''] || backendProfile.learning_goal || '兴趣学习',
    learningMotivation: calcMotivation(progressRecords),
    radarData,
    learningStyle: calcLearningStyle(progressRecords, backendProfile.learning_style),
    masteredPoints,
    weakPoints,
    timePreference: calcTimePreference(progressRecords),
    lastStudyTime: calcLastStudyTime(progressRecords),
    totalStudyHours: calcTotalStudyHours(progressRecords),
    accuracy: calcAccuracy(progressRecords),
    dailyStudyTime: calcDailyStudyTime(progressRecords),
  }
}
