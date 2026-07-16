"""
api/routes/learning_path.py - 学习路径接口（软件杯A3赛题核心功能）
- 获取用户学习路径列表
- 生成新学习路径（调用PathAgent）
- 获取路径节点详情
- 标记节点完成（触发动态更新）
- 获取/生成节点关联资源
- 提交测验结果更新掌握度
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, UTC
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, Query, Path as PathParam
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.schemas import (
    BaseResponse,
    LearningPathData,
    LearningPathNodeData,
    LearningPathNodeResourceData,
    LearningPathGenerateRequest,
    LearningPathListResponse,
    LearningPathNodeCompleteRequest,
    LearningPathQuizSubmitRequest,
)
from models.database import get_db
from models.user import User
from models.profile import UserProfile
from models.learning_path import LearningPath, LearningPathNode, LearningPathNodeResource
from api.routes.auth import get_current_user
from utils.logger import get_logger
from services.path_service import recalc_path_progress
from config.constants import (
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_SERVER_ERROR,
    DEFAULT_ESTIMATED_TIME_MIN, EXTENDED_ESTIMATED_TIME_MIN,
    LP_MASTERY_THRESHOLD,
    LP_NODE_STATUS_NOT_STARTED, LP_NODE_STATUS_IN_PROGRESS,
    LP_NODE_STATUS_COMPLETED, LP_NODE_STATUS_NEEDS_REVIEW, LP_NODE_STATUS_SKIPPED,
    LEARNING_PATH_STATUS_ACTIVE, LP_RESOURCE_STATUS_PENDING,
    LP_RESOURCE_STATUS_GENERATING, LP_RESOURCE_STATUS_COMPLETED,
    LP_MAX_NODES_PER_PATH, LP_DEFAULT_RESOURCE_TYPES,
    QUIZ_TYPE_CHOICE, DIFFICULTY_MEDIUM, ERROR_TYPE_OTHER,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_LEARNING_PATH_NOT_FOUND,
    MSG_LEARNING_PATH_GENERATED, MSG_LEARNING_PATH_NODE_NOT_FOUND,
    MSG_LEARNING_PATH_NODE_COMPLETED, MSG_LEARNING_PATH_RESOURCE_GENERATING,
    MSG_LEARNING_PATH_RESOURCE_CACHED, MSG_LEARNING_PATH_QUIZ_RECORDED,
)

router = APIRouter(prefix="/learning-path", tags=["学习路径"])
logger = get_logger(__name__, task_id="learning_path_api")


# ==================== 辅助函数 ====================

def _path_to_response(path: LearningPath) -> Dict[str, Any]:
    """将ORM对象转换为响应字典"""
    return path.to_dict()


def _node_to_response(node: LearningPathNode) -> Dict[str, Any]:
    """将节点ORM对象转换为响应字典"""
    return node.to_dict()


async def _get_user_profile(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """获取用户画像，不存在则返回默认值"""
    profile: Optional[UserProfile] = await session.get(UserProfile, user_id)
    if profile:
        return {
            "knowledge_level": profile.knowledge_level,
            "learning_goal": profile.learning_goal,
            "learning_style": profile.learning_style,
            "weak_points": profile.weak_points or [],
            "mastered_points": profile.mastered_points or [],
        }
    return {
        "knowledge_level": "beginner",
        "weak_points": [],
        "mastered_points": [],
    }


async def _generate_path_with_agent(
    user_id: int, topic: str, goal: Optional[str], profile: Dict[str, Any]
) -> Dict[str, Any]:
    """调用PathAgent生成学习路径，返回 {learning_path, path_title}"""
    from agents.path_agent import PathAgent

    agent = PathAgent(user_id=str(user_id))
    context = {
        "user_id": str(user_id),
        "profile_data": profile,
        "topic": topic,
    }
    result = await asyncio.wait_for(
        agent.process(user_input=topic, context=context),
        timeout=60,
    )
    return {
        "learning_path": result.get("learning_path", []),
        "path_title": result.get("path_title", ""),
    }


async def _save_path_to_db(
    session: AsyncSession,
    user_id: int,
    title: str,
    topic: str,
    goal: Optional[str],
    path_steps: List[Dict[str, Any]],
    description: Optional[str] = None,
) -> LearningPath:
    """将生成的路径保存到数据库"""
    now = datetime.now(UTC).replace(tzinfo=None)
    path = LearningPath(
        user_id=user_id,
        title=title,
        description=description or f"{topic}个性化学习路径",
        goal=goal or f"掌握{topic}核心知识",
        topic=topic,
        status=LEARNING_PATH_STATUS_ACTIVE,
        total_nodes=len(path_steps),
        completed_nodes=0,
        updated_at=now,
        total_estimated_time=sum(
            s.get("estimated_time_min", DEFAULT_ESTIMATED_TIME_MIN) for s in path_steps
        ),
    )
    session.add(path)
    await session.flush()

    for idx, step in enumerate(path_steps):
        kp = step.get("knowledge_point", "")
        node = LearningPathNode(
            learning_path_id=path.id,
            knowledge_point=kp,
            description=step.get("description") or f"学习{kp}",
            order=idx + 1,
            prerequisites=step.get("prerequisites", []),
            difficulty=step.get("difficulty", 0.5),
            estimated_time=step.get("estimated_time_min", DEFAULT_ESTIMATED_TIME_MIN),
            mastery_threshold=LP_MASTERY_THRESHOLD,
            status=LP_NODE_STATUS_NOT_STARTED,
            node_type=step.get("type", "new"),
        )
        session.add(node)

    await session.flush()
    return path


def _calculate_mastery(correct_count: int, total_questions: int) -> float:
    """基于答题结果计算掌握度（简化版，加权正确率）"""
    if total_questions <= 0:
        return 0.0
    accuracy = correct_count / total_questions
    # 简单映射：正确率 -> 掌握度（非线性，高正确率权重更大）
    if accuracy >= 0.9:
        return min(1.0, accuracy * 1.1)
    elif accuracy >= 0.7:
        return accuracy
    elif accuracy >= 0.5:
        return accuracy * 0.9
    else:
        return accuracy * 0.8


# ==================== 接口 ====================

@router.get("/health", response_model=BaseResponse)
async def health():
    return BaseResponse(
        code=HTTP_OK,
        message=MSG_SUCCESS,
        data={"status": "ok", "service": "learning_path"},
    )


@router.get("/", response_model=BaseResponse)
async def list_learning_paths(
    current_user: User = Depends(get_current_user),
    status: Optional[str] = Query(None, description="路径状态过滤"),
    session: AsyncSession = Depends(get_db),
):
    """获取当前用户的学习路径列表"""
    try:
        conditions = [LearningPath.user_id == current_user.id]
        if status:
            conditions.append(LearningPath.status == status)

        stmt = (
            select(LearningPath)
            .where(*conditions)
            .options(selectinload(LearningPath.nodes))
            .order_by(LearningPath.created_at.desc())
        )
        result = await session.execute(stmt)
        paths = result.scalars().all()

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "paths": [_path_to_response(p) for p in paths],
                "total": len(paths),
            },
        )
    except Exception as e:
        logger.error(f"获取路径列表失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/{path_id}", response_model=BaseResponse)
async def get_learning_path(
    path_id: int = PathParam(..., description="路径ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取单条学习路径详情（含节点和资源）"""
    try:
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path_id, LearningPath.user_id == current_user.id)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
        )
        result = await session.execute(stmt)
        path = result.scalar_one_or_none()

        if not path:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NOT_FOUND, data=None
            )

        return BaseResponse(
            code=HTTP_OK, message=MSG_SUCCESS, data=_path_to_response(path)
        )
    except Exception as e:
        logger.error(f"获取路径详情失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/generate", response_model=BaseResponse)
