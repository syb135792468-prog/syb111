"""
api/task_store.py - 后台任务存储与进度追踪（chat/resource 共用）

任务生命周期：
  register_task -> [update_progress * N] -> complete_task / fail_task

任务条目字段：
  status: "pending" | "completed" | "failed"
  data: 完成态返回的资源数据
  error: 失败态错误信息
  created_at: monotonic 时间戳（用于 TTL 清理 + pending 超时）
  progress_percent: 0-100，阶段级进度
  stage: 当前阶段标识（script/audio/render/gen/dedup/supplement/assemble）
  message: 人类可读阶段描述
  resource_type: 资源类型（quiz/video/mindmap/...）
  topic: 生成主题
"""
from __future__ import annotations

import asyncio
import time as _time
from typing import Any, Optional

from utils.logger import get_logger

logger = get_logger(__name__, task_id="task_store")

# task_id -> 任务条目
_task_results: dict = {}

# 完成态任务保留 10 分钟供前端取结果
_TASK_RESULT_TTL_SEC = 600
# pending 任务最大存活时间，超过判定失败
_TASK_PENDING_MAX_SEC = 300

_cleanup_task_ref: Optional[asyncio.Task] = None


def register_task(task_id: str, resource_type: str = "", topic: str = "") -> None:
    """注册新任务为 pending 状态，progress_percent=0。"""
    _task_results[task_id] = {
        "status": "pending",
        "created_at": _time.monotonic(),
        "progress_percent": 0,
        "stage": "",
        "message": "",
        "resource_type": resource_type,
        "topic": topic,
    }


def update_progress(task_id: str, percent: int, stage: str = "", message: str = "") -> None:
    """更新 pending 任务的进度（只增不减，防止乱序回退）。"""
    entry = _task_results.get(task_id)
    if not entry or entry.get("status") != "pending":
        return
    entry["progress_percent"] = max(entry.get("progress_percent", 0), min(100, max(0, percent)))
    if stage:
        entry["stage"] = stage
    if message:
        entry["message"] = message


def complete_task(task_id: str, data: Any) -> None:
    """标记任务完成，写入结果数据。"""
    entry = _task_results.get(task_id)
    if entry:
        entry["status"] = "completed"
        entry["data"] = data
        entry["progress_percent"] = 100


def fail_task(task_id: str, error: str) -> None:
    """标记任务失败，写入错误信息。"""
    entry = _task_results.get(task_id)
    if entry:
        entry["status"] = "failed"
        entry["error"] = error


def get_task(task_id: str) -> Optional[dict]:
    """读取任务条目（不删除）。"""
    return _task_results.get(task_id)


def pop_task(task_id: str) -> Optional[dict]:
    """弹出任务条目（读取后删除）。"""
    return _task_results.pop(task_id, None)


async def _cleanup_stale_tasks() -> None:
    """定时清理：完成态超 TTL + pending 超时。"""
    while True:
        await asyncio.sleep(60)
        now = _time.monotonic()
        stale_ids = [
            tid for tid, info in _task_results.items()
            if (
                info.get("status") != "pending"
                and now - info.get("created_at", now) > _TASK_RESULT_TTL_SEC
            )
            or (
                info.get("status") == "pending"
                and now - info.get("created_at", now) > _TASK_PENDING_MAX_SEC
            )
        ]
        for tid in stale_ids:
            _task_results.pop(tid, None)
        if stale_ids:
            logger.info(f"🧹 [BG-TASK] 清理 {len(stale_ids)} 个过期任务")


def ensure_cleanup_task() -> None:
    """启动清理协程（幂等，无事件循环时静默跳过）。"""
    global _cleanup_task_ref
    if _cleanup_task_ref is None or _cleanup_task_ref.done():
        try:
            _cleanup_task_ref = asyncio.create_task(_cleanup_stale_tasks())
        except RuntimeError:
            pass  # 没有运行中的事件循环（如测试环境）
