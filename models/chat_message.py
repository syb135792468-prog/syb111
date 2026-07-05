"""
聊天消息持久化模型
- 按用户隔离聊天记录
- 支持 user/assistant/system 三种角色
- 按 conversation 分组
"""
from __future__ import annotations
from typing import Optional
from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = {"comment": "聊天消息持久化表"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="消息ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False,
        comment="所属用户ID"
    )
    conversation_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("conversations.id", ondelete="SET NULL"), index=True, nullable=True,
        comment="所属对话ID"
    )
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="消息角色：user/assistant/system"
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="消息内容"
    )
    content_blocks_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="结构化内容块 JSON（content_blocks 架构）"
    )
    image_urls_json: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="用户消息附带的图片URL列表JSON"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )
    is_bookmarked: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False,
        comment="是否已收藏"
    )

    # 关联
    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")
    conversation: Mapped[Optional["Conversation"]] = relationship("Conversation", back_populates="messages", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, user_id={self.user_id}, role={self.role!r})>"
