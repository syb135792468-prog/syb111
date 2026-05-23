"""
用户基础模型（软件杯A3赛题专用优化版 v3）
- ✅ 支持用户名+密码登录（bcrypt 哈希）
- ✅ 异步适配：使用数据库层面时间生成，避免时区/异步陷阱
- ✅ 性能优化：关系加载使用 selectin，避免 N+1 查询
- ✅ SQLite 兼容：DateTime 字段不强制 timezone，改用无时区时间戳
- ✅ 评审友好：完整注释 + 软删除预留 + 调试友好方法
"""
from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base

if TYPE_CHECKING:
    from models.profile import UserProfile
    from models.resource import Resource


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"comment": "软件杯A3赛题用户基本信息表"}

    # ------------------------------
    # 1. 核心标识字段
    # ------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
        comment="用户唯一自增ID"
    )
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
        comment="用户唯一标识（演示可用固定值如 'learner_001'）"
    )
    password_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="密码哈希值（bcrypt）"
    )

    # ------------------------------
    # 2. 时间戳字段（SQLite 友好：无时区，数据库生成默认值）
    # ------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime,  # SQLite 不支持 timezone=True，此处移除
        server_default=func.now(),  # 插入时由数据库生成当前时间
        nullable=False,
        comment="用户创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=func.now(),  # 仅更新时自动刷新
        nullable=True,
        comment="用户信息最后更新时间"
    )

    # ------------------------------
    # 3. 软删除标志
    # ------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",  # SQLite 中布尔值存为 0/1
        nullable=False,
        comment="账户激活状态（False 表示软删除）"
    )

    # ------------------------------
    # 4. 关联关系（性能优化：selectin 异步批量加载）
    # ------------------------------
    profile: Mapped[Optional["UserProfile"]] = relationship(
        "UserProfile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    resources: Mapped[List["Resource"]] = relationship(
        "Resource",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # ------------------------------
    # 5. 调试方法
    # ------------------------------
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username!r}, active={self.is_active})>"