"""
api/routes/multimodal.py - 多模态代码分析接口
- POST /api/multimodal/analyze - 流式SSE分析接口
- 事件流：code_recognition → analysis → exercises → end
- 支持保存分析结果到资源库
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    MultimodalAnalyzeRequest,
    SaveAnalysisRequest,
    BaseResponse,
    StreamEvent,
)
from api.routes.auth import get_current_user
from models.user import User
from models.database import get_db
from utils.logger import get_logger
from config.settings import settings

logger = get_logger(__name__, task_id="multimodal_api")

router = APIRouter(prefix="/multimodal", tags=["多模态代码分析"])


def _resolve_image_path(url: str) -> Optional[Path]:
    """将图片URL转为本地文件路径"""
    if not url.startswith("/static/uploads/images/"):
        return None
    path = settings.BASE_DIR / url.lstrip("/")
    return path if path.exists() else None


@router.post("/analyze", response_class=StreamingResponse)
async def analyze_code_image(
    request: MultimodalAnalyzeRequest,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    多模态代码分析 SSE 接口

    事件流：
    - code_recognition: 识别出的代码
    - analysis: 解释+诊断+知识点
    - exercises: 练习题
    - end: 分析完成
    - error: 错误
    """
    request_id = str(uuid.uuid4())
    user_id = str(current_user.id)

    # 验证图片存在
    image_path = _resolve_image_path(request.image_url)
    if not image_path:
        raise HTTPException(status_code=400, detail=f"图片文件不存在: {request.image_url}")

    logger.info(
        f"📸 开始多模态代码分析 | user={user_id} | image={request.image_url}",
        extra={"request_id": request_id},
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            from agents.multimodal_code_agent import get_multimodal_code_agent

            agent = get_multimodal_code_agent()

            # 发送开始事件
            start_event = StreamEvent(
                event="thinking",
                data={"text": "📸 正在分析代码图片...", "request_id": request_id},
                current_step="multimodal",
            )
            yield f"event: thinking\ndata: {start_event.model_dump_json()}\n\n"

            # 流式分析
            async for step_result in agent.process_stream(str(image_path)):
                event_type = step_result.get("event", "")
                event_data = step_result.get("data", {})

                if event_type == "code_recognition":
                    # 代码识别结果
                    sse_event = StreamEvent(
                        event="code_recognition",
                        data=event_data,
                        current_step="code_recognition",
                    )
                    yield f"event: code_recognition\ndata: {sse_event.model_dump_json()}\n\n"

                elif event_type == "analysis":
                    # 分析结果（解释+诊断+知识点）
                    sse_event = StreamEvent(
                        event="multimodal_analysis",
                        data=event_data,
                        current_step="analysis",
                    )
                    yield f"event: multimodal_analysis\ndata: {sse_event.model_dump_json()}\n\n"

                elif event_type == "exercises":
                    # 练习题
                    sse_event = StreamEvent(
                        event="multimodal_exercises",
                        data=event_data,
                        current_step="exercises",
                    )
                    yield f"event: multimodal_exercises\ndata: {sse_event.model_dump_json()}\n\n"

                elif event_type == "error":
                    # 错误
                    sse_event = StreamEvent(
                        event="error",
                        data=event_data,
                        current_step="error",
                    )
                    yield f"event: error\ndata: {sse_event.model_dump_json()}\n\n"
                    return

                elif event_type == "end":
                    # 结束
                    break

            # 发送结束事件
            end_event = StreamEvent(
                event="end",
                data={"request_id": request_id, "status": "completed"},
                current_step="completed",
            )
            yield f"event: end\ndata: {end_event.model_dump_json()}\n\n"

            logger.info(
                f"✅ 多模态代码分析完成 | user={user_id}",
                extra={"request_id": request_id},
            )

        except Exception as e:
            logger.error(
                f"❌ 多模态代码分析异常: {e}",
                exc_info=True,
                extra={"request_id": request_id},
            )
            error_event = StreamEvent(
                event="error",
                data={"error": str(e)},
                current_step="error",
            )
            yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
            "Access-Control-Expose-Headers": "X-Request-ID",
        },
    )


