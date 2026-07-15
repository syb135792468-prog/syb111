"""
utils/template_renderer.py - HTML模板渲染器
集中管理模板占位符替换，支持新旧两种命名风格

命名风格：
- 旧风格：__TOPIC__, __TOPIC_JSON__（当前使用）
- 新风格：{{TOPIC}}, {{TOPIC_JSON}}（推荐，更符合模板引擎惯例）

向后兼容：同时支持两种风格
"""
from __future__ import annotations

import json
from html import escape
from typing import Dict, Any, List


class TemplateRenderer:
    """
    HTML模板渲染器
    集中管理占位符替换，支持新旧两种命名风格
    """

    # 占位符映射表（旧风格 → 新风格）
    PLACEHOLDER_MAP = {
        "TOPIC": {"old": "__TOPIC__", "new": "{{TOPIC}}"},
        "TOPIC_JSON": {"old": "__TOPIC_JSON__", "new": "{{TOPIC_JSON}}"},
        "SUBTITLE": {"old": "__SUBTITLE__", "new": "{{SUBTITLE}}"},
        "LEARNING_GOALS": {"old": "__LEARNING_GOALS__", "new": "{{LEARNING_GOALS}}"},
        "DURATION": {"old": "__DURATION__", "new": "{{DURATION}}"},
        "TOTAL_STEPS": {"old": "__TOTAL_STEPS__", "new": "{{TOTAL_STEPS}}"},
        "STEP_DOTS": {"old": "__STEP_DOTS__", "new": "{{STEP_DOTS}}"},
        "STEPS_JSON": {"old": "__STEPS_JSON__", "new": "{{STEPS_JSON}}"},
        "KEY_POINTS_JSON": {"old": "__KEY_POINTS_JSON__", "new": "{{KEY_POINTS_JSON}}"},
        "KEY_POINTS": {"old": "__KEY_POINTS__", "new": "{{KEY_POINTS}}"},
        "ENDING_TEXT": {"old": "__ENDING_TEXT__", "new": "{{ENDING_TEXT}}"},
        "ENDING_TEXT_JSON": {"old": "__ENDING_TEXT_JSON__", "new": "{{ENDING_TEXT_JSON}}"},
        "VOICE_RATE": {"old": "__VOICE_RATE__", "new": "{{VOICE_RATE}}"},
        "CODE_FILENAME": {"old": "__CODE_FILENAME__", "new": "{{CODE_FILENAME}}"},
        "CODE_FILENAME_JSON": {"old": "__CODE_FILENAME_JSON__", "new": "{{CODE_FILENAME_JSON}}"},
    }

    def __init__(self, template: str):
        """
        初始化渲染器

        Args:
            template: HTML模板字符串
        """
        self.template = template
        self._values: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> "TemplateRenderer":
        """
        设置占位符值

        Args:
            key: 占位符名称（如 TOPIC）
            value: 替换值

        Returns:
            self（支持链式调用）
        """
        self._values[key] = value
        return self

    def set_many(self, values: Dict[str, Any]) -> "TemplateRenderer":
        """
        批量设置占位符值

        Args:
            values: 占位符名称 → 值的映射

        Returns:
            self（支持链式调用）
        """
        self._values.update(values)
        return self

    def _format_value(self, key: str, value: Any, is_json: bool = False) -> str:
        """
        格式化值

        Args:
            key: 占位符名称
            value: 原始值
            is_json: 是否需要JSON转义

        Returns:
            格式化后的字符串
        """
        if is_json:
            return json.dumps(value, ensure_ascii=False)
        elif isinstance(value, str):
            return value
        elif isinstance(value, (int, float)):
            return str(value)
        elif isinstance(value, list):
            return "\n".join(str(item) for item in value)
        else:
            return str(value)

    def render(self) -> str:
        """
        渲染模板，替换所有占位符

        Returns:
            渲染后的HTML字符串
        """
        html = self.template

        for key, placeholders in self.PLACEHOLDER_MAP.items():
            if key not in self._values:
                continue

            value = self._values[key]
            is_json = key.endswith("_JSON")

            formatted = self._format_value(key, value, is_json)

            # 同时替换新旧两种风格（向后兼容）
            html = html.replace(placeholders["old"], formatted)
            html = html.replace(placeholders["new"], formatted)

        return html

    @staticmethod
    def render_goals(goals: List[str]) -> str:
        """
        渲染学习目标列表为HTML

        Args:
            goals: 学习目标列表

        Returns:
            HTML字符串
        """
        return "\n".join(f"                <li>{escape(g)}</li>" for g in goals)

    @staticmethod
    def render_key_points(points: List[str]) -> str:
        """
        渲染核心要点列表为HTML

        Args:
            points: 核心要点列表

        Returns:
            HTML字符串
        """
        return "\n".join(f"                <li>{escape(p)}</li>" for p in points)

    @staticmethod
    def render_step_dots(count: int) -> str:
        """
        渲染步骤圆点

        Args:
            count: 步骤数量

        Returns:
            HTML字符串
        """
        return "\n".join('                <div class="step-dot"></div>' for _ in range(count))


# 便捷函数（向后兼容）
def render_template(template: str, values: Dict[str, Any]) -> str:
    """
    渲染模板的便捷函数

    Args:
        template: HTML模板字符串
        values: 占位符名称 → 值的映射

    Returns:
        渲染后的HTML字符串
    """
    renderer = TemplateRenderer(template)
    renderer.set_many(values)
    return renderer.render()