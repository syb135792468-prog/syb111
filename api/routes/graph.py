"""
api/routes/graph.py - 知识图谱接口

提供：
- GET /graph/snapshot  获取用户局部图谱（含模块/状态筛选）
- GET /graph/node/{node_code}  节点详情（含前置状态+最近证据）
- GET /graph/node/{node_code}/practice  推荐练习题
- GET /graph/stats  图谱统计概览
"""
from __future__ import annotations

from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, Path as PathParam
from sqlalchemy import select, func, and_, case
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import BaseResponse
from models.database import get_db
from models.user import User
from models.knowledge_graph import (
    KnowledgeNode, KnowledgeEdge,
    UserKnowledgeMastery, KnowledgeMasteryEvidence,
    QuestionKnowledgeMap,
)
from models.resource import Resource
from models.quiz_attempt import QuizAttempt
from api.routes.auth import get_current_user
from services.mastery_service import (
    get_user_graph, get_node_detail, get_effective_state,
    STATE_LOCKED, STATE_AVAILABLE, STATE_LEARNING, STATE_MASTERED,
)
from utils.api_helpers import generate_request_id
from utils.logger import get_logger
from config.constants import HTTP_OK, HTTP_NOT_FOUND, HTTP_FORBIDDEN, HTTP_SERVER_ERROR, HTTP_BAD_REQUEST
from config.messages import MSG_SUCCESS, MSG_SERVER_ERROR

router = APIRouter(prefix="/graph", tags=["知识图谱"])
logger = get_logger(__name__, task_id="graph_api")


# ==================== 模块元数据 ====================

MODULE_META: Dict[str, Dict[str, str]] = {
    "basics": {"name": "基础语法", "color": "#3b82f6", "order": 1},
    "datatypes": {"name": "数据类型", "color": "#10b981", "order": 2},
    "control_flow": {"name": "控制流", "color": "#f59e0b", "order": 3},
    "functions": {"name": "函数", "color": "#8b5cf6", "order": 4},
    "data_structures": {"name": "数据结构进阶", "color": "#ec4899", "order": 5},
    "file_exception": {"name": "文件与异常", "color": "#14b8a6", "order": 6},
    "modules": {"name": "模块与包", "color": "#6366f1", "order": 7},
    "oop": {"name": "面向对象", "color": "#ef4444", "order": 8},
    "advanced": {"name": "进阶", "color": "#0ea5e9", "order": 9},
}

STATE_META: Dict[str, Dict[str, str]] = {
    STATE_LOCKED: {"name": "未解锁", "color": "#9ca3af"},
    STATE_AVAILABLE: {"name": "可学习", "color": "#3b82f6"},
    STATE_LEARNING: {"name": "学习中", "color": "#f59e0b"},
    STATE_MASTERED: {"name": "已掌握", "color": "#10b981"},
}


# ==================== 接口 ====================

