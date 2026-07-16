"""
services/evaluation_service.py - 路径完成评估服务（偏差 F 评估闭环）

闭合"路径完成 -> 目标达成评估 -> 画像 knowledge_level 升级 -> LLM 推荐进阶路径"链路：
1. 聚合路径节点 mastery + 错题错因分布
2. 规则评分：achievement = avg_mastery*0.6 + completion_rate*0.4
3. LLM 生成评估报告（强项/弱项/目标对比/建议）
4. 自动升级 knowledge_level（只升不降，写 ProfileChangeLog source='evaluation'）
5. LLM 生成 3 条进阶路径推荐（topic+reason+difficulty）
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.learning_path import LearningPath, LearningPathNode
from models.profile import UserProfile, ProfileChangeLog
from models.error_book import ErrorBook
from utils.llm_client import get_async_llm_client
from utils.logger import get_logger
from config.constants import (
    LEARNING_PATH_STATUS_ACTIVE,
    LEARNING_PATH_STATUS_COMPLETED,
    LP_NODE_STATUS_COMPLETED,
    LP_NODE_STATUS_SKIPPED,
    KNOWLEDGE_LEVEL_BEGINNER,
    KNOWLEDGE_LEVEL_INTERMEDIATE,
    KNOWLEDGE_LEVEL_ADVANCED,
)

logger = get_logger(__name__, task_id="evaluation_service")

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"

LEVEL_UP_INTERMEDIATE_MASTERY = 0.75
LEVEL_UP_ADVANCED_MASTERY = 0.85
LEVEL_UP_ADVANCED_PATH_COUNT = 2

SCORE_MASTERY_WEIGHT = 0.6
SCORE_COMPLETION_WEIGHT = 0.4


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


def _calc_achievement_score(mastery_list: List[float], completion_rate: float) -> float:
    avg_mastery = sum(mastery_list) / len(mastery_list) if mastery_list else 0.0
    score = (avg_mastery * SCORE_MASTERY_WEIGHT + completion_rate * SCORE_COMPLETION_WEIGHT) * 100
    return round(score, 1)


def _calc_mastery_stats(mastery_list: List[float]) -> Dict[str, float]:
    if not mastery_list:
        return {"avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "avg": round(sum(mastery_list) / len(mastery_list), 3),
        "min": round(min(mastery_list), 3),
        "max": round(max(mastery_list), 3),
    }


async def _aggregate_error_distribution(
    session: AsyncSession, user_id: int, knowledge_points: List[str]
) -> Dict[str, int]:
    if not knowledge_points:
        return {}
    result = await session.execute(
        select(ErrorBook.error_type, func.count().label("cnt"))
        .where(
            ErrorBook.user_id == user_id,
            ErrorBook.knowledge_point.in_(knowledge_points),
            ErrorBook.error_type.isnot(None),
        )
        .group_by(ErrorBook.error_type)
    )
    return {row[0]: row[1] for row in result.all() if row[0]}


def _build_evaluation_user_prompt(
    goal: str,
    mastery_stats: Dict[str, float],
    node_mastery_list: List[Dict[str, Any]],
    error_distribution: Dict[str, int],
    profile: UserProfile,
) -> str:
    parts = [f"## 学习目标\n{goal}\n"]
    parts.append(
        f"## 掌握度统计\n- 平均: {mastery_stats['avg']}\n- 最低: {mastery_stats['min']}\n- 最高: {mastery_stats['max']}\n"
    )
    parts.append("## 各节点掌握度")
    for n in node_mastery_list:
        parts.append(f"- {n['knowledge_point']}: mastery={n['mastery']}")
    parts.append("\n## 错因分布")
    if error_distribution:
        for et, cnt in error_distribution.items():
            parts.append(f"- {et}: {cnt}")
    else:
        parts.append("- 无错题记录")
    parts.append("\n## 用户画像")
    parts.append(f"- knowledge_level: {profile.knowledge_level}")
    parts.append(f"- weak_points: {profile.weak_points or []}")
    parts.append(f"- mastered_points: {profile.mastered_points or []}")
    return "\n".join(parts)


def _build_advance_user_prompt(
    path_topic: str,
    node_mastery_list: List[Dict[str, Any]],
    profile: UserProfile,
    error_distribution: Dict[str, int],
) -> str:
    parts = [f"## 已完成路径主题\n{path_topic}\n"]
    parts.append("## 各节点掌握度")
    for n in node_mastery_list:
        parts.append(f"- {n['knowledge_point']}: mastery={n['mastery']}")
    parts.append("\n## 用户画像")
    parts.append(f"- knowledge_level: {profile.knowledge_level}")
    parts.append(f"- learning_goal: {profile.learning_goal}")
    parts.append(f"- weak_points: {profile.weak_points or []}")
    parts.append(f"- mastered_points: {profile.mastered_points or []}")
    parts.append("\n## 错因分布")
    if error_distribution:
        for et, cnt in error_distribution.items():
            parts.append(f"- {et}: {cnt}")
    else:
        parts.append("- 无错题记录")
    return "\n".join(parts)


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r'{[\s\S]*}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


async def _maybe_upgrade_knowledge_level(
    session: AsyncSession,
    user_id: int,
    profile: UserProfile,
    avg_mastery: float,
) -> Optional[Dict[str, str]]:
    """自动升级 knowledge_level（只升不降），返回 {from, to} 或 None"""
    current = profile.knowledge_level
    target: Optional[str] = None

    if current == KNOWLEDGE_LEVEL_BEGINNER and avg_mastery >= LEVEL_UP_INTERMEDIATE_MASTERY:
        target = KNOWLEDGE_LEVEL_INTERMEDIATE
    elif current == KNOWLEDGE_LEVEL_INTERMEDIATE and avg_mastery >= LEVEL_UP_ADVANCED_MASTERY:
        completed_count = await session.execute(
            select(func.count()).select_from(LearningPath).where(
                LearningPath.user_id == user_id,
                LearningPath.status == LEARNING_PATH_STATUS_COMPLETED,
            )
        )
        if (completed_count.scalar() or 0) >= LEVEL_UP_ADVANCED_PATH_COUNT:
            target = KNOWLEDGE_LEVEL_ADVANCED

    if not target:
        return None

    old_level = current
    profile.knowledge_level = target

    log = ProfileChangeLog(
        user_id=user_id,
        changed_fields={"knowledge_level": {"from": old_level, "to": target}},
        source="evaluation",
    )
    session.add(log)
    logger.info(f"📈 用户 {user_id} knowledge_level 升级: {old_level} -> {target}")
    return {"from": old_level, "to": target}


async def evaluate_path(
    session: AsyncSession,
    user_id: int,
    path_id: int,
) -> Dict[str, Any]:
    """路径完成评估主函数。

    Returns:
        {
            achievement_score, mastery_stats, completion_rate,
            error_distribution, report, recommendations, level_upgraded
        }
    """
    stmt = (
        select(LearningPath)
        .where(LearningPath.id == path_id, LearningPath.user_id == user_id)
        .options(selectinload(LearningPath.nodes))
    )
    result = await session.execute(stmt)
    path = result.scalar_one_or_none()
    if not path:
        raise ValueError(f"路径 {path_id} 不存在或不属于用户 {user_id}")

    profile = await session.get(UserProfile, user_id)
    if not profile:
        raise ValueError(f"用户 {user_id} 画像不存在")

    nodes = path.nodes or []
    node_mastery_list = [
        {"knowledge_point": n.knowledge_point, "mastery": round(float(n.mastery or 0), 3)}
        for n in nodes
    ]
    mastery_list = [float(n.mastery or 0) for n in nodes]
    mastery_stats = _calc_mastery_stats(mastery_list)

    completed_count = sum(
        1 for n in nodes
        if n.status in (LP_NODE_STATUS_COMPLETED, LP_NODE_STATUS_SKIPPED)
    )
    completion_rate = completed_count / len(nodes) if nodes else 0.0
    achievement_score = _calc_achievement_score(mastery_list, completion_rate)

    knowledge_points = [n.knowledge_point for n in nodes if n.knowledge_point]
    error_distribution = await _aggregate_error_distribution(session, user_id, knowledge_points)

    eval_system = _load_prompt("path_evaluation_system")
    eval_user = _build_evaluation_user_prompt(
        goal=path.goal or f"掌握{path.topic}核心知识",
        mastery_stats=mastery_stats,
        node_mastery_list=node_mastery_list,
        error_distribution=error_distribution,
        profile=profile,
    )

    llm = get_async_llm_client()
    try:
        report_raw = await llm.call(
            messages=[
                {"role": "system", "content": eval_system},
                {"role": "user", "content": eval_user},
            ],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        report = _extract_json(report_raw)
    except Exception as e:
        logger.warning(f"⚠️ LLM 评估报告生成失败: {e}")
        report = {
            "goal_achievement": "medium",
            "strengths": [],
            "weaknesses": [],
            "goal_analysis": "评估报告生成失败，请稍后重试",
            "suggestions": [],
        }

    level_upgraded = await _maybe_upgrade_knowledge_level(
        session, user_id, profile, mastery_stats["avg"]
    )

    if path.status == LEARNING_PATH_STATUS_ACTIVE:
        path.status = LEARNING_PATH_STATUS_COMPLETED

    await session.flush()

    advance_system = _load_prompt("path_advance_recommend_system")
    advance_user = _build_advance_user_prompt(
        path_topic=path.topic,
        node_mastery_list=node_mastery_list,
        profile=profile,
        error_distribution=error_distribution,
    )

    try:
        advance_raw = await llm.call(
            messages=[
                {"role": "system", "content": advance_system},
                {"role": "user", "content": advance_user},
            ],
            temperature=0.4,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        advance_data = _extract_json(advance_raw)
        recommendations = advance_data.get("recommendations", [])
    except Exception as e:
        logger.warning(f"⚠️ LLM 进阶推荐生成失败: {e}")
        recommendations = []

    return {
        "achievement_score": achievement_score,
        "mastery_stats": mastery_stats,
        "completion_rate": round(completion_rate, 3),
        "error_distribution": error_distribution,
        "report": report,
        "recommendations": recommendations,
        "level_upgraded": level_upgraded,
    }
