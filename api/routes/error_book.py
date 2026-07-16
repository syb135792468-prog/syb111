"""
api/routes/error_book.py - 错题本接口
- GET  /api/error-book/{user_id}          列表（支持筛选）
- GET  /api/error-book/{user_id}/due      待复习列表（艾宾浩斯）
- POST /api/error-book/{id}/review        记录复习结果
- POST /api/error-book/{id}/mastered      标记已掌握
- POST /api/error-book/{id}/tutor-video   生成辅导短视频（异步，返回 task_id）
- DELETE /api/error-book/{id}              删除条目
"""
from __future__ import annotations

import uuid
from typing import Optional, AsyncGenerator
from datetime import datetime, UTC

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import BaseResponse
from models.database import AsyncSessionLocal
from models.error_book import ErrorBook
from models.user import User
from api.routes.auth import get_current_user
from ai.spaced_repetition import get_next_review_time, is_due_for_review
from config.constants import (
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_SERVER_ERROR,
    ERROR_BOOK_DEFAULT_LIMIT, ERROR_BOOK_MAX_LIMIT,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_ERROR_BOOK_ITEM_NOT_FOUND,
    MSG_ERROR_BOOK_MASTERED, MSG_DELETE_SUCCESS,
    MSG_ERROR_BOOK_REVIEW_RECORDED, MSG_ERROR_BOOK_NO_DUE_ITEMS,
)
from utils.logger import get_logger