@router.get("/snapshot", response_model=BaseResponse, summary="获取用户知识图谱快照")
async def get_graph_snapshot(
    module: Optional[str] = Query(None, description="按模块筛选（basics/datatypes/...）"),
    state: Optional[str] = Query(None, description="按状态筛选（locked/available/learning/mastered）"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    """获取用户局部图谱快照，含节点、边、统计"""
    try:
        graph = await get_user_graph(
            session, current_user.id,
            module_filter=module,
            state_filter=state,
        )
        # 附加模块和状态元数据
        graph["modules"] = MODULE_META
        graph["states"] = STATE_META
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=graph,
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"获取图谱快照失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)


@router.get("/node/{node_code}", response_model=BaseResponse, summary="获取节点详情")
async def get_node(
    node_code: str = PathParam(..., description="知识点 code"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    """获取节点详情：节点信息 + 用户掌握 + 前置节点状态 + 最近证据"""
    try:
        detail = await get_node_detail(session, current_user.id, node_code)
        if not detail:
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message=f"知识点 {node_code} 不存在",
                data=None,
                request_id=request_id,
            )
        detail["modules"] = MODULE_META
        detail["states"] = STATE_META
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=detail,
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"获取节点详情失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)


@router.get("/node/{node_code}/practice", response_model=BaseResponse, summary="推荐节点练习题")
async def get_node_practice(
    node_code: str = PathParam(..., description="知识点 code"),
    limit: int = Query(5, ge=1, le=20, description="返回题目数"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    """推荐该知识点的练习题：优先用户未做过的，其次做错的"""
    try:
        # 1. 节点是否存在
        node = (
            await session.execute(
                select(KnowledgeNode).where(KnowledgeNode.code == node_code)
            )
        ).scalar_one_or_none()
        if not node:
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message=f"知识点 {node_code} 不存在",
                data=None,
                request_id=request_id,
            )

        # 1.5 前置条件校验：locked 节点不允许练习
        eff_state = await get_effective_state(session, current_user.id, node_code)
        if eff_state == STATE_LOCKED:
            return BaseResponse(
                code=HTTP_FORBIDDEN,
                message="节点未解锁，请先完成前置知识点",
                data={"node_code": node_code, "effective_state": eff_state},
                request_id=request_id,
            )

        # 2. 查 question_knowledge_map 中映射到该节点的题目
        map_rows = (
            await session.execute(
                select(QuestionKnowledgeMap.resource_id, QuestionKnowledgeMap.question_index, QuestionKnowledgeMap.weight)
                .where(QuestionKnowledgeMap.node_code == node_code)
                .order_by(QuestionKnowledgeMap.weight.desc())
                .limit(limit * 3)  # 多取一些，过滤用户已掌握的
            )
        ).all()

        if not map_rows:
            return BaseResponse(
                code=HTTP_OK,
                message=MSG_SUCCESS,
                data={"node_code": node_code, "questions": [], "total": 0},
                request_id=request_id,
            )

        # 3. 查用户在该节点上的答题历史，按时间倒序取每题最后一次作答
        resource_ids = list({r[0] for r in map_rows})
        user_attempts = (
            await session.execute(
                select(QuizAttempt.resource_id, QuizAttempt.question_index, QuizAttempt.is_correct)
                .where(
                    and_(
                        QuizAttempt.user_id == current_user.id,
                        QuizAttempt.resource_id.in_(resource_ids),
                    )
                )
                .order_by(QuizAttempt.created_at.desc())
            )
        ).all()
        # key: (resource_id, question_index) -> is_correct
        # 按 created_at DESC 返回，只保留每个 key 的第一条（即最新一次作答）
        attempt_map: Dict[tuple, bool] = {}
        for a in user_attempts:
            key = (a[0], a[1])
            if key not in attempt_map:
                attempt_map[key] = bool(a[2])

        # 4. 查对应 resource 的标题和题型（限定当前用户，避免多用户环境下暴露他人资源）
        res_rows = (
            await session.execute(
                select(Resource.id, Resource.title, Resource.resource_type)
                .where(
                    and_(
                        Resource.id.in_(resource_ids),
                        Resource.user_id == current_user.id,
                    )
                )
            )
        ).all()
        res_map = {r[0]: {"title": r[1], "resource_type": r[2]} for r in res_rows}

        # 5. 组装题目列表，排序：未做过 > 做错过 > 做对过
        #    跳过不属于当前用户的 resource（多用户环境下不暴露他人资源 ID/标题）
        questions = []
        for resource_id, question_index, weight in map_rows:
            res_info = res_map.get(resource_id)
            if not res_info:
                continue
            key = (resource_id, question_index)
            attempted = key in attempt_map
            correct = attempt_map.get(key, False)
            questions.append({
                "resource_id": resource_id,
                "question_index": question_index,
                "title": res_info.get("title", f"题目 {question_index}"),
                "resource_type": res_info.get("resource_type", "quiz"),
                "weight": weight,
                "attempted": attempted,
                "last_correct": correct,
                "priority": 0 if not attempted else (1 if not correct else 2),
            })

        # 按 priority 排序，截取 limit
        questions.sort(key=lambda q: (q["priority"], -q["weight"]))
        questions = questions[:limit]

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "node_code": node_code,
                "node_name": node.name,
                "questions": questions,
                "total": len(questions),
            },
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"获取节点练习题失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)


@router.get("/stats", response_model=BaseResponse, summary="图谱统计概览")
async def get_graph_stats(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    """图谱统计：总节点数、各状态分布、各模块分布、最近证据"""
    try:
        # 全图统计（含未激活用户节点）
        total_nodes = (
            await session.execute(
                select(func.count(KnowledgeNode.id)).where(KnowledgeNode.is_active == 1)
            )
        ).scalar_one()

        # 用户掌握统计
        mastery_rows = (
            await session.execute(
                select(UserKnowledgeMastery.state, func.count(UserKnowledgeMastery.id))
                .where(UserKnowledgeMastery.user_id == current_user.id)
                .group_by(UserKnowledgeMastery.state)
            )
        ).all()
        state_counts = {row[0]: row[1] for row in mastery_rows}

        # 用户各模块掌握数
        module_rows = (
            await session.execute(
                select(
                    KnowledgeNode.module,
                    func.count(UserKnowledgeMastery.id),
                    func.sum(
                        case(
                            (UserKnowledgeMastery.state == STATE_MASTERED, 1),
                            else_=0,
                        )
                    ),
                )
                .join(UserKnowledgeMastery, UserKnowledgeMastery.node_code == KnowledgeNode.code)
                .where(UserKnowledgeMastery.user_id == current_user.id)
                .group_by(KnowledgeNode.module)
            )
        ).all()
        module_stats = [
            {
                "module": row[0],
                "module_name": MODULE_META.get(row[0], {}).get("name", row[0]),
                "color": MODULE_META.get(row[0], {}).get("color", "#999"),
                "touched": row[1],
                "mastered": int(row[2] or 0),
            }
            for row in module_rows
        ]

        # 最近 7 天证据数
        from datetime import datetime, UTC, timedelta
        seven_days_ago = (datetime.now(UTC) - timedelta(days=7)).replace(tzinfo=None)
        recent_evidence_count = (
            await session.execute(
                select(func.count(KnowledgeMasteryEvidence.id))
                .where(
                    and_(
                        KnowledgeMasteryEvidence.user_id == current_user.id,
                        KnowledgeMasteryEvidence.created_at >= seven_days_ago,
                    )
                )
            )
        ).scalar_one()

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "total_nodes": total_nodes,
                "state_counts": {
                    STATE_LOCKED: state_counts.get(STATE_LOCKED, 0),
                    STATE_AVAILABLE: state_counts.get(STATE_AVAILABLE, 0),
                    STATE_LEARNING: state_counts.get(STATE_LEARNING, 0),
                    STATE_MASTERED: state_counts.get(STATE_MASTERED, 0),
                },
                "module_stats": module_stats,
                "recent_evidence_count_7d": recent_evidence_count,
                "states": STATE_META,
            },
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"获取图谱统计失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)
