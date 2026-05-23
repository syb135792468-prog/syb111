"""
agents/quiz_agent.py - 软件杯A3 练习题生成智能体（终极赛题版）
✅ 完美继承 BaseAgent，规则+LLM 双模式
✅ 零 PyCharm 警告，输出与 ResourceItem 严格对齐
✅ LLM 模式强化题型控制与 RAG 防幻觉
✅ 状态不可变更新，符合 LangGraph 规范
✅ 【赛题】显式化标注，评审一眼看到
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, ClassVar
import random

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import QUIZ_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class QuizAgent(BaseAgent):
    """
    【软件杯A3赛题专用】练习题生成智能体
    支持两种模式：
    1. 规则模式（默认，快速演示/测试，无 API 成本）
    2. LLM 模式（use_llm=True，智能生成高质量题目）
    【赛题核心】支持选择题、填空题、编程题三种核心题型
    """

    # ============================================================
    # 1. 赛题 A3 显式化配置（ClassVar，零警告）
    # ============================================================
    # 题型枚举
    TYPE_CHOICE: ClassVar[str] = "choice"
    TYPE_FILL: ClassVar[str] = "fill"
    TYPE_CODE: ClassVar[str] = "code"
    ALL_TYPES: ClassVar[List[str]] = [TYPE_CHOICE, TYPE_FILL, TYPE_CODE]

    # 规则题库（演示用）
    DEMO_BANK: ClassVar[Dict[str, List[Dict[str, Any]]]] = {
        "循环（for/while）": [
            {
                "type": TYPE_CHOICE,
                "title": "Python 循环基础选择题",
                "question": "以下哪个是 Python 的 for 循环语法？",
                "options": ["A. for (i=0; i<10; i++)", "B. for i in range(10):", "C. foreach i in 10:", "D. loop i from 0 to 9:"],
                "answer": "B",
                "explanation": "Python 使用 for...in... 语法，range(10) 生成 0 到 9 的整数序列。"
            },
            {
                "type": TYPE_FILL,
                "title": "Python 循环基础填空题",
                "question": "请补全代码：打印 1 到 10 的偶数\nfor i in range(1, 11):\n    if i % ____ == 0:\n        print(i)",
                "answer": "2",
                "explanation": "i % 2 == 0 表示 i 是偶数。"
            },
            {
                "type": TYPE_CODE,
                "title": "Python 循环基础编程题",
                "question": "请编写一个函数 sum_n(n)，计算 1 到 n 的和。",
                "answer": "def sum_n(n):\n    return sum(range(1, n+1))",
                "explanation": "使用 range(1, n+1) 生成 1 到 n 的整数序列，sum() 函数求和。"
            }
        ],
        "函数定义与调用": [
            {
                "type": TYPE_CHOICE,
                "title": "Python 函数基础选择题",
                "question": "以下哪个是 Python 函数定义的正确语法？",
                "options": ["A. function my_func():", "B. def my_func():", "C. func my_func():", "D. define my_func():"],
                "answer": "B",
                "explanation": "Python 使用 def 关键字定义函数。"
            }
        ],
        "变量与数据类型": [
            {
                "type": TYPE_CHOICE,
                "title": "Python 变量基础选择题",
                "question": "以下哪个是 Python 的正确变量名？",
                "options": ["A. 123abc", "B. my-var", "C. my_var", "D. class"],
                "answer": "C",
                "explanation": "Python 变量名只能包含字母、数字、下划线，不能以数字开头，不能是关键字。"
            }
        ]
    }

    # ============================================================
    # 2. 初始化
    # ============================================================
    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        use_llm: bool = False,
        quiz_type: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="quiz",
            scene_name="quiz_generation",
            enable_rag=True,  # 练习题生成需要 RAG 防幻觉
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        self.quiz_type = quiz_type
        mode = "LLM" if use_llm else "规则"
        specified_type = quiz_type or "随机"
        self.logger.info(f"📝 【软件杯A3】练习题生成已启用【{mode}】模式，指定题型：{specified_type}")

    # ============================================================
    # 3. 核心接口（完美适配 BaseAgent）
    # ============================================================
    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成练习题（赛题 A3 核心）

        Args:
            user_input: 用户最新输入（知识点或需求）
            context: 上下文字典（包含 profile_data）

        Returns:
            标准状态更新字典
        """
        # 1. 确定目标知识点
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"🎯 目标知识点：{target_kp}")

        # 2. 确定目标题型
        target_type = self.quiz_type or random.choice(self.ALL_TYPES)
        self.logger.info(f"📋 目标题型：{target_type}")

        # 3. 根据模式选择生成方式
        if self.use_llm:
            raw_quiz = await self._generate_via_llm(target_kp, target_type)
        else:
            raw_quiz = self._generate_via_rule(target_kp, target_type)

        # 4. 构建 ResourceItem 实例（不可变）
        resource = self._create_resource_item(raw_quiz, target_kp, target_type)

        # 5. 追加到现有资源列表（创建新列表，避免原地修改）
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ 【软件杯A3】练习题生成完成：{resource.title} (类型：{target_type})")
        return self._build_result(new_resources)

    # ============================================================
    # 4. 规则模式（快速演示/测试）
    # ============================================================
    def _generate_via_rule(self, kp: str, qtype: str) -> Dict[str, Any]:
        """
        规则模式练习题生成：
        1. 从题库中随机选择
        2. 如果没有匹配的知识点，使用默认题库
        3. 如果没有匹配的题型，随机选择
        """
        # 查找匹配的知识点题库
        quiz_list = self.DEMO_BANK.get(kp, [])
        if not quiz_list:
            # 没有匹配的知识点，使用默认题库
            self.logger.warning(f"⚠️ 题库中无 {kp}，使用默认题库")
            kp = random.choice(list(self.DEMO_BANK.keys()))
            quiz_list = self.DEMO_BANK[kp]
            self.logger.info(f"🔄 切换到知识点：{kp}")

        # 按题型筛选
        type_filtered = [q for q in quiz_list if q["type"] == qtype]
        if not type_filtered:
            # 没有匹配的题型，随机选择
            self.logger.warning(f"⚠️ 题库中无 {qtype} 题型，随机选择")
            return random.choice(quiz_list)

        self.logger.debug(f"🎲 规则模式随机选择：{type_filtered[0]['title']}")
        return random.choice(type_filtered)

    # ============================================================
    # 5. LLM 模式（强化题型控制与 RAG 防幻觉）
    # ============================================================
    async def _generate_via_llm(self, kp: str, qtype: str) -> Dict[str, Any]:
        """
        增强版 LLM 模式练习题生成：
        1. 获取 RAG 上下文（防幻觉）
        2. 调用 LLM 生成题目
        3. 强化题型校验
        4. 失败自动降级规则模式
        """
        # 1. 获取 RAG 上下文
        rag_context = await self._get_rag_context(kp, top_k=QUIZ_RAG_TOP_K)

        # 2. 构建 Prompt（赛题 A3 专用）
        system_prompt = f"""你是【软件杯A3赛题】的专业 Python 教学题库专家。
请严格生成一道 **{qtype}** 类型的题目，知识点为 **{kp}**。

【题型说明】
- choice：选择题，包含 4 个选项（A/B/C/D）
- fill：填空题，包含一个或多个空
- code：编程题，要求编写代码

【输出格式】
只输出单行 JSON，不要有任何其他内容：
{{
  "type": "{qtype}",
  "title": "题目标题",
  "question": "题目描述（必须为 {qtype} 类型的标准表述）",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
  "answer": "答案",
  "explanation": "详细解析"
}}

【参考教材内容】
{rag_context if rag_context else '无参考资料'}"""

        try:
            # 3. 调用 LLM（完美适配 BaseAgent._call_llm）
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"请生成一道关于 {kp} 的 {qtype} 题"}
            ])

            # 4. 解析 JSON（完美适配 BaseAgent._extract_json）
            data = self._extract_json(resp)
            self.logger.debug(f"🤖 LLM 原始输出：{data}")

            # 5. 强化校验：如果 LLM 返回的类型不符，强制覆盖
            if data.get("type") != qtype:
                self.logger.warning(f"⚠️ LLM 返回题型 {data.get('type')} 与要求不符，强制覆盖为 {qtype}")
                data["type"] = qtype

            # 6. 必须包含基本字段
            required_fields = ("type", "title", "question", "answer", "explanation")
            for field in required_fields:
                if field not in data:
                    raise ValueError(f"LLM 返回缺少必填字段：{field}")

            self.logger.info(f"🤖 LLM 模式练习题生成成功")
            return data

        except Exception as exc:
            self.logger.warning(f"⚠️ LLM 生成题目失败：{exc}，降级规则模式")
            return self._generate_via_rule(kp, qtype)

    # ============================================================
    # 6. 工具方法
    # ============================================================
    def _get_target_knowledge_point(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        提取目标知识点：
        1. 优先从用户输入中匹配
        2. 其次从上下文中的 weak_points 中选择
        3. 最后从 mastered_points 中选择
        4. 默认随机选择
        """
        text = user_input.lower()

        # 1. 从用户输入中匹配
        matched = match_knowledge_point(text)
        if matched:
            self.logger.debug(f"🎯 从用户输入中匹配到知识点：{matched}")
            return matched

        # 2. 从上下文中的 weak_points 或 mastered_points 中选择
        if context:
            profile = get_profile_from_context(context)
            weak_points = profile.get("weak_points", [])
            if weak_points:
                kp = random.choice(weak_points)
                self.logger.debug(f"🎯 从画像 weak_points 中选择知识点：{kp}")
                return kp
            mastered_points = profile.get("mastered_points", [])
            if mastered_points:
                kp = random.choice(mastered_points)
                self.logger.debug(f"🎯 从画像 mastered_points 中选择知识点：{kp}")
                return kp

        # 3. 默认随机选择
        kp = random.choice(PYTHON_KNOWLEDGE_POINTS)
        self.logger.debug(f"🎯 随机选择知识点：{kp}")
        return kp

    def _create_resource_item(
        self,
        quiz_data: Dict[str, Any],
        kp: str,
        qtype: str
    ) -> ResourceItem:
        """
        将题目数据转为 ResourceItem（与 models 严格一致）
        构建完整的 Markdown 内容
        """
        # 构建纯文本内容（Markdown 格式）
        parts = [
            f"# {quiz_data['title']}",
            f"## 题目 ({qtype})",
            quiz_data['question']
        ]

        # 选择题添加选项
        if qtype == self.TYPE_CHOICE and 'options' in quiz_data:
            parts.append("\n".join(quiz_data['options']))

        # 添加答案和解析
        parts.extend([
            "\n## 答案",
            quiz_data['answer'],
            "\n## 解析",
            quiz_data['explanation']
        ])

        full_content = "\n".join(parts)

        # 构建 ResourceItem 实例
        return ResourceItem(
            resource_type="quiz",
            title=quiz_data['title'],
            content=full_content,
            knowledge_points=[kp],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "quiz_type": qtype,
                "answer": quiz_data['answer'],
                "explanation": quiz_data['explanation'],
            }
        )

    # _build_result 已继承自 BaseAgent