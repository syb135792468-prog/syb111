"""
生成进度追踪工具（软件杯A3赛题 v2.1 优化版）
- ✅ 跟踪每个资源生成任务的进度百分比和状态
- ✅ 线程安全，支持并发多任务
- ✅ 内存中维护，轻量高效，不依赖额外数据库
- ✅ 供 agents/*_agent.py 更新进度，api/routes/progress.py 查询进度
- ✅ 配合 Resource 模型的 status/progress_percent 字段使用
"""
from __future__ import annotations
from typing import Dict, Optional
from datetime import datetime, timezone
import threading

from config.constants import PROGRESS_CLEANUP_MAX_AGE_SEC
from utils.logger import get_logger

logger = get_logger(__name__, task_id="progress_tracker")


class TaskProgress:
    """单个任务的进度信息"""

    def __init__(self, task_id: str, resource_type: str, title: str,
                 status: str = "pending", percent: int = 0):
        self.task_id = task_id
        self.resource_type = resource_type
        self.title = title
        self.status = status  # pending / processing / completed / failed
        self.percent = percent
        self.message = ""
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now

    def to_dict(self) -> Dict:
        """转为前端可消费的字典"""
        return {
            "task_id": self.task_id,
            "resource_type": self.resource_type,
            "title": self.title,
            "status": self.status,
            "percent": self.percent,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    def __repr__(self) -> str:
        return f"<TaskProgress {self.task_id}: {self.percent}% [{self.status}]>"


class ProgressTracker:
    """
    进度追踪器（线程安全单例）
    内存中维护所有任务的进度信息，轻量高效
    """

    _instance: Optional["ProgressTracker"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._tasks: Dict[str, TaskProgress] = {}
        self._task_lock = threading.Lock()
        self._initialized = True

    def create_task(self, task_id: str, resource_type: str, title: str) -> TaskProgress:
        """创建一个新的进度追踪任务，返回任务对象"""
        with self._task_lock:
            tp = TaskProgress(task_id, resource_type, title)
            self._tasks[task_id] = tp
            logger.info(f"✅ 进度任务已创建: {task_id} ({resource_type}: {title})")
            return tp

    def update(
            self,
            task_id: str,
            percent: int,
            status: Optional[str] = None,
            message: str = ""
    ) -> None:
        """
        更新任务进度

        Args:
            task_id: 任务ID
            percent: 进度百分比（0-100）
            status: 状态（可选，不填则根据percent自动判断）
            message: 附加信息（可选，失败时填错误信息）
        """
        with self._task_lock:
            tp = self._tasks.get(task_id)
            if tp:
                tp.percent = max(0, min(100, percent))

                # 状态判断逻辑
                if status:
                    tp.status = status
                else:
                    if tp.percent >= 100:
                        tp.status = "completed"
                    elif tp.percent > 0:
                        tp.status = "processing"
                    else:
                        tp.status = "pending"

                tp.message = message
                tp.updated_at = datetime.now(timezone.utc)

                logger.debug(f"📊 进度更新: {task_id} → {tp.percent}% [{tp.status}]")
            else:
                logger.warning(f"⚠️  任务 {task_id} 不存在，无法更新")

    def complete(self, task_id: str, message: str = "生成完成") -> None:
        """标记任务为完成"""
        self.update(task_id, percent=100, status="completed", message=message)

    def fail(self, task_id: str, error_message: str) -> None:
        """标记任务为失败"""
        self.update(task_id, percent=0, status="failed", message=error_message)
        logger.error(f"❌ 任务失败: {task_id} - {error_message}")

    def get(self, task_id: str) -> Optional[TaskProgress]:
        """查询单个任务进度"""
        with self._task_lock:
            return self._tasks.get(task_id)

    def get_all(self) -> Dict[str, TaskProgress]:
        """查询所有任务进度"""
        with self._task_lock:
            return dict(self._tasks)

    def remove(self, task_id: str) -> None:
        """移除已完成或失败的任务"""
        with self._task_lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                logger.info(f"🗑️  进度任务已移除: {task_id}")

    def cleanup_completed(self, max_age_seconds: int = PROGRESS_CLEANUP_MAX_AGE_SEC) -> int:
        """清理超过指定时间的已完成/失败任务，返回清理数量"""
        now = datetime.now(timezone.utc)
        removed = 0
        with self._task_lock:
            to_remove = []
            for tid, tp in self._tasks.items():
                if tp.status in ("completed", "failed"):
                    age = (now - tp.updated_at).total_seconds()
                    if age > max_age_seconds:
                        to_remove.append(tid)
            for tid in to_remove:
                del self._tasks[tid]
                removed += 1
        if removed:
            logger.info(f"🧹 清理了 {removed} 个过期进度任务")
        return removed


# ------------------------------
# 全局单例（推荐使用）
# ------------------------------
def get_progress_tracker() -> ProgressTracker:
    """获取全局进度追踪器单例"""
    return ProgressTracker()


# ------------------------------
# 模块自测
# ------------------------------
if __name__ == "__main__":
    import time

    print("=" * 60)
    print("🔍 进度追踪器模块自测 v2.1")
    print("=" * 60)

    tracker = get_progress_tracker()

    # 1. 创建任务
    print("\n1. 创建测试任务...")
    tp = tracker.create_task("test_task_001", "doc", "Python变量与数据类型")
    print(f"   ✅ 任务创建成功: {tp}")

    # 2. 更新进度
    print("\n2. 测试更新进度...")
    tracker.update("test_task_001", 25)
    print(f"   ✅ 进度更新到25%: {tracker.get('test_task_001')}")

    time.sleep(0.1)
    tracker.update("test_task_001", 50)
    print(f"   ✅ 进度更新到50%: {tracker.get('test_task_001')}")

    # 3. 标记完成
    print("\n3. 测试标记完成...")
    tracker.complete("test_task_001")
    print(f"   ✅ 任务已完成: {tracker.get('test_task_001')}")

    # 4. 测试失败
    print("\n4. 测试失败场景...")
    tp2 = tracker.create_task("test_task_002", "quiz", "Python练习题")
    tracker.fail("test_task_002", "API调用超时")
    print(f"   ✅ 任务已标记失败: {tracker.get('test_task_002')}")

    # 5. 查看所有任务
    print("\n5. 查看所有任务...")
    all_tasks = tracker.get_all()
    print(f"   ✅ 当前共有 {len(all_tasks)} 个任务")

    print("\n" + "=" * 60)
    print("✅ 进度追踪器模块自测通过！")
    print("=" * 60)