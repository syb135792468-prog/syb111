"""
api/routes/notification.py - 用户实时通知 SSE 长连接端点

客户端通过 fetch + ReadableStream 订阅 GET /api/notifications/stream，
接收路径变更/资源生成/评估完成/测验同步/辅导视频就绪等事件。

事件类型：
- path_updated: 检测到薄弱点自动插入复习节点
- path_reordered: 路径手动重排
- evaluation_completed: 路径评估完成（含画像升级信息）
- quiz_synced: 测验结果同步到路径节点
- resource_ready: 异步资源生成完成
- tutor_video_ready: 错题辅导视频生成完成
"""
import asyncio

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from api.routes.auth import get_current_user
from models.user import User
from services.notification_service import subscribe, unsubscribe, format_sse
from utils.logger import get_logger

logger = get_logger(__name__, task_id="notification_api")

router = APIRouter(prefix="/notifications", tags=["通知推送"])

HEARTBEAT_SEC = 15  # 心跳间隔，防止代理超时关闭连接


@router.get("/stream")
async def notification_stream(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """SSE 长连接：推送用户专属通知事件。"""
    user_id = current_user.id
    queue = subscribe(user_id)
    logger.info(f"🔌 通知 SSE 连接建立: user={user_id}")

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SEC)
                    yield format_sse(event["type"], event["data"])
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            logger.info(f"🔌 通知 SSE 连接断开: user={user_id}")
            unsubscribe(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
