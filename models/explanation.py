"""
models/explanation.py - 消息详解记录表
- 与 ChatMessage 强绑定，作为主对话消息的附属注解
- 支持追问（follow_ups JSON 数组）
- 随会话一同保存和切换
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, UTC

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, JSON, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class Explanation(Base):
    __tablename__ = "explanations"
    __table_args__ = (
        Index("idx_explanation_conversation", "conversation_id", "created_at"),
        Index("idx_explanation_message", "message_id"),
        {"comment": "消息详解记录表：绑定到具体消息的解释内容"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="详解ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属用户ID"
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True, index=True, comment="所属会话ID"
    )
    message_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"),
        nullable=True, comment="绑定的消息ID"
    )
    selected_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="被解释的原文"
    )
    explanation: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI生成的解释内容"
    )
    follow_ups: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True, default=list, server_default="'[]'",
        comment="追问记录 [{question, answer, created_at}]"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True, comment="最后更新时间"
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "selected_text": self.selected_text,
            "explanation": self.explanation,
            "follow_ups": self.follow_ups or [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<Explanation(id={self.id}, msg={self.message_id}, "
            f"text={self.selected_text[:20]!r}...)>"
        )
