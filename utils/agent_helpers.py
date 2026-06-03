"""
utils/agent_helpers.py - Agent 共享工具函数
从多个 Agent 中提取的重复逻辑，统一维护。
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional

from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import KP_PARTIAL_MATCH_MIN_LENGTH, KP_KEYWORD_MIN_LENGTH


def match_knowledge_point(text: str) -> Optional[str]:
    """
    将用户输入匹配到标准知识点。
    匹配优先级：精确匹配 > 编程关键字别名 > 完整KP在输入中 > 输入在KP中(≥2字符) > 关键词匹配。

    Args:
        text: 用户输入

    Returns:
        匹配到的知识点字符串，无匹配返回 None
    """
    import re
    text_lower = text.lower().strip()

    # 0. 编程关键字别名（短关键字无法通过分割提取）
    _CODE_ALIASES = {
        "def": "函数定义与调用",
        "return": "函数定义与调用",
        "for": "循环（for/while）",
        "while": "循环（for/while）",
        "if": "条件判断（if/elif/else）",
        "elif": "条件判断（if/elif/else）",
        "else": "条件判断（if/elif/else）",
        "class": "类与对象",
        "try": "异常处理",
        "except": "异常处理",
        "import": "模块与包",
        "list": "列表与元组",
        "tuple": "列表与元组",
        "dict": "字典与集合",
        "set": "字典与集合",
        "str": "字符串操作",
        "int": "变量与数据类型",
        "float": "变量与数据类型",
        "bool": "变量与数据类型",
        "open": "文件操作",
        "read": "文件操作",
        "write": "文件操作",
    }
    if text_lower in _CODE_ALIASES:
        return _CODE_ALIASES[text_lower]

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
        # 唯一匹配，直接返回
        return partial_matches[0]
    if len(partial_matches) > 1:
        # 多个匹配：≥2字符时返回最短KP；1字符时要求KP以该字开头（更精确）
        if len(text_lower) >= KP_PARTIAL_MATCH_MIN_LENGTH:
            return min(partial_matches, key=len)
        else:
            # 单字匹配：优先返回以该字开头的最短KP
            starts_with = [kp for kp in partial_matches if kp.lower().startswith(text_lower)]
            if starts_with:
                return min(starts_with, key=len)
            return min(partial_matches, key=len)

    # 4. 关键词匹配：提取知识点中的关键词，检查用户输入是否包含
    for kp in PYTHON_KNOWLEDGE_POINTS:
        keywords = re.split(r'[（）、。，：/、，。\s与()]+', kp.lower())
        keywords = [kw for kw in keywords if len(kw) >= KP_KEYWORD_MIN_LENGTH]
        for kw in keywords:
            if kw in text_lower:
                return kp

    # 5. 反向子串匹配：检查输入中是否有中文子串出现在某个知识点中
    #    例如 "我想学习函数" 中 "函数" 是 "函数定义与调用" 的子串
    _FILLER = '想学习怎么如何给我出看看讲讲告诉什么的是帮请想要能不能可以吗呢吧啊哦嗯'
    text_chinese = re.sub(r'[^一-鿿]', '', text_lower)
    text_cleaned = re.sub(r'[' + _FILLER + ']', '', text_chinese)
    if len(text_cleaned) >= 2:
        for kp in PYTHON_KNOWLEDGE_POINTS:
            kp_lower = kp.lower()
            for length in range(len(text_cleaned), 1, -1):
                for start in range(len(text_cleaned) - length + 1):
                    substr = text_cleaned[start:start + length]
                    if substr in kp_lower:
                        return kp

    # 6. 英文关键字匹配（处理 "def关键字怎么用" 这类混合输入）
    #    在单字中文匹配之前执行，避免 "def关键字" 中 "字" 误匹配 "字典与集合"
    text_alpha = re.sub(r'[^a-z]', '', text_lower)
    if text_alpha in _CODE_ALIASES:
        return _CODE_ALIASES[text_alpha]
    for alias, kp in _CODE_ALIASES.items():
        if len(alias) >= 2 and re.search(r'(?<![a-z])' + re.escape(alias) + r'(?![a-z])', text_lower):
            return kp

    # 7. 单字中文匹配（最后兜底，仅当输入中无英文关键字时）
    #    避免 "default值" 中 "值" 误匹配 "函数参数与返回值"
    if len(text_cleaned) <= 1 and not text_alpha:
        for ch in text_chinese:
            if ch in _FILLER:
                continue
            starts_with = [kp for kp in PYTHON_KNOWLEDGE_POINTS if kp.lower().startswith(ch)]
            if starts_with:
                return min(starts_with, key=len)
            contains = [kp for kp in PYTHON_KNOWLEDGE_POINTS if ch in kp.lower()]
            if contains:
                return min(contains, key=len)

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
