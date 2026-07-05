"""
utils/agent_helpers.py - Agent 共享工具函数
从多个 Agent 中提取的重复逻辑，统一维护。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from config.model_config import PYTHON_KNOWLEDGE_POINTS, CODE_KEYWORD_ALIASES
from config.constants import KP_PARTIAL_MATCH_MIN_LENGTH, KP_KEYWORD_MIN_LENGTH


def match_knowledge_point(text: str) -> Optional[str]:
    """
    将用户输入匹配到标准知识点。只做高置信度匹配，模糊匹配返回None由调用方决定。

    匹配优先级：编程关键字别名 > 精确匹配 > 完整KP在输入中 > 输入在KP中 > 英文关键字。

    Args:
        text: 用户输入

    Returns:
        匹配到的知识点字符串，无匹配返回 None
    """
    import re
    text_lower = text.lower().strip()

    # 0. 编程关键字别名（短关键字无法通过分割提取）
    if text_lower in CODE_KEYWORD_ALIASES:
        return CODE_KEYWORD_ALIASES[text_lower]

    # 1. 精确匹配
    for kp in PYTHON_KNOWLEDGE_POINTS:
        if text_lower == kp.lower():
            return kp

    # 2. 完整知识点名出现在用户输入中（输入较长，如"学习列表与元组"）
    #    优先返回最长匹配（最精确）
    full_matches = [kp for kp in PYTHON_KNOWLEDGE_POINTS if kp.lower() in text_lower]
    if full_matches:
        return max(full_matches, key=len)

    # 3. 用户输入出现在知识点名中（输入较短，如"列表" → "列表与元组"）
    #    优先返回最短的KP（更精确的匹配）
    partial_matches = [kp for kp in PYTHON_KNOWLEDGE_POINTS if text_lower in kp.lower()]
    if len(partial_matches) == 1:
        return partial_matches[0]
    if len(partial_matches) > 1:
        if len(text_lower) >= KP_PARTIAL_MATCH_MIN_LENGTH:
            return min(partial_matches, key=len)
        else:
            starts_with = [kp for kp in partial_matches if kp.lower().startswith(text_lower)]
            if starts_with:
                return min(starts_with, key=len)
            return min(partial_matches, key=len)

    # 4. 英文关键字匹配（处理 "def关键字怎么用" 这类混合输入）
    text_alpha = re.sub(r'[^a-z]', '', text_lower)
    if text_alpha in CODE_KEYWORD_ALIASES:
        return CODE_KEYWORD_ALIASES[text_alpha]
    for alias, kp in CODE_KEYWORD_ALIASES.items():
        if len(alias) >= KP_KEYWORD_MIN_LENGTH and re.search(r'(?<![a-z])' + re.escape(alias) + r'(?![a-z])', text_lower):
            return kp

    # 无高置信度匹配，返回 None（调用方用原始输入或LLM提取）
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


# ------ 知识点分类稳定性 ------

# 掌握度阈值：progress score >= 此值才允许从薄弱改为掌握
MASTERY_EVIDENCE_THRESHOLD = 75.0
# 薄弱度阈值：progress score < 此值才允许从掌握改为薄弱
WEAK_EVIDENCE_THRESHOLD = 50.0

