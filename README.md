# Python 智能学习助手 — Multi-Agent 协作系统

> 基于 LangGraph + FastAPI + React 19 的多智能体个性化学习平台，10+ 专职 Agent 通过统一路由动态协作，实现从学习、练习到评估的完整闭环。

## 核心亮点

- **Multi-Agent 架构**：10+ 专职 Agent（Quiz / Mindmap / Code / Video / Socratic 等），通过统一路由 Agent 动态分发
- **LangGraph 状态机**：苏格拉底导学工作流包含 11 个节点、条件路由、interrupt/Command 机制，支持会话持久化与恢复
- **RAG 防幻觉**：ChromaDB 向量检索 + 余弦距离，知识片段注入 LLM prompt，确保生成内容基于教材
- **自适应难度**：IRT 模型实时估计用户能力，动态调整题目难度（5 级）
- **实时学习状态追踪**：normal / struggling / confused / bored / mastering 五状态机，驱动教学策略实时切换
- **置信度校准**：LLM 自报置信度经过校准器校准，低置信度自动降级为关键词兜底
- **SSE 流式输出**：全链路异步，前端实时渲染 Agent 思考过程

## 架构总览

```
用户输入
  │
  ▼
┌─────────────────────────────────────────────────────┐
│              UnifiedRouterAgent (统一路由)            │
│  单次 LLM 调用 = 意图识别 + 资源路由 + 画像更新       │
│  置信度校准 → 低置信度降级为关键词兜底                  │
└───────────────────────┬─────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ 学习路径  │  │ 资源生成  │  │ 苏格拉底  │
    │ PathAgent│  │ 6种Agent │  │ 导学工作流│
    └──────────┘  └────┬─────┘  └────┬─────┘
                       │             │
              ┌────────┼────────┐    │
              ▼        ▼        ▼    ▼
         ┌──────┐ ┌──────┐ ┌──────┐ ┌─────────────┐
         │ Quiz │ │ Code │ │Video │ │ SocraticWorkflow │
         │Agent │ │Agent │ │Agent │ │ (LangGraph)  │
         └──┬───┘ └──┬───┘ └──┬───┘ │ 11节点/条件路由│
            │        │        │     │ interrupt恢复 │
            ▼        ▼        ▼     └──────┬──────┘
         ┌─────────────────────────────┐    │
         │     RAG 知识库检索           │    │
         │  ChromaDB + 余弦距离        │    │
         │  知识片段注入 prompt 防幻觉   │    │
         └─────────────────────────────┘    │
                                            ▼
                                   ┌─────────────────┐
                                   │  数据持久化层     │
                                   │  画像/错题本/进度  │
                                   │  IRT能力估计      │
                                   │  间隔重复调度      │
                                   └─────────────────┘
```

## 技术栈

| 层 | 技术 | 说明 |
|---|------|------|
| **Agent 编排** | LangGraph | StateGraph + conditional_edges + interrupt/Command |
| **Agent 基类** | 自研 BaseAgent | 统一 LLM 调用、RAG 检索、JSON 提取、安全拦截 |
| **路由** | UnifiedRouterAgent | 单次 LLM 调用完成意图+路由+画像，置信度校准 |
| **后端** | FastAPI + SQLAlchemy | 全异步，SSE 流式，自动 DB 迁移 |
| **前端** | React 19 + TypeScript + Zustand | SPA，CodeMirror 代码编辑，Mermaid 思维导图 |
| **向量库** | ChromaDB | PersistentClient，余弦距离，自动构建+检索 |
| **LLM** | 智谱 GLM-5.2（主，火山方舟Coding Plan）/ DeepSeek（备） | 统一客户端，自动降级重试 |
| **自适应** | IRT + 实时学习状态机 | 能力估计 + 5 状态驱动教学策略 |
| **记忆** | 短期（chat_history）+ 长期（user_memory.json） | 增量更新，禁止全量覆盖 |

## Agent 清单

| Agent | 职责 | 核心能力 |
|-------|------|---------|
| `UnifiedRouterAgent` | 统一路由 | 意图识别 + 资源类型 + 主题提取 + 画像更新，单次 LLM 调用 |
| `QuizAgent` | 测验生成 | RAG 检索防幻觉，知识点归一化，自适应难度 |
| `CodeAgent` | 代码练习 | 代码生成 + 沙箱执行 + 结果评估 |
| `MindmapAgent` | 思维导图 | JSON / Markdown / Mermaid 三种格式生成 |
| `VideoAgent` | 视频资源 | 脚本生成 + HTML 播放器渲染 |
| `DocAgent` | 文档生成 | 知识点结构化文档，RAG 增强 |
| `PathAgent` | 学习路径 | 问卷画像 → 路径规划 → 进度追踪 |
| `TutorAgent` | 自由问答 | 多轮对话，上下文记忆 |
| `EvaluationAgent` | 学习评估 | 掌握度评估 + 薄弱点分析 |
| `AggregatorAgent` | 结果聚合 | 多 Agent 输出合并为统一响应 |
| `ProfileAgent` | 用户画像 | 从对话中提取学习特征，动态更新 |
| `SocraticWorkflow` | 苏格拉底导学 | 11 节点 LangGraph 状态机（见下方） |

