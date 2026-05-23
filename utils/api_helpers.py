"""
utils/api_helpers.py - API 路由共享工具函数
从多个路由文件中提取的重复逻辑，统一维护。
"""
from __future__ import annotations
from datetime import datetime, UTC
import uuid


def generate_request_id() -> str:
    """生成唯一请求 ID"""
    return str(uuid.uuid4())


def get_current_utc_time() -> datetime:
    """获取无时区 UTC 时间（SQLite 兼容）"""
    return datetime.now(UTC).replace(tzinfo=None)
