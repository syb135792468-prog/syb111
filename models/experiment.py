"""
models/experiment.py - A/B 测试实验模型
- experiments: 实验定义（名称、变体配置、流量分配）
- experiment_assignments: 用户分组记录（确定性哈希）
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import (
    Integer, Float, String, Text, DateTime, ForeignKey,
    UniqueConstraint, Index, func, JSON
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        Index("idx_experiment_status", "status"),
        {"comment": "A/B 测试实验表"}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    variants: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    traffic_allocation: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "variants": self.variants,
            "traffic_allocation": self.traffic_allocation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ExperimentAssignment(Base):
    __tablename__ = "experiment_assignments"
    __table_args__ = (
        UniqueConstraint("experiment_id", "user_id", name="uq_exp_assignment"),
        Index("idx_exp_assign_user", "user_id"),
        Index("idx_exp_assign_exp_variant", "experiment_id", "variant"),
        {"comment": "实验分组记录表"}
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    variant: Mapped[str] = mapped_column(String(50), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "experiment_id": self.experiment_id,
            "user_id": self.user_id,
            "variant": self.variant,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
        }
