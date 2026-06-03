"""
用户画像模型（软件杯A3赛题 v3 统筹版）
- ✅ 7个教育场景核心维度（满足赛题≥6要求）
- ✅ 完全适配 SQLite + SQLAlchemy 2.0 异步架构
- ✅ 数据库层面 CheckConstraint 约束，保证数据合法性
- ✅ 与 User 模型共享主键，关系使用 selectin 加载优化
- ✅ 字段定义与 profile_agent 输出 JSON 严格对应（见下方注释）
"""
from __future__ import annotations
from typing import Optional, List, TYPE_CHECKING
from datetime import datetime

from sqlalchemy import (
    Integer, String, DateTime, ForeignKey, JSON, Boolean, Float,
    CheckConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base

if TYPE_CHECKING:
    from models.user import User


class UserProfile(Base):
    __tablename__ = "user_profiles"
    __table_args__ = (
        CheckConstraint(
            "knowledge_level IN ('beginner', 'intermediate', 'advanced')",
            name="ck_profile_knowledge_level"
        ),
        CheckConstraint(
            "learning_style IN ('visual', 'auditory', 'kinesthetic', 'mixed')",
            name="ck_profile_learning_style"
        ),
        CheckConstraint(
            "learning_goal IN ('exam', 'interest', 'employment', 'competition')",
            name="ck_profile_learning_goal"
        ),
        CheckConstraint(
            "duration_preference IN ('short', 'medium', 'long')",
            name="ck_profile_duration_preference"
        ),
        CheckConstraint(
            "motivation_level IN ('high', 'medium', 'low')",
            name="ck_profile_motivation_level"
        ),
        {"comment": "用户画像表（7个教育场景核心维度 + 随学随新字段）"}
    )

    # ------------------------------
    # 主键（共享 users.id）
    # ------------------------------
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        comment="关联用户表主键"
    )

    # ------------------------------
    # 7 个核心画像维度（与 profile_agent 输出字段完全一致）
    # ------------------------------
    # 1. 编程基础水平
    knowledge_level: Mapped[str] = mapped_column(
        String(20),
        default="beginner",
        server_default="'beginner'",
        nullable=False,
        comment="beginner / intermediate / advanced"
    )

    # 2. 主导学习风格
    learning_style: Mapped[str] = mapped_column(
        String(20),
        default="mixed",
        server_default="'mixed'",
        nullable=False,
        comment="visual / auditory / kinesthetic / mixed"
    )

    # 3. 核心学习目标
    learning_goal: Mapped[str] = mapped_column(
        String(20),
        default="interest",
        server_default="'interest'",
        nullable=False,
        comment="exam / interest / employment / competition"
    )

    # 4. 单次学习时长偏好（新增，影响资源切分粒度）
    duration_preference: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        server_default="'medium'",
        nullable=False,
        comment="short(10-15min) / medium(30-45min) / long(1h+)"
    )

    # 5. 薄弱知识点列表
    weak_points: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        server_default="'[]'",
        nullable=False,
        comment="JSON数组，如 ['循环', '函数']"
    )

    # 6. 已掌握知识点列表
    mastered_points: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        server_default="'[]'",
        nullable=False,
        comment="JSON数组，如 ['变量', '数据类型']"
    )

    # 7. 当前学习动力水平
    motivation_level: Mapped[str] = mapped_column(
        String(20),
        default="medium",
        server_default="'medium'",
        nullable=False,
        comment="high / medium / low"
    )

    # ------------------------------
    # 「随学随新」辅助字段
    # ------------------------------
    current_topic: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="当前正在学习的知识点（用于路径追踪）"
    )
    last_study_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,  # SQLite 不支持 timezone，已移除
        nullable=True,
        comment="最近一次学习时间（UTC）"
    )

    # ------------------------------
    # 时间戳（与 User 模型风格统一，无时区）
    # ------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="画像创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=func.now(),
        nullable=True,
        comment="画像最后更新时间（随学随新自动更新）"
    )

    # ------------------------------
    # 软删除标志
    # ------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",
        nullable=False,
        comment="是否激活（False 表示软删除）"
    )

    # ------------------------------
    # 关系
    # ------------------------------
    user: Mapped["User"] = relationship(
        "User",
        back_populates="profile",
        lazy="selectin"
    )

    # ------------------------------
    # 调试方法
    # ------------------------------
    def __repr__(self) -> str:
        return (
            f"<UserProfile(user_id={self.user_id}, "
            f"level={self.knowledge_level}, goal={self.learning_goal})>"
        )


class ProfileChangeLog(Base):
    """画像变更日志，记录每次画像更新的字段变化"""
    __tablename__ = "profile_change_logs"
    __table_args__ = (
        {"comment": "用户画像变更日志表"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    changed_fields: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="变更的字段和新旧值"
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="api",
        comment="变更来源: llm / evaluation / api"
    )
    raw_llm_output: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="LLM 原始输出（仅 source=llm 时记录）"
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True, comment="LLM 信心度（仅 source=llm 时记录）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )