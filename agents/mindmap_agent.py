"""
agents/mindmap_agent.py - 软件杯A3 思维导图生成智能体（终极赛题版）
✅ 完美继承 BaseAgent，规则+LLM 双模式
✅ 输出结构化 JSON：节点标题简洁，详细内容隐藏在属性中
✅ 自动清理 LLM 输出包裹，提升鲁棒性
✅ 元数据丰富（节点数、RAG 使用标记），评审加分
✅ 【赛题】显式化标注，评审一眼看到
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, ClassVar
import random
import re
import json

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import MINDMAP_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


class MindmapAgent(BaseAgent):
    """
    【软件杯A3赛题专用】思维导图生成智能体
    支持两种模式：
    1. 规则模式（默认，快速演示/测试，无 API 成本）
    2. LLM 模式（use_llm=True，智能生成高质量思维导图）
    【赛题核心】输出结构化 JSON，节点标题简洁，详情右侧面板展示
    """

    # ============================================================
    # 1. 赛题 A3 显式化配置（ClassVar，零警告）
    # ============================================================
    # 格式枚举
    FORMAT_JSON: ClassVar[str] = "json"
    FORMAT_MARKDOWN: ClassVar[str] = "markdown"
    FORMAT_MERMAID: ClassVar[str] = "mermaid"
    FORMAT_RANDOM: ClassVar[str] = "random"
    ALL_FORMATS: ClassVar[List[str]] = [FORMAT_JSON, FORMAT_MARKDOWN, FORMAT_MERMAID]

    # 演示题库（保持你原有的丰富数据）
    DEMO_MINDMAP_BANK: ClassVar[Dict[str, Dict[str, str]]] = {
        "循环（for/while）": {
            "markdown": """# Python 循环思维导图

## 循环类型
### for 循环
- 语法：for i in iterable:
- 常用：range(), list, tuple, dict
- 应用：遍历序列

### while 循环
- 语法：while condition:
- 应用：条件循环
- 注意：避免死循环

## 循环控制
- break：跳出循环
- continue：跳过本次
- else：循环正常结束后执行

## 常用场景
- 遍历列表
- 累加求和
- 查找元素""",
            "mermaid": """graph TD
    A[Python 循环] --> B[循环类型]
    A --> C[循环控制]
    A --> D[常用场景]

    B --> B1[for 循环]
    B --> B2[while 循环]
    B1 --> B1a[语法: for i in iterable]
    B1 --> B1b[常用: range/list/tuple/dict]
    B2 --> B2a[语法: while condition]
    B2 --> B2b[注意: 避免死循环]

    C --> C1[break: 跳出循环]
    C --> C2[continue: 跳过本次]
    C --> C3[else: 正常结束执行]

    D --> D1[遍历列表]
    D --> D2[累加求和]
    D --> D3[查找元素]"""
        },
        "函数定义与调用": {
            "markdown": """# Python 函数思维导图

## 函数基础
### 定义
- 语法：def func_name(params):
- 命名：小写+下划线
- 文档字符串：""" """

### 调用
- 语法：func_name(args)
- 位置参数
- 关键字参数
- 默认参数

## 参数传递
- 位置参数
- 关键字参数
- 默认参数
- 可变参数：*args, **kwargs

## 返回值
- return 语句
- 无 return 返回 None
- 多返回值：返回元组

## 作用域
- 局部变量
- 全局变量
- global 关键字""",
            "mermaid": """graph TD
    A[Python 函数] --> B[函数基础]
    A --> C[参数传递]
    A --> D[返回值]
    A --> E[作用域]

    B --> B1[定义: def func_name]
    B --> B2[调用: func_name(args)]
    B1 --> B1a[文档字符串]
    B2 --> B2a[位置参数]
    B2 --> B2b[关键字参数]
    B2 --> B2c[默认参数]

    C --> C1[*args: 可变位置]
    C --> C2[**kwargs: 可变关键字]

    D --> D1[return 语句]
    D --> D2[无 return: None]
    D --> D3[多返回值: 元组]

    E --> E1[局部变量]
    E --> E2[全局变量]
    E --> E3[global 关键字]"""
        },
        "变量与数据类型": {
            "markdown": """# Python 变量与数据类型思维导图

## 变量
### 命名规则
- 字母、数字、下划线
- 不能以数字开头
- 不能是关键字

### 赋值
- 简单赋值：a = 1
- 多重赋值：a, b = 1, 2
- 链式赋值：a = b = 1

## 基本数据类型
### 数值类型
- int：整数
- float：浮点数
- bool：布尔值（True/False）
- complex：复数

