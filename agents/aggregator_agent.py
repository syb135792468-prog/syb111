"""
agents/aggregator_agent.py - 内容聚合智能体
将多个Agent的输出整合为一份连贯的Markdown学习包
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional

from agents.base_agent import BaseAgent


class AggregatorAgent(BaseAgent):
    """聚合智能体：调用LLM将多个Agent的输出整合为连贯的学习材料"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="aggregator",
            scene_name="aggregation",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ctx = context or {}
        topic = ctx.get("topic", "Python")
        agent_contents = ctx.get("agent_contents", [])
        profile_data = ctx.get("profile_data", {})

        system_prompt = self._load_prompt("aggregator_system")
        user_prompt = self._build_user_prompt(topic, agent_contents, profile_data)

        result = await self._call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        return {"final_response": result}

    def _build_user_prompt(
        self,
        topic: str,
        agent_contents: List[Dict[str, str]],
        profile_data: Dict[str, Any],
    ) -> str:
        parts = [f"## 学习主题\n{topic}\n"]

        level = profile_data.get("knowledge_level", "")
        if level:
            level_map = {"beginner": "零基础", "intermediate": "有基础", "advanced": "进阶"}
            parts.append(f"## 学生水平\n{level_map.get(level, level)}\n")

        for item in agent_contents:
            label = item.get("label", "未知模块")
            content = item.get("content", "")
            if content:
                parts.append(f"## {label}\n{content}\n")

        return "\n".join(parts)
