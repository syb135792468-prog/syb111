# 软件杯 A3 赛题：基于大模型的个性化资源生成与学习多智能体系统

## 🚀 快速启动

```bash
# 1. 复制环境变量，填写你的 API 密钥
cp .env.example .env

# 2. 一键启动
docker-compose up
```

启动后访问：http://localhost:8000

## 📁 项目结构
```
project/
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── README.md
├── requirements.txt
│
├── config/
│   ├── __init__.py
│   ├── settings.py
│   └── model_config.py
│
├── api/
│   ├── __init__.py
│   ├── app.py
│   └── routes/
│       ├── __init__.py
│       ├── chat.py
│       ├── profile.py
│       ├── resource.py
│       └── progress.py
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── .env.development
│   └── package.json
│
├── data/
│   ├── knowledge_base/
│   │   └── python_basics/
│   └── vector_db/
│
├── models/
│   ├── __init__.py
│   ├── database.py
│   ├── user.py
│   ├── profile.py
│   ├── resource.py
│   └── schemas.py
│
├── utils/
│   ├── __init__.py
│   ├── llm_client.py
│   ├── rag_utils.py
│   ├── security.py
│   ├── multimodal_api.py
│   ├── progress_tracker.py
│   ├── behavior_tracker.py
│   ├── resource_planner.py
│   └── logger.py
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py
│   ├── profile_agent.py
│   ├── intent_agent.py
│   ├── doc_agent.py
│   ├── quiz_agent.py
│   ├── mindmap_agent.py
│   ├── code_agent.py
│   ├── video_agent.py
│   ├── path_agent.py
│   ├── tutor_agent.py
│   └── evaluation_agent.py
│
├── graph/
│   ├── __init__.py
│   ├── state.py
│   ├── workflow.py
│   └── checkpointer.py
│
├── static/
├── logs/
├── generated/
│
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_api.py
│   └── test_e2e.py
│
└── main.py

```

## 📦 用到的开源工具与协议

| 工具 | 用途 | 协议 |
|------|------|------|
| LangGraph | 多智能体编排 | MIT |
| FastAPI | 后端框架 | MIT |
| ChromaDB | 向量数据库 | Apache 2.0 |
| SQLAlchemy | ORM | MIT |
| Pydantic | 数据校验 | MIT |
