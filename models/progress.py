"""
models/progress.py - 学习进度数据模型
- SQLAlchemy 2.0 Mapped 风格
- 完整数据库级约束
- 软删除支持
- 唯一约束：同一用户同一知识点仅一条记录
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC

from sqlalchemy import (
    Integer, String, Float, DateTime, Boolean, ForeignKey,
    CheckConstraint, UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class LearningProgress(Base):
    __tablename__ = "learning_progress"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed', 'failed')",
            name="ck_progress_status"
        ),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="ck_progress_score_range"
        ),
        CheckConstraint(
            "duration >= 0",
            name="ck_progress_duration_non_negative"
        ),
        UniqueConstraint("user_id", "topic", name="uq_user_topic"),
        Index("idx_progress_user_status", "user_id", "status"),
        Index("idx_progress_user_updated", "user_id", "updated_at"),
        {"comment": "用户知识点学习进度表"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_started", server_default="'not_started'"
    )
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="1", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True
    )

    _STATUS_PRIORITY = {
        "not_started": 0,
        "failed": 1,
        "in_progress": 2,
        "completed": 3,
    }

    def update_progress(
        self,
        status: Optional[str] = None,
        score: Optional[float] = None,
        duration: Optional[int] = None,
        overwrite_duration: bool = False,
    ) -> LearningProgress:
        if status is not None and status in self._STATUS_PRIORITY:
            current_priority = self._STATUS_PRIORITY.get(self.status or "not_started", 0)
            next_priority = self._STATUS_PRIORITY[status]
            if next_priority >= current_priority:
                self.status = status
        if score is not None:
            bounded_score = max(0.0, min(100.0, score))
            self.score = bounded_score if self.score is None else max(self.score, bounded_score)
        if duration is not None and duration >= 0:
            self.duration = duration if overwrite_duration else (self.duration or 0) + duration
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return self

    def mark_completed(self, score: Optional[float] = None) -> LearningProgress:
        return self.update_progress(status="completed", score=score)

    def soft_delete(self) -> LearningProgress:
        self.is_active = False
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "topic": self.topic,
            "status": self.status,
            "score": self.score,
            "duration": self.duration,
            "is_active": self.is_active,
            "created_at": (self.created_at.isoformat() + "Z") if self.created_at else None,
            "updated_at": (self.updated_at.isoformat() + "Z") if self.updated_at else None,
        }
