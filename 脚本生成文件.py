# setup_project.py
# 运行此脚本一键生成 A3 赛题项目结构（包含完整配置文件）

import os
import pathlib

ROOT = pathlib.Path(__file__).parent

# ==================== 目录列表 ====================
DIRS = [
    "config",
    "api/routes",
    "frontend/src",
    "frontend/public",
    "data/knowledge_base/python_basics",
    "data/vector_db",
    "models",
    "utils",
    "agents",
    "graph",
    "generated",
    "tests",
    "static",
    "logs",
]

# ==================== 文件内容模板（全部用括号字符串避免三引号问题） ====================

REQUIREMENTS = (
    "fastapi==0.110.0\n"
    "uvicorn==0.29.0\n"
    "langgraph==0.2.19\n"
    "langchain==0.2.0\n"
    "langchain-community==0.2.0\n"
    "chromadb==0.5.0\n"
    "python-dotenv==1.0.1\n"
    "pydantic==2.7.0\n"
    "sqlalchemy==2.0.29\n"
    "requests==2.31.0\n"
    "tenacity==8.3.0\n"
    "python-multipart==0.0.9\n"
    "sse-starlette==1.6.1\n"
    "openai==1.50.0\n"
)

DOCKERFILE = (
    "FROM python:3.10-slim\n"
    "\n"
    "WORKDIR /app\n"
    "\n"
    "# 系统依赖\n"
    "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
    "    build-essential \\\n"
    "    libsqlite3-dev \\\n"
    "    curl \\\n"
    "    nodejs \\\n"
    "    npm \\\n"
    "    && rm -rf /var/lib/apt/lists/*\n"
    "\n"
    "# Python 依赖\n"
    "COPY requirements.txt .\n"
    "RUN pip install --no-cache-dir -r requirements.txt\n"
    "\n"
    "# 前端构建\n"
    "COPY frontend/ /app/frontend/\n"
    "RUN cd frontend && npm install && npm run build && cp -r dist/* /app/static/\n"
    "\n"
    "# 后端代码\n"
    "COPY . .\n"
    "\n"
    "EXPOSE 8000\n"
    'CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]\n'
)

DOCKER_COMPOSE = (
    "version: '3.8'\n"
    "\n"
    "services:\n"
    "  app:\n"
    "    build: .\n"
    "    ports:\n"
    '      - "8000:8000"\n'
    "    volumes:\n"
    "      - ./data:/app/data\n"
    "      - ./generated:/app/generated\n"
    "      - ./logs:/app/logs\n"
    "    environment:\n"
    "      - ENVIRONMENT=production\n"
    "    restart: unless-stopped\n"
)

README_PART1 = (
    "# 软件杯 A3 赛题：基于大模型的个性化资源生成与学习多智能体系统\n"
    "\n"
    "## 🚀 快速启动\n"
    "\n"
    "```bash\n"
    "# 1. 复制环境变量，填写你的 API 密钥\n"
    "cp .env.example .env\n"
    "\n"
    "# 2. 一键启动\n"
    "docker-compose up\n"
    "```\n"
    "\n"
    "启动后访问：http://localhost:8000\n"
    "\n"
    "## 📁 项目结构\n"
    "```\n"
)
# 结构部分单独拼接，避免三引号内嵌三引号
README_PART2 = (
    "```\n"
    "\n"
    "## 📦 用到的开源工具与协议\n"
    "\n"
    "| 工具 | 用途 | 协议 |\n"
    "|------|------|------|\n"
    "| LangGraph | 多智能体编排 | MIT |\n"
    "| FastAPI | 后端框架 | MIT |\n"
    "| ChromaDB | 向量数据库 | Apache 2.0 |\n"
    "| SQLAlchemy | ORM | MIT |\n"
    "| Pydantic | 数据校验 | MIT |\n"
)

