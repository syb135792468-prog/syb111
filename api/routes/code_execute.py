"""
api/routes/code_execute.py - 代码执行接口（加固版）
- POST /api/code/execute    执行 Python 代码（带限流）
- GET  /api/code/metrics    获取执行器全局指标
"""
from __future__ import annotations

import time
import asyncio

from collections import defaultdict
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.schemas import BaseResponse
from config.constants import (
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE,
    CODE_EXEC_DEFAULT_TIMEOUT, CODE_EXEC_MIN_TIMEOUT, CODE_EXEC_MAX_TIMEOUT,
    CODE_EXEC_RATE_LIMIT_PER_MIN, CODE_EXEC_RATE_LIMIT_WINDOW_SEC,
)
from config.messages import MSG_SUCCESS, MSG_CODE_EMPTY, MSG_CODE_EXEC_FAILED
from utils.code_executor import execute_python_code, get_executor_metrics
from utils.logger import get_logger
from models.database import get_db, AsyncSessionLocal
from models.user import User
from api.routes.auth import get_current_user

router = APIRouter(prefix="/code", tags=["代码执行"])
logger = get_logger(__name__, task_id="code_execute_api")

# ============================================================
# 用户级别限流器（内存实现）
# ============================================================
_rate_limit_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(user_key: str) -> bool:
    """检查是否超过限流，返回 True 表示允许"""
    now = time.monotonic()
    window_start = now - CODE_EXEC_RATE_LIMIT_WINDOW_SEC
    # 清理过期记录
    timestamps = _rate_limit_store[user_key]
    _rate_limit_store[user_key] = [t for t in timestamps if t > window_start]
    # 检查是否超限
    if len(_rate_limit_store[user_key]) >= CODE_EXEC_RATE_LIMIT_PER_MIN:
        return False
    _rate_limit_store[user_key].append(now)
    return True


def _get_client_ip(request: Request) -> str:
    """获取客户端标识（优先 X-Forwarded-For，兜底为 host）"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ============================================================
# 接口
# ============================================================
@router.post("/execute", response_model=BaseResponse)
async def run_code(
    body: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    try:
        code = body.get("code", "")
        if not code.strip():
            return BaseResponse(code=HTTP_BAD_REQUEST, message=MSG_CODE_EMPTY, data=None)

        # 限流检查
        client_id = _get_client_ip(request)
        if not _check_rate_limit(client_id):
            logger.warning(f"限流触发 | client={client_id}")
            return BaseResponse(
                code=HTTP_SERVICE_UNAVAILABLE,
                message=f"执行过于频繁，每分钟最多 {CODE_EXEC_RATE_LIMIT_PER_MIN} 次",
                data=None,
            )

        timeout = body.get("timeout", CODE_EXEC_DEFAULT_TIMEOUT)
        timeout = max(CODE_EXEC_MIN_TIMEOUT, min(timeout, CODE_EXEC_MAX_TIMEOUT))

        result = await execute_python_code(code, timeout=timeout)

        # 仅当带 knowledge_point 时异步回写 code_run 证据
        # playground 不传 knowledge_point，自然不写；测验代码题由 quiz.py 单独走 record_code_evidence
        # 失败时走 weak_signal 机制：首次同类异常不降 posterior，累计达阈值才降
        knowledge_point = body.get("knowledge_point")
        if knowledge_point:
            success = bool(result.get("success", False))

            async def _write_code_evidence():
                try:
                    async with AsyncSessionLocal() as graph_db:
                        async with graph_db.begin():
                            from services.mastery_service import _resolve_node_by_name, record_playground_code_evidence
                            node = await _resolve_node_by_name(graph_db, knowledge_point)
                            if not node:
                                return
                            await record_playground_code_evidence(
                                graph_db, current_user.id, node.code,
                                success=success,
                                stderr=result.get("stderr", "") or "",
                            )
                except Exception as e:
                    logger.warning(f"⚠️ code_run 证据回写失败: {e}")

            asyncio.create_task(_write_code_evidence())

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=result,
        )
    except Exception as e:
        logger.error(f"代码执行失败: {e}", exc_info=True)
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"{MSG_CODE_EXEC_FAILED}: {str(e)}",
            data=None
        )


@router.get("/metrics", response_model=BaseResponse)
async def code_metrics():
    """获取代码执行器全局指标"""
    return BaseResponse(
        code=HTTP_OK,
        message=MSG_SUCCESS,
        data=get_executor_metrics(),
    )
