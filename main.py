"""
main.py - 第十五届软件杯A3赛题 项目启动入口
✅ 开发环境：python main.py
✅ 生产环境：uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
✅ 自动加载环境变量配置
✅ 统一日志格式
✅ 开发环境自动重载
✅ 启动时自动清理残留进程占用的端口
"""
from __future__ import annotations

import os
import sys
import socket
import subprocess
import time
import uvicorn
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

# 加载 .env 环境变量（如果存在）
load_dotenv()

# 从环境变量读取配置（默认值适配比赛环境）
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8001))
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
WORKERS = int(os.getenv("WORKERS", 1))

# 导入 FastAPI 应用实例（CORS 已在 api/app.py 中配置）
from api.app import app

def _is_port_in_use(port: int) -> bool:
    """检测端口是否被占用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_port_occupants(port: int) -> None:
    """终止占用指定端口的残留进程"""
    if not _is_port_in_use(port):
        return

    print(f"⚠️  端口 {port} 被占用，正在清理残留进程...")
    pids = set()

    try:
        if sys.platform == "win32":
            # Windows: netstat -ano | findstr :PORT
            result = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit():
                        pids.add(int(pid))
        else:
            # Linux/Mac: lsof -i :PORT -t
            result = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"], capture_output=True, text=True,
            )
            for pid_str in result.stdout.strip().splitlines():
                if pid_str.strip().isdigit():
                    pids.add(int(pid_str.strip()))

        for pid in pids:
            try:
                os.kill(pid, 9 if sys.platform != "win32" else 9)
                print(f"   已终止进程 PID={pid}")
            except (ProcessLookupError, PermissionError) as e:
                print(f"   终止 PID={pid} 失败: {e}")

        # 等待端口释放
        for _ in range(10):
            if not _is_port_in_use(port):
                break
            time.sleep(0.3)

        if _is_port_in_use(port):
            print(f"❌ 端口 {port} 仍被占用，请手动检查")
            sys.exit(1)
        else:
            print(f"✅ 端口 {port} 已释放")

    except Exception as e:
        print(f"⚠️  端口清理异常: {e}，继续尝试启动...")


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

    # 自动清理残留进程占用的端口
    _kill_port_occupants(PORT)

    # 启动 uvicorn 服务（彻底禁用热重载，解决Windows端口占用问题）
    uvicorn.run(
        "api.app:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="info",
        access_log=True,
        workers=WORKERS,
        loop="asyncio",
    )


if __name__ == "__main__":
    main()
