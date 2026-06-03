# 学习画像页面动态化改造说明

## 一、核心改动

**从"随机模拟数据"改为"基于真实学习行为的评分引擎"。**

所有数值来自 `LearningProgress` 表的实际记录，计算公式公开透明，随学习进度实时变化。

## 二、评分标准（scoringEngine.js）

### 2.1 知识点掌握度（mastery）

```
mastery = bestScore × 0.6 + avgScore × 0.25 + statusBonus × 0.15
```

| 指标 | 含义 | 来源 |
|------|------|------|
| bestScore | 该知识点历次得分最高值 | LearningProgress.score |
| avgScore | 该知识点所有得分平均值 | LearningProgress.score |
| statusBonus | completed=100, in_progress=40, failed=20, not_started=0 | LearningProgress.status |

**示例：** 某用户对"循环"做了3次练习，得分 60、75、90，状态 completed：
- bestScore = 90, avgScore = 75, statusBonus = 100
- mastery = 90×0.6 + 75×0.25 + 100×0.15 = 54 + 18.75 + 15 = **87.75 → 88**

### 2.2 知识水平等级

| 平均掌握度 | 等级 |
|-----------|------|
| ≥ 75% | 精通者 |
| 55-74% | 进阶者 |
| 35-54% | 入门者 |
| 15-34% | 初学者 |
| < 15% | 初学者 |

### 2.3 学习动力

基于**最近7天**的实际学习时长：

| 7天内总时长 | 状态 | 动力值 |
|------------|------|--------|
| 0（无记录） | 低迷 | 0 |
| < 30分钟 | 低迷 | 10-30 |
| 30分钟-2小时 | 适中 | 30-60 |
| 2-5小时 | 适中 | 60-85 |
| > 5小时 | 高涨 | 85-100 |

### 2.4 答题正确率

```
accuracy = 所有 status=completed 且 score!=null 的记录的平均分
```

无已完成记录时返回 0，显示"暂无"。

### 2.5 已掌握/薄弱知识点

| 分类 | 条件 | 排序 |
|------|------|------|
| 已掌握 | mastery ≥ 80 | 按掌握度降序 |
| 薄弱 | 0 < mastery ≤ 30 | 按掌握度升序 |

注意：mastery=0 的知识点（完全未学习）不会出现在任何列表中。

### 2.6 总学习时长

```
totalStudyHours = Σ(duration) / 60
```

所有记录的 duration 字段累加（单位：分钟），转换为小时。

### 2.7 时长偏好

基于所有记录的平均单次学习时长：

| 平均时长 | 偏好 |
|---------|------|
| ≥ 60分钟 | 长时段 |
| 30-59分钟 | 适中节奏 |
| < 30分钟 | 碎片化 |

## 三、数据流

```
用户学习行为（答题/看视频/写代码）
        │
        ▼
POST /api/progress/update  ← 记录到 LearningProgress 表
        │
        ▼
GET /api/progress/{userId} ← 读取所有学习记录
GET /api/profile/{userId}  ← 读取画像配置
        │
        ▼
scoringEngine.js           ← 基于公式计算各项指标
        │
        ▼
LearningProfile 对象       ← 返回给页面渲染
```

## 四、修改文件清单

| 文件 | 改动 |
|------|------|
| `src/utils/scoringEngine.js` | **新增** 评分引擎，所有计算公式 |
| `src/api/learningProfile.js` | **重写** 移除随机 mock，改为调用 progress API + 评分引擎 |
| `src/views/ProfileView.vue` | 骨架屏 + 错误态 + 零值显示"暂无" |
| `src/components/profile/ProfileCards.vue` | 动力进度条，0 值显示"暂无学习记录" |
| `src/components/profile/RadarChart.vue` | 接收 mastery 数组，hover 显示百分比 |
| `src/components/profile/StyleChart.vue` | 接收风格分布对象，hover 显示占比 |
| `src/components/profile/KnowledgeTags.vue` | 标签显示"知识点名 (XX%)" |
| `src/composables/useLearningProfile.js` | 跨页面通知机制 |

## 五、后端对接

前端已对接的后端接口（无需新增）：

| 接口 | 方法 | 用途 |
|------|------|------|
| `/api/progress/{user_id}` | GET | 获取用户所有学习记录 |
| `/api/progress/update` | POST | 记录学习行为 |
| `/api/profile/{user_id}` | GET | 获取画像配置 |

### 其他页面触发画像更新

```javascript
import { recordLearningEvent } from '@/api/learningProfile'

// 用户完成一道练习题
const updatedProfile = await recordLearningEvent(userId, {
  action: 'quiz_complete',
  topic: '循环',
  score: 85,
  duration: 15,
})
// updatedProfile 是重新计算后的完整画像
```
