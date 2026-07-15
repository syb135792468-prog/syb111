"""
api/routes/course.py - 课程信息接口（赛题对齐：高等教育 Python 课程入口展示）

提供 GET /api/course/info，返回课程基本信息 + 知识点大纲（标注掌握状态） + 学习进度统计。
前端课程概览页和侧边栏课程信息卡由此接口取数据。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVER_ERROR
from config.messages import MSG_SUCCESS
from config.model_config import COMPETITION_INFO, PYTHON_KNOWLEDGE_POINTS
from models.resource import Resource
from models.error_book import ErrorBook
from api.routes.resource import load_profile_context, get_user_or_404, get_db, get_request_id
from api.schemas import BaseResponse
from utils.logger import get_logger

router = APIRouter(prefix="/course", tags=["课程信息"])
logger = get_logger(__name__, task_id="course_api")


@router.get("/info", response_model=BaseResponse)
async def get_course_info(
    user_id: int = Query(..., description="用户ID"),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id),
):
    """返回课程基本信息 + 知识点大纲（标注掌握状态） + 学习进度统计。"""
    try:
        await get_user_or_404(session, user_id)
        profile_ctx = await load_profile_context(session, user_id)

        weak = set(profile_ctx.get("weak_points", []) or [])
        mastered = set(profile_ctx.get("mastered_points", []) or [])
        outline = []
        for idx, kp in enumerate(PYTHON_KNOWLEDGE_POINTS, 1):
            status = "mastered" if kp in mastered else ("weak" if kp in weak else "not_started")
            outline.append({"order": idx, "name": kp, "status": status})

        resource_count = (await session.execute(
            select(func.count(Resource.id)).where(
                Resource.user_id == user_id, Resource.is_active == True
            )
        )).scalar() or 0
        error_count = (await session.execute(
            select(func.count(ErrorBook.id)).where(ErrorBook.user_id == user_id)
        )).scalar() or 0

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "course": {
                    "name": COMPETITION_INFO["course_name"],
                    "intro": COMPETITION_INFO["course_intro"],
                    "target": COMPETITION_INFO["course_target"],
                    "audience": COMPETITION_INFO["course_audience"],
                    "modules": COMPETITION_INFO["course_modules"],
                    "competition": {
                        "name": COMPETITION_INFO["name"],
                        "problem_id": COMPETITION_INFO["problem_id"],
                        "problem_name": COMPETITION_INFO["problem_name"],
                    },
                },
                "outline": outline,
                "progress": {
                    "mastered_count": len(mastered),
                    "weak_count": len(weak),
                    "total_points": len(PYTHON_KNOWLEDGE_POINTS),
                    "resource_count": resource_count,
                    "error_count": error_count,
                    "knowledge_level": profile_ctx.get("knowledge_level"),
                    "learning_goal": profile_ctx.get("learning_goal"),
                },
            },
            request_id=request_id,
        )
    except ValueError as e:
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"获取课程信息失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"获取课程信息失败: {e}",
            data=None,
            request_id=request_id,
        )