async def generate_learning_path(
    req: LearningPathGenerateRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """生成新的学习路径"""
    try:
        # 获取用户画像
        profile = await _get_user_profile(session, current_user.id)

        # 问卷数据覆盖 DB 画像
        if req.mastered_points is not None:
            profile["mastered_points"] = req.mastered_points
        if req.weak_points is not None:
            profile["weak_points"] = req.weak_points
        if req.target_points is not None:
            profile["target_points"] = req.target_points

        # 调用PathAgent生成路径
        agent_result = await _generate_path_with_agent(
            user_id=current_user.id,
            topic=req.topic,
            goal=req.goal,
            profile=profile,
        )
        path_steps = agent_result.get("learning_path", [])
        llm_title = agent_result.get("path_title", "")

        if not path_steps:
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message="无法生成学习路径：你已掌握所有相关知识点，试试换个学习方向吧",
                data=None,
            )

        # 限制步数
        if req.max_steps:
            path_steps = path_steps[:req.max_steps]

        # 优先使用LLM生成的标题
        title = llm_title or f"{req.topic}学习路径"
        path = await _save_path_to_db(
            session=session,
            user_id=current_user.id,
            title=title,
            topic=req.topic,
            goal=req.goal,
            path_steps=path_steps,
        )

        # 重新加载路径（含节点）
        await session.refresh(path)
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(selectinload(LearningPath.nodes))
        )
        result = await session.execute(stmt)
        path = result.scalar_one()

        logger.info(f"✅ 用户{current_user.id}生成路径: {title}, {len(path_steps)}步")

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_LEARNING_PATH_GENERATED,
            data=_path_to_response(path),
        )
    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_SERVER_ERROR, message="路径生成超时，请重试", data=None
        )
    except Exception as e:
        logger.error(f"生成路径失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/nodes/{node_id}/complete", response_model=BaseResponse)
