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
    EVAL_DEFAULT_DAYS, EVAL_TEMPERATURE, EVAL_MAX_TOKENS,
    EVAL_QUIZ_MIN_COUNT, EVAL_STUDY_HOURS_THRESHOLD, EVAL_RESOURCE_VIEWS_THRESHOLD,
    EVAL_REPORT_MAX_WORDS,
    RESOURCE_STATUS_COMPLETED, MOTIVATION_LEVEL_HIGH, MOTIVATION_LEVEL_MEDIUM,
    BATCH_MOTIVATION_COMPLETION_RATE_HIGH, BATCH_MOTIVATION_COMPLETION_RATE_MEDIUM,
    BATCH_WEAK_POINT_QUESTION_COUNT,
    ERROR_PREFERENCES_TOP_N, ERROR_PREFERENCES_MIN_SAMPLES, ERROR_TYPE_OTHER,
)
from config.settings import settings
from utils.agent_helpers import (
    match_knowledge_point,
    MASTERY_EVIDENCE_THRESHOLD,
    WEAK_EVIDENCE_THRESHOLD,
)


class ProfileAgent(BaseAgent):
    """大模型原生用户画像构建智能体。每条消息都交给大模型判断是否需要更新。"""

    PROFILE_DIMENSIONS: ClassVar[List[str]] = [
        "gender",
        "age",
        "knowledge_level",
        "learning_goal",
        "learning_style",
        "duration_preference",
        "weak_points",
        "mastered_points",
        "motivation_level",
        "error_preferences",
    ]

    DIMENSION_OPTIONS: ClassVar[Dict[str, List[str]]] = {
        "gender": ["male", "female", "other"],
        "knowledge_level": ["beginner", "intermediate", "advanced"],
        "learning_goal": ["exam", "interest", "employment", "competition"],
        "learning_style": ["visual", "auditory", "kinesthetic", "mixed"],
        "duration_preference": ["short", "medium", "long"],
        "motivation_level": ["high", "medium", "low"],
    }

    DEFAULT_PROFILE: ClassVar[Dict[str, Any]] = {
        "gender": None,
        "age": None,
        "knowledge_level": "beginner",
        "learning_style": "mixed",
        "learning_goal": "interest",
        "duration_preference": "medium",
        "weak_points": ["循环（for/while）", "函数定义与调用"],
        "mastered_points": [],
        "motivation_level": "medium",
        "error_preferences": [],
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
        progress_scores = context.get("progress_scores", {}) if context else {}

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
            gender_options=self.DIMENSION_OPTIONS["gender"],
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
            validated = self._validate_llm_output(raw_output, old_profile, progress_scores)
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

            # 自动聚合易错点偏好（从错题本统计，行为驱动，非 LLM 提取）
            new_profile = await self._aggregate_error_preferences(new_profile)

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
        self,
        parsed: Dict[str, Any],
        old_profile: Dict[str, Any],
        progress_scores: Optional[Dict[str, float]] = None,
    ) -> Dict[str, Any]:
        validated: Dict[str, Any] = {}

        # error_preferences 由错题行为聚合驱动，忽略 LLM 输出（避免幻觉）
        parsed.pop("error_preferences", None)

        # 1. 分类字段校验
        for dim, options in self.DIMENSION_OPTIONS.items():
            if dim in parsed:
                if parsed[dim] not in options:
                    self.logger.warning(f"⚠️ 非法枚举值: {dim}={parsed[dim]}，丢弃")
                    continue
                validated[dim] = parsed[dim]

        # 1.5. 年龄校验（正整数，3-120）
        if "age" in parsed:
            try:
                age = int(parsed["age"])
                if 3 <= age <= 120:
                    validated["age"] = age
                else:
                    self.logger.warning(f"⚠️ 年龄超出合理范围: {age}，丢弃")
            except (ValueError, TypeError):
                self.logger.warning(f"⚠️ 年龄格式非法: {parsed['age']}，丢弃")

        # 2. current_topic 校验
        if "current_topic" in parsed and isinstance(parsed["current_topic"], str):
            validated["current_topic"] = parsed["current_topic"]

        # 3. 知识点列表校验 + 归一化 + 证据过滤 + 合并
        old_weak = set(old_profile.get("weak_points", []))
        old_mastered = set(old_profile.get("mastered_points", []))
        all_known = old_weak | old_mastered
        uid_tag = self.user_id or "unknown"

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
                # 3a. 证据过滤：先过滤 LLM 新增项，阻止无依据的重分类
                if progress_scores:
                    opposite = old_mastered if field == "weak_points" else old_weak
                    threshold = WEAK_EVIDENCE_THRESHOLD if field == "weak_points" else MASTERY_EVIDENCE_THRESHOLD
                    filtered = []
                    for p in normalized:
                        if p in opposite:
                            # 重分类：需要证据达标
                            score = progress_scores.get(p, None)
                            if score is not None:
                                if field == "weak_points" and score < threshold:
                                    filtered.append(p)
                                elif field == "mastered_points" and score >= threshold:
                                    filtered.append(p)
                                else:
                                    self.logger.info(
                                        f"🚫 拦截重分类 | user={uid_tag} kp={p} "
                                        f"{opposite}→{field} score={score} threshold={threshold}"
                                    )
                            else:
                                self.logger.info(
                                    f"🚫 拦截无数据重分类 | user={uid_tag} kp={p} {opposite}→{field}"
                                )
                        elif p not in all_known:
                            # 全新知识点：薄弱放行，掌握需证据
                            if field == "mastered_points":
                                score = progress_scores.get(p, None)
                                if score is not None and score >= MASTERY_EVIDENCE_THRESHOLD:
                                    filtered.append(p)
                                else:
                                    self.logger.info(
                                        f"🚫 拦截无证据新知识点入掌握 | user={uid_tag} kp={p} "
                                        f"score={score}"
                                    )
                            else:
                                filtered.append(p)  # 新知识点入薄弱：放行
                        else:
                            filtered.append(p)  # 已在目标列表中：保留
                    normalized = filtered
                else:
                    # 无 progress 数据时：冷启动放行，非冷启动的掌握列表限制新增
                    if old_mastered or old_weak:
                        filtered = []
                        for p in normalized:
                            if p in all_known or field == "weak_points":
                                filtered.append(p)
                            else:
                                self.logger.info(
                                    f"🚫 拦截无证据新知识点入掌握(无progress) | user={uid_tag} kp={p}"
                                )
                        normalized = filtered

                if normalized:
                    # 3b. 增量合并：追加到旧列表，去重
                    old_list = old_profile.get(field, [])
                    merged = list(dict.fromkeys(old_list + normalized))
                    validated[field] = merged

        # 4. 知识点冲突处理：掌握的自动从薄弱中移除，反之亦然
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
    # 易错点偏好聚合（行为驱动，从错题本统计，非 LLM 提取）
    # ------------------------------------------------------------------
    async def _aggregate_error_preferences(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """从 error_book 聚合用户 top-3 错因，写入 error_preferences。
        错题总数 < MIN_SAMPLES 时跳过（保留旧值）。
        """
        try:
            from models.error_book import ErrorBook
            from models.database import AsyncSessionLocal
            from sqlalchemy import select, func

            uid = profile.get("user_id") or self.user_id
            if not uid or not str(uid).isdigit():
                return profile
            user_id = int(uid)

            async with AsyncSessionLocal() as session:
                # 错题总数检查
                total_result = await session.execute(
                    select(func.count()).select_from(ErrorBook)
                    .where(ErrorBook.user_id == user_id)
                )
                total = total_result.scalar() or 0
                if total < ERROR_PREFERENCES_MIN_SAMPLES:
                    return profile

                # 聚合 top-3 错因（排除 null 和 other）
                result = await session.execute(
                    select(ErrorBook.error_type, func.count().label("cnt"))
                    .where(
                        ErrorBook.user_id == user_id,
                        ErrorBook.error_type.isnot(None),
                        ErrorBook.error_type != ERROR_TYPE_OTHER,
                    )
                    .group_by(ErrorBook.error_type)
                    .order_by(func.count().desc())
                    .limit(ERROR_PREFERENCES_TOP_N)
                )
                top_types = [row[0] for row in result.all() if row[0]]

            if top_types and list(profile.get("error_preferences") or []) != top_types:
                profile["error_preferences"] = top_types
                self.logger.info(
                    f"🎯 易错点偏好聚合: user={user_id}, top={top_types}"
                )
        except Exception as exc:
            self.logger.debug(f"易错点偏好聚合跳过: {exc}")

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

    # ------------------------------------------------------------------
    # 学习效果评估（原 EvaluationAgent 能力）
    # ------------------------------------------------------------------
    async def _get_stats(self, context: Dict) -> Optional[Dict[str, Any]]:
        """从行为追踪器获取用户近30天学习统计数据"""
        from utils.behavior_tracker import behavior_tracker

        user_id_str = context.get("user_id") or self.user_id
        if not user_id_str:
            self.logger.warning("未获取到用户ID，跳过行为统计")
            return None

        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            self.logger.warning(f"用户ID格式无效：{user_id_str}")
            return None

        try:
            stats = await behavior_tracker.get_user_stats(user_id, days=EVAL_DEFAULT_DAYS)
            self.logger.debug(f"成功获取用户学习统计：{stats}")
            return stats
        except Exception as e:
            self.logger.warning(f"获取学习统计失败：{str(e)}")
            return None

    async def generate_evaluation_report(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        生成学习效果评估报告（原 EvaluationAgent.process）
        流程：获取上下文 → 拉取学习统计 → 生成评估报告 → 更新用户画像
        """
        try:
            context = context or {}
            profile_data = context.get("profile_data", {})
            resource_list = context.get("resource_list", [])
            chat_history = context.get("chat_history", [])

            self.logger.info("📊 开始执行学习效果评估")

            # 1. 获取用户学习行为统计
            study_stats = await self._get_stats(context)

            # 2. 生成评估报告（LLM/规则二选一）
            evaluation_report = (
                await self._llm_evaluate(profile_data, resource_list, study_stats)
                if use_llm
                else self._rule_evaluate(profile_data, resource_list, study_stats)
            )

            # 3. 基于完成资源更新用户画像
            updated_profile = self._update_profile_by_resources(profile_data, resource_list)

            # 4. 基于学习统计二次优化画像
            if study_stats and study_stats.get("quizzes_completed", 0) > 0:
                updated_profile = self._update_profile_by_stats(updated_profile, study_stats)

            # 5. 不可变更新对话历史
            new_chat_history = [*chat_history, {"role": "assistant", "content": evaluation_report}]

            self.logger.info("✅ 学习效果评估完成，用户画像已更新")
            return {
                "chat_history": new_chat_history,
                "profile_data": updated_profile,
                "current_step": "eval",
                "updated_at": self._get_current_utc_time(),
            }

        except Exception as e:
            self.logger.error(f"❌ 学习效果评估执行异常：{str(e)}", exc_info=True)
            return {
                "chat_history": context.get("chat_history", []),
                "profile_data": context.get("profile_data", {}),
                "current_step": "eval",
                "updated_at": self._get_current_utc_time(),
            }

    @staticmethod
    def _rule_evaluate(
        profile: Dict,
        resources: List[Dict],
        stats: Optional[Dict],
    ) -> str:
        """规则模式：生成简洁标准化评估报告"""
        weak_points = profile.get("weak_points", [])
        mastered_points = profile.get("mastered_points", [])
        total_resources = len(resources)
        completed_res = sum(1 for r in resources if r.get("status") == RESOURCE_STATUS_COMPLETED)

        study_hours = stats.get("total_study_hours", 0) if stats else 0
        quiz_count = stats.get("quizzes_completed", 0) if stats else 0

        if not weak_points:
            suggestion = "\n🎉 很棒！所有知识点均已掌握，继续保持学习热情！"
        else:
            suggestion = f"\n💪 学习建议：重点加强 {', '.join(weak_points)} 的练习"

        return (
            f"📊 **学习效果评估报告**\n"
            f"- 累计学习：{study_hours:.1f} 小时\n"
            f"- 资源完成：{completed_res}/{total_resources}\n"
            f"- 练习完成：{quiz_count} 次\n"
            f"- 已掌握：{', '.join(mastered_points) if mastered_points else '暂无'}\n"
            f"- 待加强：{', '.join(weak_points) if weak_points else '暂无'}\n"
            f"{suggestion}"
        )

    async def _llm_evaluate(
        self,
        profile: Dict,
        resources: List[Dict],
        stats: Optional[Dict],
    ) -> str:
        """LLM模式：生成个性化评估报告，失败自动降级规则模式"""
        try:
            mastered = profile.get("mastered_points", [])
            weak = profile.get("weak_points", [])
            total_res = len(resources)
            completed_res = sum(1 for r in resources if r.get("status") == RESOURCE_STATUS_COMPLETED)

            context_text = (
                f"用户画像：\n- 基础水平：{profile.get('knowledge_level', '未知')}\n"
                f"- 学习目标：{profile.get('learning_goal', '未知')}\n"
                f"- 已掌握：{', '.join(mastered) if mastered else '无'}\n"
                f"- 薄弱点：{', '.join(weak) if weak else '无'}\n"
                f"资源完成：{completed_res}/{total_res} 个"
            )

            if stats:
                context_text += (
                    f"\n\n近30天学习：\n- 总时长：{stats.get('total_study_hours', 0):.1f} 小时\n"
                    f"- 浏览资源：{stats.get('resources_viewed', 0)} 次\n"
                    f"- 完成练习：{stats.get('quizzes_completed', 0)} 题"
                )

            prompt = self._load_prompt(
                "evaluation_user",
                max_words=EVAL_REPORT_MAX_WORDS,
                context_text=context_text,
            )

            return await self._call_llm(
                messages=[{"role": "user", "content": prompt}],
                temperature=EVAL_TEMPERATURE,
                max_tokens=EVAL_MAX_TOKENS,
            )

        except Exception as e:
            self.logger.warning(f"LLM评估失败，自动降级规则模式：{str(e)}")
            return self._rule_evaluate(profile, resources, stats)

    @staticmethod
    def _update_profile_by_resources(profile: Dict, resources: List[Dict]) -> Dict:
        """根据已完成资源，自动将知识点从薄弱移至掌握"""
        new_profile = {**profile}
        weak_list = list(new_profile.get("weak_points", []))
        mastered_list = list(new_profile.get("mastered_points", []))

        finished_kps = set()
        for res in resources:
            if res.get("status") == RESOURCE_STATUS_COMPLETED:
                finished_kps.update(res.get("knowledge_points", []))

        for kp in finished_kps:
            if kp in weak_list:
                weak_list.remove(kp)
            if kp not in mastered_list:
                mastered_list.append(kp)

        new_profile["weak_points"] = weak_list
        new_profile["mastered_points"] = mastered_list
        return new_profile

    @staticmethod
    def _update_profile_by_stats(profile: Dict, stats: Dict) -> Dict:
        """根据学习行为统计，优化知识点掌握情况+学习动力"""
        new_profile = {**profile}
        weak_list = list(new_profile.get("weak_points", []))
        mastered_list = list(new_profile.get("mastered_points", []))

        studied_points = set(stats.get("points_studied", []))
        if stats.get("quizzes_completed", 0) >= EVAL_QUIZ_MIN_COUNT:
            for point in studied_points:
                if point in weak_list:
                    weak_list.remove(point)
                if point not in mastered_list:
                    mastered_list.append(point)

        new_profile["weak_points"] = weak_list
        new_profile["mastered_points"] = mastered_list

        study_hours = stats.get("total_study_hours", 0)
        resource_views = stats.get("resources_viewed", 0)
        if study_hours > EVAL_STUDY_HOURS_THRESHOLD:
            new_profile["motivation_level"] = MOTIVATION_LEVEL_HIGH
        elif resource_views > EVAL_RESOURCE_VIEWS_THRESHOLD:
            new_profile["motivation_level"] = MOTIVATION_LEVEL_MEDIUM

        return new_profile

    # ------------------------------------------------------------------
    # 批量更新（每天凌晨执行）
    # ------------------------------------------------------------------
    @staticmethod
    async def batch_update_all_users() -> Dict[str, int]:
        """
        批量更新所有用户的 motivation_level 和频率型 weak_points。
        由定时任务调度器每天凌晨调用。
        """
        from utils.behavior_tracker import behavior_tracker
        from models.database import AsyncSessionLocal
        from models.profile import UserProfile
        from models.user import User
        from sqlalchemy import select
        from utils.api_helpers import get_current_utc_time

        updated = 0
        failed = 0

        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User.id))
            user_ids = [row[0] for row in result.all()]

        for uid in user_ids:
            try:
                stats = await behavior_tracker.get_user_stats(uid, days=7)
                if not stats:
                    continue

                async with AsyncSessionLocal() as session:
                    db_result = await session.execute(
                        select(UserProfile).where(UserProfile.user_id == uid)
                    )
                    profile = db_result.scalar_one_or_none()
                    if not profile:
                        continue

                    changed = False

                    # 1. 更新 motivation_level
                    study_days = stats.get("study_days", 0)
                    total_quizzes = stats.get("quizzes_completed", 0)
                    total_views = stats.get("resources_viewed", 0)
                    denom = total_quizzes + total_views
                    completion_rate = total_quizzes / denom if denom > 0 else 0

                    if study_days >= BATCH_MOTIVATION_STUDY_DAYS_HIGH and completion_rate >= BATCH_MOTIVATION_COMPLETION_RATE_HIGH:
                        new_motivation = MOTIVATION_LEVEL_HIGH
                    elif study_days >= BATCH_MOTIVATION_STUDY_DAYS_MEDIUM and completion_rate >= BATCH_MOTIVATION_COMPLETION_RATE_MEDIUM:
                        new_motivation = MOTIVATION_LEVEL_MEDIUM
                    else:
                        new_motivation = "low"

                    if profile.motivation_level != new_motivation:
                        profile.motivation_level = new_motivation
                        changed = True

                    # 2. 基于提问频率添加 weak_points
                    question_by_point = stats.get("question_by_point", {})
                    weak_list = list(profile.weak_points or [])
                    for kp, count in question_by_point.items():
                        if count >= BATCH_WEAK_POINT_QUESTION_COUNT and kp not in weak_list:
                            weak_list.append(kp)
                            changed = True

                    if changed:
                        profile.updated_at = get_current_utc_time()
                        await session.commit()
                        updated += 1
            except Exception as e:
                failed += 1

        return {"updated": updated, "failed": failed, "total": len(user_ids)}

    async def update_motivation_on_milestone(self, user_id: int) -> None:
        """
        用户完成里程碑时（如连续完成3个资源），立即更新动力水平。
        """
        from utils.behavior_tracker import behavior_tracker
        from models.database import AsyncSessionLocal
        from models.profile import UserProfile
        from sqlalchemy import select
        from utils.api_helpers import get_current_utc_time

        stats = await behavior_tracker.get_user_stats(user_id, days=7)
        if not stats:
            return

        study_days = stats.get("study_days", 0)
        total_quizzes = stats.get("quizzes_completed", 0)
        total_views = stats.get("resources_viewed", 0)
        denom = total_quizzes + total_views
        completion_rate = total_quizzes / denom if denom > 0 else 0

        if study_days >= BATCH_MOTIVATION_STUDY_DAYS_HIGH and completion_rate >= BATCH_MOTIVATION_COMPLETION_RATE_HIGH:
            new_motivation = MOTIVATION_LEVEL_HIGH
        elif study_days >= BATCH_MOTIVATION_STUDY_DAYS_MEDIUM and completion_rate >= BATCH_MOTIVATION_COMPLETION_RATE_MEDIUM:
            new_motivation = MOTIVATION_LEVEL_MEDIUM
        else:
            new_motivation = "low"

        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
                profile = result.scalar_one_or_none()
                if profile and profile.motivation_level != new_motivation:
                    profile.motivation_level = new_motivation
                    profile.updated_at = get_current_utc_time()
                    await session.commit()
                    self.logger.info(f"🎯 里程碑触发动力更新: user={user_id}, level={new_motivation}")
        except Exception as e:
            self.logger.warning(f"⚠️ 里程碑动力更新失败: {e}")
