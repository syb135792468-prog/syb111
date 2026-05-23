"""
agents/tutor_agent.py - 软件杯A3 智能辅导智能体
功能：RAG驱动精准答疑 | 支持LLM/规则双模式 | 对话历史闭环更新
规范：统一继承BaseAgent | 防幻觉设计 | 适配LangGraph工作流
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from config.constants import DEFAULT_RAG_TOP_K, TUTOR_HISTORY_WINDOW, TUTOR_INPUT_TRUNCATE_LENGTH
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
            # 提取最近4轮对话上下文
            chat_history = context.get("chat_history", []) if context else []
            recent_history = chat_history[-TUTOR_HISTORY_WINDOW:]
            history_text = "\n".join(
                f"{'学生' if m['role'] == 'user' else '老师'}: {m['content']}" for m in recent_history
            )

            # 系统提示词（防幻觉核心）
            system_prompt = f"""
你是专业且耐心的Python一对一辅导老师，必须严格遵守规则：
1. 仅基于【教材参考】内容回答，绝不编造知识
2. 语言通俗易懂，条理清晰，可附带简单示例
3. 结合【对话历史】理解上下文，保持对话连贯
4. 无相关知识时，诚实告知并给出学习建议

【对话历史】
{history_text}

【教材参考】
{rag_context}
"""

            # 复用基类封装LLM（自动重试+降级）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ]
            return await self._call_llm(messages)

        except Exception as e:
            self.logger.warning(f"⚠️ LLM调用失败，自动降级为规则模式：{str(e)}")
            return self._rule_answer(question)

    @staticmethod
    def _rule_answer(user_input: str) -> str:
        """规则模式兜底：关键词快速应答，无LLM也可演示"""
        input_text = user_input.lower()

        if any(key in input_text for key in ["循环", "for", "while"]):
            return (
                "Python 循环知识点：\n"
                "1. for 循环：遍历列表、字符串等序列\n"
                "2. while 循环：条件为真时持续执行\n"
                "示例代码：\n"
                "```python\nfor i in range(5):\n    print(i)\n```\n"
                "⚠️ 注意：避免死循环，合理使用 break/continue"
            )

        elif any(key in input_text for key in ["函数", "def"]):
            return (
                "Python 函数定义：\n"
                "1. 使用 def 关键字定义函数\n"
                "2. 支持参数、默认参数、返回值\n"
                "示例代码：\n"
                "```python\ndef greet(name):\n    return f'Hello {name}'\n```"
            )

        else:
            return "我可以为你解答Python相关问题！你可以询问循环、函数、列表等知识点~"

    @staticmethod
    def _extract_query(user_input: str, context: Optional[Dict] = None) -> str:
        """统一规则：提取RAG检索关键词（与全项目Agent逻辑一致）"""
        input_text = user_input.lower()

        # 优先匹配标准知识点
        matched = match_knowledge_point(input_text)
        if matched:
            return matched

        # 兜底：用户薄弱知识点
        profile = get_profile_from_context(context)
        if profile:
            weak_points = profile.get("weak_points", [])
            if weak_points:
                return weak_points[0]

        # 最终兜底：截取用户问题
        return user_input[:TUTOR_INPUT_TRUNCATE_LENGTH]