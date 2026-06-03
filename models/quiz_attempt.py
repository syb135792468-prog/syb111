"""
models/quiz_attempt.py - 答题记录数据模型
- 记录用户每次答题的详细信息
- 支持自适应难度计算
- 支持错题本自动收录
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime, UTC

from sqlalchemy import (
    Integer, String, Float, Boolean, DateTime, ForeignKey,
    CheckConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('choice', 'fill', 'code')",
            name="ck_quiz_attempt_type_valid"
        ),
        CheckConstraint(
            "score >= 0 AND score <= 10",
            name="ck_quiz_attempt_score_range"
        ),
        Index("idx_attempt_user_kp", "user_id", "knowledge_point"),
        Index("idx_attempt_user_time", "user_id", "created_at"),
        Index("idx_attempt_resource", "resource_id", "question_index"),
        {"comment": "用户答题记录表"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=False
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_type: Mapped[str] = mapped_column(String(20), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    knowledge_point: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    user_answer: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    correct_answer: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    spent_time: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="作答耗时(秒)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "question_index": self.question_index,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "knowledge_point": self.knowledge_point,
            "user_answer": self.user_answer,
            "correct_answer": self.correct_answer,
            "is_correct": self.is_correct,
            "score": self.score,
            "spent_time": self.spent_time,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