FRONTEND_PACKAGE = (
    "{\n"
    '  "name": "a3-frontend",\n'
    '  "private": true,\n'
    '  "version": "0.0.0",\n'
    '  "type": "module",\n'
    '  "scripts": {\n'
    '    "dev": "vite",\n'
    '    "build": "vite build",\n'
    '    "preview": "vite preview"\n'
    "  },\n"
    '  "dependencies": {\n'
    '    "vue": "^3.4.21"\n'
    "  },\n"
    '  "devDependencies": {\n'
    '    "@vitejs/plugin-vue": "^5.0.4",\n'
    '    "vite": "^5.2.8"\n'
    "  }\n"
    "}\n"
)

ENV_EXAMPLE = (
    "# 环境标识\n"
    "ENVIRONMENT=development\n"
    "LOG_LEVEL=INFO\n"
    "\n"
    "# 讯飞星火 API\n"
    "SPARK_APP_ID=你的APPID\n"
    "SPARK_API_KEY=你的APIKey\n"
    "SPARK_API_SECRET=你的APISecret\n"
    "\n"
    "# 讯飞 SeeDance 多模态 API\n"
    "SEEDANCE_API_KEY=你的SeeDance密钥\n"
    "\n"
    "# DeepSeek API（备用降级）\n"
    "DEEPSEEK_API_KEY=你的DeepSeek密钥\n"
    "\n"
    "# 数据库\n"
    "DATABASE_URL=sqlite:///./data/database.db\n"
)

GITIGNORE = (
    ".env\n"
    "__pycache__/\n"
    "*.pyc\n"
    ".venv/\n"
    "venv/\n"
    "data/vector_db/\n"
    "data/database.db\n"
    "generated/\n"
    "frontend/node_modules/\n"
    "frontend/dist/\n"
    "logs/\n"
    "*.log\n"
    ".vscode/\n"
    ".idea/\n"
    "*.pid\n"
)

STRUCTURE_STR = (
    "project/\n"
    "├── .env.example\n"
    "├── .gitignore\n"
    "├── Dockerfile\n"
    "├── docker-compose.yml\n"
    "├── README  book1.md\n"
    "├── requirements.txt\n"
    "│\n"
    "├── config/\n"
    "│   ├── __init__.py\n"
    "│   ├── settings.py\n"
    "│   └── model_config.py\n"
    "│\n"
    "├── api/\n"
    "│   ├── __init__.py\n"
    "│   ├── app.py\n"
    "│   └── routes/\n"
    "│       ├── __init__.py\n"
    "│       ├── chat.py\n"
    "│       ├── profile.py\n"
    "│       ├── resource.py\n"
    "│       └── progress.py\n"
    "│\n"
    "├── frontend/\n"
    "│   ├── src/\n"
    "│   ├── public/\n"
    "│   ├── .env.development\n"
    "│   └── package.json\n"
    "│\n"
    "├── data/\n"
    "│   ├── knowledge_base/\n"
    "│   │   └── python_basics/\n"
    "│   └── vector_db/\n"
    "│\n"
    "├── models/\n"
    "│   ├── __init__.py\n"
    "│   ├── database.py\n"
    "│   ├── user.py\n"
    "│   ├── profile.py\n"
    "│   ├── resource.py\n"
    "│   └── schemas.py\n"
    "│\n"
    "├── utils/\n"
    "│   ├── __init__.py\n"
    "│   ├── llm_client.py\n"
    "│   ├── rag_utils.py\n"
    "│   ├── security.py\n"
    "│   ├── multimodal_api.py\n"
    "│   ├── progress_tracker.py\n"
    "│   ├── behavior_tracker.py\n"
    "│   ├── resource_planner.py\n"
    "│   └── logger.py\n"
    "│\n"
    "├── agents/\n"
    "│   ├── __init__.py\n"
    "│   ├── base_agent.py\n"
    "│   ├── profile_agent.py\n"
    "│   ├── intent_agent.py\n"
    "│   ├── doc_agent.py\n"
    "│   ├── quiz_agent.py\n"
    "│   ├── mindmap_agent.py\n"
    "│   ├── code_agent.py\n"
    "│   ├── video_agent.py\n"
    "│   ├── path_agent.py\n"
    "│   ├── tutor_agent.py\n"
    "│   └── evaluation_agent.py\n"
    "│\n"
    "├── graph/\n"
    "│   ├── __init__.py\n"
    "│   ├── state.py\n"
    "│   ├── workflow.py\n"
    "│   └── checkpointer.py\n"
    "│\n"
    "├── static/\n"
    "├── logs/\n"
    "├── generated/\n"
    "│\n"
    "├── tests/\n"
    "│   ├── __init__.py\n"
    "│   ├── test_agents.py\n"
    "│   ├── test_api.py\n"
    "│   └── test_e2e.py\n"
    "│\n"
    "└── main.py\n"
)

