"""
agents/chat_judge_agent.py - 对话判题 Agent（信号触发）

仅当用户消息含代码块/明确作答时调用，不每条消息都判。
输出 JSON: {is_evaluable, node_code, node_name, evidence_type, result, misconception, confidence}

首个启用 JSON mode（response_format={"type":"json_object"}）的 Agent。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Callable, Awaitable

from agents.base_agent import BaseAgent


class ChatJudgeAgent(BaseAgent):
    """对话判题：判断用户消息是否构成可评估的学习证据。"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="chat_judge",
            scene_name="chat_judge",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[int, str, str], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        判断用户消息是否可评估，返回结构化判题结果。

        context 需包含:
            node_catalog: str - 知识点目录摘要（code + name）
            chat_history: str - 近期对话摘要
        """
        context = context or {}
        system_prompt = self._load_prompt(
            "chat_judge_system",
            node_catalog=context.get("node_catalog", ""),
            chat_history=context.get("chat_history", ""),
        )

        raw = await self._call_llm(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_input},
            ],
            temperature=0.1,
            max_tokens=512,
            response_format={"type": "json_object"},
        )

        result = self._extract_json(raw)

        return {
            "is_evaluable": bool(result.get("is_evaluable", False)),
            "node_code": result.get("node_code"),
            "node_name": result.get("node_name"),
            "evidence_type": result.get("evidence_type") or "quiz",
            "result": result.get("result"),
            "misconception": result.get("misconception"),
            "confidence": float(result.get("confidence", 0.5) or 0.5),
        }