@router.post("/save", response_model=BaseResponse)
async def save_analysis_result(
    payload: SaveAnalysisRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    保存分析结果到资源库

    将多模态分析结果保存为 Resource，可在资源管理页面查看
    """
    from models.resource import Resource
    from config.constants import RESOURCE_PROGRESS_COMPLETE

    code_text = payload.code_text
    explanation = payload.explanation
    problems = payload.problems
    exercises = payload.exercises
    knowledge_points = payload.knowledge_points

    # 构建内容
    content = f"""## 代码识别结果

```python
{code_text}
```

## 代码解释

{explanation}

## 问题诊断

{problems}

## 练习题

{exercises}
"""

    # 创建资源
    resource = Resource(
        user_id=current_user.id,
        task_id=str(uuid.uuid4()),
        resource_type="multimodal",
        title=f"多模态代码分析 - {code_text[:50]}...",
        content=content,
        knowledge_points=knowledge_points,
        status="completed",
        progress_percent=RESOURCE_PROGRESS_COMPLETE,
        in_library=True,
        extra_metadata={
            "image_url": payload.image_url,
            "code_text": code_text,
            "explanation": explanation,
            "problems": [p.model_dump() for p in problems],
            "exercises": [e.model_dump() for e in exercises],
        },
    )

    db.add(resource)
    await db.commit()
    await db.refresh(resource)

    logger.info(f"✅ 分析结果已保存 | resource_id={resource.id} | user={current_user.id}")

    return BaseResponse(data={
        "id": resource.id,
        "title": resource.title,
        "resource_type": resource.resource_type,
    })


@router.get("/history", response_model=BaseResponse)
async def list_analysis_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    """获取多模态代码分析历史列表"""
    from models.resource import Resource

    conditions = [
        Resource.user_id == current_user.id,
        Resource.resource_type == "multimodal",
        Resource.is_active == True,
    ]

    # 总数
    count_q = select(func.count(Resource.id)).where(*conditions)
    total = (await db.execute(count_q)).scalar() or 0

    # 数据
    data_q = (
        select(Resource)
        .where(*conditions)
        .order_by(Resource.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(data_q)).scalars().all()

    items = []
    for r in rows:
        meta = r.extra_metadata or {}
        items.append({
            "id": r.id,
            "title": r.title,
            "code_text": meta.get("code_text", ""),
            "image_url": meta.get("image_url", ""),
            "explanation": meta.get("explanation", ""),
            "problems": meta.get("problems", []),
            "exercises": meta.get("exercises", []),
            "knowledge_points": r.knowledge_points or [],
            "in_library": r.in_library,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return BaseResponse(data={
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    })


@router.post("/{resource_id}/favorite", response_model=BaseResponse)
async def toggle_favorite(
    resource_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """收藏/取消收藏多模态分析结果"""
    from models.resource import Resource

    q = select(Resource).where(
        Resource.id == resource_id,
        Resource.user_id == current_user.id,
        Resource.resource_type == "multimodal",
        Resource.is_active == True,
    )
    resource = (await db.execute(q)).scalar_one_or_none()
    if not resource:
        raise HTTPException(status_code=404, detail="分析记录不存在")

    resource.in_library = not resource.in_library
    await db.commit()

    return BaseResponse(data={
        "id": resource.id,
        "in_library": resource.in_library,
    })


@router.get("/health", response_model=BaseResponse)
async def health():
    """健康检查（根据 VISION_PROVIDER 检查对应视觉模型）"""
    try:
        from config.settings import settings
        provider = (settings.VISION_PROVIDER or "ark").lower()
        if provider == "xf":
            from utils.xfyun_vision_api import xf_vision_api
            healthy = await xf_vision_api.health_check()
            api_name = "xf_vision_api"
        else:
            from utils.ark_vision_api import mimo_omni_api
            healthy = await mimo_omni_api.health_check()
            api_name = "ark_vision_api"
        return BaseResponse(data={
            "status": "ok" if healthy else "degraded",
            api_name: healthy,
            "provider": provider,
            "service": "multimodal",
        })
    except Exception as e:
        return BaseResponse(data={
            "status": "error",
            "error": str(e),
            "service": "multimodal",
        })
