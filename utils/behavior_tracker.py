"""
学习行为追踪工具（软件杯A3赛题 v2.0 简化版）
- ✅ 记录用户的学习行为：查看资源、完成练习、提问、学习会话等
- ✅ 数据持久化到 SQLite，供 evaluation_agent 评估学习效果
- ✅ 依赖 models/user.py 和 models/profile.py
- ✅ 不创建新的模型文件，BehaviorLog 直接定义在这里
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, UTC
from enum import Enum
import threading

from sqlalchemy import (
    Integer, String, DateTime, ForeignKey, JSON,
    CheckConstraint, func, Index
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base, AsyncSessionLocal
from utils.logger import get_logger
from config.constants import (
    DEFAULT_BEHAVIOR_DAYS, DEFAULT_BEHAVIOR_LIMIT,
    STATS_AGGREGATION_DAYS, STATS_AGGREGATION_LIMIT, SECONDS_PER_HOUR,
)

# 延迟导入避免循环依赖
_real_time_engine = None

def _get_real_time_engine():
    global _real_time_engine
    if _real_time_engine is None:
        from ai.real_time_adaptation import real_time_adaptation_engine
        _real_time_engine = real_time_adaptation_engine
    return _real_time_engine

logger = get_logger(__name__, task_id="behavior_tracker")


# ------------------------------
# 1. 行为类型枚举
# ------------------------------
class BehaviorType(Enum):
    """用户学习行为类型枚举"""
    VIEW_RESOURCE = "view_resource"  # 查看资源
    COMPLETE_QUIZ = "complete_quiz"  # 完成练习
    ASK_QUESTION = "ask_question"  # 提问
    STUDY_SESSION = "study_session"  # 学习会话
    WATCH_VIDEO = "watch_video"  # 观看视频
    READ_DOC = "read_doc"  # 阅读文档


# ------------------------------
# 2. 行为日志数据模型（直接定义在这里）
# ------------------------------
class BehaviorLog(Base):
    __tablename__ = "behavior_logs"
    __table_args__ = (
        # 枚举合法性约束
        CheckConstraint(
            f"behavior_type IN {tuple(bt.value for bt in BehaviorType)}",
            name="ck_behavior_type_valid"
        ),
        # 最左前缀复合索引：优化按用户+类型+时间的常用查询
        Index("idx_behavior_user_type_time", "user_id", "behavior_type", "created_at"),
        {"comment": "软件杯A3赛题用户学习行为日志表"}
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    behavior_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True
    )
    resource_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    knowledge_point: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "behavior_type": self.behavior_type,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "knowledge_point": self.knowledge_point,
            "duration_seconds": self.duration_seconds,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ------------------------------
# 3. 行为追踪器（线程安全单例）
# ------------------------------
class BehaviorTracker:
    """用户学习行为记录与分析"""

    _instance: Optional["BehaviorTracker"] = None
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
        self._initialized = True

    @staticmethod
    async def log(
            user_id: int,
            behavior_type: BehaviorType,
            resource_id: Optional[int] = None,
            resource_type: Optional[str] = None,
            knowledge_point: Optional[str] = None,
            duration_seconds: Optional[int] = None,
            extra_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """记录一条学习行为，并同步更新实时学习状态"""
        try:
            async with AsyncSessionLocal() as session:
                log_entry = BehaviorLog(
                    user_id=user_id,
                    behavior_type=behavior_type.value if isinstance(behavior_type, BehaviorType) else behavior_type,
                    resource_id=resource_id,
                    resource_type=resource_type,
                    knowledge_point=knowledge_point,
                    duration_seconds=duration_seconds,
                    extra_data=extra_data,
                )
                session.add(log_entry)
                await session.commit()
                logger.debug(f"📝 行为记录: user={user_id}, type={log_entry.behavior_type}")
        except Exception as e:
            logger.error(f"❌ 记录行为失败: {e}", exc_info=True)

    @staticmethod
    async def log_quiz_answer(
            user_id: int,
            session_id: str,
            is_correct: bool,
            response_time_ms: int,
            knowledge_point: Optional[str] = None,
            resource_id: Optional[int] = None,
    ) -> None:
        """记录答题行为并同步更新实时学习状态"""
        # 记录行为日志
        await BehaviorTracker.log(
            user_id=user_id,
            behavior_type=BehaviorType.COMPLETE_QUIZ,
            resource_id=resource_id,
            resource_type="quiz",
            knowledge_point=knowledge_point,
            duration_seconds=response_time_ms // 1000,
            extra_data={"is_correct": is_correct, "session_id": session_id},
        )
        # 同步更新实时学习状态
        try:
            engine = _get_real_time_engine()
            engine.update_state_with_answer(user_id, session_id, is_correct, response_time_ms)
        except Exception as e:
            logger.warning(f"⚠️ 实时状态更新失败（不影响行为记录）: {e}")

    @staticmethod
    async def get_user_behaviors(
            user_id: int,
            behavior_type: Optional[BehaviorType] = None,
            days: int = DEFAULT_BEHAVIOR_DAYS,
            limit: int = DEFAULT_BEHAVIOR_LIMIT,
    ) -> List[BehaviorLog]:
        """查询用户近期行为日志"""
        from sqlalchemy import select
        async with AsyncSessionLocal() as session:
            stmt = select(BehaviorLog).where(BehaviorLog.user_id == user_id)

            if days > 0:
                since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
                stmt = stmt.where(BehaviorLog.created_at >= since)

            if behavior_type:
                type_value = behavior_type.value if isinstance(behavior_type, BehaviorType) else behavior_type
                stmt = stmt.where(BehaviorLog.behavior_type == type_value)

            stmt = stmt.order_by(BehaviorLog.created_at.desc()).limit(limit)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    @staticmethod
    async def get_user_stats(user_id: int, days: int = STATS_AGGREGATION_DAYS) -> Dict[str, Any]:
        """
        获取用户学习统计摘要，供 evaluation_agent 使用
        """
        behaviors = await BehaviorTracker.get_user_behaviors(user_id, days=days, limit=STATS_AGGREGATION_LIMIT)
        stats = {
            "total_study_hours": 0.0,
            "resources_viewed": 0,
            "quizzes_completed": 0,
            "questions_asked": 0,
            "points_studied": [],
            "study_days": 0,
            "question_by_point": {},
        }
        seen_points = set()
        study_dates = set()
        for b in behaviors:
            if b.duration_seconds:
                stats["total_study_hours"] += b.duration_seconds / SECONDS_PER_HOUR
            if b.created_at:
                study_dates.add(b.created_at.date())
            if b.behavior_type == BehaviorType.VIEW_RESOURCE.value:
                stats["resources_viewed"] += 1
            elif b.behavior_type == BehaviorType.COMPLETE_QUIZ.value:
                stats["quizzes_completed"] += 1
            elif b.behavior_type == BehaviorType.ASK_QUESTION.value:
                stats["questions_asked"] += 1
                if b.knowledge_point:
                    stats["question_by_point"][b.knowledge_point] = (
                        stats["question_by_point"].get(b.knowledge_point, 0) + 1
                    )
            if b.knowledge_point and b.knowledge_point not in seen_points:
                seen_points.add(b.knowledge_point)
                stats["points_studied"].append(b.knowledge_point)
        stats["total_study_hours"] = round(stats["total_study_hours"], 1)
        stats["study_days"] = len(study_dates)
        return stats


# ------------------------------
# 4. 全局单例
# ------------------------------
behavior_tracker = BehaviorTracker()