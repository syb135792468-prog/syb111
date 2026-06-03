"""
utils/code_executor.py - 安全代码执行沙箱（加固版）
- subprocess 隔离执行（非 exec()）
- asyncio 超时控制 + 并发信号量
- 资源限制（内存、CPU 时间）
- 执行日志与 metrics
- 禁止危险模块导入
"""
from __future__ import annotations
import asyncio
import sys
import tempfile
import os
import time
from typing import Dict, Any
from collections import defaultdict
from utils.logger import get_logger
from config.constants import (
    CODE_EXEC_DEFAULT_TIMEOUT, CODE_EXEC_MAX_STDOUT_LENGTH, CODE_EXEC_MAX_STDERR_LENGTH,
    CODE_EXEC_MAX_CONCURRENT, CODE_EXEC_MAX_MEMORY_MB, CODE_EXEC_MAX_CPU_SEC,
)

logger = get_logger(__name__, task_id="code_executor")

# ============================================================
# 1. 并发控制：信号量限制同时执行的子进程数量
# ============================================================
_exec_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _exec_semaphore
    if _exec_semaphore is None:
        _exec_semaphore = asyncio.Semaphore(CODE_EXEC_MAX_CONCURRENT)
    return _exec_semaphore


# ============================================================
# 2. 执行 Metrics（内存中统计，定期可输出到日志）
# ============================================================
class _ExecMetrics:
    """轻量级执行指标收集器"""

    def __init__(self) -> None:
        self.total_executions = 0
        self.success_count = 0
        self.failure_count = 0
        self.timeout_count = 0
        self.blocked_import_count = 0
        self.total_exec_time = 0.0
        self._recent_durations: list[float] = []

    def record(
        self,
        success: bool,
        timed_out: bool,
        exec_time: float,
        blocked_import: bool = False,
    ) -> None:
        self.total_executions += 1
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        if timed_out:
            self.timeout_count += 1
        if blocked_import:
            self.blocked_import_count += 1
        self.total_exec_time += exec_time
        self._recent_durations.append(exec_time)
        if len(self._recent_durations) > 100:
            self._recent_durations = self._recent_durations[-50:]

    @property
    def avg_exec_time(self) -> float:
        if not self._recent_durations:
            return 0.0
        return sum(self._recent_durations) / len(self._recent_durations)

    def summary(self) -> Dict[str, Any]:
        return {
            "total": self.total_executions,
            "success": self.success_count,
            "failure": self.failure_count,
            "timeout": self.timeout_count,
            "blocked_import": self.blocked_import_count,
            "avg_exec_time_ms": round(self.avg_exec_time * 1000, 1),
        }


_metrics = _ExecMetrics()

# ============================================================
# 3. 危险模块黑名单
# ============================================================
BLOCKED_MODULES = {
    "os", "subprocess", "shutil", "sys", "socket", "http", "urllib",
    "ctypes", "multiprocessing", "threading", "signal",
    "importlib", "compileall", "code",
}

BLOCKED_BUILTINS = {"exec", "eval", "compile", "__import__", "open", "breakpoint"}

GUARD_CODE = '''
import sys as _sys
_blocked = {blocked_modules}
_original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__
_blocked_triggered = False
def _safe_import(name, *args, **kwargs):
    global _blocked_triggered
    top = name.split('.')[0]
    if top in _blocked:
        _blocked_triggered = True
        raise ImportError(f"模块 {{name}} 不允许导入")
    return _original_import(name, *args, **kwargs)
if hasattr(__builtins__, '__import__'):
    __builtins__.__import__ = _safe_import
else:
    import builtins
    builtins.__import__ = _safe_import
'''


# ============================================================
# 4. 子进程资源限制（preexec_fn）
# ============================================================
def _set_resource_limits() -> None:
    """在子进程中设置资源限制（仅 Unix）"""
    try:
        import resource
        # 限制虚拟内存（RSS）
        mem_bytes = CODE_EXEC_MAX_MEMORY_MB * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
        # 限制 CPU 时间
        resource.setrlimit(resource.RLIMIT_CPU, (CODE_EXEC_MAX_CPU_SEC, CODE_EXEC_MAX_CPU_SEC))
        # 限制可创建的子进程数（禁止 fork）
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except (ImportError, ValueError, OSError):
        # Windows 或 resource 不可用时跳过
        pass


# ============================================================
# 5. 核心执行函数
# ============================================================
async def execute_python_code(code: str, timeout: int = CODE_EXEC_DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """
    安全执行 Python 代码（加固版）

    Returns:
        {
            "stdout": str,
            "stderr": str,
            "success": bool,
            "timed_out": bool,
            "execution_time": float,  # 秒
            "metrics": dict           # 执行器全局指标
        }
    """
    blocked_str = ", ".join(f"'{m}'" for m in BLOCKED_MODULES)
    guard = GUARD_CODE.format(blocked_modules=f"{{{blocked_str}}}")
    full_code = guard + "\n" + code

    # 写入临时文件
    fd, tmp_path = tempfile.mkstemp(suffix=".py", prefix="sandbox_exec_")
    blocked_import_triggered = False

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(full_code)

        start_time = time.monotonic()

        # 并发控制：获取信号量
        sem = _get_semaphore()
        async with sem:
            try:
                child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                # Unix: 使用 preexec_fn 设置资源限制
                # Windows: 跳过（resource 模块不可用）
                preexec = _set_resource_limits if sys.platform != "win32" else None

                proc = await asyncio.create_subprocess_exec(
                    sys.executable, tmp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=child_env,
                    preexec_fn=preexec,
                )
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
                elapsed = time.monotonic() - start_time

                stdout = stdout_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "")[:CODE_EXEC_MAX_STDOUT_LENGTH]
                stderr = stderr_bytes.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "")[:CODE_EXEC_MAX_STDERR_LENGTH]

                # 检测是否触发了模块拦截
                if "不允许导入" in stderr:
                    blocked_import_triggered = True

                success = proc.returncode == 0
                _metrics.record(success=success, timed_out=False, exec_time=elapsed, blocked_import=blocked_import_triggered)

                logger.info(
                    f"代码执行完成 | success={success} | time={elapsed:.3f}s | "
                    f"stdout_len={len(stdout)} | stderr_len={len(stderr)}"
                )

                return {
                    "stdout": stdout,
                    "stderr": stderr,
                    "success": success,
                    "timed_out": False,
                    "execution_time": round(elapsed, 3),
                    "metrics": _metrics.summary(),
                }

            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start_time
                try:
                    proc.kill()
                except Exception:
                    pass

                _metrics.record(success=False, timed_out=True, exec_time=elapsed)
                logger.warning(f"代码执行超时 | timeout={timeout}s")

                return {
                    "stdout": "",
                    "stderr": f"代码执行超时（{timeout}秒）",
                    "success": False,
                    "timed_out": True,
                    "execution_time": round(elapsed, 3),
                    "metrics": _metrics.summary(),
                }

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def get_executor_metrics() -> Dict[str, Any]:
    """获取执行器全局指标（供 API 调用）"""
    return _metrics.summary()
