"""
models/daily_challenge.py - 每日一题挑战记录模型
- 每个用户每天最多一题
- 记录答题结果，配合火花(streak)系统
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from sqlalchemy import (
    Integer, String, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class DailyChallenge(Base):
    __tablename__ = "daily_challenges"
    __table_args__ = (
        UniqueConstraint("user_id", "challenge_date", name="uq_user_daily_challenge"),
        Index("idx_daily_user_date", "user_id", "challenge_date"),
        {"comment": "每日一题挑战记录表"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    challenge_date: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="挑战日期 YYYY-MM-DD"
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False,
        comment="关联的题目资源ID"
    )
    is_correct: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True,
        comment="是否答对（未作答为None）"
    )
    user_answer: Mapped[Optional[str]] = mapped_column(
        String(2000), nullable=True,
        comment="用户提交的答案"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True,
        comment="完成时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
