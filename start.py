"""
start.py - 一键启动脚本
双击或运行 python start.py 即可启动服务并自动打开浏览器
"""
import os
import sys
import time
import webbrowser
import subprocess
import socket
from pathlib import Path

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


def wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    """等待服务启动完成"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def check_frontend() -> bool:
    """检查前端文件是否存在"""
    frontend_dir = Path(__file__).parent / "frontend"
    index_html = frontend_dir / "index.html"
    if not index_html.exists():
        print(f"[!] 前端文件不存在: {index_html}")
        print("    请确保 frontend/index.html 文件存在")
        return False
    return True


def main():
    print("=" * 50)
    print("  Python 智能学习助手 - 一键启动")
    print("=" * 50)

    if not check_frontend():
        input("\n按回车键退出...")
        sys.exit(1)

    print(f"[*] 正在启动服务: {URL}")
    print(f"[*] API 文档: {URL}/docs")
    print()

    # 启动 uvicorn 子进程
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app",
         "--host", HOST, "--port", str(PORT),
         "--log-level", "info"],
        cwd=str(Path(__file__).parent),
    )

    # 等待服务就绪后打开浏览器
    print("[*] 等待服务启动...")
    if wait_for_server(HOST, PORT, timeout=30):
        print(f"[+] 服务已启动，正在打开浏览器...")
        webbrowser.open(URL)
    else:
        print("[!] 服务启动超时，请检查日志")

    print()
    print(f"[i] 访问地址: {URL}")
    print("[i] 按 Ctrl+C 停止服务")
    print()

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[*] 正在停止服务...")
        proc.terminate()
        proc.wait(timeout=5)
        print("[+] 服务已停止")


if __name__ == "__main__":
    main()