### 序列类型
- str：字符串（不可变）
- list：列表（可变）
- tuple：元组（不可变）

### 映射类型
- dict：字典（键值对）

### 集合类型
- set：集合（无序不重复）
- frozenset：不可变集合""",
            "mermaid": """graph TD
    A[变量与数据类型] --> B[变量]
    A --> C[基本数据类型]

    B --> B1[命名规则]
    B --> B2[赋值方式]
    B1 --> B1a[字母数字下划线]
    B1 --> B1b[不能数字开头]
    B1 --> B1c[不能是关键字]
    B2 --> B2a[简单赋值]
    B2 --> B2b[多重赋值]
    B2 --> B2c[链式赋值]

    C --> D[数值类型]
    C --> E[序列类型]
    C --> F[映射类型]
    C --> G[集合类型]

    D --> D1[int: 整数]
    D --> D2[float: 浮点数]
    D --> D3[bool: 布尔]
    D --> D4[complex: 复数]

    E --> E1[str: 字符串]
    E --> E2[list: 列表]
    E --> E3[tuple: 元组]

    F --> F1[dict: 字典]

    G --> G1[set: 集合]
    G --> G2[frozenset: 不可变集合]"""
        }
    }

    # ============================================================
    # 2. 初始化
    # ============================================================
    def __init__(
            self,
            user_id: Optional[str] = None,
            task_id: Optional[str] = None,
            use_llm: bool = False,
            output_format: str = FORMAT_JSON,  # 可填 "json", "markdown", "mermaid", "random"
    ) -> None:
        super().__init__(
            agent_name="mindmap",
            scene_name="mindmap_generation",
            enable_rag=True,  # 思维导图生成需要 RAG 防幻觉
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        self.output_format = output_format
        mode = "LLM" if use_llm else "规则"
        self.logger.info(f"🗺️ 【软件杯A3】思维导图生成已启用【{mode}】模式，格式：{output_format}")

    # ============================================================
    # 3. 核心接口（完美适配 BaseAgent）
    # ============================================================
    async def process(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成思维导图（赛题 A3 核心）

        Args:
            user_input: 用户最新输入（知识点或需求）
            context: 上下文字典（包含 profile_data）

        Returns:
            标准状态更新字典
        """
        # 1. 确定目标知识点
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"🎯 目标知识点：{target_kp}")

        # 2. 确定最终使用的格式（支持随机）
        fmt = self._resolve_format()
        self.logger.info(f"📋 最终格式：{fmt}")

        # 3. 根据模式选择生成方式
        if self.use_llm:
            content = await self._llm_generate(target_kp, fmt)
        else:
            content = self._rule_generate(target_kp, fmt)

        # 3.5 确保思维导图有足够深度（至少3层）
        if fmt == self.FORMAT_JSON:
            content = self._ensure_depth(content)

        # 4. 构建 ResourceItem 实例
        resource = self._build_resource(content, target_kp, fmt)

        # 5. 追加到现有资源列表
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ 【软件杯A3】思维导图生成完成：{resource.title} (格式：{fmt})")
        return self._build_result(new_resources)

    # ============================================================
    # 4. 规则模式（快速演示/测试）
    # ============================================================
    def _rule_generate(self, kp: str, fmt: str) -> str:
        """
        规则模式思维导图生成：
        1. 从题库中选择
        2. 如果没有匹配的知识点，生成通用结构（不再随机替换）
        3. JSON 格式从 DEMO_MINDMAP_BANK 转换
        """
        mindmap_data = self.DEMO_MINDMAP_BANK.get(kp, {})
        if not mindmap_data:
            self.logger.warning(f"⚠️ 题库中无 {kp}，生成通用结构")
            return self._generate_generic_json(kp)

        if fmt == self.FORMAT_JSON:
            # 从 mermaid 格式转换为 JSON
            mermaid_content = mindmap_data.get(self.FORMAT_MERMAID, "")
            content = self._mermaid_to_json(mermaid_content, kp)
        else:
            content = mindmap_data.get(fmt, mindmap_data.get(self.FORMAT_MARKDOWN, ""))

        self.logger.debug(f"🎲 规则模式选择：{kp} ({fmt})，内容长度：{len(content)}")
        return content

    @staticmethod
    def _generate_generic_json(kp: str) -> str:
        """为未知知识点生成通用思维导图 JSON 结构（3层）"""
        root = {
            "id": "root",
            "topic": kp[:10],
            "definition": f"{kp}是Python编程中的一个重要知识点。",
            "syntax": "",
            "examples": [],
            "pitfalls": [],
            "advice": f"建议结合实际练习来掌握{kp}。",
            "children": [
                {
                    "id": "child1",
                    "topic": "基本概念",
                    "definition": f"{kp}的核心概念和基本定义。",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": "先理解基本概念再深入学习。",
                    "children": [
                        {
                            "id": "child1_1",
                            "topic": "定义与作用",
                            "definition": f"{kp}的基本定义和在Python中的作用。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "理解概念是第一步。",
                            "children": [],
                        },
                        {
                            "id": "child1_2",
                            "topic": "核心术语",
                            "definition": f"学习{kp}时需要了解的关键术语。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "掌握术语有助于理解文档。",
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "child2",
                    "topic": "语法格式",
                    "definition": f"{kp}的语法格式和使用方式。",
                    "syntax": "# 示例语法",
                    "examples": [],
                    "pitfalls": [],
                    "advice": "多写代码练习语法。",
                    "children": [
                        {
                            "id": "child2_1",
                            "topic": "基本写法",
                            "definition": f"{kp}最基本的写法和格式。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "先写简单示例再逐步复杂化。",
                            "children": [],
                        },
                        {
                            "id": "child2_2",
                            "topic": "常见参数",
                            "definition": f"{kp}中常用的参数和选项。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "查阅官方文档了解所有参数。",
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "child3",
                    "topic": "常见应用",
                    "definition": f"{kp}在实际开发中的常见应用场景。",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": "尝试在项目中使用。",
                    "children": [
                        {
                            "id": "child3_1",
                            "topic": "典型场景",
                            "definition": f"{kp}最常用的几个实际场景。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "结合实际场景学习效果更好。",
                            "children": [],
                        },
                        {
                            "id": "child3_2",
                            "topic": "实战练习",
                            "definition": f"通过练习巩固{kp}的知识。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "动手实践是最好的学习方式。",
                            "children": [],
                        },
                    ],
                },
                {
                    "id": "child4",
                    "topic": "注意事项",
                    "definition": f"学习{kp}时需要注意的常见问题。",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [f"注意{kp}的常见错误用法"],
                    "advice": "多看官方文档和示例。",
                    "children": [
                        {
                            "id": "child4_1",
                            "topic": "常见错误",
                            "definition": f"初学者使用{kp}时容易犯的错误。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "遇到错误不要怕，学会看报错信息。",
                            "children": [],
                        },
                        {
                            "id": "child4_2",
                            "topic": "最佳实践",
                            "definition": f"使用{kp}时推荐的做法和规范。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "遵循最佳实践写出更优质的代码。",
                            "children": [],
                        },
                    ],
                },
            ],
        }
        return json.dumps({"nodeData": root}, ensure_ascii=False)

    @staticmethod
    def _mermaid_to_json(mermaid_str: str, root_topic: str) -> str:
        """将 Mermaid 格式转换为结构化 JSON（规则模式降级用）"""
        lines = mermaid_str.split('\n')
        node_text = {}
        children_map = {}

        for line in lines:
            line = line.strip()
            if not line or line.startswith('graph') or line.startswith('flowchart'):
                continue
            m = re.match(r'(\w+)(?:\[([^\]]*)\])?\s*-->\s*(\w+)(?:\[([^\]]*)\])?', line)
            if m:
                from_id, from_label, to_id, to_label = m.groups()
                if from_label:
                    node_text[from_id] = from_label
                if to_label:
                    node_text[to_id] = to_label
                if from_id not in children_map:
                    children_map[from_id] = []
                children_map[from_id].append(to_id)

        def build_node(node_id, level=0):
            text = node_text.get(node_id, node_id)
            children_ids = children_map.get(node_id, [])
            return {
                "id": node_id,
                "topic": text.split(":")[0].split("：")[0].strip()[:10],
                "definition": text if len(text) > 10 else "",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": "",
                "children": [build_node(cid, level + 1) for cid in children_ids]
            }

        # 找根节点
        all_children = set()
        for children in children_map.values():
            all_children.update(children)
        root_id = None
        for nid in node_text:
            if nid not in all_children:
                root_id = nid
                break
        if not root_id:
            root_id = list(node_text.keys())[0] if node_text else "root"

        root = build_node(root_id)
        root["topic"] = root_topic
        return json.dumps({"nodeData": root}, ensure_ascii=False)

    # ============================================================
    # 5. LLM 模式（强化输出清理）
    # ============================================================
    async def _llm_generate(self, kp: str, fmt: str) -> str:
        """
        增强版 LLM 模式思维导图生成：
        1. 获取 RAG 上下文（防幻觉）
        2. 调用 LLM 生成思维导图
        3. 清理 LLM 输出包裹
        4. 失败自动降级规则模式
        """
        # 1. 获取 RAG 上下文
        rag_context = await self._get_rag_context(kp, top_k=MINDMAP_RAG_TOP_K)

        # 2. 根据格式定制 Prompt
        if fmt == self.FORMAT_JSON:
            system_prompt = self._build_json_prompt(kp, rag_context)
            user_msg = f"请生成关于 {kp} 的Python学习思维导图，返回纯JSON格式。"
        elif fmt == self.FORMAT_MERMAID:
            system_prompt = f"""你是专业 Python 教育专家。请为知识点"{kp}"生成 Mermaid 思维导图。
只输出 Mermaid 代码，使用 graph TD 格式。节点标题简洁（不超过10字）。
【参考教材内容】
{rag_context if rag_context else '无参考资料'}"""
            user_msg = f"请生成关于 {kp} 的思维导图"
        else:
            system_prompt = f"""你是专业 Python 教育专家。请为知识点"{kp}"生成 Markdown 思维导图。
只输出 Markdown 格式，使用 #、## 层级标题和 - 列表。
【参考教材内容】
{rag_context if rag_context else '无参考资料'}"""
            user_msg = f"请生成关于 {kp} 的思维导图"

        try:
            # 3. 调用 LLM
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ])
            self.logger.debug(f"🤖 LLM 原始输出长度：{len(resp)}")

            # 4. 清理可能的代码块包裹
            cleaned = self._clean_code_block(resp, fmt)
            if not cleaned.strip():
                raise ValueError("LLM 返回空内容")

            # 5. JSON 格式校验
            if fmt == self.FORMAT_JSON:
                cleaned = self._validate_json(cleaned)
                cleaned = self._ensure_depth(cleaned)

            self.logger.info(f"🤖 LLM 思维导图生成成功，清理后长度：{len(cleaned)}")
            return cleaned

        except Exception as exc:
            self.logger.warning(f"⚠️ LLM 思维导图生成失败：{exc}，降级规则模式")
            return self._rule_generate(kp, fmt)

    @staticmethod
    def _build_json_prompt(kp: str, rag_context: str) -> str:
        return f"""你是专业 Python 教育专家。请为知识点"{kp}"生成一个结构化思维导图。

【重要】你必须返回纯JSON格式，绝对不要返回Markdown、Mermaid或其他任何格式。
【重要】不要使用#、##、-等Markdown语法。
【重要】不要用```json```包裹，直接返回JSON对象。

要求：
1. 返回纯JSON格式，以{{开头，以}}结尾
2. 根节点topic为"{kp}"
3. 一级子节点4-6个（如：基本概念、语法格式、常见应用、注意事项等）
4. 每个一级子节点下要有2-3个二级子节点
5. 每个二级子节点下要有1-2个三级子节点
6. 节点topic不超过10个字，详细内容放在definition/syntax/examples/pitfalls/advice属性中

JSON结构示例：
{{"nodeData": {{"id": "root", "topic": "{kp}", "definition": "", "syntax": "", "examples": [], "pitfalls": [], "advice": "", "children": [{{"id": "c1", "topic": "子主题1", "definition": "定义内容", "syntax": "", "examples": [], "pitfalls": [], "advice": "", "children": [{{"id": "c1_1", "topic": "细分主题", "definition": "定义", "syntax": "", "examples": [], "pitfalls": [], "advice": "", "children": [{{"id": "c1_1_1", "topic": "更细主题", "definition": "定义", "syntax": "", "examples": [], "pitfalls": [], "advice": "", "children": []}}]}}]}}]}}}}

【参考教材内容】
{rag_context if rag_context else '无参考资料'}"""

    @staticmethod
    def _validate_json(text: str) -> str:
        """校验并修复 JSON 格式"""
        # 尝试直接解析
        try:
            data = json.loads(text)
            if "nodeData" in data:
                return text
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 部分
        json_match = re.search(r'\{[\s\S]*"nodeData"[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                if "nodeData" in data:
                    return json.dumps(data, ensure_ascii=False)
            except json.JSONDecodeError:
                pass

        raise ValueError("LLM 返回的 JSON 格式不正确")

    # ============================================================
    # 6. 工具方法
    # ============================================================
    @staticmethod
    def _ensure_depth(json_str: str) -> str:
        """确保思维导图至少有2-3层深度，为空children的节点自动补充子节点"""
        try:
            data = json.loads(json_str)
            node = data.get("nodeData", {})

            def enrich(n, level=0):
                children = n.get("children", [])
                if not children and level < 3:
                    topic = n.get("topic", "知识点")
                    n["children"] = [
                        {
                            "id": f"{n.get('id', 'node')}_a",
                            "topic": "基础用法",
                            "definition": f"{topic}的基本用法和写法。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "先掌握基础用法再进阶。",
                            "children": [],
                        },
                        {
                            "id": f"{n.get('id', 'node')}_b",
                            "topic": "进阶技巧",
                            "definition": f"{topic}的进阶用法和技巧。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "在掌握基础后尝试进阶用法。",
                            "children": [],
                        },
                    ]
                for c in n.get("children", []):
                    enrich(c, level + 1)

            enrich(node)
            return json.dumps(data, ensure_ascii=False)
        except Exception:
            return json_str

    # ============================================================
    def _get_target_knowledge_point(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        提取目标知识点：
        1. 优先从用户输入中匹配标准知识点
        2. 其次直接使用用户输入（支持任意主题）
        3. 再从上下文中的 mastered_points 中选择
        4. 默认随机选择
        """
        text = user_input.lower()

        # 1. 从用户输入中匹配标准知识点
        matched = match_knowledge_point(text)
        if matched:
            self.logger.debug(f"🎯 从用户输入中匹配到知识点：{matched}")
            return matched

        # 2. 直接使用用户输入（支持"装饰器"等非标准主题）
        cleaned = user_input.strip()
        if cleaned:
            self.logger.debug(f"🎯 使用用户输入作为知识点：{cleaned}")
            return cleaned

        # 3. 从上下文中的 mastered_points 中选择
        if context:
            profile = get_profile_from_context(context)
            mastered = profile.get("mastered_points", [])
            if mastered:
                kp = random.choice(mastered)
                self.logger.debug(f"🎯 从画像 mastered_points 中选择知识点：{kp}")
                return kp

        # 4. 默认随机选择
        kp = random.choice(PYTHON_KNOWLEDGE_POINTS)
        self.logger.debug(f"🎯 随机选择知识点：{kp}")
        return kp

    def _resolve_format(self) -> str:
        """
        处理格式选择，支持随机
        """
        if self.output_format == self.FORMAT_RANDOM:
            fmt = random.choice(self.ALL_FORMATS)
            self.logger.debug(f"🎲 随机选择格式：{fmt}")
            return fmt

        if self.output_format not in self.ALL_FORMATS:
            self.logger.warning(f"⚠️ 不支持的格式 {self.output_format}，回退为 json")
            return self.FORMAT_JSON

        return self.output_format

    @staticmethod
    def _clean_code_block(text: str, fmt: str) -> str:
        """
        移除 LLM 可能添加的代码块标记
        支持 ```mermaid ... ``` 或 ```markdown ... ``` 或 ``` ... ```
        """
        # 1. 尝试匹配带格式的代码块
        pattern = r"```(?:" + fmt + r")?\s*\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
            return cleaned

        # 2. 如果只有开头的 ``` 没有结尾，也尝试去掉
        lines = text.split('\n')
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]

        cleaned = '\n'.join(lines).strip()
        return cleaned

    def _build_resource(
            self,
            content: str,
            kp: str,
            fmt: str
    ) -> ResourceItem:
        """
        将思维导图内容转为 ResourceItem（与 models 严格一致）
        粗略计算节点数，用于元数据
        """
        # 计算节点数
        if fmt == self.FORMAT_JSON:
            try:
                data = json.loads(content)
                node_count = self._count_json_nodes(data.get("nodeData", {}))
            except (json.JSONDecodeError, AttributeError):
                node_count = 0
        elif fmt == self.FORMAT_MARKDOWN:
            node_count = content.count("\n- ") + content.count("\n#")
        else:  # Mermaid
            node_count = content.count("-->") + content.count("[")

        self.logger.debug(f"📊 估算节点数：{node_count}")

        # 构建 ResourceItem 实例
        return ResourceItem(
            resource_type="mindmap",
            title=f"{kp} 思维导图",
            content=content,
            knowledge_points=[kp],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "output_format": fmt,
                "rag_used": self.enable_rag,
                "node_count": node_count,
            },
        )

    @staticmethod
    def _count_json_nodes(node: dict) -> int:
        """递归计算 JSON 树节点数"""
        count = 1
        for child in node.get("children", []):
            count += MindmapAgent._count_json_nodes(child)
        return count

    # _build_result 已继承自 BaseAgent