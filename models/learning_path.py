"""
models/learning_path.py - 学习路径数据模型（软件杯A3赛题核心功能）
- SQLAlchemy 2.0 Mapped 风格，与项目现有模型 100% 一致
- 三表设计：LearningPath（路径）→ LearningPathNode（节点）→ LearningPathNodeResource（资源）
- 支持同一用户多条路径（不同学习方向）
- 节点状态驱动的动态更新机制
- 资源与节点深度绑定，支持多类型资源（doc/quiz/mindmap/code/video）
- SQLite 完全兼容：无时区 DateTime，布尔字段使用 Integer 存储
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, UTC
import logging

from sqlalchemy import (
    Integer, String, Float, Text, DateTime, Boolean, ForeignKey, JSON,
    CheckConstraint, UniqueConstraint, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.database import Base

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from models.user import User


# ============================================================
# 1. 学习路径主表
# ============================================================
class LearningPath(Base):
    __tablename__ = "learning_paths"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'archived')",
            name="ck_learning_path_status"
        ),
        Index("idx_learning_path_user_status", "user_id", "status"),
        Index("idx_learning_path_user_updated", "user_id", "updated_at"),
        {"comment": "学习路径主表：一个用户可有多条路径（不同方向）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="路径唯一ID"
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="关联用户ID"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="路径标题（如：Python基础学习路径）"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="路径描述"
    )
    goal: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="学习目标（如：掌握Python基础语法）"
    )
    topic: Mapped[str] = mapped_column(
        String(100), nullable=False, default="Python基础",
        server_default="'Python基础'", comment="路径主题/方向"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="'active'",
        index=True, comment="路径状态：active/paused/completed/archived"
    )
    total_nodes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="总节点数"
    )
    completed_nodes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="已完成节点数"
    )
    total_estimated_time: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="总预计学习时长（分钟）"
    )
    progress_percent: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="整体进度百分比（0-100）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True, comment="最后更新时间"
    )

    # 关系
    nodes: Mapped[List["LearningPathNode"]] = relationship(
        "LearningPathNode", back_populates="learning_path",
        cascade="all, delete-orphan", lazy="selectin",
        order_by="LearningPathNode.order"
    )

    def update_progress(self) -> None:
        """根据节点完成情况更新进度"""
        if self.total_nodes > 0:
            self.progress_percent = round(
                (self.completed_nodes / self.total_nodes) * 100, 1
            )
        else:
            self.progress_percent = 0.0
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "goal": self.goal,
            "topic": self.topic,
            "status": self.status,
            "total_nodes": self.total_nodes,
            "completed_nodes": self.completed_nodes,
            "total_estimated_time": self.total_estimated_time,
            "progress_percent": self.progress_percent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "nodes": [n.to_dict() for n in (self.nodes or [])],
        }

    def __repr__(self) -> str:
        return (
            f"<LearningPath(id={self.id}, user={self.user_id}, "
            f"title={self.title!r}, progress={self.progress_percent}%)>"
        )


# ============================================================
# 2. 学习路径节点表
# ============================================================
class LearningPathNode(Base):
    __tablename__ = "learning_path_nodes"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed', 'needs_review', 'skipped')",
            name="ck_lp_node_status"
        ),
        CheckConstraint(
            "mastery >= 0 AND mastery <= 1",
            name="ck_lp_node_mastery_range"
        ),
        CheckConstraint(
            "difficulty >= 0 AND difficulty <= 1",
            name="ck_lp_node_difficulty_range"
        ),
        CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_lp_node_progress_range"
        ),
        UniqueConstraint("learning_path_id", "knowledge_point", name="uq_path_knowledge_point"),
        Index("idx_lp_node_path_order", "learning_path_id", "order"),
        Index("idx_lp_node_status", "learning_path_id", "status"),
        {"comment": "学习路径节点表：每个节点对应一个知识点"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="节点唯一ID"
    )
    learning_path_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_paths.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属路径ID"
    )
    knowledge_point: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="知识点名称（与PYTHON_KNOWLEDGE_POINTS一致）"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="节点描述/学习目标"
    )
    order: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="节点在路径中的顺序（从1开始）"
    )
    prerequisites: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="'[]'",
        comment="前置知识点列表（JSON数组）"
    )
    difficulty: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5",
        comment="知识点难度（0-1）"
    )
    estimated_time: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, server_default="15",
        comment="预计学习时长（分钟）"
    )
    mastery_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.7, server_default="0.7",
        comment="掌握度阈值（达到此值视为掌握）"
    )
    mastery: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="当前掌握度（0-1，基于测验/练习计算）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_started",
        server_default="'not_started'", index=True,
        comment="节点状态：not_started/in_progress/completed/needs_review/skipped"
    )
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="节点学习进度（0-100）"
    )
    node_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="'new'",
        comment="节点类型：new（新学）/review（复习）"
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="开始学习时间"
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="完成时间"
    )
    last_study_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最后学习时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )

    # 关系
    learning_path: Mapped["LearningPath"] = relationship(
        "LearningPath", back_populates="nodes"
    )
    resources: Mapped[List["LearningPathNodeResource"]] = relationship(
        "LearningPathNodeResource", back_populates="node",
        cascade="all, delete-orphan", lazy="selectin"
    )

    def mark_started(self) -> None:
        """标记节点开始学习"""
        if self.status == "not_started":
            self.status = "in_progress"
            self.started_at = datetime.now(UTC).replace(tzinfo=None)
        self.last_study_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_completed(self) -> None:
        """标记节点完成"""
        self.status = "completed"
        self.progress = 100.0
        self.mastery = max(self.mastery, self.mastery_threshold)
        self.completed_at = datetime.now(UTC).replace(tzinfo=None)
        self.last_study_at = self.completed_at

    def mark_needs_review(self) -> None:
        """标记节点需要复习"""
        self.status = "needs_review"
        self.last_study_at = datetime.now(UTC).replace(tzinfo=None)

    def update_mastery(self, new_mastery: float) -> None:
        """更新掌握度（取历史最高，避免退步）"""
        self.mastery = max(self.mastery, min(1.0, max(0.0, new_mastery)))
        self.last_study_at = datetime.now(UTC).replace(tzinfo=None)
        if self.mastery >= self.mastery_threshold and self.status != "completed":
            self.mark_completed()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "learning_path_id": self.learning_path_id,
            "knowledge_point": self.knowledge_point,
            "description": self.description,
            "order": self.order,
            "prerequisites": self.prerequisites or [],
            "difficulty": self.difficulty,
            "estimated_time": self.estimated_time,
            "mastery_threshold": self.mastery_threshold,
            "mastery": self.mastery,
            "status": self.status,
            "progress": self.progress,
            "node_type": self.node_type,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_study_at": self.last_study_at.isoformat() if self.last_study_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resources": [r.to_dict() for r in (self.resources or [])],
        }

    def __repr__(self) -> str:
        return (
            f"<LearningPathNode(id={self.id}, kp={self.knowledge_point!r}, "
            f"status={self.status!r}, mastery={self.mastery})>"
        )


# ============================================================
# 3. 路径节点资源关联表
# ============================================================
class LearningPathNodeResource(Base):
    __tablename__ = "learning_path_node_resources"
    __table_args__ = (
        CheckConstraint(
            "resource_type IN ('doc', 'quiz', 'mindmap', 'code', 'video')",
            name="ck_lp_resource_type"
        ),
        CheckConstraint(
            "status IN ('pending', 'generating', 'completed', 'failed')",
            name="ck_lp_resource_status"
        ),
        Index("idx_lp_resource_node_type", "node_id", "resource_type"),
        {"comment": "学习路径节点资源关联表：每个节点可关联多种类型资源"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="资源关联ID"
    )
    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("learning_path_nodes.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属节点ID"
    )
    resource_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="资源类型：doc/quiz/mindmap/code/video"
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="资源标题"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="资源描述"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="资源内容（文本类资源直接存储）"
    )
    resource_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="SET NULL"),
        nullable=True, comment="关联的全局资源ID（复用resources表）"
    )
    duration: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="预计时长（分钟）"
    )
    difficulty: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5",
        comment="资源难度（0-1）"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="'pending'",
        comment="资源状态：pending/generating/completed/failed"
    )
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="扩展元数据"
    )
    is_cached: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False,
        comment="是否已缓存（已生成过的资源可复用）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关系
    node: Mapped["LearningPathNode"] = relationship(
        "LearningPathNode", back_populates="resources"
    )

    def mark_generating(self) -> None:
        self.status = "generating"

    def mark_completed(self, content: Optional[str] = None) -> None:
        self.status = "completed"
        self.is_cached = True
        if content is not None:
            self.content = content
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def mark_failed(self) -> None:
        self.status = "failed"
        self.updated_at = datetime.now(UTC).replace(tzinfo=None)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "node_id": self.node_id,
            "resource_type": self.resource_type,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "resource_id": self.resource_id,
            "duration": self.duration,
            "difficulty": self.difficulty,
            "status": self.status,
            "extra_metadata": self.extra_metadata,
            "is_cached": self.is_cached,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<LearningPathNodeResource(id={self.id}, node={self.node_id}, "
            f"type={self.resource_type!r}, status={self.status!r})>"
        )
