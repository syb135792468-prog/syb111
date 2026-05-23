"""
main.py - 第十五届软件杯A3赛题 项目启动入口
✅ 开发环境：python main.py
✅ 生产环境：uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
✅ 自动加载环境变量配置
✅ 统一日志格式
✅ 开发环境自动重载
"""
from __future__ import annotations

import os
import uvicorn
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# 加载 .env 环境变量（如果存在）
load_dotenv()

# 从环境变量读取配置（默认值适配比赛环境）
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
WORKERS = int(os.getenv("WORKERS", 1))

# 导入 FastAPI 应用实例（CORS 已在 api/app.py 中配置）
from api.app import app

def main():
    """项目主函数"""
    print("=" * 60)
    print("🚀 第十五届软件杯A3赛题 - Python智能学习助手")
    print("=" * 60)
    print(f"📌 服务地址: http://{HOST}:{PORT}")
    print(f"📚 接口文档: http://{HOST}:{PORT}/docs")
    print(f"🔍 ReDoc文档: http://{HOST}:{PORT}/redoc")
    print(f"⚙️ 开发模式: {'开启' if DEBUG else '关闭'}")
    print(f"👷 工作进程: {WORKERS}")
    print("=" * 60)
    print("✅ 服务启动成功，按 Ctrl+C 停止")
    print()

    # 启动 uvicorn 服务
    uvicorn.run(
        "api.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        reload_dirs=["api", "models", "agents", "utils"],
        log_level="info",
        access_log=True,
        workers=WORKERS if not DEBUG else 1,
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