async def complete_node(
    node_id: int = PathParam(..., description="节点ID"),
    req: LearningPathNodeCompleteRequest = LearningPathNodeCompleteRequest(),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """标记节点为完成状态，更新路径进度"""
    try:
        # 获取节点并验证归属
        stmt = (
            select(LearningPathNode)
            .where(LearningPathNode.id == node_id)
            .options(
                selectinload(LearningPathNode.learning_path).selectinload(LearningPath.nodes),
            )
        )
        result = await session.execute(stmt)
        node = result.scalar_one_or_none()

        if not node:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        path = node.learning_path
        if path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        # 更新节点状态
        mastery = req.mastery if req.mastery is not None else LP_MASTERY_THRESHOLD
        node.update_mastery(mastery)
        if node.status != LP_NODE_STATUS_COMPLETED:
            node.mark_completed()

        # 更新路径进度（统一口径：completed + skipped）
        recalc_path_progress(path)

        await session.flush()

        # 图谱回写：通过知识点名匹配图谱节点，写 path_node 证据
        try:
            from services.mastery_service import record_path_node_evidence
            matched_code = await record_path_node_evidence(
                session, current_user.id,
                knowledge_point_name=node.knowledge_point,
                mastery=mastery,
                node_id=node.id,
            )
            if matched_code:
                logger.info(f"✅ 路径节点图谱回写: user={current_user.id}, kp={node.knowledge_point}, node_code={matched_code}, mastery={mastery}")
        except Exception as graph_err:
            logger.warning(f"⚠️ 路径节点图谱回写失败: {graph_err}")

        # 重新加载路径
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
        )
        result = await session.execute(stmt)
        path = result.scalar_one()

        logger.info(f"✅ 节点{node_id}完成, 路径进度: {path.progress_percent}%")

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_LEARNING_PATH_NODE_COMPLETED,
            data=_path_to_response(path),
        )
    except Exception as e:
        logger.error(f"标记节点完成失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/nodes/{node_id}/resources", response_model=BaseResponse)
