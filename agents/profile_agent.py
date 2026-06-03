"""
agents/profile_agent.py - 大模型原生画像构建智能体
所有消息都直接调用大模型，由大模型自主判断是否需要更新画像。
无关键词匹配、无规则模式，完全依赖大模型的自然语言理解能力。
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Dict, Any, Optional, List, ClassVar

from agents.base_agent import BaseAgent
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import (
    PROFILE_LLM_COOLDOWN_SEC,
    PROFILE_LLM_CONFIDENCE_THRESHOLD,
    BATCH_MOTIVATION_STUDY_DAYS_HIGH,
    BATCH_MOTIVATION_STUDY_DAYS_MEDIUM,
)
from config.settings import settings
from utils.agent_helpers import match_knowledge_point


class ProfileAgent(BaseAgent):
    """大模型原生用户画像构建智能体。每条消息都交给大模型判断是否需要更新。"""

    PROFILE_DIMENSIONS: ClassVar[List[str]] = [
        "knowledge_level",
        "learning_goal",
        "learning_style",
        "duration_preference",
        "weak_points",
        "mastered_points",
        "motivation_level",
    ]

    DIMENSION_OPTIONS: ClassVar[Dict[str, List[str]]] = {
        "knowledge_level": ["beginner", "intermediate", "advanced"],
        "learning_goal": ["exam", "interest", "employment", "competition"],
        "learning_style": ["visual", "auditory", "kinesthetic", "mixed"],
        "duration_preference": ["short", "medium", "long"],
        "motivation_level": ["high", "medium", "low"],
    }

    DEFAULT_PROFILE: ClassVar[Dict[str, Any]] = {
        "knowledge_level": "beginner",
        "learning_style": "mixed",
        "learning_goal": "interest",
        "duration_preference": "medium",
        "weak_points": ["循环（for/while）", "函数定义与调用"],
        "mastered_points": [],
        "motivation_level": "medium",
        "current_topic": None,
        "last_study_at": None,
    }

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="profile",
            scene_name="profile_building",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )
        self._llm_last_call: Dict[str, datetime] = {}
        self._cooldown = timedelta(seconds=PROFILE_LLM_COOLDOWN_SEC)
        self.logger.info("🎨 画像构建已启用【大模型原生】模式")

    # ------------------------------------------------------------------
    # 核心入口
    # ------------------------------------------------------------------
    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        old_profile = context.get("profile_data", {}) if context else {}
        chat_history = context.get("chat_history", []) if context else []

        # 冷却检查（演示模式跳过冷却）
        uid = self.user_id or "_global"
        if not self._can_call_llm(uid):
            self.logger.debug("⏸️ 冷却期内，跳过 LLM 调用")
            new_profile = {**self.DEFAULT_PROFILE, **old_profile}
            new_profile["last_study_at"] = self._get_current_utc_time()
            return self._build_result(new_profile)

        # 构建 prompt
        system_prompt = self._load_prompt(
            "profile_building_system",
            knowledge_level_options=self.DIMENSION_OPTIONS["knowledge_level"],
            learning_goal_options=self.DIMENSION_OPTIONS["learning_goal"],
            learning_style_options=self.DIMENSION_OPTIONS["learning_style"],
            duration_preference_options=self.DIMENSION_OPTIONS["duration_preference"],
            motivation_level_options=self.DIMENSION_OPTIONS["motivation_level"],
            knowledge_points="\n".join(f"- {kp}" for kp in PYTHON_KNOWLEDGE_POINTS),
            old_profile=self._format_profile_for_prompt(old_profile),
        )

        # 构建用户消息（包含最近对话历史，帮助理解指代）
        user_message = self._build_user_message(user_input, chat_history)

        try:
            response = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ])
            raw_output = self._extract_json(response)
            self.logger.debug(f"🤖 LLM 原始输出：{raw_output}")

            # 空对象 = 大模型判断没有新信息
            if not raw_output:
                self.logger.info("📭 大模型判断无新画像信息")
                new_profile = {**self.DEFAULT_PROFILE, **old_profile}
                new_profile["last_study_at"] = self._get_current_utc_time()
                return self._build_result(new_profile)

            # 信心度过滤
            confidence = raw_output.pop("confidence", 0.0)
            if confidence < PROFILE_LLM_CONFIDENCE_THRESHOLD:
                self.logger.info(
                    f"🔒 信心度过低({confidence}<{PROFILE_LLM_CONFIDENCE_THRESHOLD})，忽略本次提取"
                )
                new_profile = {**self.DEFAULT_PROFILE, **old_profile}
                new_profile["last_study_at"] = self._get_current_utc_time()
                return self._build_result(new_profile)

            # 校验并过滤 LLM 输出（含知识点冲突处理）
            validated = self._validate_llm_output(raw_output, old_profile)
            if not validated:
                self.logger.info("📭 校验后无有效更新")
                new_profile = {**self.DEFAULT_PROFILE, **old_profile}
                new_profile["last_study_at"] = self._get_current_utc_time()
                return self._build_result(new_profile)

            # 有有效更新 → 启动冷却计时
            self._mark_called(uid)

            # 合并更新
            new_profile = {**self.DEFAULT_PROFILE, **old_profile, **validated}
            new_profile["last_study_at"] = self._get_current_utc_time()

            # 自动更新动力水平（基于行为数据）
            new_profile = await self._update_motivation_level(new_profile)

            self.logger.info(
                f"✅ 画像更新: 水平={new_profile['knowledge_level']}, "
                f"目标={new_profile['learning_goal']}, "
                f"弱点={len(new_profile.get('weak_points', []))}个"
            )
            return self._build_result(
                new_profile,
                raw_llm_output=raw_output,
                confidence=confidence,
            )

        except Exception as exc:
            self.logger.warning(f"⚠️ LLM 画像构建失败：{exc}")
            # LLM 失败时只更新时间，保留旧画像
            new_profile = {**self.DEFAULT_PROFILE, **old_profile}
            new_profile["last_study_at"] = self._get_current_utc_time()
            return self._build_result(new_profile)

    # ------------------------------------------------------------------
    # 冷却机制（演示模式跳过）
    # ------------------------------------------------------------------
    def _can_call_llm(self, uid: str) -> bool:
        if settings.DEMO_MODE:
            return True
        if uid not in self._llm_last_call:
            return True
        return datetime.now(UTC) - self._llm_last_call[uid] > self._cooldown

    def _mark_called(self, uid: str) -> None:
        self._llm_last_call[uid] = datetime.now(UTC)

    # ------------------------------------------------------------------
    # 用户消息构建（注入对话历史，帮助理解指代）
    # ------------------------------------------------------------------
    def _build_user_message(
        self, user_input: str, chat_history: List[Dict[str, str]]
    ) -> str:
        parts = []
        # 最近 3 轮对话历史（chat_history 不含当前用户消息）
        if chat_history:
            recent = chat_history[-3:]
            if recent:
                history_lines = []
                for msg in recent:
                    role = "用户" if msg.get("role") == "user" else "助手"
                    content = msg.get("content", "")[:200]
                    history_lines.append(f"{role}: {content}")
                parts.append("最近对话历史：\n" + "\n".join(history_lines))

        parts.append(f"用户最新消息：\n{user_input}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # LLM 输出校验（含知识点冲突处理）
    # ------------------------------------------------------------------
    def _validate_llm_output(
        self, parsed: Dict[str, Any], old_profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        validated: Dict[str, Any] = {}

        # 1. 分类字段校验
        for dim, options in self.DIMENSION_OPTIONS.items():
            if dim in parsed:
                if parsed[dim] not in options:
                    self.logger.warning(f"⚠️ 非法枚举值: {dim}={parsed[dim]}，丢弃")
                    continue
                validated[dim] = parsed[dim]

        # 2. current_topic 校验
        if "current_topic" in parsed and isinstance(parsed["current_topic"], str):
            validated["current_topic"] = parsed["current_topic"]

        # 3. 知识点列表校验 + 归一化
        for field in ("weak_points", "mastered_points"):
            if field not in parsed or not isinstance(parsed[field], list):
                continue
            normalized: List[str] = []
            seen: set = set()
            for point in parsed[field]:
                if not isinstance(point, str):
                    continue
                std = match_knowledge_point(point)
                if std and std not in seen:
                    normalized.append(std)
                    seen.add(std)
            if normalized:
                # 增量合并：追加到旧列表，去重
                old_list = old_profile.get(field, [])
                merged = list(dict.fromkeys(old_list + normalized))
                validated[field] = merged

        # 4. 知识点冲突处理：掌握的自动从薄弱中移除，反之亦然
        old_weak = set(old_profile.get("weak_points", []))
        old_mastered = set(old_profile.get("mastered_points", []))

        if "mastered_points" in validated:
            new_mastered = set(validated["mastered_points"])
            # 新掌握的从薄弱点中移除
            remaining_weak = (old_weak | set(validated.get("weak_points", []))) - new_mastered
            validated["weak_points"] = list(remaining_weak)

        if "weak_points" in validated:
            new_weak = set(validated["weak_points"])
            # 新薄弱的从已掌握中移除
            remaining_mastered = (old_mastered | set(validated.get("mastered_points", []))) - new_weak
            validated["mastered_points"] = list(remaining_mastered)

        return validated

    # ------------------------------------------------------------------
    # 动力水平自动更新（基于行为数据）
    # ------------------------------------------------------------------
    async def _update_motivation_level(
        self, profile: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            from utils.behavior_tracker import behavior_tracker

            uid = profile.get("user_id") or self.user_id
            if not uid or not str(uid).isdigit():
                return profile

            stats = await behavior_tracker.get_user_stats(int(uid), days=7)
            study_days = stats.get("study_days", 0)

            if study_days >= BATCH_MOTIVATION_STUDY_DAYS_HIGH:
                new_level = "high"
            elif study_days >= BATCH_MOTIVATION_STUDY_DAYS_MEDIUM:
                new_level = "medium"
            else:
                new_level = "low"

            if new_level != profile.get("motivation_level"):
                self.logger.info(
                    f"📊 动力水平自动更新: {profile.get('motivation_level')} → {new_level} "
                    f"(7天学习{study_days}天)"
                )
                profile["motivation_level"] = new_level

        except Exception as exc:
            self.logger.debug(f"动力水平更新跳过: {exc}")

        return profile

    # ------------------------------------------------------------------
    # 结果构建
    # ------------------------------------------------------------------
    def _build_result(
        self,
        profile_data: Dict[str, Any],
        raw_llm_output: Optional[Dict[str, Any]] = None,
        confidence: Optional[float] = None,
    ) -> Dict[str, Any]:
        result = {
            "profile_data": profile_data,
            "current_step": "profile",
            "updated_at": self._get_current_utc_time(),
        }
        if raw_llm_output is not None:
            result["_profile_raw_llm_output"] = raw_llm_output
        if confidence is not None:
            result["_profile_confidence"] = confidence
        return result

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    @staticmethod
    def _format_profile_for_prompt(profile: Dict[str, Any]) -> str:
        if not profile:
            return "（暂无画像信息）"
        lines = []
        for k, v in profile.items():
            if k == "last_study_at":
                continue
            if isinstance(v, list):
                lines.append(f"- {k}: {', '.join(v) if v else '无'}")
            else:
                lines.append(f"- {k}: {v or '未识别'}")
        return "\n".join(lines) if lines else "（暂无画像信息）"
