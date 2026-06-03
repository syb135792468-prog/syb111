"""
agents/tutor_agent.py - 软件杯A3 智能辅导智能体
功能：RAG驱动精准答疑 | 支持LLM/规则双模式 | 对话历史闭环更新
规范：统一继承BaseAgent | 防幻觉设计 | 适配LangGraph工作流
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from ai.real_time_adaptation import real_time_adaptation_engine
from config.constants import DEFAULT_RAG_TOP_K, TUTOR_HISTORY_WINDOW, TUTOR_INPUT_TRUNCATE_LENGTH, DEFAULT_TOPIC
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class TutorAgent(BaseAgent):
    """智能辅导智能体：基于教材知识库答疑，自动维护对话历史，支持降级兜底"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        use_llm: bool = True,
    ) -> None:
        super().__init__(
            agent_name="tutor",
            scene_name="tutoring",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        run_mode = "LLM" if use_llm else "规则"
        self.logger.info(f"🎓 智能辅导初始化 | 运行模式：{run_mode}")

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Agent 核心执行入口
        执行流程：检索知识 → 生成回答 → 更新对话历史 → 返回标准状态
        """
        try:
            # 1. 提取RAG检索关键词（知识点/薄弱点）
            query = self._extract_query(user_input, context)
            self.logger.info(f"🔍 辅导检索关键词：{query}")

            # 2. 获取知识库参考内容
            rag_context = await self._get_rag_context(query, top_k=DEFAULT_RAG_TOP_K)

            # 3. 生成辅导答案（LLM/规则二选一）
            answer = await self._llm_answer(user_input, rag_context, context) if self.use_llm else self._rule_answer(user_input)

            # 4. 不可变更新对话历史（工作流标准规范）
            chat_history = context.get("chat_history", []) if context else []
            new_chat_history = [*chat_history, {"role": "assistant", "content": answer}]

            self.logger.info("✅ 智能辅导回答生成完成，对话历史已更新")
            return {
                "chat_history": new_chat_history,
                "current_step": "tutor",
                "updated_at": self._get_current_utc_time(),
            }

        except Exception as e:
            self.logger.error(f"❌ 智能辅导执行异常：{str(e)}", exc_info=True)
            # 异常兜底：返回原对话历史，保证工作流不中断
            return {
                "chat_history": context.get("chat_history", []),
                "current_step": "tutor",
                "updated_at": self._get_current_utc_time(),
            }

    async def _llm_answer(
        self,
        question: str,
        rag_context: str,
        context: Optional[Dict] = None,
    ) -> str:
        """LLM生成答案：复用基类LLM调用，严格基于RAG知识防幻觉"""
        try:
            # 提取最近对话上下文
            chat_history = context.get("chat_history", []) if context else []
            recent_history = chat_history[-TUTOR_HISTORY_WINDOW:]
            history_text = "\n".join(
                f"{'学生' if m['role'] == 'user' else '老师'}: {m['content']}" for m in recent_history
            )

            # 提取用户画像（跨会话记忆核心）
            profile = get_profile_from_context(context)
            profile_text = ""
            if profile:
                level_map = {"beginner": "零基础初学者", "intermediate": "有一定基础", "advanced": "进阶学习者"}
                goal_map = {"exam": "考试备考", "interest": "兴趣学习", "employment": "就业求职", "competition": "竞赛提升"}
                style_map = {"visual": "视觉型（喜欢看图/视频）", "auditory": "听觉型（喜欢听讲解）", "kinesthetic": "动手型（喜欢练习）", "mixed": "混合型"}
                profile_text = f"""
【用户画像】
- 水平：{level_map.get(profile.get('knowledge_level', ''), '未知')}
- 目标：{goal_map.get(profile.get('learning_goal', ''), '未知')}
- 风格：{style_map.get(profile.get('learning_style', ''), '未知')}
- 薄弱点：{', '.join(profile.get('weak_points', [])) or '暂无'}
- 已掌握：{', '.join(profile.get('mastered_points', [])) or '暂无'}
"""

            # 实时适应：根据会话内学习状态调整讲解策略
            user_id = context.get("user_id") if context else None
            session_id = context.get("session_id") if context else None
            adaptation_text = ""
            if user_id and session_id:
                # A/B 实验：检查是否启用实时适应
                should_inject_adaptation = True
                try:
                    from ai.experiment_engine import experiment_engine
                    from models.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as exp_db:
                        adapt_config = await experiment_engine.get_variant_config(
                            int(user_id), "realtime_adaptation", exp_db
                        )
                    if adapt_config and not adapt_config.get("inject_learning_state", True):
                        should_inject_adaptation = False
                except Exception:
                    pass

                if should_inject_adaptation:
                    try:
                        adaptation_prompt = real_time_adaptation_engine.get_explanation_prompt(
                            int(user_id), str(session_id)
                        )
                        adaptation_text = f"\n【实时讲解策略】\n{adaptation_prompt}"
                    except (ValueError, TypeError):
                        pass

            # 系统提示词（防幻觉 + 用户画像 + 跨会话记忆 + 实时适应）
            system_prompt = self._load_prompt(
                "tutoring_system",
                profile_text=profile_text + adaptation_text,
                history_text=history_text,
                rag_context=rag_context,
            )

            # 复用基类封装LLM（自动重试+降级）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._load_prompt("tutoring_user", question=question)},
            ]
            return await self._call_llm(messages)

        except Exception as e:
            self.logger.warning(f"⚠️ LLM调用失败：{str(e)}")
            return "抱歉，AI辅导服务暂时不可用，请稍后再试。你也可以先查看相关学习文档和思维导图来辅助理解。"

    @staticmethod
    def _extract_query(user_input: str, context: Optional[Dict] = None) -> str:
        """直接使用用户输入作为检索关键词"""
        return user_input.strip()[:TUTOR_INPUT_TRUNCATE_LENGTH] or DEFAULT_TOPIC