"""
agents/unified_router_agent.py - 统一路由智能体（合并画像提取版）
单次 LLM 调用同时返回：意图 + 资源类型 + 主题 + 画像更新
消除路由和画像更新之间的串行等待
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from agents.base_agent import BaseAgent
from ai.confidence_calibrator import confidence_calibrator
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import PROFILE_LLM_CONFIDENCE_THRESHOLD, CONFIDENCE_FALLBACK_THRESHOLD
from utils.agent_helpers import match_knowledge_point

VALID_INTENTS = {
    "start_learning", "ask_question", "do_quiz",
    "view_path", "generate_resource", "evaluate",
}
VALID_RESOURCE_TYPES = {"mindmap", "doc", "code", "video", "quiz"}

PROFILE_ENUM_OPTIONS = {
    "knowledge_level": ["beginner", "intermediate", "advanced"],
    "learning_goal": ["exam", "interest", "employment", "competition"],
    "learning_style": ["visual", "auditory", "kinesthetic", "mixed"],
    "duration_preference": ["short", "medium", "long"],
    "motivation_level": ["high", "medium", "low"],
}


class UnifiedRouterAgent(BaseAgent):
    """统一路由智能体：单次 LLM 调用完成意图识别 + 资源类型 + 主题 + 画像提取"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="unified_router",
            scene_name="unified_routing",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not user_input or not user_input.strip():
            return self._build_fallback()

        old_profile = (context or {}).get("profile_data", {})
        chat_history = (context or {}).get("chat_history", [])

        # 构建带对话历史的用户消息
        user_message = self._build_user_message(user_input, chat_history)

        try:
            system_prompt = self._load_prompt(
                "unified_routing_system",
                knowledge_points="\n".join(f"- {kp}" for kp in PYTHON_KNOWLEDGE_POINTS),
            )
            response = await self._call_llm(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=256,
            )

            # 置信度校准：提取并校准 LLM 自报置信度
            cleaned_response, calibrated_confidence = confidence_calibrator.extract_confidence(response)

            parsed = self._extract_json(cleaned_response)

            # 校准后置信度过低 → 降级为关键词兜底
            if confidence_calibrator.should_use_fallback(calibrated_confidence, CONFIDENCE_FALLBACK_THRESHOLD):
                self.logger.info(f"校准后置信度过低({calibrated_confidence:.2f})，降级为关键词兜底")
                return self._build_fallback()

            # ---- 路由字段 ----
            intent = parsed.get("intent", "").strip()
            resource_type = parsed.get("resource_type")
            topic = parsed.get("topic", "").strip()

            if resource_type == "null" or resource_type == "":
                resource_type = None
            if intent not in VALID_INTENTS:
                intent = "ask_question"
            if resource_type is not None and resource_type not in VALID_RESOURCE_TYPES:
                resource_type = None
            if intent == "generate_resource" and resource_type is None:
                resource_type = "doc"

            # ---- 画像字段 ----
            profile_update = parsed.get("profile_update", {})
            confidence = parsed.get("confidence", 0.0)
            validated_profile = self._validate_profile_update(
                profile_update, confidence, old_profile
            )

            self.logger.info(
                f"路由结果: intent={intent}, resource_type={resource_type}, topic={topic}, "
                f"profile_update={bool(validated_profile)}, confidence={confidence}"
            )

            result = {
                "user_intent": intent,
                "resource_type": resource_type,
                "topic": topic,
                "current_step": "unified_router",
                "updated_at": self._get_current_utc_time(),
            }

            # 画像更新数据附加到结果中，由调用方决定如何处理
            if validated_profile:
                result["_profile_update"] = validated_profile
                result["_profile_confidence"] = confidence
                result["_profile_raw_output"] = profile_update

            return result

        except Exception as e:
            self.logger.warning(f"统一路由失败: {e}，降级为默认")
            return self._build_fallback()

    # ------------------------------------------------------------------
    # 画像校验（从 ProfileAgent 迁移的核心逻辑）
    # ------------------------------------------------------------------
    def _validate_profile_update(
        self,
        raw: Dict[str, Any],
        confidence: float,
        old_profile: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not raw or not isinstance(raw, dict):
            return {}
        if confidence < PROFILE_LLM_CONFIDENCE_THRESHOLD:
            self.logger.debug(f"画像信心度过低({confidence})，丢弃")
            return {}

        validated: Dict[str, Any] = {}

        # 枚举字段校验
        for dim, options in PROFILE_ENUM_OPTIONS.items():
            if dim in raw:
                if raw[dim] not in options:
                    self.logger.warning(f"⚠️ 非法枚举值: {dim}={raw[dim]}，丢弃")
                    continue
                validated[dim] = raw[dim]

        # current_topic
        if "current_topic" in raw and isinstance(raw["current_topic"], str):
            validated["current_topic"] = raw["current_topic"]

        # 知识点列表校验 + 归一化
        for field in ("weak_points", "mastered_points"):
            if field not in raw or not isinstance(raw[field], list):
                continue
            normalized = []
            seen = set()
            for point in raw[field]:
                if not isinstance(point, str):
                    continue
                std = match_knowledge_point(point)
                if std and std not in seen:
                    normalized.append(std)
                    seen.add(std)
            if normalized:
                old_list = old_profile.get(field, [])
                validated[field] = list(dict.fromkeys(old_list + normalized))

        # 知识点冲突处理
        old_weak = set(old_profile.get("weak_points", []))
        old_mastered = set(old_profile.get("mastered_points", []))

        if "mastered_points" in validated:
            new_mastered = set(validated["mastered_points"])
            remaining_weak = (old_weak | set(validated.get("weak_points", []))) - new_mastered
            validated["weak_points"] = list(remaining_weak)

        if "weak_points" in validated:
            new_weak = set(validated["weak_points"])
            remaining_mastered = (old_mastered | set(validated.get("mastered_points", []))) - new_weak
            validated["mastered_points"] = list(remaining_mastered)

        return validated

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _build_user_message(
        self, user_input: str, chat_history: list
    ) -> str:
        parts = []
        if chat_history:
            recent = chat_history[-3:]
            if recent:
                lines = []
                for msg in recent:
                    role = "用户" if msg.get("role") == "user" else "助手"
                    content = msg.get("content", "")[:200]
                    lines.append(f"{role}: {content}")
                parts.append("最近对话历史：\n" + "\n".join(lines))
        parts.append(f"用户最新消息：\n{user_input}")
        return "\n\n".join(parts)

    def _build_fallback(self) -> Dict[str, Any]:
        return {
            "user_intent": "ask_question",
            "resource_type": None,
            "topic": "",
            "current_step": "unified_router",
            "updated_at": self._get_current_utc_time(),
        }