async def get_or_generate_node_resources(
    node_id: int = PathParam(..., description="节点ID"),
    resource_types: Optional[str] = Query(
        None, description="资源类型过滤，逗号分隔（如：doc,quiz,mindmap）"
    ),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取节点关联的资源，不存在则触发AI生成"""
    try:
        # 获取节点
        stmt = (
            select(LearningPathNode)
            .where(LearningPathNode.id == node_id)
            .options(
                selectinload(LearningPathNode.resources),
                selectinload(LearningPathNode.learning_path),
            )
        )
        result = await session.execute(stmt)
        node = result.scalar_one_or_none()

        if not node:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        if node.learning_path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        # 确定需要的资源类型
        types_to_check = (
            resource_types.split(",") if resource_types
            else LP_DEFAULT_RESOURCE_TYPES
        )
        types_to_check = [t.strip() for t in types_to_check if t.strip()]

        # 检查已有缓存资源
        existing = {
            r.resource_type: r for r in (node.resources or [])
            if r.status == LP_RESOURCE_STATUS_COMPLETED and r.is_cached
        }
        missing_types = [t for t in types_to_check if t not in existing]

        # 标记节点开始学习
        if node.status == LP_NODE_STATUS_NOT_STARTED:
            node.mark_started()

        # 如果有缺失资源，调用 ResourceAgent 生成
        if missing_types:
            profile = await _get_user_profile(session, current_user.id)
            from agents.resource_agent import ResourceAgent
            agent = ResourceAgent(user_id=str(current_user.id))

            gen_result = await asyncio.wait_for(
                agent.process(
                    user_input=node.knowledge_point,
                    context={
                        "resource_types": missing_types,
                        "profile_data": profile,
                        "user_id": str(current_user.id),
                    },
                ),
                timeout=120,
            )

            # 将生成结果保存到数据库
            generated = gen_result.get("resources", [])
            new_db_resources = []
            for res_data in generated:
                rtype = res_data.get("resource_type", "")
                status = res_data.get("status", "failed")
                res = LearningPathNodeResource(
                    node_id=node_id,
                    resource_type=rtype,
                    title=res_data.get("title", f"{node.knowledge_point} - {rtype}"),
                    description=res_data.get("description"),
                    content=res_data.get("content"),
                    status=LP_RESOURCE_STATUS_COMPLETED if status == "completed" else "failed",
                    is_cached=status == "completed",
                    extra_metadata=res_data.get("extra_metadata"),
                )
                session.add(res)
                new_db_resources.append(res)

            await session.flush()

        # 重新加载节点资源
        await session.refresh(node)
        all_resources = node.resources or []
        resource_data = [r.to_dict() for r in all_resources]

        cached_count = sum(1 for r in all_resources if r.is_cached)
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_LEARNING_PATH_RESOURCE_CACHED if not missing_types else f"已生成{len(missing_types)}种资源",
            data={
                "node_id": node_id,
                "knowledge_point": node.knowledge_point,
                "resources": resource_data,
                "cached_count": cached_count,
                "total_count": len(resource_data),
            },
        )
    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_SERVER_ERROR, message="资源生成超时，请重试", data=None
        )
    except Exception as e:
        logger.error(f"获取节点资源失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/quiz/submit", response_model=BaseResponse)
async def submit_quiz_result(
    req: LearningPathQuizSubmitRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """提交测验结果，更新节点掌握度和路径状态"""
    try:
        # 获取节点
        stmt = (
            select(LearningPathNode)
            .where(LearningPathNode.id == req.node_id)
            .options(
                selectinload(LearningPathNode.learning_path).selectinload(LearningPath.nodes),
            )
        )
        result = await session.execute(stmt)
        node = result.scalar_one_or_none()

        if not node:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        path = node.learning_path
        if path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        # 计算掌握度
        mastery = _calculate_mastery(req.correct_count, req.total_questions)
        node.update_mastery(mastery)

        # 如果掌握度明显不足，标记需要复习
        if mastery < LP_MASTERY_THRESHOLD * 0.7:
            if node.status == LP_NODE_STATUS_COMPLETED:
                node.mark_needs_review()

        # 统一重新计算路径进度（completed + skipped，避免 SKIPPED 节点进度倒退）
        recalc_path_progress(path)
        await session.flush()

        # 图谱回写：通过知识点名匹配图谱节点，写 path_node 证据
        try:
            from services.mastery_service import record_path_node_evidence
            matched_code = await record_path_node_evidence(
                session, current_user.id,
                knowledge_point_name=node.knowledge_point,
                mastery=mastery,
                node_id=node.id,
            )
            if matched_code:
                logger.info(f"✅ 路径测验图谱回写: user={current_user.id}, kp={node.knowledge_point}, node_code={matched_code}, mastery={mastery:.2f}")
        except Exception as graph_err:
            logger.warning(f"⚠️ 路径测验图谱回写失败: {graph_err}")

        # 重新加载
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
        )
        result = await session.execute(stmt)
        path = result.scalar_one()

        logger.info(
            f"✅ 测验结果: 用户{current_user.id}, 节点{req.node_id}, "
            f"正确率={req.correct_count}/{req.total_questions}, 掌握度={mastery:.2f}"
        )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_LEARNING_PATH_QUIZ_RECORDED,
            data={
                "path": _path_to_response(path),
                "quiz_result": {
                    "node_id": req.node_id,
                    "correct_count": req.correct_count,
                    "total_questions": req.total_questions,
                    "mastery": round(mastery, 2),
                },
            },
        )
    except Exception as e:
        logger.error(f"提交测验结果失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


# ==================== 节点前置测试（PathAgent ↔ QuizAgent 协作链）====================

@router.post("/nodes/{node_id}/pre-test", response_model=BaseResponse)
async def generate_node_pre_test(
    node_id: int = PathParam(..., description="节点ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """为节点生成前置测试题（PathAgent 调 QuizAgent，Agent 间协作）。
    若已有前置测试资源则命中缓存直接返回。
    """
    try:
        # 取节点并验证归属
        stmt = (
            select(LearningPathNode)
            .where(LearningPathNode.id == node_id)
            .options(selectinload(LearningPathNode.resources))
        )
        result = await session.execute(stmt)
        node = result.scalar_one_or_none()
        if not node or node.learning_path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        # 命中缓存：已有前置测试资源直接返回
        cached = next(
            (r for r in (node.resources or [])
             if r.resource_type == "quiz" and (r.extra_metadata or {}).get("is_pre_test")),
            None,
        )
        if cached:
            meta = cached.extra_metadata or {}
            return BaseResponse(
                code=HTTP_OK,
                message=MSG_LEARNING_PATH_RESOURCE_CACHED,
                data={
                    "question": cached.content,
                    "answer": meta.get("answer", ""),
                    "explanation": meta.get("explanation", ""),
                    "common_mistakes": meta.get("common_mistakes", []),
                    "difficulty": meta.get("difficulty", DIFFICULTY_MEDIUM),
                    "resource_id": cached.id,
                    "cached": True,
                    "collaboration_info": {
                        "agents": [
                            {"name": "PathAgent", "role": "路径规划", "action": "发起前置测试请求"},
                            {"name": "QuizAgent", "role": "测验生成", "action": "生成选择题（已缓存）"},
                        ],
                        "description": "PathAgent 协同 QuizAgent 生成前置测试（命中缓存）",
                    },
                },
            )

        # 调 PathAgent.generate_pre_test（内部调 QuizAgent，Agent 间协作）
        from agents.path_agent import PathAgent
        from models.learning_path import LearningPath as LPModel

        # 取节点 difficulty 字符串映射
        diff_val = node.difficulty or 0.5
        if diff_val <= 0.3:
            difficulty = "easy"
        elif diff_val >= 0.65:
            difficulty = "hard"
        else:
            difficulty = DIFFICULTY_MEDIUM

        path_agent = PathAgent(user_id=str(current_user.id))
        pre_test = await path_agent.generate_pre_test(
            knowledge_point=node.knowledge_point, difficulty=difficulty
        )

        # 存为 LearningPathNodeResource
        resource_item = pre_test.get("resource_item")
        resource = LearningPathNodeResource(
            node_id=node.id,
            resource_type="quiz",
            title=f"{node.knowledge_point} 前置测试",
            content=pre_test["question"],
            extra_metadata={
                "is_pre_test": True,
                "answer": pre_test["answer"],
                "explanation": pre_test["explanation"],
                "common_mistakes": pre_test["common_mistakes"],
                "difficulty": pre_test["difficulty"],
                "knowledge_point": node.knowledge_point,
            },
            status=LP_RESOURCE_STATUS_COMPLETED,
            is_cached=True,
        )
        session.add(resource)
        await session.commit()
        await session.refresh(resource)

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "question": pre_test["question"],
                "answer": pre_test["answer"],
                "explanation": pre_test["explanation"],
                "common_mistakes": pre_test["common_mistakes"],
                "difficulty": pre_test["difficulty"],
                "resource_id": resource.id,
                "cached": False,
                "collaboration_info": pre_test.get("collaboration_info"),
            },
        )
    except Exception as e:
        logger.error(f"生成前置测试失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/nodes/{node_id}/pre-test/submit", response_model=BaseResponse)
async def submit_node_pre_test(
    node_id: int = PathParam(..., description="节点ID"),
    body: dict = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """提交前置测试答案。答对则节点跳过(SKIPPED)并推进路径进度，答错则保留节点。"""
    try:
        body = body or {}
        resource_id = body.get("resource_id")
        user_answer = str(body.get("user_answer", "")).strip()

        if not resource_id or not user_answer:
            return BaseResponse(
                code=HTTP_BAD_REQUEST, message="缺少 resource_id 或 user_answer", data=None
            )

        # 取资源 + 节点 + 路径
        stmt = (
            select(LearningPathNodeResource)
            .where(LearningPathNodeResource.id == resource_id)
            .options(
                selectinload(LearningPathNodeResource.node)
                .selectinload(LearningPathNode.learning_path)
                .selectinload(LearningPath.nodes)
            )
        )
        result = await session.execute(stmt)
        resource = result.scalar_one_or_none()
        if not resource or not resource.extra_metadata or not resource.extra_metadata.get("is_pre_test"):
            return BaseResponse(code=HTTP_NOT_FOUND, message="前置测试题不存在", data=None)

        node = resource.node
        path = node.learning_path
        if path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        meta = resource.extra_metadata
        correct_answer = meta.get("answer", "")
        common_mistakes = meta.get("common_mistakes", [])

        # 判分（复用 grading_service.grade_choice）
        from services.grading_service import grade_choice
        is_correct = grade_choice(user_answer, correct_answer)

        # 错因比对（复用 _match_error_type 逻辑）
        matched_error_type = ERROR_TYPE_OTHER
        if not is_correct and common_mistakes:
            user_norm = user_answer.upper()
            for m in common_mistakes:
                if isinstance(m, dict) and str(m.get("wrong", "")).strip().upper() == user_norm:
                    matched_error_type = m.get("error_type", ERROR_TYPE_OTHER)
                    break

        now = datetime.now(UTC).replace(tzinfo=None)
        if is_correct:
            # 答对 -> 节点跳过 + 推进路径进度
            was_completed = node.status in (LP_NODE_STATUS_COMPLETED, LP_NODE_STATUS_SKIPPED)
            node.status = LP_NODE_STATUS_SKIPPED
            node.mastery = 1.0
            node.completed_at = now
            node.last_study_at = now
            if not was_completed:
                recalc_path_progress(path)
            await session.flush()

            # 重新加载完整路径（含 nodes + resources）
            stmt = (
                select(LearningPath)
                .where(LearningPath.id == path.id)
                .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
            )
            result = await session.execute(stmt)
            path = result.scalar_one()
            logger.info(
                f"✅ 前置测试答对: node={node_id} 跳过, path={path.id} 进度={path.progress_percent}%"
            )
        else:
            # 答错 -> 节点保留 NOT_STARTED，返回错题解析
            logger.info(
                f"📝 前置测试答错: node={node_id}, user={user_answer}, correct={correct_answer}, "
                f"error_type={matched_error_type}"
            )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "is_correct": is_correct,
                "correct_answer": correct_answer,
                "explanation": meta.get("explanation", ""),
                "matched_error_type": matched_error_type if not is_correct else None,
                "path": _path_to_response(path) if is_correct else None,
            },
        )
    except Exception as e:
        logger.error(f"提交前置测试失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/nodes/{node_id}/unskip", response_model=BaseResponse)
async def unskip_node(
    node_id: int = PathParam(..., description="节点ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """取消跳过：节点恢复 NOT_STARTED，路径进度回退。"""
    try:
        stmt = (
            select(LearningPathNode)
            .where(LearningPathNode.id == node_id)
            .options(
                selectinload(LearningPathNode.learning_path).selectinload(LearningPath.nodes)
            )
        )
        result = await session.execute(stmt)
        node = result.scalar_one_or_none()
        if not node or node.learning_path.user_id != current_user.id:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NODE_NOT_FOUND, data=None
            )

        if node.status != LP_NODE_STATUS_SKIPPED:
            return BaseResponse(
                code=HTTP_BAD_REQUEST, message="节点非跳过状态，无需取消", data=None
            )

        path = node.learning_path
        node.status = LP_NODE_STATUS_NOT_STARTED
        node.mastery = 0.0
        node.completed_at = None
        recalc_path_progress(path)
        await session.flush()

        # 重新加载完整路径
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
        )
        result = await session.execute(stmt)
        path = result.scalar_one()

        logger.info(f"✅ 节点{node_id}取消跳过, path={path.id} 进度={path.progress_percent}%")
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=_path_to_response(path),
        )
    except Exception as e:
        logger.error(f"取消跳过失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{path_id}/reorder", response_model=BaseResponse)
async def reorder_path(
    path_id: int = PathParam(..., description="路径ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """规则重排路径中 NOT_STARTED 节点的顺序（薄弱点优先 + 难度递增）。

    固定节点（IN_PROGRESS/COMPLETED/SKIPPED/NEEDS_REVIEW）位置不变，
    只重排 NOT_STARTED 节点。
    """
    try:
        from agents.path_agent import PathAgent

        # 查路径 + 节点
        stmt = (
            select(LearningPath)
            .where(
                LearningPath.id == path_id,
                LearningPath.user_id == current_user.id,
            )
            .options(selectinload(LearningPath.nodes))
        )
        result = await session.execute(stmt)
        path = result.scalar_one_or_none()
        if not path:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NOT_FOUND, data=None
            )

        # 查用户画像（取 weak_points）
        profile = await _get_user_profile(session, current_user.id)
        weak_points = profile.get("weak_points", [])

        # 调规则重排
        reordered_ids = PathAgent.reorder_pending_nodes(path.nodes, weak_points)

        # 构建 id -> node 映射
        node_map = {n.id: n for n in path.nodes}

        # 按 reordered_ids 顺序重新分配 order（1, 2, 3...）
        pending_count = sum(
            1 for n in path.nodes if n.status == LP_NODE_STATUS_NOT_STARTED
        )
        for new_order, node_id in enumerate(reordered_ids, start=1):
            node = node_map.get(node_id)
            if node:
                node.order = new_order

        await session.flush()
        recalc_path_progress(path)
        await session.commit()

        # 重新加载（含 resources）
        stmt2 = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources))
        )
        result2 = await session.execute(stmt2)
        path = result2.scalar_one()

        logger.info(
            f"🔄 路径重排完成: user={current_user.id}, path={path_id}, "
            f"重排 {pending_count} 个未学节点"
        )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                **_path_to_response(path),
                "reorder_info": {
                    "reordered_count": pending_count,
                    "weak_points_prioritized": [
                        kp for kp in weak_points
                        if kp in {n.knowledge_point for n in path.nodes}
                    ],
                },
            },
        )
    except Exception as e:
        logger.error(f"路径重排失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{path_id}/evaluate", response_model=BaseResponse)
async def evaluate_path_endpoint(
    path_id: int = PathParam(..., description="路径ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """路径完成评估：规则评分 + LLM 报告 + 画像 knowledge_level 升级 + LLM 进阶推荐。

    闭合"路径完成 -> 目标达成评估 -> 画像升级 -> 进阶推荐"链路（偏差 F 评估闭环）。
    评估后路径 status 从 active 流转为 completed。
    """
    try:
        from services.evaluation_service import evaluate_path

        result = await evaluate_path(session, current_user.id, path_id)
        await session.commit()

        logger.info(
            f"📊 路径评估完成: user={current_user.id}, path={path_id}, "
            f"achievement={result['achievement_score']}, "
            f"level_upgraded={result['level_upgraded']}"
        )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=result,
        )
    except ValueError as e:
        return BaseResponse(
            code=HTTP_NOT_FOUND, message=str(e), data=None
        )
    except Exception as e:
        logger.error(f"路径评估失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{path_id}/advance", response_model=BaseResponse)
async def create_advance_path(
    path_id: int = PathParam(..., description="原路径ID"),
    body: dict = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """基于评估推荐的 topic 创建进阶学习路径（一键创建）。

    复用 PathAgent 生成逻辑，传入推荐 topic + 用户画像。
    """
    try:
        body = body or {}
        topic = str(body.get("topic", "")).strip()
        reason = str(body.get("reason", "")).strip()

        if not topic:
            return BaseResponse(
                code=HTTP_BAD_REQUEST, message="缺少 topic 参数", data=None
            )

        # 校验原路径属于用户
        orig_stmt = select(LearningPath).where(
            LearningPath.id == path_id,
            LearningPath.user_id == current_user.id,
        )
        orig_result = await session.execute(orig_stmt)
        if not orig_result.scalar_one_or_none():
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NOT_FOUND, data=None
            )

        # 获取用户画像
        profile = await _get_user_profile(session, current_user.id)

        # 调用 PathAgent 生成新路径
        agent_result = await _generate_path_with_agent(
            user_id=current_user.id,
            topic=topic,
            goal=reason or f"进阶学习：{topic}",
            profile=profile,
        )
        path_steps = agent_result.get("learning_path", [])
        llm_title = agent_result.get("path_title", "")

        if not path_steps:
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message=f"无法生成进阶路径：{topic}（可能你已掌握相关知识点）",
                data=None,
            )

        title = llm_title or f"{topic}进阶学习路径"
        new_path = await _save_path_to_db(
            session=session,
            user_id=current_user.id,
            title=title,
            topic=topic,
            goal=reason or f"进阶学习：{topic}",
            path_steps=path_steps,
        )

        # 重新加载路径（含节点）
        await session.refresh(new_path)
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == new_path.id)
            .options(selectinload(LearningPath.nodes))
        )
        result = await session.execute(stmt)
        new_path = result.scalar_one()

        logger.info(
            f"🚀 进阶路径创建: user={current_user.id}, 原路径={path_id}, "
            f"新路径={new_path.id}, topic={topic}"
        )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_LEARNING_PATH_GENERATED,
            data=_path_to_response(new_path),
        )
    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_SERVER_ERROR, message="进阶路径生成超时，请重试", data=None
        )
    except Exception as e:
        logger.error(f"进阶路径创建失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.delete("/{path_id}", response_model=BaseResponse)
async def delete_learning_path(
    path_id: int = PathParam(..., description="路径ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """删除学习路径"""
    try:
        stmt = select(LearningPath).where(
            LearningPath.id == path_id,
            LearningPath.user_id == current_user.id,
        )
        result = await session.execute(stmt)
        path = result.scalar_one_or_none()

        if not path:
            return BaseResponse(
                code=HTTP_NOT_FOUND, message=MSG_LEARNING_PATH_NOT_FOUND, data=None
            )

        await session.delete(path)
        await session.flush()

        return BaseResponse(
            code=HTTP_OK, message="学习路径已删除", data=None
        )
    except Exception as e:
        logger.error(f"删除路径失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)
