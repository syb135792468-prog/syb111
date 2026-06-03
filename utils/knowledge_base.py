"""
utils/knowledge_base.py - 统一知识点管理系统
系统唯一的知识点权威来源，所有组件必须使用这里定义的标准。
解决前后端知识点名称不一致的问题。
"""
from __future__ import annotations
from typing import Dict, Optional, Set

# 后端标准知识点列表（与 config/model_config.py PYTHON_KNOWLEDGE_POINTS 完全一致）
BACKEND_KNOWLEDGE_POINTS: list[str] = [
    "变量与数据类型",
    "运算符与表达式",
    "条件判断（if/elif/else）",
    "循环（for/while）",
    "函数定义与调用",
    "函数参数与返回值",
    "列表与元组",
    "字典与集合",
    "字符串操作",
    "面向对象基础",
    "类与对象",
    "继承与多态",
    "异常处理",
    "文件操作",
    "模块与包",
]

# 前端展示名称映射：后端标准名称 -> 前端显示名称
FRONTEND_DISPLAY_MAP: Dict[str, str] = {
    "条件判断（if/elif/else）": "条件判断",
    "循环（for/while）": "循环",
    "函数定义与调用": "函数定义",
    "函数参数与返回值": "函数参数与返回值",
    "面向对象基础": "面向对象基础",
    "类与对象": "类与对象",
    "继承与多态": "继承与多态",
}

# 别名映射：用户自然语言/旧名称/前端名称 -> 后端标准名称
KNOWLEDGE_POINT_ALIASES: Dict[str, str] = {
    # 前端显示名称 -> 后端标准名称
    "条件判断": "条件判断（if/elif/else）",
    "循环": "循环（for/while）",
    "函数定义": "函数定义与调用",
    # 用户常用说法
    "变量": "变量与数据类型",
    "运算符": "运算符与表达式",
    "if语句": "条件判断（if/elif/else）",
    "条件语句": "条件判断（if/elif/else）",
    "for循环": "循环（for/while）",
    "while循环": "循环（for/while）",
    "函数": "函数定义与调用",
    "函数调用": "函数定义与调用",
    "函数参数": "函数参数与返回值",
    "函数返回值": "函数参数与返回值",
    "返回值": "函数参数与返回值",
    "列表": "列表与元组",
    "元组": "列表与元组",
    "字典": "字典与集合",
    "集合": "字典与集合",
    "字符串": "字符串操作",
    "面向对象": "面向对象基础",
    "OOP": "面向对象基础",
    "类": "类与对象",
    "对象": "类与对象",
    "继承": "继承与多态",
    "多态": "继承与多态",
    "异常": "异常处理",
    "文件": "文件操作",
    "模块": "模块与包",
    "包": "模块与包",
    "import": "模块与包",
    # 英文别名（LLM 可能返回英文）
    "variable": "变量与数据类型",
    "variables": "变量与数据类型",
    "data type": "变量与数据类型",
    "data types": "变量与数据类型",
    "operator": "运算符与表达式",
    "operators": "运算符与表达式",
    "expression": "运算符与表达式",
    "if": "条件判断（if/elif/else）",
    "elif": "条件判断（if/elif/else）",
    "else": "条件判断（if/elif/else）",
    "conditional": "条件判断（if/elif/else）",
    "condition": "条件判断（if/elif/else）",
    "for": "循环（for/while）",
    "while": "循环（for/while）",
    "loop": "循环（for/while）",
    "loops": "循环（for/while）",
    "function": "函数定义与调用",
    "functions": "函数定义与调用",
    "parameter": "函数参数与返回值",
    "parameters": "函数参数与返回值",
    "return": "函数参数与返回值",
    "return value": "函数参数与返回值",
    "list": "列表与元组",
    "lists": "列表与元组",
    "tuple": "列表与元组",
    "tuples": "列表与元组",
    "dictionary": "字典与集合",
    "dict": "字典与集合",
    "dictionaries": "字典与集合",
    "set": "字典与集合",
    "sets": "字典与集合",
    "string": "字符串操作",
    "strings": "字符串操作",
    "oop": "面向对象基础",
    "object oriented": "面向对象基础",
    "class": "类与对象",
    "classes": "类与对象",
    "object": "类与对象",
    "objects": "类与对象",
    "inheritance": "继承与多态",
    "polymorphism": "继承与多态",
    "exception": "异常处理",
    "exceptions": "异常处理",
    "try": "异常处理",
    "except": "异常处理",
    "file": "文件操作",
    "files": "文件操作",
    "file io": "文件操作",
    "module": "模块与包",
    "modules": "模块与包",
    "package": "模块与包",
    "packages": "模块与包",
}

# 所有合法的后端知识点集合
ALL_BACKEND_POINTS: Set[str] = set(BACKEND_KNOWLEDGE_POINTS)


def normalize_to_backend(point_name: str) -> Optional[str]:
    """
    将任意来源的知识点名称标准化为后端数据库使用的标准名称。
    优先精确匹配，其次别名匹配，最后包含匹配。
    """
    if not point_name or not point_name.strip():
        return None

    stripped = point_name.strip()

    # 1. 直接匹配后端标准名称
    if stripped in ALL_BACKEND_POINTS:
        return stripped

    # 2. 别名精确匹配（忽略大小写）
    lower = stripped.lower()
    for alias, standard in KNOWLEDGE_POINT_ALIASES.items():
        if alias.lower() == lower:
            return standard

    # 3. 包含匹配（输入是别名的子串，或别名是输入的子串）
    for alias, standard in KNOWLEDGE_POINT_ALIASES.items():
        if lower in alias.lower() or alias.lower() in lower:
            return standard

    return None


def convert_to_frontend(backend_name: str) -> str:
    """将后端标准名称转换为前端显示名称"""
    return FRONTEND_DISPLAY_MAP.get(backend_name, backend_name)


def get_all_frontend_names() -> list[str]:
    """获取所有前端显示名称列表（保持后端顺序）"""
    return [convert_to_frontend(kp) for kp in BACKEND_KNOWLEDGE_POINTS]
