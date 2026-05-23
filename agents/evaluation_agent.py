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
)
from utils.agent_helpers import get_profile_from_context


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
        completed_res = sum(1 for r in resources if r.get("status") == "completed")

        # 统计数据兜底
        study_hours = stats.get("total_study_hours", 0) if stats else 0
        quiz_count = stats.get("quizzes_completed", 0) if stats else 0

        # 构建报告
        report_lines = [
            "📊 **学习效果评估报告**",
            f"- 累计学习：{study_hours:.1f} 小时",
            f"- 资源完成：{completed_res}/{total_resources}",
            f"- 练习完成：{quiz_count} 次",
            f"- 已掌握：{', '.join(mastered_points) if mastered_points else '暂无'}",
            f"- 待加强：{', '.join(weak_points) if weak_points else '暂无'}",
        ]

        # 个性化建议
        if not weak_points:
            report_lines.append("\n🎉 很棒！所有知识点均已掌握，继续保持学习热情！")
        else:
            report_lines.append(f"\n💪 学习建议：重点加强 {', '.join(weak_points)} 的练习")

        return "\n".join(report_lines)

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
            completed_res = sum(1 for r in resources if r.get("status") == "completed")

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
            prompt = (
                "你是专业的Python学习评估师，生成300字内的鼓励式评估报告，包含：\n"
                "1. 学习概况 2. 进步亮点 3. 针对性建议\n"
                f"评估数据：{context_text}"
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
            if res.get("status") == "completed":
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
            new_profile["motivation_level"] = "high"
        elif resource_views > EVAL_RESOURCE_VIEWS_THRESHOLD:
            new_profile["motivation_level"] = "medium"

        return new_profile