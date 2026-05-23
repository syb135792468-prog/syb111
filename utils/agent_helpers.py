"""
utils/agent_helpers.py - Agent 共享工具函数
从多个 Agent 中提取的重复逻辑，统一维护。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from config.model_config import PYTHON_KNOWLEDGE_POINTS


def match_knowledge_point(text: str) -> Optional[str]:
    """
    将用户输入匹配到标准知识点。
    遍历 PYTHON_KNOWLEDGE_POINTS，返回第一个在 text 中出现的知识点。

    Args:
        text: 用户输入（已转小写）

    Returns:
        匹配到的知识点字符串，无匹配返回 None
    """
    for kp in PYTHON_KNOWLEDGE_POINTS:
        if kp.lower() in text:
            return kp
    return None


def get_profile_from_context(context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    从 context 中安全提取 profile_data。

    Args:
        context: 上下文字典，可为 None

    Returns:
        profile_data 字典，无数据返回空字典
    """
    if not context:
        return {}
    return context.get("profile_data", {})


def append_resource_to_list(
    context: Optional[Dict[str, Any]],
    resource: Any,
) -> List[Any]:
    """
    不可变地将 resource 追加到 context["resource_list"]。

    Args:
        context: 上下文字典，可为 None
        resource: 要追加的资源对象

    Returns:
        新的资源列表（不修改原列表）
    """
    old_resources = context.get("resource_list", []) if context else []
    return list(old_resources) + [resource]


def build_resource_result(
    resource_list: List[Any],
    updated_at: Any,
) -> Dict[str, Any]:
    """
    构建资源 Agent 标准返回字典。

    Args:
        resource_list: 资源列表
        updated_at: 时间戳

    Returns:
        标准状态更新字典
    """
    return {
        "resource_list": resource_list,
        "current_step": "resource",
        "updated_at": updated_at,
    }
