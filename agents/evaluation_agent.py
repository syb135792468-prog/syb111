"""
agents/evaluation_agent.py - 软件杯A3 学习效果评估智能体
功能：基于学习行为+资源完成度生成评估报告 | 自动更新用户画像知识点
规范：继承BaseAgent | LLM/规则双模式 | 适配LangGraph对话工作流
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from utils.behavior_tracker import behavior_tracker
from config.constants import (
    EVAL_DEFAULT_DAYS, EVAL_TEMPERATURE, EVAL_MAX_TOKENS,
    EVAL_QUIZ_MIN_COUNT, EVAL_STUDY_HOURS_THRESHOLD, EVAL_RESOURCE_VIEWS_THRESHOLD,
    EVAL_REPORT_MAX_WORDS,
    RESOURCE_STATUS_COMPLETED, MOTIVATION_LEVEL_HIGH, MOTIVATION_LEVEL_MEDIUM,
    BATCH_MOTIVATION_STUDY_DAYS_HIGH, BATCH_MOTIVATION_STUDY_DAYS_MEDIUM,
    BATCH_MOTIVATION_COMPLETION_RATE_HIGH, BATCH_MOTIVATION_COMPLETION_RATE_MEDIUM,
    BATCH_WEAK_POINT_QUESTION_COUNT,
)
from utils.agent_helpers import get_profile_from_context, match_knowledge_point


class EvaluationAgent(BaseAgent):
    """学习效果评估智能体：数据驱动评估，自动优化用户掌握/薄弱知识点"""

    def __init__(
            self,
            user_id: Optional[str] = None,
            task_id: Optional[str] = None,
            use_llm: bool = False,
    ) -> None:
        super().__init__(
            agent_name="evaluation",
            scene_name="evaluation",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        run_mode = "LLM" if use_llm else "规则"
        self.logger.info(f"📊 学习效果评估初始化 | 运行模式：{run_mode}")

    async def process(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Agent 核心执行入口
        流程：获取上下文 → 拉取学习统计 → 生成评估报告 → 更新用户画像 → 返回对话状态
        """
        try:
            # 初始化上下文默认值
            context = context or {}
            profile_data = get_profile_from_context(context)
            resource_list = context.get("resource_list", [])
            chat_history = context.get("chat_history", [])

            self.logger.info("📊 开始执行学习效果评估")

            # 1. 获取用户学习行为统计
            study_stats = await self._get_stats(context)

            # 2. 生成评估报告（LLM/规则二选一）
            evaluation_report = (
                await self._llm_evaluate(profile_data, resource_list, study_stats)
                if self.use_llm
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
            # 异常兜底：返回原上下文，保证工作流不中断
            return {
                "chat_history": context.get("chat_history", []),
                "profile_data": get_profile_from_context(context),
                "current_step": "eval",
                "updated_at": self._get_current_utc_time(),
            }

    async def _get_stats(self, context: Dict) -> Optional[Dict[str, Any]]:
        """从行为追踪器获取用户近30天学习统计数据"""
        user_id_str = context.get("user_id") or self.user_id
        if not user_id_str:
            self.logger.warning("未获取到用户ID，跳过行为统计")
            return None

        # 转换用户ID为整型
        try:
            user_id = int(user_id_str)
        except (ValueError, TypeError):
            self.logger.warning(f"用户ID格式无效：{user_id_str}")
            return None

        # 获取学习统计
        try:
            stats = await behavior_tracker.get_user_stats(user_id, days=EVAL_DEFAULT_DAYS)
            self.logger.debug(f"成功获取用户学习统计：{stats}")
            return stats
        except Exception as e:
            self.logger.warning(f"获取学习统计失败：{str(e)}")
            return None

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

        # 统计数据兜底
        study_hours = stats.get("total_study_hours", 0) if stats else 0
        quiz_count = stats.get("quizzes_completed", 0) if stats else 0

        # 个性化建议
        if not weak_points:
            suggestion = "\n🎉 很棒！所有知识点均已掌握，继续保持学习热情！"
        else:
            suggestion = f"\n💪 学习建议：重点加强 {', '.join(weak_points)} 的练习"

        # 加载模板构建报告（实例方法，需要 agent 引用）
        # 由于 _rule_evaluate 是 staticmethod，此处直接拼接
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
        """LLM模式：生成个性化、鼓励式评估报告，失败自动降级规则模式"""
        try:
            # 构造评估上下文数据
            mastered = profile.get("mastered_points", [])
            weak = profile.get("weak_points", [])
            total_res = len(resources)
            completed_res = sum(1 for r in resources if r.get("status") == RESOURCE_STATUS_COMPLETED)

            # 拼接基础信息
            context_text = (
                f"用户画像：\n- 基础水平：{profile.get('knowledge_level', '未知')}\n"
                f"- 学习目标：{profile.get('learning_goal', '未知')}\n"
                f"- 已掌握：{', '.join(mastered) if mastered else '无'}\n"
                f"- 薄弱点：{', '.join(weak) if weak else '无'}\n"
                f"资源完成：{completed_res}/{total_res} 个"
            )

            # 追加行为统计
            if stats:
                context_text += (
                    f"\n\n近30天学习：\n- 总时长：{stats.get('total_study_hours', 0):.1f} 小时\n"
                    f"- 浏览资源：{stats.get('resources_viewed', 0)} 次\n"
                    f"- 完成练习：{stats.get('quizzes_completed', 0)} 题"
                )

            # LLM提示词
            prompt = self._load_prompt(
                "evaluation_user",
                max_words=EVAL_REPORT_MAX_WORDS,
                context_text=context_text,
            )

            # 复用基类LLM调用
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
        """根据已完成资源，自动将知识点从薄弱移至掌握（纯字典操作）"""
        new_profile = {**profile}
        weak_list = list(new_profile.get("weak_points", []))
        mastered_list = list(new_profile.get("mastered_points", []))

        # 收集所有已完成资源的知识点
        finished_kps = set()
        for res in resources:
            if res.get("status") == RESOURCE_STATUS_COMPLETED:
                finished_kps.update(res.get("knowledge_points", []))

        # 更新掌握/薄弱列表
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

        # 练习完成≥2，自动标记学习过的知识点为掌握
        studied_points = set(stats.get("points_studied", []))
        if stats.get("quizzes_completed", 0) >= EVAL_QUIZ_MIN_COUNT:
            for point in studied_points:
                if point in weak_list:
                    weak_list.remove(point)
                if point not in mastered_list:
                    mastered_list.append(point)

        # 更新知识点
        new_profile["weak_points"] = weak_list
        new_profile["mastered_points"] = mastered_list

        # 智能调整学习动力
        study_hours = stats.get("total_study_hours", 0)
        resource_views = stats.get("resources_viewed", 0)
        if study_hours > EVAL_STUDY_HOURS_THRESHOLD:
            new_profile["motivation_level"] = MOTIVATION_LEVEL_HIGH
        elif resource_views > EVAL_RESOURCE_VIEWS_THRESHOLD:
            new_profile["motivation_level"] = MOTIVATION_LEVEL_MEDIUM

        return new_profile

    # ============================================================
    # 批量更新（每天凌晨执行）
    # ============================================================
    @staticmethod
    async def batch_update_all_users() -> Dict[str, int]:
        """
        批量更新所有用户的 motivation_level 和频率型 weak_points。
        由定时任务调度器每天凌晨调用。
        """
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
                    # 简单完成率：quizzes / (quizzes + views)，避免除零
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