"""
api/routes/task.py - 后台任务状态查询端点
用于前端轮询资源生成进度（思维导图、视频等不阻塞聊天的后台任务）
"""
import time as _time
from fastapi import APIRouter

from api.task_store import get_task, pop_task, _TASK_PENDING_MAX_SEC

router = APIRouter(prefix="/tasks", tags=["任务查询"])


@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """
    查询后台任务状态。
    返回：
    - {"status": "pending", "progress_percent": 0-100, "stage": "...", "message": "..."}
    - {"status": "completed", "data": [...]}  - 任务完成，返回资源数据
    - {"status": "failed", "error": "..."}  - 任务失败
    - {"status": "failed", "error": "任务不存在或已过期"}  - task_id 无效
    """
    result = get_task(task_id)
    if not result:
        return {"status": "failed", "error": "任务不存在或已过期"}
    # pending 超时保护：防止后台任务崩溃后前端永远轮询
    if result["status"] == "pending":
        elapsed = _time.monotonic() - result.get("created_at", _time.monotonic())
        if elapsed > _TASK_PENDING_MAX_SEC:
            pop_task(task_id)
            return {"status": "failed", "error": "任务执行超时，请重试"}
    if result["status"] == "completed":
        pop_task(task_id)
    return result
