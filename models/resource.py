"""
资源元数据模型（软件杯A3赛题 v4.0 赛题深度适配版）
- ✅ 全局风格统一：与 user/profile 100%一致的异步 SQLAlchemy 2.0 写法
- ✅ 全局依赖统一：从 config.model_config 导入枚举，禁止硬编码
- ✅ 严格对应赛题：5种核心资源、完善的进度追踪、知识点关联
- ✅ 【新增】RAG深度联动：vector_db_id 直接关联向量库文档
- ✅ 【新增】业务辅助方法：更新进度、添加知识点、标记复用
- ✅ 【新增】常用查询类方法：按类型/知识点/状态快速查询
- ✅ 【新增】资源版本控制：支持资源迭代更新
- ✅ 【新增】唯一约束：避免用户重复创建同名同类型资源
- ✅ SQLite 完全兼容：统一使用无时区 DateTime，布尔字段使用 Integer 存储
- ✅ 更精确的类型注解：Dict[str, Any] 替代 dict，List[str] 替代 list
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
import logging

from sqlalchemy import (
    Integer, String, Text, DateTime, ForeignKey, JSON,
    CheckConstraint, func, Index, Boolean, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# 配置日志
logger = logging.getLogger(__name__)

# 🔴 全局依赖统一：从 config.model_config 导入枚举（需确保该文件已定义）
try:
    from config.model_config import RESOURCE_TYPES, RESOURCE_STATUS
except ImportError:
    # 开发阶段的 fallback，生产环境应确保 config 正确导出
    logger.warning("⚠️  未从 config.model_config 导入枚举，使用默认值")
    RESOURCE_TYPES = ("doc", "quiz", "mindmap", "code", "video", "daily_challenge", "daily_extra", "multimodal")
    RESOURCE_STATUS = ("pending", "processing", "completed", "failed")

from models.database import Base

if TYPE_CHECKING:
    from models.user import User


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (
        # 枚举合法性约束（动态生成，与 config 保持一致）
        CheckConstraint(
            f"resource_type IN {tuple(RESOURCE_TYPES)}",
            name="ck_resource_type_valid"
        ),
        CheckConstraint(
            f"status IN {tuple(RESOURCE_STATUS)}",
            name="ck_resource_status_valid"
        ),
        CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name="ck_progress_percent_range"
        ),
        # 【新增】唯一约束：避免用户重复创建同名同类型资源
        UniqueConstraint(
            "user_id", "title", "resource_type",
            name="uq_user_title_type",
        ),
        # 最左前缀复合索引：优化按用户+状态+类型的常用查询
        Index("idx_resource_user_status_type", "user_id", "status", "resource_type"),
        # 注意：JSON 列在 SQLite 上无法有效建索引，查询使用 json_extract() 函数
        {"comment": "软件杯A3赛题资源元数据表（5种核心资源+进度追踪+RAG联动）"}
    )

    # ------------------------------
    # 1. 基础业务字段
    # ------------------------------
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True,
        autoincrement=True,
        comment="资源唯一自增ID"
    )

    # LangGraph 任务关联（用于状态持久化追踪）
    task_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="关联的 LangGraph 工作流任务 ID（thread_id）"
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联的用户ID"
    )

    # ------------------------------
    # 2. 资源类型（从 config 导入，保证统一）
    # ------------------------------
    resource_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment=f"资源类型：{', '.join(RESOURCE_TYPES)}"
    )

    # ------------------------------
    # 3. 资源内容与存储
    # ------------------------------
    title: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="资源标题/名称"
    )

    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="文本资源内容（doc/quiz/mindmap/code）"
    )

    file_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="大文件存储路径（video）"
    )

    # 【修复】metadata → 改为 extra_metadata（避免冲突）
    extra_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=True,
        comment="""结构化元数据：
        - doc: {"word_count": int, "difficulty": str}
        - quiz: {"answer": str, "explanation": str, "difficulty": str}
        - mindmap: {"nodes": List[Dict], "edges": List[Dict]}
        - code: {"language": str, "run_result": str, "has_error": bool}
        - video: {"duration": int, "thumbnail_path": str}
        - reading: {"source": str, "author": str}
        """
    )

    # ------------------------------
    # 4. 【新增】RAG深度联动字段
    # ------------------------------
    vector_db_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="关联的向量库文档ID（ChromaDB/FAISS的document ID）"
    )

    # ------------------------------
    # 5. 关联知识点（与 profile.weak_points/mastered_points 格式一致）
    # ------------------------------
    knowledge_points: Mapped[List[str]] = mapped_column(
        JSON,
        default=list,
        server_default="'[]'",      # ✅ SQLite 默认空数组
        nullable=False,
        comment="该资源涉及的知识点编码列表（JSON 数组，如：['PY001', 'PY002']）"
    )

    # ------------------------------
    # 6. 【新增】资源版本控制
    # ------------------------------
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
        comment="资源版本号（从1开始，每次更新+1）"
    )

    # ------------------------------
    # 7. 生成进度追踪
    # ------------------------------
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RESOURCE_STATUS[0],   # "pending"
        server_default=f"'{RESOURCE_STATUS[0]}'",
        index=True,
        comment=f"生成状态：{', '.join(RESOURCE_STATUS)}"
    )

    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="生成进度百分比（0-100）"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="生成失败时的错误信息"
    )

    # ------------------------------
    # 8. 资源库标记
    # ------------------------------
    in_library: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",
        nullable=False,
        comment="是否已加入资源库（默认False，用户手动收藏后为True）"
    )

    note: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="用户对该资源的学习笔记"
    )

    # ------------------------------
    # 9. 资源复用标记（加分项）
    # ------------------------------
    is_reusable: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="0",   # SQLite 中布尔存储为 0/1
        nullable=False,
        comment="是否可复用（True=加入公共资源库）"
    )

    # ------------------------------
    # 9. 生命周期管理字段（无时区，与 User/Profile 统一）
    # ------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
        comment="资源创建时间（UTC）"
    )

    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        onupdate=func.now(),
        nullable=True,
        comment="资源最后更新时间"
    )

    # ------------------------------
    # 10. 软删除预留字段
    # ------------------------------
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default="1",   # SQLite 中布尔存储为 0/1
        nullable=False,
        comment="是否激活（False 表示软删除）"
    )

    # ------------------------------
    # 11. 关系（全局风格统一：selectin 优化）
    # ------------------------------
    user: Mapped["User"] = relationship(
        "User",
        back_populates="resources",
        lazy="selectin"
    )

    # ------------------------------
    # 12. 【新增】业务辅助方法
    # ------------------------------
    def add_knowledge_point(self, kp_code: str) -> "Resource":
        """添加知识点编码（自动去重）"""
        if kp_code not in self.knowledge_points:
            self.knowledge_points.append(kp_code)
        return self

    def remove_knowledge_point(self, kp_code: str) -> "Resource":
        """移除知识点编码"""
        if kp_code in self.knowledge_points:
            self.knowledge_points.remove(kp_code)
        return self

    def update_progress(
            self,
            percent: int,
            status: Optional[str] = None,
            error_msg: Optional[str] = None
    ) -> "Resource":
        """
        更新资源生成进度

        Args:
            percent: 进度百分比（0-100）
            status: 状态（可选，不填则根据percent自动判断）
            error_msg: 错误信息（可选，status=failed时必填）
        """
        self.progress_percent = max(0, min(100, percent))

        if status:
            self.status = status
        else:
            # 根据进度自动判断状态
            if self.progress_percent >= 100:
                self.status = "completed"
            elif self.progress_percent > 0:
                self.status = "processing"
            else:
                self.status = "pending"

        if error_msg:
            self.error_message = error_msg
        elif self.status != "failed":
            self.error_message = None

        return self

    def mark_reusable(self) -> "Resource":
        """标记为可复用资源"""
        self.is_reusable = True
        return self

    def mark_unusable(self) -> "Resource":
        """取消可复用标记"""
        self.is_reusable = False
        return self

    def increment_version(self) -> "Resource":
        """版本号+1（更新资源时调用）"""
        self.version += 1
        return self

    def soft_delete(self) -> "Resource":
        """软删除资源"""
        self.is_active = False
        return self

    # ------------------------------
    # 13. 【新增】常用查询类方法（需配合AsyncSession使用）
    # ------------------------------
    @classmethod
    async def get_active_resources(
            cls,
            session,
            user_id: int,
            resource_type: Optional[str] = None
    ) -> List["Resource"]:
        """获取用户的活跃资源（未软删除）"""
        from sqlalchemy import select

        stmt = select(cls).where(
            cls.user_id == user_id,
            cls.is_active == True
        )

        if resource_type:
            stmt = stmt.where(cls.resource_type == resource_type)

        stmt = stmt.order_by(cls.created_at.desc())
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_by_knowledge_point(
            cls,
            session,
            user_id: int,
            kp_code: str,
            resource_type: Optional[str] = None
    ) -> List["Resource"]:
        """获取涉及指定知识点的资源"""
        from sqlalchemy import select

        stmt = select(cls).where(
            cls.user_id == user_id,
            cls.is_active == True,
            # SQLite JSON数组包含查询
            func.json_extract(cls.knowledge_points, f"$[*]").like(f"%{kp_code}%")
        )

        if resource_type:
            stmt = stmt.where(cls.resource_type == resource_type)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    @classmethod
    async def get_by_status(
            cls,
            session,
            user_id: int,
            status: str
    ) -> List["Resource"]:
        """获取指定状态的资源"""
        from sqlalchemy import select

        stmt = select(cls).where(
            cls.user_id == user_id,
            cls.is_active == True,
            cls.status == status
        ).order_by(cls.created_at.desc())

        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------
    # 14. 【改进】调试方法
    # ------------------------------
    def __repr__(self) -> str:
        return (
            f"<Resource("
            f"id={self.id}, "
            f"user_id={self.user_id}, "
            f"type={self.resource_type!r}, "
            f"title={self.title[:30]!r}, "
            f"status={self.status!r}, "
            f"progress={self.progress_percent}%, "
            f"version={self.version}"
            f")>"
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于API响应）"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "title": self.title,
            "content": self.content,
            "file_path": self.file_path,
            "extra_metadata": self.extra_metadata,
            "vector_db_id": self.vector_db_id,
            "knowledge_points": self.knowledge_points,
            "version": self.version,
            "status": self.status,
            "progress_percent": self.progress_percent,
            "error_message": self.error_message,
            "in_library": self.in_library,
            "is_reusable": self.is_reusable,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }