"""
agents/tutor_agent.py - 软件杯A3 智能辅导智能体
功能：RAG驱动精准答疑 | 支持LLM/规则双模式 | 对话历史闭环更新
增强：代码错误分析 | 多模态解答 | 代码执行集成
规范：统一继承BaseAgent | 防幻觉设计 | 适配LangGraph工作流
"""
from __future__ import annotations

import re
from typing import Dict, Any, Optional, List

from agents.base_agent import BaseAgent
from ai.real_time_adaptation import real_time_adaptation_engine
from config.constants import DEFAULT_RAG_TOP_K, TUTOR_HISTORY_WINDOW, TUTOR_INPUT_TRUNCATE_LENGTH, DEFAULT_TOPIC
from utils.agent_helpers import match_knowledge_point, get_profile_from_context
from utils.code_error_analyzer import code_error_analyzer, analyze_code_with_suggestions
from utils.visual_explainer import (
    visual_explainer,
    generate_concept_diagram,
    generate_process_flowchart,
    generate_code_visualization,
)


class TutorAgent(BaseAgent):
    """智能辅导智能体：基于教材知识库答疑，自动维护对话历史，支持降级兜底"""

    # 问题类型分类
    QUESTION_TYPES = {
        'code_error': ['错误', '报错', 'bug', 'SyntaxError', 'TypeError', 'NameError', 'IndexError'],
        'code_question': ['代码', '编写', '实现', '怎么写', '如何写', 'def', 'class'],
        'concept': ['是什么', '什么是', '定义', '概念', '解释', '说明'],
        'debug': ['调试', '排错', '修复', '解决', '为什么'],
        'practice': ['练习', '题目', '作业', '测验', '考试'],
    }

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

    def _detect_question_type(self, user_input: str) -> str:
        """
        检测问题类型
        
        Returns:
            question_type: code_error | code_question | concept | debug | practice | other
        """
        lower_input = user_input.lower()
        
        for qtype, keywords in self.QUESTION_TYPES.items():
            for keyword in keywords:
                if keyword.lower() in lower_input:
                    self.logger.debug(f"🔍 检测到问题类型: {qtype}")
                    return qtype
        
        # 检查是否包含代码块
        if '```' in user_input or '```python' in user_input:
            return 'code_question'
        
        return 'other'

    def _extract_code_from_input(self, user_input: str) -> Optional[str]:
        """从用户输入中提取代码块"""
        # 匹配 ```python ... ```
        match = re.search(r'```(?:python)?\s*(.*?)\s*```', user_input, re.DOTALL)
        if match:
            return match.group(1).strip()
        
        # 匹配缩进代码块（4空格或制表符）
        lines = user_input.split('\n')
        code_lines = []
        for line in lines:
            if line.startswith('    ') or line.startswith('\t'):
                code_lines.append(line)
            elif code_lines:
                break
        
        if code_lines:
            return '\n'.join(code_lines)
        
        return None

    async def _execute_code(self, code: str) -> Dict[str, Any]:
        """
        执行代码并返回结果
        
        Returns:
            {
                'success': bool,
                'output': str,
                'error': str,
                'execution_time': float
            }
        """
        try:
            from utils.code_executor import execute_python_code
            result = await execute_python_code(code)
            return result
        except ImportError:
            self.logger.warning("代码执行引擎不可用")
            return {'success': False, 'output': '', 'error': '代码执行引擎未配置', 'execution_time': 0}
        except Exception as e:
            self.logger.error(f"代码执行失败: {e}")
            return {'success': False, 'output': '', 'error': str(e), 'execution_time': 0}

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Agent 核心执行入口
        执行流程：检测问题类型 → 代码分析（如适用）→ 检索知识 → 生成多模态回答 → 更新对话历史
        """
        try:
            # 1. 检测问题类型
            question_type = self._detect_question_type(user_input)
            self.logger.info(f"🔍 问题类型：{question_type}")

            # 2. 提取代码（如果包含）并分析
            code_snippet = self._extract_code_from_input(user_input)
            code_analysis = None
            if code_snippet:
                code_analysis = analyze_code_with_suggestions(code_snippet)
                self.logger.info(f"📊 代码分析结果：{'有错误' if code_analysis.get('has_errors') else '正常'}")

            # 3. 提取RAG检索关键词（知识点/薄弱点）
            query = self._extract_query(user_input, context)
            self.logger.info(f"🔍 辅导检索关键词：{query}")

            # 4. 获取知识库参考内容
            rag_context = await self._get_rag_context(query, top_k=DEFAULT_RAG_TOP_K)

            # 5. 生成辅导答案（多模态策略）
            answer = await self._generate_multimodal_answer(
                user_input, rag_context, context, question_type, code_snippet, code_analysis
            )

            # 6. 不可变更新对话历史（工作流标准规范）
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

    async def _generate_multimodal_answer(
        self,
        user_input: str,
        rag_context: str,
        context: Optional[Dict],
        question_type: str,
        code_snippet: Optional[str] = None,
        code_analysis: Optional[Dict] = None,
    ) -> str:
        """
        生成多模态解答
        根据问题类型选择合适的解答策略
        """
        # 1. 代码错误分析
        if question_type == 'code_error' or (code_analysis and code_analysis.get('has_errors')):
            return await self._generate_code_error_answer(user_input, code_snippet, code_analysis, context)
        
        # 2. 代码相关问题（带图解）
        if question_type == 'code_question' and code_snippet:
            return await self._generate_code_with_diagram_answer(user_input, code_snippet, rag_context, context)
        
        # 3. 概念类问题（带图解）
        if question_type == 'concept':
            return await self._generate_concept_with_diagram_answer(user_input, rag_context, context)
        
        # 4. 调试相关问题
        if question_type == 'debug':
            return await self._generate_debug_answer(user_input, rag_context, context)
        
        # 5. 默认：通用答疑（带可选图解）
        return await self._generate_default_answer(user_input, rag_context, context)

    async def _generate_code_error_answer(
        self,
        user_input: str,
        code_snippet: Optional[str],
        code_analysis: Optional[Dict],
        context: Optional[Dict],
    ) -> str:
        """
        生成代码错误分析回答
        包含：错误诊断、修复建议、正确代码、相关知识点
        """
        if not code_analysis:
            return await self._llm_answer(user_input, "", context)

        errors = code_analysis.get('errors', [])
        suggestions = code_analysis.get('suggestions', [])
        fixed_code = code_analysis.get('fixed_code')

        # 构建错误分析报告
        report_parts = []
        
        report_parts.append("🔍 **代码错误分析**")
        
        if errors:
            report_parts.append("\n**发现的问题：**")
            for i, error in enumerate(errors, 1):
                error_type = error.get('type', 'Unknown')
                message = error.get('message', '')
                line = error.get('line', '')
                report_parts.append(f"{i}. **{error_type}**{f'（第{line}行）' if line else ''}")
                report_parts.append(f"   {message}")
        
        if suggestions:
            report_parts.append("\n**修复建议：**")
            for i, suggestion in enumerate(suggestions, 1):
                report_parts.append(f"{i}. {suggestion}")
        
        if fixed_code:
            report_parts.append("\n**修复后的代码：**")
            report_parts.append(f"```python\n{fixed_code}\n```")
        
        # 添加相关知识点
        related_topics = []
        for error in errors:
            topics = error.get('related_topics', [])
            related_topics.extend(topics)
        
        if related_topics:
            unique_topics = list(set(related_topics))
            report_parts.append(f"\n📚 **相关学习资源：**")
            report_parts.append(f"建议学习：{', '.join(unique_topics)}")

        # 最后用LLM润色并添加更详细的解释
        report_text = "\n".join(report_parts)
        
        # 调用LLM生成更详细的解释
        final_answer = await self._llm_answer(
            f"请帮我详细解释这段代码错误分析报告，并给出更详细的学习建议：\n\n{report_text}",
            "",
            context
        )
        
        return final_answer

    async def _generate_code_answer(
        self,
        user_input: str,
        code_snippet: str,
        rag_context: str,
        context: Optional[Dict],
    ) -> str:
        """
        生成代码相关回答
        包含：代码解释、执行结果、优化建议
        """
        # 执行代码获取结果
        execution_result = await self._execute_code(code_snippet)
        
        answer_parts = []
        answer_parts.append("💻 **代码分析**")
        answer_parts.append(f"\n**原始代码：**")
        answer_parts.append(f"```python\n{code_snippet}\n```")
        
        if execution_result['success']:
            answer_parts.append(f"\n**执行结果：**")
            answer_parts.append(f"```\n{execution_result['output']}\n```")
            answer_parts.append(f"⏱️ 执行时间：{execution_result['execution_time']:.2f}秒")
        else:
            answer_parts.append(f"\n**执行错误：**")
            answer_parts.append(f"```\n{execution_result['error']}\n```")
            
            # 分析错误
            error_analysis = code_error_analyzer.analyze_error_output(execution_result['error'])
            if error_analysis.get('suggestions'):
                answer_parts.append("\n**错误分析与修复建议：**")
                for i, suggestion in enumerate(error_analysis['suggestions'], 1):
                    answer_parts.append(f"{i}. {suggestion}")
        
        # 调用LLM添加详细解释
        answer_text = "\n".join(answer_parts)
        final_answer = await self._llm_answer(
            f"请详细解释这段代码的功能、执行过程和潜在优化空间：\n\n{answer_text}",
            rag_context,
            context
        )
        
        return final_answer

    async def _generate_debug_answer(
        self,
        user_input: str,
        rag_context: str,
        context: Optional[Dict],
    ) -> str:
        """
        生成调试相关回答
        包含：问题诊断、调试步骤、验证方法
        """
        # 调用LLM生成调试指南
        debug_prompt = f"""
用户正在调试问题：{user_input}

请提供详细的调试步骤，包括：
1. 可能的原因分析
2. 逐步调试方法
3. 验证解决方案的方法
4. 相关知识点回顾
"""
        
        return await self._llm_answer(debug_prompt, rag_context, context)

    async def _generate_code_with_diagram_answer(
        self,
        user_input: str,
        code_snippet: str,
        rag_context: str,
        context: Optional[Dict],
    ) -> str:
        """
        生成带图解的代码回答
        包含：代码解释、执行结果、代码流程图
        """
        # 生成代码流程图
        flow_diagram = generate_code_visualization(code_snippet)
        
        # 执行代码获取结果
        execution_result = await self._execute_code(code_snippet)
        
        answer_parts = []
        answer_parts.append("💻 **代码分析与可视化**")
        answer_parts.append(f"\n**原始代码：**")
        answer_parts.append(f"```python\n{code_snippet}\n```")
        
        if execution_result['success']:
            answer_parts.append(f"\n**执行结果：**")
            answer_parts.append(f"```\n{execution_result['output']}\n```")
        else:
            answer_parts.append(f"\n**执行错误：**")
            answer_parts.append(f"```\n{execution_result['error']}\n```")
        
        # 添加流程图
        answer_parts.append("\n📊 **代码执行流程：**")
        answer_parts.append(flow_diagram)
        
        # 调用LLM添加详细解释
        answer_text = "\n".join(answer_parts)
        final_answer = await self._llm_answer(
            f"请详细解释这段代码的功能、执行过程和潜在优化空间：\n\n{answer_text}",
            rag_context,
            context
        )
        
        return final_answer

    async def _generate_concept_with_diagram_answer(
        self,
        user_input: str,
        rag_context: str,
        context: Optional[Dict],
    ) -> str:
        """
        生成带图解的概念回答
        包含：概念解释、相关概念关系图
        """
        # 获取用户画像，判断学习风格
        profile = get_profile_from_context(context)
        learning_style = profile.get('learning_style', 'mixed')
        
        # 提取相关知识点
        related_topics = []
        if rag_context:
            # 简单提取关键词作为相关主题
            keywords = ['变量', '函数', '循环', '条件', '类', '对象', '模块', '异常']
            for kw in keywords:
                if kw in user_input or kw in rag_context:
                    related_topics.append(kw)
        
        # 生成概念关系图
        concept_diagram = generate_concept_diagram(user_input[:50], related_topics[:5])
        
        # 构建回答
        answer_parts = []
        answer_parts.append(f"📚 **{user_input}**")
        answer_parts.append("\n**概念关系图：**")
        answer_parts.append(concept_diagram)
        
        # 调用LLM添加详细解释
        answer_text = "\n".join(answer_parts)
        final_answer = await self._llm_answer(
            f"请详细解释这个概念，包括定义、特点、用法和示例：\n\n{answer_text}",
            rag_context,
            context
        )
        
        return final_answer

    async def _generate_default_answer(
        self,
        user_input: str,
        rag_context: str,
        context: Optional[Dict],
    ) -> str:
        """
        生成默认回答（带可选图解）
        根据用户学习风格决定是否添加图解
        """
        profile = get_profile_from_context(context)
        learning_style = profile.get('learning_style', 'mixed')
        
        # 视觉型学习者添加图解
        if learning_style == 'visual':
            # 尝试生成相关图解
            related_topics = []
            keywords = ['变量', '函数', '循环', '条件', '类', '对象', '模块']
            for kw in keywords:
                if kw in user_input:
                    related_topics.append(kw)
            
            if related_topics:
                diagram = generate_concept_diagram(user_input[:50], related_topics[:5])
                enhanced_question = f"{user_input}\n\n请用图解方式解释：\n{diagram}"
                return await self._llm_answer(enhanced_question, rag_context, context)
        
        return await self._llm_answer(user_input, rag_context, context)

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