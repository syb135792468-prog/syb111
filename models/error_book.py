"""
models/error_book.py - 错题本数据模型
- 自动收录答错的题目
- 支持按知识点/难度筛选
- 支持标记已掌握
- 艾宾浩斯遗忘曲线复习调度（SM-2 算法）
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime, UTC

from sqlalchemy import (
    Integer, Float, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ErrorBook(Base):
    __tablename__ = "error_book"
    __table_args__ = (
        UniqueConstraint("user_id", "resource_id", "question_index", name="uq_error_book_question"),
        Index("idx_error_book_user_kp", "user_id", "knowledge_point"),
        Index("idx_error_book_user_mastered", "user_id", "mastered"),
        Index("idx_error_book_next_review", "user_id", "next_review_at"),
        {"comment": "错题本表"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"), nullable=True
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    question_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    question_type: Mapped[str] = mapped_column(String(20), nullable=False, default="choice")
    user_answer: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    correct_answer: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_point: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    error_type: Mapped[Optional[str]] = mapped_column(
        String(40),
        nullable=True,
        default=None,
        comment="错因类型: syntax_error/type_confusion/scope_confusion/boundary_error/concept_misunderstanding/api_misuse/logic_error/other"
    )
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_wrong_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    mastered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # SM-2 间隔重复字段
    next_review_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_interval_days: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    easiness_factor: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    repetition_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "resource_id": self.resource_id,
            "question_index": self.question_index,
            "question_text": self.question_text,
            "question_type": self.question_type,
            "user_answer": self.user_answer,
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "knowledge_point": self.knowledge_point,
            "difficulty": self.difficulty,
            "error_type": self.error_type,
            "error_count": self.error_count,
            "last_wrong_at": self.last_wrong_at.isoformat() if self.last_wrong_at else None,
            "mastered": self.mastered,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "next_review_at": self.next_review_at.isoformat() if self.next_review_at else None,
            "review_interval_days": self.review_interval_days,
            "easiness_factor": round(self.easiness_factor, 2),
            "repetition_count": self.repetition_count,
        }
