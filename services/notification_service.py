"""
services/notification_service.py - 用户实时通知推送中心

per-user asyncio.Queue 单进程内存通知中心，配合 api/routes/notification.py
的 SSE 长连接端点，让前端实时感知路径变更/资源生成/评估完成/测验同步等事件。

设计权衡：
- 单进程内存：与 api/task_store.py 一致，多实例部署需换 Redis Pub/Sub（本次不做）
- 队列容量上限 100：避免慢消费者无限堆积，超容量丢弃最旧消息
- 队列不存在即丢弃：用户未订阅时不缓存历史消息（push 是 best-effort）
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Set

from utils.logger import get_logger

logger = get_logger(__name__, task_id="notification")

_QUEUE_MAXSIZE = 100
_user_queues: Dict[int, Set[asyncio.Queue]] = {}


def subscribe(user_id: int) -> asyncio.Queue:
    """Create an independent queue for each browser connection."""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    _user_queues.setdefault(user_id, set()).add(queue)
    return queue


def unsubscribe(user_id: int, queue: asyncio.Queue) -> None:
    """Remove only the disconnected browser's queue."""
    queues = _user_queues.get(user_id)
    if not queues:
        return
    queues.discard(queue)
    if not queues:
        _user_queues.pop(user_id, None)


async def push_notification(user_id: int, event_type: str, data: Dict[str, Any]) -> None:
    """向用户推送一条通知事件。best-effort：无订阅者或队列满则丢弃/挤掉最旧。"""
    queues = tuple(_user_queues.get(user_id, ()))
    if not queues:
        return
    payload = {"type": event_type, "data": data}
    for queue in queues:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                queue.get_nowait()
                queue.put_nowait(payload)
            except Exception:
                logger.warning(f"通知队列满且无法腾位: user={user_id}, event={event_type}")
    logger.info(f"📨 通知已推送: user={user_id}, event={event_type}")


def format_sse(event_type: str, data: Dict[str, Any]) -> str:
    """格式化为 SSE 事件块。"""
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
