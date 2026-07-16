"""
services/path_service.py - 学习路径领域服务

从 api/routes/learning_path.py 下沉的跨层复用逻辑，供 routes 层和 services 层共用，
避免 services 层反向 import routes 层（架构倒置）。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.learning_path import LearningPath, LearningPathNode
from config.constants import (
    DEFAULT_ESTIMATED_TIME_MIN,
    LP_MASTERY_THRESHOLD,
    LP_NODE_STATUS_COMPLETED,
    LP_NODE_STATUS_NOT_STARTED,
    LP_NODE_STATUS_SKIPPED,
    LEARNING_PATH_STATUS_ACTIVE,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="path_service")


def recalc_path_progress(path: LearningPath) -> None:
    """重算路径 completed_nodes 和 progress_percent。

    completed + skipped 都算已完成（与前置测试答对跳过的语义一致）。
    """
    completed = sum(
        1 for n in path.nodes
        if n.status in (LP_NODE_STATUS_COMPLETED, LP_NODE_STATUS_SKIPPED)
    )
    path.completed_nodes = completed
    path.progress_percent = (
        round(completed / path.total_nodes * 100) if path.total_nodes else 0
    )


async def insert_weak_node_if_missing(
    session: AsyncSession, user_id: int, knowledge_point: str
) -> bool:
    """检测到新增薄弱点时，自动插入复习节点到用户 active path（幂等）。

    Args:
        session: 数据库会话
        user_id: 用户 ID
        knowledge_point: 新增薄弱知识点名称

    Returns:
        是否实际插入了新节点（False = 已存在/无 active path/失败）
    """
    if not knowledge_point:
        return False

    path_stmt = (
        select(LearningPath)
        .where(
            LearningPath.user_id == user_id,
            LearningPath.status == LEARNING_PATH_STATUS_ACTIVE,
        )
        .order_by(LearningPath.created_at.desc())
        .limit(1)
        .options(selectinload(LearningPath.nodes))
    )
    result = await session.execute(path_stmt)
    path = result.scalar_one_or_none()
    if not path or not path.nodes:
        return False

    existing_kps = {n.knowledge_point for n in path.nodes}
    if knowledge_point in existing_kps:
        return False

    pending_nodes = [
        n for n in path.nodes
        if n.status == LP_NODE_STATUS_NOT_STARTED
    ]
    insert_order = min((n.order for n in pending_nodes), default=path.total_nodes + 1)

    for n in path.nodes:
        if n.order >= insert_order:
            n.order += 1

    new_node = LearningPathNode(
        learning_path_id=path.id,
        knowledge_point=knowledge_point,
        order=insert_order,
        prerequisites=[],
        difficulty=0.4,
        estimated_time=DEFAULT_ESTIMATED_TIME_MIN,
        status=LP_NODE_STATUS_NOT_STARTED,
        mastery=0.0,
        mastery_threshold=LP_MASTERY_THRESHOLD,
        node_type="review",
    )
    session.add(new_node)
    path.total_nodes = (path.total_nodes or 0) + 1
    recalc_path_progress(path)
    await session.flush()
    logger.info(f"📌 薄弱点自动插入节点: user={user_id}, kp={knowledge_point}, path={path.id}, order={insert_order}")
    return True
