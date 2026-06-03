"""
start.py - 一键启动脚本
双击或运行 python start.py 即可启动服务并自动打开浏览器
自动处理：端口占用清理、前端构建检查
"""
import os
import sys
import time
import webbrowser
import subprocess
import socket
from pathlib import Path

from config.constants import SERVER_WAIT_TIMEOUT_SEC, SOCKET_TIMEOUT, RETRY_INTERVAL_SEC

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


def kill_port_occupier(port: int) -> bool:
    """释放被占用的端口（Windows）"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        pids = set()
        for line in result.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.split()
                if parts:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) != os.getpid():
                        pids.add(pid)
        if not pids:
            return False
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
            print(f"[!] 已终止占用端口 {port} 的进程 (PID: {pid})")
        return True
    except Exception:
        return False


def check_port(host: str, port: int) -> bool:
    """检查端口是否被占用，被占用则尝试释放"""
    try:
        with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT):
            # 端口被占用，尝试释放
            print(f"[!] 端口 {port} 已被占用，正在尝试释放...")
            if kill_port_occupier(port):
                time.sleep(1)
                # 再次检查
                try:
                    with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT):
                        print(f"[!] 端口 {port} 释放失败，请手动关闭占用进程")
                        return False
                except OSError:
                    return True  # 释放成功
            return False
        return True  # 端口未被占用
    except OSError:
        return True  # 端口未被占用


def check_and_build_frontend() -> bool:
    """检查前端 dist 是否需要重新构建"""
    project_dir = Path(__file__).parent
    dist_dir = project_dir / "frontend" / "dist"
    src_dir = project_dir / "frontend" / "src"

    # dist 不存在，需要构建
    if not dist_dir.exists():
        print("[*] 前端 dist 不存在，正在构建...")
        return _run_build(project_dir)

    # 检查 src 是否比 dist 新（任一源文件修改时间晚于 dist/index.html）
    dist_time = (dist_dir / "index.html").stat().st_mtime
    for src_file in src_dir.rglob("*"):
        if src_file.is_file() and src_file.stat().st_mtime > dist_time:
            print("[*] 前端源码有更新，正在重新构建...")
            return _run_build(project_dir)

    return True


def _run_build(project_dir: Path) -> bool:
    """执行 npm run build"""
    frontend_dir = project_dir / "frontend"
    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True, text=True,
            timeout=120
        )
        if result.returncode == 0:
            print("[+] 前端构建成功")
            return True
        else:
            print(f"[!] 前端构建失败:\n{result.stderr[:500]}")
            return False
    except FileNotFoundError:
        print("[!] npm 未安装，请手动构建前端: cd frontend && npm run build")
        return False
    except subprocess.TimeoutExpired:
        print("[!] 前端构建超时")
        return False


def wait_for_server(host: str, port: int, timeout: float = SERVER_WAIT_TIMEOUT_SEC) -> bool:
    """等待服务启动完成"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=SOCKET_TIMEOUT):
                return True
        except OSError:
            time.sleep(RETRY_INTERVAL_SEC)
    return False


def main():
    print("=" * 50)
    print("  Python 智能学习助手 - 一键启动")
    print("=" * 50)

    # 1. 检查并释放端口
    check_port(HOST, PORT)

    # 2. 检查并构建前端
    check_and_build_frontend()

    print(f"[*] 正在启动服务: {URL}")
    print(f"[*] API 文档: {URL}/docs")
    print()

    # 3. 启动 uvicorn 子进程
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.app:app",
         "--host", HOST, "--port", str(PORT),
         "--log-level", "info"],
        cwd=str(Path(__file__).parent),
    )

    # 4. 等待服务就绪后打开浏览器
    print("[*] 等待服务启动...")
    if wait_for_server(HOST, PORT, timeout=SERVER_WAIT_TIMEOUT_SEC):
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
