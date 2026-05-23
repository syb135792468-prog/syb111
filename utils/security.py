"""
utils/security.py - 内容安全工具
- 输入内容校验（长度、空值、敏感词基础过滤）
- 配合 llm_client.py 的 ContentSecurityError 被动拦截使用
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

from utils.logger import get_logger

logger = get_logger(__name__, task_id="security")

# 基础敏感关键词（实际生产环境应从配置文件加载）
BANNED_PATTERNS = [
    r"(?:hack|exploit|inject)\s*(?:system|server|database)",
    r"(?:rm\s+-rf|DROP\s+TABLE|DELETE\s+FROM)",
]


def validate_user_input(text: str, max_length: int = 2000) -> Tuple[bool, Optional[str]]:
    """
    校验用户输入是否合法。

    Returns:
        (is_valid, error_message)
    """
    if not text or not text.strip():
        return False, "输入内容不能为空"

    if len(text) > max_length:
        return False, f"输入内容超出最大长度限制（{max_length}字符）"

    return True, None


def sanitize_input(text: str) -> str:
    """清理用户输入：去除首尾空白、限制长度"""
    text = text.strip()
    if len(text) > 2000:
        text = text[:2000]
    return text


def check_content_safety(text: str) -> Tuple[bool, Optional[str]]:
    """
    基础内容安全检查（关键词匹配）。
    注意：主要安全拦截由 llm_client.py 的被动拦截机制处理。

    Returns:
        (is_safe, reason)
    """
    text_lower = text.lower()
    for pattern in BANNED_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.warning(f"内容安全检查命中: pattern={pattern}")
            return False, "输入内容包含不允许的关键词"
    return True, None
