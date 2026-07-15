"""
models/knowledge_graph.py - Python 知识图谱数据模型

设计原则：
- 全局目录与用户状态分层：knowledge_nodes / knowledge_edges 是共享真相
- 用户掌握状态投影其上：user_knowledge_mastery / knowledge_mastery_evidence
- 证据不可变，掌握度可重算（保留评分规则可调整空间）
- 用稳定 string code 关联，便于跨环境迁移和重建

5 张表：
1. knowledge_nodes - 全局知识点目录（节点）
2. knowledge_edges - 有向依赖关系（边）
3. user_knowledge_mastery - 用户每节点掌握状态
4. knowledge_mastery_evidence - 不可变掌握证据
5. question_knowledge_map - 题目到知识点的多对多映射
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from datetime import datetime, UTC

from sqlalchemy import (
    Integer, String, Float, Text, DateTime, Boolean, ForeignKey, JSON,
    CheckConstraint, UniqueConstraint, Index, func, text
)
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


# ============================================================
# 1. 全局知识点目录
# ============================================================
class KnowledgeNode(Base):
    __tablename__ = "knowledge_nodes"
    __table_args__ = (
        CheckConstraint(
            "level IN (1, 2, 3)",
            name="ck_knode_level"
        ),
        CheckConstraint(
            "difficulty >= 0 AND difficulty <= 1",
            name="ck_knode_difficulty_range"
        ),
        CheckConstraint(
            "mastery_threshold >= 0 AND mastery_threshold <= 100",
            name="ck_knode_threshold_range"
        ),
        Index("idx_knode_module_level", "module", "level"),
        {"comment": "Python全局知识点目录（共享真相）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    code: Mapped[str] = mapped_column(
        String(60), unique=True, nullable=False, index=True,
        comment="稳定 string ID，如 py_list_basic"
    )
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="中文显示名"
    )
    module: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True,
        comment="所属模块：basics/datatypes/control_flow/functions/data_structures/file_exception/modules/oop/advanced"
    )
    level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
        comment="层级 1=基础 2=进阶 3=高级"
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="节点描述/学习目标"
    )
    difficulty: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.3, server_default="0.3",
        comment="难度 0-1"
    )
    estimated_time: Mapped[int] = mapped_column(
        Integer, nullable=False, default=15, server_default="15",
        comment="预计学习时长（分钟）"
    )
    mastery_threshold: Mapped[float] = mapped_column(
        Float, nullable=False, default=50.0, server_default="50.0",
        comment="掌握度阈值 0-100，达到即视为已掌握"
    )
    aliases: Mapped[List[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="'[]'",
        comment="别名 JSON 数组，用于 name-based 回退匹配"
    )
    is_active: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
        comment="是否启用（0=下线，不展示）"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "module": self.module,
            "level": self.level,
            "description": self.description,
            "difficulty": self.difficulty,
            "estimated_time": self.estimated_time,
            "mastery_threshold": self.mastery_threshold,
            "aliases": self.aliases or [],
            "is_active": bool(self.is_active),
        }


# ============================================================
# 2. 知识点依赖边（有向图）
# ============================================================
class KnowledgeEdge(Base):
    __tablename__ = "knowledge_edges"
    __table_args__ = (
        CheckConstraint(
            "edge_type IN ('prerequisite', 'contains', 'related')",
            name="ck_kedge_type"
        ),
        CheckConstraint(
            "source_code != target_code",
            name="ck_kedge_no_self_loop"
        ),
        UniqueConstraint(
            "source_code", "target_code", "edge_type",
            name="uq_kedge_source_target_type"
        ),
        Index("idx_kedge_target", "target_code", "edge_type"),
        Index("idx_kedge_source", "source_code", "edge_type"),
        {"comment": "知识点依赖边（有向）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    source_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="前置节点 code"
    )
    target_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="后续节点 code"
    )
    edge_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="prerequisite", server_default="'prerequisite'",
        comment="边类型：prerequisite=前置 / contains=包含 / related=相关"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_code": self.source_code,
            "target_code": self.target_code,
            "edge_type": self.edge_type,
        }


# ============================================================
# 3. 用户每节点掌握状态
# ============================================================
class UserKnowledgeMastery(Base):
    __tablename__ = "user_knowledge_mastery"
    __table_args__ = (
        CheckConstraint(
            "mastery_score >= 0 AND mastery_score <= 100",
            name="ck_ukm_score_range"
        ),
        CheckConstraint(
            "state IN ('locked', 'available', 'learning', 'mastered')",
            name="ck_ukm_state"
        ),
        CheckConstraint(
            "evidence_count >= 0",
            name="ck_ukm_evidence_non_negative"
        ),
        CheckConstraint(
            "posterior >= 0 AND posterior <= 1",
            name="ck_ukm_posterior_range"
        ),
        CheckConstraint(
            "uncertainty >= 0 AND uncertainty <= 1",
            name="ck_ukm_uncertainty_range"
        ),
        CheckConstraint(
            "review_risk >= 0 AND review_risk <= 1",
            name="ck_ukm_review_risk_range"
        ),
        UniqueConstraint("user_id", "node_code", name="uq_ukm_user_node"),
        Index("idx_ukm_user_state", "user_id", "state"),
        Index("idx_ukm_user_node", "user_id", "node_code"),
        {"comment": "用户每知识点掌握状态（4 态：locked/available/learning/mastered）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    node_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="关联知识点 code"
    )
    mastery_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="掌握度 0-100（派生字段 = posterior*100，前端兼容）"
    )
    posterior: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="内部掌握概率 0-1（真相字段）"
    )
    uncertainty: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.9, server_default="0.9",
        comment="不确定度 0-1，新节点高不确定"
    )
    last_verified: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近一次被强证据验证的时间"
    )
    review_risk: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0.0",
        comment="复习风险 0-1（阶段5时间衰减用，本批置0）"
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="available", server_default="'available'",
        comment="状态：locked=前置未满足 / available=可学习 / learning=学习中 / mastered=已掌握"
    )
    evidence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="累计证据数"
    )
    quiz_correct_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="测验答对次数（用于 70% 正确率维度）"
    )
    quiz_total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="测验总答题次数"
    )
    code_practice_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="代码实践成功次数（用于 30% 代码维度）"
    )
    last_evidence_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最近一次证据时间"
    )
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False,
        comment="掌握度最近计算时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "node_code": self.node_code,
            "mastery_score": self.mastery_score,
            "posterior": self.posterior,
            "uncertainty": self.uncertainty,
            "last_verified": self.last_verified.isoformat() if self.last_verified else None,
            "review_risk": self.review_risk,
            "state": self.state,
            "evidence_count": self.evidence_count,
            "quiz_correct_count": self.quiz_correct_count,
            "quiz_total_count": self.quiz_total_count,
            "code_practice_count": self.code_practice_count,
            "last_evidence_at": self.last_evidence_at.isoformat() if self.last_evidence_at else None,
            "calculated_at": self.calculated_at.isoformat() if self.calculated_at else None,
        }


# ============================================================
# 4. 不可变掌握证据
# ============================================================
class KnowledgeMasteryEvidence(Base):
    __tablename__ = "knowledge_mastery_evidence"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('quiz_attempt', 'path_node', 'code_run', 'review', 'manual', 'chat_judge')",
            name="ck_kme_source_type"
        ),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_kme_score_range"
        ),
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_kme_weight_range"
        ),
        CheckConstraint(
            "signal_type IN ('direct', 'inferred')",
            name="ck_kme_signal_type"
        ),
        CheckConstraint(
            "source_weight >= 0 AND source_weight <= 1",
            name="ck_kme_source_weight_range"
        ),
        Index("idx_kme_user_node", "user_id", "node_code", "created_at"),
        Index("idx_kme_source", "source_type", "source_id"),
        # 部分唯一索引：仅约束有 source_id 的自动事件，实现幂等去重
        # （manual/review 等 source_id 为 NULL 的事件不受约束，可多条共存）
        Index(
            "uq_kme_user_node_source",
            "user_id", "node_code", "source_type", "source_id",
            unique=True,
            sqlite_where=text("source_id IS NOT NULL"),
            postgresql_where=text("source_id IS NOT NULL"),
        ),
        {"comment": "不可变掌握证据（一次写入永不修改，支持掌握度重算）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    node_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="关联知识点 code"
    )
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="来源类型：quiz_attempt/path_node/code_run/review/manual"
    )
    source_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="来源记录 ID（如 quiz_attempts.id），可空（如手动评分）"
    )
    score: Mapped[float] = mapped_column(
        Float, nullable=False,
        comment="本次证据得分 0-100"
    )
    weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0",
        comment="该证据对节点的权重 0-1（一题对应多节点时按权重分摊）"
    )
    detail: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True,
        comment="附加信息（题目类型、难度、知识点覆盖等）"
    )
    signal_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="direct", server_default="direct",
        comment="direct=直接证据 / inferred=图谱推断（阶段4）"
    )
    source_weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0",
        comment="证据质量权重=difficulty_weight*hint_penalty*copy_penalty"
    )
    difficulty: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True,
        comment="题目难度 easy/medium/hard"
    )
    weak_signal: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="弱信号标记：1=单次代码异常不降posterior，0=正常证据"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "node_code": self.node_code,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "score": self.score,
            "weight": self.weight,
            "detail": self.detail,
            "signal_type": self.signal_type,
            "source_weight": self.source_weight,
            "difficulty": self.difficulty,
            "weak_signal": self.weak_signal,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================
# 5. 题目-知识点映射（一题对多节点）
# ============================================================
class QuestionKnowledgeMap(Base):
    __tablename__ = "question_knowledge_map"
    __table_args__ = (
        CheckConstraint(
            "weight >= 0 AND weight <= 1",
            name="ck_qkm_weight_range"
        ),
        UniqueConstraint(
            "resource_id", "question_index", "node_code",
            name="uq_qkm_res_qidx_node"
        ),
        Index("idx_qkm_resource_qidx", "resource_id", "question_index"),
        Index("idx_qkm_node", "node_code"),
        {"comment": "题目到知识点映射（一题可考察多知识点，含权重）"}
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("resources.id", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="关联资源 ID（题目所属资源）"
    )
    question_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
        comment="题目在资源中的序号（0-based）"
    )
    node_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="关联知识点 code"
    )
    weight: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0, server_default="1.0",
        comment="该题对该知识点的考察权重 0-1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "question_index": self.question_index,
            "node_code": self.node_code,
            "weight": self.weight,
        }


# ============================================================
# 6. 用户知识点误解记录（与掌握状态共存，不影响 posterior）
# ============================================================
class UserMisconception(Base):
    __tablename__ = "user_misconceptions"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_umis_confidence"
        ),
        Index("idx_umis_user_node", "user_id", "node_code", "resolved"),
        {"comment": "用户知识点误解记录（与掌握状态共存，不影响posterior）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    node_code: Mapped[str] = mapped_column(
        String(60), ForeignKey("knowledge_nodes.code", ondelete="CASCADE"),
        nullable=False, index=True,
        comment="关联知识点 code"
    )
    misconception_text: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="误解描述"
    )
    trigger_evidence_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="触发证据ID（不建FK，证据永删）"
    )
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.5, server_default="0.5",
        comment="置信度 0-1，疑似=0.5"
    )
    resolved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
        comment="是否已纠偏"
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="纠偏时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "node_code": self.node_code,
            "misconception_text": self.misconception_text,
            "trigger_evidence_id": self.trigger_evidence_id,
            "confidence": self.confidence,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
