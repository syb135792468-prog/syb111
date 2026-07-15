"""
api/routes/playground.py - 自由练习出题接口
- POST /api/playground/generate-code-quiz  按知识点+难度生成编程题

生成的题目持久化为 Resource(resource_type="quiz")，提交判分复用 /api/quiz/{resource_id}/submit，
自动走 ErrorBook + 图谱证据 + 路径节点同步的完整错题闭环。
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agents.quiz_agent import QuizAgent
from api.routes.auth import get_current_user
from api.routes.quiz import _parse_single_question
from api.schemas import BaseResponse
from config.constants import (
    HTTP_BAD_REQUEST, HTTP_OK, HTTP_SERVER_ERROR,
    RESOURCE_PROGRESS_COMPLETE, RESOURCE_GENERATE_TIMEOUT_SEC,
)
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.messages import MSG_SUCCESS
from models.database import get_db
from models.resource import Resource
from models.user import User
from utils.logger import get_logger

router = APIRouter(prefix="/playground", tags=["自由练习"])
logger = get_logger(__name__, task_id="playground_api")


@router.post("/generate-code-quiz", response_model=BaseResponse)
async def generate_code_quiz(
    body: dict,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """按知识点+难度生成编程题（自由练习）

    请求：{knowledge_point: str, difficulty: "easy"|"medium"|"hard"}
    返回：{resource_id, title, question_text, difficulty, knowledge_point, has_test_cases}
    （不含 answer/explanation，提交后由判分接口返回）
    """
    import asyncio

    knowledge_point = body.get("knowledge_point", "").strip()
    difficulty = body.get("difficulty", "medium").strip()

    # 参数校验
    if knowledge_point not in PYTHON_KNOWLEDGE_POINTS:
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=f"知识点无效，可选：{', '.join(PYTHON_KNOWLEDGE_POINTS[:5])}等",
            data=None,
        )
    if difficulty not in ("easy", "medium", "hard"):
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message="难度必须为 easy / medium / hard",
            data=None,
        )

    try:
        agent = QuizAgent(user_id=str(current_user.id))
        context = {
            "user_id": str(current_user.id),
            "topic": knowledge_point,
            "resource_list": [],
        }
        result = await asyncio.wait_for(
            agent.process(
                user_input=knowledge_point,
                context=context,
                quiz_type="code",
                difficulty=difficulty,
                force_knowledge_point=knowledge_point,
            ),
            timeout=RESOURCE_GENERATE_TIMEOUT_SEC,
        )

        items = result.get("resource_list", [])
        if not items:
            return BaseResponse(
                code=HTTP_SERVER_ERROR,
                message="出题失败，请稍后重试",
                data=None,
            )
        item = items[0]

        # 构造 ORM Resource（extra_metadata 加 source 标识，便于筛选）
        meta = dict(item.extra_metadata or {})
        meta["source"] = "free_practice"
        db_resource = Resource(
            user_id=current_user.id,
            task_id=str(uuid.uuid4()),
            resource_type="quiz",
            title=item.title,
            content=item.content,
            knowledge_points=item.knowledge_points or [knowledge_point],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            in_library=False,
            extra_metadata=meta,
        )
        session.add(db_resource)
        await session.commit()
        await session.refresh(db_resource)

        # 写 question_knowledge_map，让判分时的 record_code_evidence 和 _sync_learning_path_nodes
        # 能通过 resource_id+question_index 找到知识点节点（否则图谱证据和路径 mastery 不回写）
        try:
            from models.knowledge_graph import QuestionKnowledgeMap
            from services.mastery_service import _resolve_node_by_name
            node = await _resolve_node_by_name(session, knowledge_point)
            if node:
                session.add(QuestionKnowledgeMap(
                    resource_id=db_resource.id,
                    question_index=0,
                    node_code=node.code,
                    weight=1.0,
                ))
                await session.commit()
                logger.info(f"📋 question_knowledge_map 写入: resource={db_resource.id} node={node.code}")
            else:
                logger.warning(f"⚠️ 知识点 {knowledge_point} 未匹配到图谱节点，跳过映射")
        except Exception as map_err:
            logger.warning(f"⚠️ question_knowledge_map 写入失败（不影响出题）: {map_err}")

        # 解析题目正文（不含答案）
        parsed = _parse_single_question(db_resource.content, meta)
        question_text = parsed.get("questionText", "")

        logger.info(
            f"✅ 自由练习出题 | user={current_user.id} | kp={knowledge_point} | "
            f"difficulty={difficulty} | resource={db_resource.id} | "
            f"test_cases={len(meta.get('test_cases', []))}"
        )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "resource_id": db_resource.id,
                "title": db_resource.title,
                "question_text": question_text,
                "difficulty": meta.get("difficulty", difficulty),
                "knowledge_point": knowledge_point,
                "has_test_cases": bool(meta.get("test_cases")),
            },
        )

    except asyncio.TimeoutError:
        logger.warning(f"⚠️ 自由练习出题超时 | user={current_user.id} | kp={knowledge_point}")
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message="出题超时，请稍后重试",
            data=None,
        )
    except Exception as e:
        logger.error(f"❌ 自由练习出题失败: {e}", exc_info=True)
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"出题失败：{e}",
            data=None,
        )
