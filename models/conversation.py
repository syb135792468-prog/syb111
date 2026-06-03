"""
对话会话模型 - 每个用户可以有多个对话
"""
from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base
from config.constants import DEFAULT_CONVERSATION_TITLE

if TYPE_CHECKING:
    from models.chat_message import ChatMessage


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = {"comment": "对话会话表"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="会话ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False,
        comment="所属用户ID"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default=DEFAULT_CONVERSATION_TITLE, comment="会话标题"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False, comment="最后更新时间"
    )

    messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="conversation",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="ChatMessage.created_at"
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, user_id={self.user_id}, title={self.title!r})>"
