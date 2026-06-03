"""
api/routes/experiment.py - A/B 测试实验管理接口
- GET  /api/experiments                      列表
- GET  /api/experiments/{name}/analysis      分析（含统计检验）
- POST /api/experiments/{name}/status        更新状态
- GET  /api/experiments/{name}/users         分组详情
"""
from __future__ import annotations

from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import BaseResponse
from models.database import AsyncSessionLocal
from models.experiment import Experiment, ExperimentAssignment
from ai.experiment_engine import experiment_engine
from config.constants import (
    HTTP_OK, HTTP_NOT_FOUND, HTTP_BAD_REQUEST, HTTP_SERVER_ERROR,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_EXPERIMENT_NOT_FOUND,
    MSG_EXPERIMENT_ANALYSIS, MSG_EXPERIMENT_STATUS_UPDATED,
)
from utils.logger import get_logger

router = APIRouter(prefix="/experiments", tags=["A/B测试"])
logger = get_logger(__name__, task_id="experiment_api")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@router.get("", response_model=BaseResponse)
async def list_experiments(session: AsyncSession = Depends(get_db)):
    """获取所有实验列表及分组统计"""
    try:
        experiments = await experiment_engine.get_experiment_list(session)
        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data=experiments)
    except Exception as e:
        logger.error(f"获取实验列表失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/{name}/analysis", response_model=BaseResponse)
async def get_analysis(name: str, session: AsyncSession = Depends(get_db)):
    """获取实验分析结果（含卡方检验等统计检验）"""
    try:
        analysis = await experiment_engine.get_experiment_analysis(name, session)
        if not analysis:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_EXPERIMENT_NOT_FOUND, data=None)
        return BaseResponse(code=HTTP_OK, message=MSG_EXPERIMENT_ANALYSIS, data=analysis)
    except Exception as e:
        logger.error(f"获取实验分析失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{name}/status", response_model=BaseResponse)
async def update_status(
    name: str,
    status: str = Query(..., description="新状态: draft/active/completed"),
    session: AsyncSession = Depends(get_db),
):
    """更新实验状态"""
    try:
        if status not in ("draft", "active", "completed"):
            return BaseResponse(code=HTTP_BAD_REQUEST, message="状态必须是 draft/active/completed", data=None)

        result = await session.execute(
            select(Experiment).where(Experiment.name == name)
        )
        experiment = result.scalar_one_or_none()
        if not experiment:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_EXPERIMENT_NOT_FOUND, data=None)

        experiment.status = status
        await session.commit()
        return BaseResponse(
            code=HTTP_OK, message=MSG_EXPERIMENT_STATUS_UPDATED,
            data=experiment.to_dict(),
        )
    except Exception as e:
        logger.error(f"更新实验状态失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/{name}/users", response_model=BaseResponse)
async def list_assignments(name: str, session: AsyncSession = Depends(get_db)):
    """获取实验的用户分组详情"""
    try:
        result = await session.execute(
            select(Experiment).where(Experiment.name == name)
        )
        experiment = result.scalar_one_or_none()
        if not experiment:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_EXPERIMENT_NOT_FOUND, data=None)

        result = await session.execute(
            select(ExperimentAssignment)
            .where(ExperimentAssignment.experiment_id == experiment.id)
            .order_by(ExperimentAssignment.assigned_at.desc())
            .limit(200)
        )
        assignments = result.scalars().all()

        # 按变体汇总
        variant_counts: dict = {}
        for a in assignments:
            variant_counts[a.variant] = variant_counts.get(a.variant, 0) + 1

        return BaseResponse(
            code=HTTP_OK, message=MSG_SUCCESS,
            data={
                "experiment": experiment.to_dict(),
                "assignments": [a.to_dict() for a in assignments],
                "variant_counts": variant_counts,
            },
        )
    except Exception as e:
        logger.error(f"获取分组详情失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)