## 苏格拉底导学工作流（核心模块）

基于 LangGraph 的完整状态机，实现苏格拉底式引导教学：

```
analyze_problem → teaching_decision_engine
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
   ask_question    explain_concept   code_demo
   practice_ex    rephrase_question  relate_knowledge
         │              │              │
         ▼              ▼              ▼
   evaluate_and_decide ────────────────┘
         │
         ▼ (条件路由)
   generate_hint / summarize → END
```

**设计亮点：**
- **动态决策引擎**：`teaching_decision_engine` 根据用户表现实时选择教学动作（提问/讲解/代码演示/练习/关联知识）
- **安全阀机制**：连续错误>=4 / 提示>=8 / 轮次>=20 → 强制进入总结，防止死循环
- **防重复机制**：同一动作+同一知识点连续 2 次后强制切换，避免单调
- **interrupt/Command**：支持暂停等待用户输入，会话状态持久化到 checkpointer
- **IRT 自适应**：基于项目反应理论实时估计用户能力，动态调整题目难度
- **实时学习状态机**：5 种状态（normal / struggling / confused / bored / mastering）驱动教学策略切换
- **错题本 + 间隔重复**：自动记录错题，SM-2 算法调度下次复习时间

## 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/syb135792468-prog/syb111.git
cd syb111

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 3. Docker 一键启动
docker-compose up
```

启动后访问 http://localhost:8000

**本地开发：**

```bash
# 后端
pip install -r requirements.txt
python main.py

# 前端
cd frontend
npm install
npm run dev
```

## 项目结构

```
├── agents/                    # Agent 层
│   ├── base_agent.py          # Agent 基类（统一 LLM/RAG/JSON/安全）
│   ├── unified_router_agent.py# 统一路由（意图+资源+画像，单次LLM）
│   ├── socratic_workflow.py   # 苏格拉底导学（LangGraph 11节点状态机）
│   ├── quiz_agent.py          # 测验生成
│   ├── code_agent.py          # 代码练习
│   ├── mindmap_agent.py       # 思维导图
│   ├── video_agent.py         # 视频资源
│   ├── path_agent.py          # 学习路径
│   └── ...
│
├── ai/                        # AI 引擎层
│   ├── adaptive_difficulty.py # IRT 自适应难度
│   ├── real_time_adaptation.py# 实时学习状态机
│   ├── spaced_repetition.py   # 间隔重复（SM-2）
│   ├── confidence_calibrator.py# LLM 置信度校准
│   └── prompts/               # 苏格拉底教学 prompt
│
├── api/                       # 后端 API 层
│   ├── app.py                 # FastAPI 应用入口
│   └── routes/                # 路由（chat/resource/profile/quiz/path）
│
├── config/                    # 配置层
│   ├── model_config.py        # 模型配置 + 知识点枚举
│   ├── settings.py            # 环境变量
│   ├── constants.py           # 全局常量
│   └── prompts/               # 34 个 Agent prompt 模板
│
├── frontend/                  # 前端（React 19 + TypeScript）
│   └── src/
│       ├── components/        # UI 组件（Chat/Quiz/Mindmap/Path/Profile）
│       ├── api/               # API 调用层
│       ├── stores/            # Zustand 状态管理
│       └── composables/       # SSE 流式处理
│
├── graph/                     # LangGraph 工作流层
│   ├── workflow.py            # 全流程工作流（统一路由版）
│   └── checkpointer.py       # 会话持久化
│
├── models/                    # 数据模型层
│   ├── database.py            # SQLAlchemy 异步引擎
│   ├── profile.py             # 用户画像模型
│   ├── error_book.py          # 错题本模型
│   └── progress.py            # 学习进度模型
│
├── utils/                     # 工具层
│   ├── llm_client.py          # 统一 LLM 客户端（降级重试）
│   ├── rag_utils.py           # ChromaDB 向量检索
│   ├── code_executor.py       # 代码沙箱执行
│   └── behavior_tracker.py    # 用户行为追踪
│
└── tests/                     # 测试
    ├── test_agents.py         # Agent 单元测试
    ├── test_socratic.py       # 苏格拉底工作流测试
    └── test_e2e.py            # 端到端测试
```

## Prompt 工程

34 个 prompt 模板文件（`config/prompts/*.txt`），采用分层设计：

- **System Prompt**：角色定义 + 输出格式约束 + 知识点列表
- **User Prompt**：动态数据注入（用户输入 + 对话历史 + RAG 检索结果）
- **场景化参数**：每个 Agent 独立配置 temperature / max_tokens
- **花括号转义**：自动处理 RAG 上下文中的 `{}`，防止 `str.format()` 误解析

## 记忆系统

| 类型 | 实现 | 用途 |
|------|------|------|
| 短期记忆 | `chat_history` 列表 | 当前会话上下文，路由时取最近 3 轮 |
| 长期记忆 | `user_memory.json` | 用户画像、学习偏好、知识点掌握 |
| 学习状态 | `real_time_adaptation_engine` | 5 种状态实时切换，驱动教学策略 |
| 错题记忆 | `ErrorBook` + SM-2 | 间隔重复调度，自动安排复习 |
| 能力估计 | IRT 模型 | 基于答题历史估计用户能力值 |

## License

MIT
