"""
agents/path_agent.py - 学习路径规划智能体
LLM 动态生成 | 根据用户主题生成个性化学习路径 | 支持画像感知
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import DEFAULT_ESTIMATED_TIME_MIN, MAX_LEARNING_PATH_STEPS
from utils.agent_helpers import get_profile_from_context


class PathAgent(BaseAgent):
    """学习路径规划智能体，用LLM根据用户主题动态生成个性化学习路径"""

    def __init__(self, user_id=None, task_id=None):
        super().__init__(
            agent_name="path",
            scene_name="path_planning",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成个性化学习路径。

        Returns:
            dict: {"learning_path": [...], "current_step": "path", ...}
        """
        profile = get_profile_from_context(context)
        topic = (user_input or "").strip()
        if not topic:
            topic = "Python基础"

        # 构建prompt
        system_prompt = self._load_prompt("path_generation_system")
        user_prompt = self._build_user_prompt(topic, profile)

        # 调LLM生成路径，最多重试2次
        last_error = None
        for attempt in range(2):
            try:
                response = await self._call_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                    max_tokens=2048,
                )
                path_data = self._extract_json(response)
                learning_path, path_title = self._validate_and_format(path_data, profile)
                if learning_path:
                    self.logger.info(f"✅ LLM生成 {len(learning_path)} 步学习路径 | topic={topic} | attempt={attempt+1}")
                    return {
                        "learning_path": learning_path,
                        "path_title": path_title,
                        "current_step": "path",
                        "updated_at": self._get_current_utc_time(),
                    }
                self.logger.warning(f"LLM返回的路径数据格式无效 (attempt {attempt+1}/2)")
                last_error = "格式无效"
            except Exception as e:
                self.logger.error(f"LLM生成路径失败 (attempt {attempt+1}/2): {e}")
                last_error = str(e)

        # fallback：用硬编码知识点生成简单线性路径
        self.logger.warning(f"LLM生成失败，使用fallback路径 | 最后错误: {last_error}")
        fallback = self._build_fallback_path(topic, profile)
        self.logger.info(f"⚠️ 使用fallback路径: {len(fallback)} 步")
        return {
            "learning_path": fallback,
            "path_title": f"{topic}学习路径",
            "current_step": "path",
            "updated_at": self._get_current_utc_time(),
        }

    def _build_user_prompt(self, topic: str, profile: Dict[str, Any]) -> str:
        """构建用户prompt，注入画像信息"""
        # 画像信息
        level = profile.get("knowledge_level", "")
        goal = profile.get("learning_goal", "")
        style = profile.get("learning_style", "")
        profile_parts = []
        if level:
            level_map = {"beginner": "零基础", "intermediate": "有基础", "advanced": "进阶"}
            profile_parts.append(f"水平：{level_map.get(level, level)}")
        if goal:
            goal_map = {"exam": "备考", "interest": "兴趣学习", "employment": "就业", "competition": "竞赛"}
            profile_parts.append(f"目标：{goal_map.get(goal, goal)}")
        if style:
            style_map = {"visual": "视觉型", "auditory": "听觉型", "kinesthetic": "动手型", "mixed": "混合型"}
            profile_parts.append(f"学习风格：{style_map.get(style, style)}")
        profile_text = f"\n【用户画像】{'、'.join(profile_parts)}" if profile_parts else ""

        # 已掌握知识点
        mastered = profile.get("mastered_points", [])
        mastered_text = f"\n【已掌握】{'、'.join(mastered)}" if mastered else ""

        # 薄弱点
        weak = profile.get("weak_points", [])
        weak_text = f"\n【薄弱点】{'、'.join(weak)}" if weak else ""

        return self._load_prompt(
            "path_generation_user",
            topic=topic,
            profile_text=profile_text,
            mastered_text=mastered_text,
            weak_text=weak_text,
        )

    def _validate_and_format(
        self, data: Dict[str, Any], profile: Dict[str, Any]
    ) -> tuple[List[Dict[str, Any]], str]:
        """验证LLM返回的路径数据，格式化为前端可展示的结构。

        Returns:
            (learning_path, path_title) 元组
        """
        steps = data.get("steps")
        if not steps or not isinstance(steps, list):
            return [], ""

        mastered = set(profile.get("mastered_points", []))
        path_title = data.get("path_title", "")
        learning_path = []

        for step in steps:
            # 兼容多种字段名：knowledge_point / name / title / 知识点
            kp = step.get("knowledge_point") or step.get("name") or step.get("title") or step.get("知识点")
            kp = str(kp).strip() if kp else ""
            if not kp:
                continue

            # 兼容多种时间字段，用 is not None 判断避免 0 被跳过
            time_min = step.get("estimated_time_min")
            if time_min is None:
                time_min = step.get("time")
            if time_min is None:
                time_min = step.get("duration")
            if time_min is None:
                time_min = DEFAULT_ESTIMATED_TIME_MIN

            # 兼容多种难度字段，用 is not None 判断避免 0 被跳过
            difficulty = step.get("difficulty")
            if difficulty is None:
                difficulty = step.get("level")
            if difficulty is None:
                difficulty = 0.5

            # 兼容多种前置依赖字段
            prerequisites = step.get("prerequisites") or step.get("deps") or step.get("前置") or []

            # 兼容 description 字段
            description = step.get("description") or step.get("说明") or ""

            learning_path.append({
                "order": step.get("order", len(learning_path) + 1),
                "knowledge_point": kp,
                "description": str(description).strip() if description else f"学习{kp}",
                "estimated_time_min": int(time_min),
                "type": "review" if kp in mastered else "new",
                "prerequisites": prerequisites if isinstance(prerequisites, list) else [],
                "difficulty": float(difficulty),
            })

        # 按 order 排序，重新编号
        learning_path.sort(key=lambda x: x["order"])
        for i, step in enumerate(learning_path):
            step["order"] = i + 1

        # 验证前置依赖：移除不存在的引用
        valid_kps = {s["knowledge_point"] for s in learning_path}
        for step in learning_path:
            step["prerequisites"] = [p for p in step["prerequisites"] if p in valid_kps]

        return learning_path, str(path_title).strip() if path_title else ""

    def _build_fallback_path(
        self, topic: str, profile: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """LLM失败时的fallback：用硬编码知识点生成简单路径"""
        mastered = set(profile.get("mastered_points", []))
        weak_points = profile.get("weak_points", [])

        # 优先从薄弱点开始，然后补充未掌握的知识点
        ordered_kps = []
        for kp in weak_points:
            if kp in PYTHON_KNOWLEDGE_POINTS and kp not in mastered:
                ordered_kps.append(kp)
        for kp in PYTHON_KNOWLEDGE_POINTS:
            if kp not in mastered and kp not in ordered_kps:
                ordered_kps.append(kp)

        learning_path = []
        for i, kp in enumerate(ordered_kps[:MAX_LEARNING_PATH_STEPS], 1):
            learning_path.append({
                "order": i,
                "knowledge_point": kp,
                "estimated_time_min": DEFAULT_ESTIMATED_TIME_MIN,
                "type": "review" if kp in mastered else "new",
                "prerequisites": [],
                "difficulty": round(0.1 + (i - 1) * 0.1, 2),
            })

        return learning_path
