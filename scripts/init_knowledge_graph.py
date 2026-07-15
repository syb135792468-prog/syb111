"""
scripts/init_knowledge_graph.py - 知识图谱初始化脚本

功能：
1. 创建知识图谱 5 张表（依赖 init_db，幂等）
2. 注入 65 节点种子（幂等：code 冲突跳过）
3. 注入 76 前置依赖边（幂等：(source, target, type) 冲突跳过）
4. 验证：节点数、边数、环检测

使用方式：
    python -m scripts.init_knowledge_graph
    python -m scripts.init_knowledge_graph --force   # 强制重新注入（按 code 更新已有节点）
"""
from __future__ import annotations
import asyncio
import argparse
import sys
from pathlib import Path

# 保证项目根目录在 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_db, engine
from models.knowledge_graph import KnowledgeNode, KnowledgeEdge
from data.knowledge_catalog import NODES, EDGES, _self_check
from utils.logger import get_logger

logger = get_logger(__name__, task_id="kg_init")


async def inject_nodes(session: AsyncSession, force: bool = False) -> tuple[int, int]:
    """注入节点，返回 (新增数, 更新数)"""
    inserted = 0
    updated = 0

    existing_codes = {
        row[0] for row in (
            await session.execute(select(KnowledgeNode.code))
        ).fetchall()
    }

    for node_data in NODES:
        code = node_data["code"]
        if code in existing_codes:
            if force:
                stmt = (
                    select(KnowledgeNode)
                    .where(KnowledgeNode.code == code)
                )
                node = (await session.execute(stmt)).scalar_one_or_none()
                if node:
                    node.name = node_data["name"]
                    node.module = node_data["module"]
                    node.level = node_data["level"]
                    node.description = node_data.get("description")
                    node.difficulty = node_data["difficulty"]
                    node.estimated_time = node_data["estimated_time"]
                    node.aliases = node_data.get("aliases", [])
                    node.is_active = 1
                    updated += 1
            continue

        session.add(KnowledgeNode(
            code=code,
            name=node_data["name"],
            module=node_data["module"],
            level=node_data["level"],
            description=node_data.get("description"),
            difficulty=node_data["difficulty"],
            estimated_time=node_data["estimated_time"],
            mastery_threshold=50.0,
            aliases=node_data.get("aliases", []),
            is_active=1,
        ))
        inserted += 1

    await session.flush()
    return inserted, updated


async def inject_edges(session: AsyncSession, force: bool = False) -> tuple[int, int]:
    """注入边，返回 (新增数, 跳过数)"""
    inserted = 0
    skipped = 0

    # 一次性查出所有现有边
    existing_edges = {
        (row[0], row[1], row[2])
        for row in (
            await session.execute(
                select(KnowledgeEdge.source_code, KnowledgeEdge.target_code, KnowledgeEdge.edge_type)
            )
        ).fetchall()
    }

    # 校验所有边引用的节点都存在
    valid_codes = {
        row[0] for row in (
            await session.execute(select(KnowledgeNode.code))
        ).fetchall()
    }

    for src, tgt, etype in EDGES:
        if src not in valid_codes:
            logger.warning(f"跳过边：source 节点不存在 {src}")
            skipped += 1
            continue
        if tgt not in valid_codes:
            logger.warning(f"跳过边：target 节点不存在 {tgt}")
            skipped += 1
            continue
        if (src, tgt, etype) in existing_edges:
            skipped += 1
            continue

        session.add(KnowledgeEdge(
            source_code=src,
            target_code=tgt,
            edge_type=etype,
        ))
        inserted += 1
        existing_edges.add((src, tgt, etype))

    await session.flush()
    return inserted, skipped


async def verify(session: AsyncSession) -> dict:
    """验证图谱完整性"""
    node_count = (await session.execute(select(func.count(KnowledgeNode.id)))).scalar_one()
    edge_count = (await session.execute(select(func.count(KnowledgeEdge.id)))).scalar_one()

    # 按模块统计
    module_counts = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(KnowledgeNode.module, func.count(KnowledgeNode.id))
                .group_by(KnowledgeNode.module)
                .order_by(KnowledgeNode.module)
            )
        ).fetchall()
    }

    # 按层级统计
    level_counts = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(KnowledgeNode.level, func.count(KnowledgeNode.id))
                .group_by(KnowledgeNode.level)
                .order_by(KnowledgeNode.level)
            )
        ).fetchall()
    }

    # 边类型统计
    edge_type_counts = {
        row[0]: row[1]
        for row in (
            await session.execute(
                select(KnowledgeEdge.edge_type, func.count(KnowledgeEdge.id))
                .group_by(KnowledgeEdge.edge_type)
            )
        ).fetchall()
    }

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "module_counts": module_counts,
        "level_counts": level_counts,
        "edge_type_counts": edge_type_counts,
    }


async def main(force: bool = False) -> None:
    logger.info("=" * 60)
    logger.info("知识图谱初始化脚本启动")
    logger.info("=" * 60)

    # 1. 种子数据自检（含环检测）
    logger.info("步骤 1/4: 种子数据自检...")
    _self_check()

    # 2. 初始化数据库（确保所有表存在，幂等）
    logger.info("步骤 2/4: 初始化数据库表结构...")
    await init_db()

    # 3. 注入节点和边
    logger.info("步骤 3/4: 注入节点和边...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_nodes, updated_nodes = await inject_nodes(session, force=force)
            new_edges, skipped_edges = await inject_edges(session, force=force)

    logger.info(f"  节点: 新增 {new_nodes}, 更新 {updated_nodes}")
    logger.info(f"  边: 新增 {new_edges}, 跳过 {skipped_edges}")

    # 4. 验证
    logger.info("步骤 4/4: 验证图谱完整性...")
    async with AsyncSessionLocal() as session:
        stats = await verify(session)

    logger.info("-" * 60)
    logger.info(f"节点总数: {stats['node_count']}")
    logger.info(f"边总数: {stats['edge_count']}")
    logger.info(f"模块分布: {stats['module_counts']}")
    logger.info(f"层级分布: {stats['level_counts']}")
    logger.info(f"边类型分布: {stats['edge_type_counts']}")
    logger.info("=" * 60)
    logger.info("✅ 知识图谱初始化完成")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="知识图谱初始化")
    parser.add_argument("--force", action="store_true", help="强制更新已有节点字段")
    args = parser.parse_args()

    asyncio.run(main(force=args.force))