router = APIRouter(prefix="/error-book", tags=["错题本"])
logger = get_logger(__name__, task_id="error_book_api")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@router.get("/{user_id}", response_model=BaseResponse)
async def list_error_book(
    user_id: int,
    knowledge_point: Optional[str] = Query(None),
    difficulty: Optional[str] = Query(None),
    mastered: Optional[bool] = Query(None),
    limit: int = Query(ERROR_BOOK_DEFAULT_LIMIT, ge=1, le=ERROR_BOOK_MAX_LIMIT),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        if user_id != current_user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_ERROR_BOOK_ITEM_NOT_FOUND, data=None)
        conditions = [ErrorBook.user_id == current_user.id]
        if knowledge_point:
            conditions.append(ErrorBook.knowledge_point == knowledge_point)
        if difficulty:
            conditions.append(ErrorBook.difficulty == difficulty)
        if mastered is not None:
            conditions.append(ErrorBook.mastered == mastered)

        count_stmt = select(func.count(ErrorBook.id)).where(*conditions)
        total = (await session.execute(count_stmt)).scalar() or 0

        stmt = (
            select(ErrorBook)
            .where(*conditions)
            .order_by(ErrorBook.last_wrong_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return BaseResponse(
            code=HTTP_OK, message=MSG_SUCCESS,
            data={
                "items": [item.to_dict() for item in items],
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        )
    except Exception as e:
        logger.error(f"获取错题本失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/{user_id}/due", response_model=BaseResponse)
async def list_due_reviews(
    user_id: int,
    limit: int = Query(ERROR_BOOK_DEFAULT_LIMIT, ge=1, le=ERROR_BOOK_MAX_LIMIT),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取到期待复习的错题（按 next_review_at 升序）。"""
    try:
        if user_id != current_user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_ERROR_BOOK_ITEM_NOT_FOUND, data=None)
        now = datetime.now(UTC)
        conditions = [
            ErrorBook.user_id == current_user.id,
            ErrorBook.mastered == False,
        ]

        # 优先返回已到期的；如果全部未到期则返回最近的
        count_stmt = select(func.count(ErrorBook.id)).where(*conditions)
        total = (await session.execute(count_stmt)).scalar() or 0

        # 已到期的题目
        due_conditions = conditions + [
            (ErrorBook.next_review_at <= now) | (ErrorBook.next_review_at.is_(None))
        ]
        due_count_stmt = select(func.count(ErrorBook.id)).where(*due_conditions)
        due_count = (await session.execute(due_count_stmt)).scalar() or 0

        stmt = (
            select(ErrorBook)
            .where(due_conditions)
            .order_by(ErrorBook.next_review_at.asc().nullsfirst())
            .limit(limit)
        )
        result = await session.execute(stmt)
        items = result.scalars().all()

        return BaseResponse(
            code=HTTP_OK, message=MSG_SUCCESS,
            data={
                "items": [item.to_dict() for item in items],
                "total": total,
                "due_count": due_count,
            },
        )
    except Exception as e:
        logger.error(f"获取待复习列表失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{item_id}/review", response_model=BaseResponse)
async def record_review(
    item_id: int,
    quality: int = Query(..., ge=0, le=5, description="复习质量 0-5"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """
    记录一次复习结果，根据 SM-2 算法更新下次复习时间。
    quality: 0=完全忘记, 1=错误但有印象, 2=错误但熟悉, 3=正确但费力, 4=正确略有犹豫, 5=完美
    """
    try:
        item = await session.get(ErrorBook, item_id)
        if not item or item.user_id != current_user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_ERROR_BOOK_ITEM_NOT_FOUND, data=None)

        next_review_at, new_interval, new_ef, new_rep = get_next_review_time(
            quality=quality,
            repetition_count=item.repetition_count,
            easiness_factor=item.easiness_factor,
            current_interval_days=item.review_interval_days,
        )

        item.next_review_at = next_review_at
        item.review_interval_days = new_interval
        item.easiness_factor = new_ef
        item.repetition_count = new_rep

        # 连续正确 5 次自动标记掌握
        if new_rep >= 5:
            item.mastered = True

        await session.commit()
        return BaseResponse(
            code=HTTP_OK, message=MSG_ERROR_BOOK_REVIEW_RECORDED,
            data=item.to_dict(),
        )
    except Exception as e:
        logger.error(f"记录复习失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{item_id}/mastered", response_model=BaseResponse)
async def mark_mastered(
    item_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        item = await session.get(ErrorBook, item_id)
        if not item or item.user_id != current_user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_ERROR_BOOK_ITEM_NOT_FOUND, data=None)

        item.mastered = True
        await session.commit()
        return BaseResponse(code=HTTP_OK, message=MSG_ERROR_BOOK_MASTERED, data=item.to_dict())
    except Exception as e:
        logger.error(f"标记已掌握失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{item_id}/tutor-video", response_model=BaseResponse)
async def generate_tutor_video(
    item_id: int,
    current_user: User = Depends(get_current_user),
):
    """为指定错题生成辅导短视频（异步，返回 task_id，前端轮询 /tasks/{task_id}）。

    闭合"答错题 -> 错题本 -> 辅导短视频"链路（偏差 D）。
    """
    try:
        async with AsyncSessionLocal() as session:
            item = await session.get(ErrorBook, item_id)
            if not item or item.user_id != current_user.id:
                return BaseResponse(
                    code=HTTP_NOT_FOUND,
                    message=MSG_ERROR_BOOK_ITEM_NOT_FOUND,
                    data=None,
                )

            error_context = {
                "error_book_id": item.id,
                "knowledge_point": item.knowledge_point or "",
                "error_type": item.error_type or "other",
                "question_text": item.question_text or "",
                "user_answer": item.user_answer or "",
                "correct_answer": item.correct_answer or "",
                "explanation": item.explanation or "",
            }

        from api.task_store import register_task
        from api.routes.resource import _run_async_generation, ResourceRequest, get_request_id
        from config.constants import RESOURCE_TYPE_TUTOR_VIDEO

        task_id = str(uuid.uuid4())
        req = ResourceRequest(
            user_id=str(item.user_id),
            topic=item.knowledge_point or "错题辅导",
            resource_type=RESOURCE_TYPE_TUTOR_VIDEO,
            config={"error_context": error_context},
        )
        register_task(task_id, RESOURCE_TYPE_TUTOR_VIDEO, req.topic)
        import asyncio
        asyncio.create_task(_run_async_generation(task_id, req, get_request_id()))

        logger.info(f"🎬 辅导短视频生成任务已提交: item={item_id}, user={item.user_id}, task={task_id}")
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={"task_id": task_id, "error_context": error_context},
        )
    except Exception as e:
        logger.error(f"生成辅导短视频失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.delete("/{item_id}", response_model=BaseResponse)
async def delete_error_book(
    item_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    try:
        item = await session.get(ErrorBook, item_id)
        if not item or item.user_id != current_user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_ERROR_BOOK_ITEM_NOT_FOUND, data=None)

        await session.delete(item)
        await session.commit()
        return BaseResponse(code=HTTP_OK, message=MSG_DELETE_SUCCESS, data=None)
    except Exception as e:
        logger.error(f"删除错题失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)
