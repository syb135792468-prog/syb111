"""
api/routes/progress.py - 学习进度接口
- 查询用户知识点学习进度
- 更新学习进度（完成/失败/学习中）
- 重置进度
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from api.schemas import BaseResponse
from models.database import get_db
from models.progress import LearningProgress
from utils.api_helpers import generate_request_id
from utils.logger import get_logger
from config.constants import (
    HTTP_OK, HTTP_NOT_FOUND, HTTP_SERVER_ERROR,
)

router = APIRouter(prefix="/progress", tags=["学习进度"])
logger = get_logger(__name__, task_id="progress_api")


@router.get("/{user_id}", response_model=BaseResponse)
async def get_progress(
    user_id: int,
    topic: Optional[str] = Query(None, description="知识点名称（可选，不传返回全部）"),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    try:
        conditions = [LearningProgress.user_id == user_id, LearningProgress.is_active == True]
        if topic:
            conditions.append(LearningProgress.topic == topic)

        stmt = select(LearningProgress).where(*conditions).order_by(LearningProgress.updated_at.desc())
        result = await session.execute(stmt)
        records = result.scalars().all()

        return BaseResponse(
            code=HTTP_OK,
            message="success",
            data=[r.to_dict() for r in records],
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"查询进度失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message="服务器错误", data=None, request_id=request_id)


@router.post("/update", response_model=BaseResponse)
async def update_progress(
    user_id: int = Query(...),
    topic: str = Query(..., min_length=1),
    status: Optional[str] = Query(None),
    score: Optional[float] = Query(None, ge=0, le=100),
    duration: Optional[int] = Query(None, ge=0),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    try:
        stmt = select(LearningProgress).where(
            LearningProgress.user_id == user_id,
            LearningProgress.topic == topic,
            LearningProgress.is_active == True,
        )
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            record = LearningProgress(user_id=user_id, topic=topic)
            session.add(record)

        record.update_progress(status=status, score=score, duration=duration)
        await session.flush()
        await session.refresh(record)

        return BaseResponse(
            code=HTTP_OK, message="success", data=record.to_dict(), request_id=request_id,
        )
    except Exception as e:
        logger.error(f"更新进度失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message="服务器错误", data=None, request_id=request_id)


@router.delete("/{user_id}", response_model=BaseResponse)
async def reset_progress(
    user_id: int,
    topic: Optional[str] = Query(None, description="知识点名称（可选，不传重置全部）"),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(generate_request_id),
):
    try:
        conditions = [LearningProgress.user_id == user_id, LearningProgress.is_active == True]
        if topic:
            conditions.append(LearningProgress.topic == topic)

        stmt = select(LearningProgress).where(*conditions)
        result = await session.execute(stmt)
        records = result.scalars().all()

        for r in records:
            r.soft_delete()

        return BaseResponse(
            code=HTTP_OK, message=f"已重置 {len(records)} 条进度记录", data=None, request_id=request_id,
        )
    except Exception as e:
        logger.error(f"重置进度失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message="服务器错误", data=None, request_id=request_id)


@router.get("/health", response_model=BaseResponse)
async def health(request_id: str = Depends(generate_request_id)):
    return BaseResponse(
        code=HTTP_OK, message="success",
        data={"status": "ok", "service": "progress"},
        request_id=request_id,
    )