# ==================== 空文件列表 ====================
FILES = [
    "config/__init__.py",
    "config/settings.py",
    "config/model_config.py",
    "api/__init__.py",
    "api/app.py",
    "api/routes/__init__.py",
    "api/routes/chat.py",
    "api/routes/profile.py",
    "api/routes/resource.py",
    "api/routes/progress.py",
    "frontend/.env.development",
    "models/__init__.py",
    "models/database.py",
    "models/user.py",
    "models/profile.py",
    "models/resource.py",
    "models/schemas.py",
    "utils/__init__.py",
    "utils/llm_client.py",
    "utils/rag_utils.py",
    "utils/security.py",
    "utils/multimodal_api.py",
    "utils/progress_tracker.py",
    "utils/behavior_tracker.py",
    "utils/resource_planner.py",
    "utils/logger.py",
    "agents/__init__.py",
    "agents/base_agent.py",
    "agents/profile_agent.py",
    "agents/intent_agent.py",
    "agents/doc_agent.py",
    "agents/quiz_agent.py",
    "agents/mindmap_agent.py",
    "agents/code_agent.py",
    "agents/video_agent.py",
    "agents/path_agent.py",
    "agents/tutor_agent.py",
    "agents/evaluation_agent.py",
    "graph/__init__.py",
    "graph/state.py",
    "graph/workflow.py",
    "graph/checkpointer.py",
    "tests/__init__.py",
    "tests/test_agents.py",
    "tests/test_api.py",
    "tests/test_e2e.py",
    "main.py",
]

# ==================== 主函数 ====================
def create_structure():
    # 创建目录
    for d in DIRS:
        dir_path = ROOT / d
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"✅ 目录: {dir_path}")

    # 创建空业务文件
    for f in FILES:
        file_path = ROOT / f
        if not file_path.exists():
            file_path.touch()
            print(f"📄 文件: {file_path}")
        else:
            print(f"⏭️ 跳过（已存在）: {file_path}")

    # 写入有内容的配置文件
    def write_if_empty(path, content):
        p = ROOT / path
        if not p.exists() or p.stat().st_size == 0:
            p.write_text(content, encoding="utf-8")
            print(f"📝 写入: {path}")

    write_if_empty(".gitignore", GITIGNORE)
    write_if_empty(".env.example", ENV_EXAMPLE)
    write_if_empty("requirements.txt", REQUIREMENTS)
    write_if_empty("Dockerfile", DOCKERFILE)
    write_if_empty("docker-compose.yml", DOCKER_COMPOSE)
    write_if_empty("frontend/package.json", FRONTEND_PACKAGE)

    # 拼接 README
    readme_content = README_PART1 + STRUCTURE_STR + "\n" + README_PART2
    write_if_empty("README.md", readme_content)

    write_if_empty("data/knowledge_base/python_basics/README  book1.md",
                   "# 《Python程序设计》课程知识库\n\n本知识库用于 RAG 检索，覆盖 Python 基础全部知识点。\n")

    print("\n" + "=" * 50)
    print("🎉 项目结构生成完毕！")
    print("""
接下来你只需要：
1. cp .env.example .env          # 复制环境变量，填写你的 API 密钥
2. docker-compose up             # 一键启动整个项目
3. 访问 http://localhost:8000    # 即可使用
""")
    print("=" * 50)


if __name__ == "__main__":
    create_structure()