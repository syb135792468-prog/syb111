"""
agents/mindmap_agent.py - 思维导图生成智能体
LLM 主力生成 | RAG 防幻觉 | 输出结构化 JSON / Markdown / Mermaid
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, ClassVar
import random
import re
import json

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.constants import (
    MINDMAP_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC,
    RESOURCE_STATUS_COMPLETED, MINDMAP_TOPIC_MAX_LENGTH,
    MINDMAP_DEFINITION_MIN_LENGTH, MINDMAP_EXPAND_RAG_TOP_K,
    MINDMAP_EXPAND_MAX_CHILDREN, MINDMAP_SQL_DETECT_PATTERN,
    MINDMAP_ER_RAG_TOP_K, MINDMAP_ER_GENERATE_TIMEOUT_SEC,
    MINDMAP_EXPAND_TIMEOUT_SEC,
)
from utils.sql_parser import parse_sql_tables, generate_ddl_doc_markdown


class MindmapAgent(BaseAgent):
    """思维导图生成智能体：LLM 生成结构化 Python 知识点思维导图"""

    # 格式枚举
    FORMAT_JSON: ClassVar[str] = "json"
    FORMAT_MARKDOWN: ClassVar[str] = "markdown"
    FORMAT_MERMAID: ClassVar[str] = "mermaid"
    FORMAT_RANDOM: ClassVar[str] = "random"
    ALL_FORMATS: ClassVar[List[str]] = [FORMAT_JSON, FORMAT_MARKDOWN, FORMAT_MERMAID]

    def __init__(
            self,
            user_id: Optional[str] = None,
            task_id: Optional[str] = None,
            output_format: str = FORMAT_JSON,
    ) -> None:
        super().__init__(
            agent_name="mindmap",
            scene_name="mindmap_generation",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )
        self.output_format = output_format
        self.logger.info(f"🗺️ 思维导图生成已启用，格式：{output_format}")

    async def process(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 检测是否为 SQL 输入
        if self._is_sql_input(user_input):
            self.logger.info("🗄️ 检测到 SQL 建表语句，进入 ER 图生成模式")
            return await self._process_sql(user_input, context)

        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"🎯 目标知识点：{target_kp}")

        fmt = self._resolve_format()
        self.logger.info(f"📋 最终格式：{fmt}")

        content = await self._llm_generate(target_kp, fmt)

        if fmt == self.FORMAT_JSON:
            content = self._ensure_depth(content)

        resource = self._build_resource(content, target_kp, fmt)
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ 思维导图生成完成：{resource.title} (格式：{fmt})")
        return self._build_result(new_resources)

    # ============================================================
    # SQL → ER 图生成
    # ============================================================

    @staticmethod
    def _is_sql_input(user_input: str) -> bool:
        """检测用户输入是否为 SQL 建表语句"""
        stripped = user_input.strip().upper()
        # 去掉可能的代码块包裹
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            stripped = "\n".join(lines).strip()
        return MINDMAP_SQL_DETECT_PATTERN in stripped[:200]

    async def _process_sql(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """SQL 建表语句 → ER 图思维导图的完整处理流程"""
        # 1. 解析 SQL
        parse_result = parse_sql_tables(user_input)

        if not parse_result["success"]:
            # 解析失败，返回错误提示思维导图
            self.logger.warning(f"⚠️ SQL 解析失败: {parse_result['error']}")
            content = self._generate_sql_error_json(
                parse_result["error"], parse_result.get("suggestion", "")
            )
            resource = self._build_resource(content, "SQL解析失败", self.FORMAT_JSON)
            new_resources = self._append_resource(context, resource)
            return self._build_result(new_resources)

        tables = parse_result["tables"]
        db_name = parse_result.get("database", "") or "数据库设计"
        self.logger.info(f"✅ SQL 解析成功：{len(tables)} 张表，数据库：{db_name}")

        # 2. 生成 Markdown 设计文档
        doc_markdown = generate_ddl_doc_markdown(tables, db_name)

        # 3. 用 LLM 生成 ER 图 JSON
        try:
            content = await self._llm_generate_er(tables, db_name, doc_markdown)
        except Exception as exc:
            self.logger.warning(f"⚠️ LLM ER 图生成失败：{exc}，使用 Python 兜底")
            content = self._generate_er_fallback(tables, db_name, doc_markdown)

        # 4. 验证 + 深度保证
        try:
            content = self._validate_json(content)
            content = self._ensure_depth(content)
        except Exception as exc:
            self.logger.warning(f"⚠️ ER 图 JSON 验证失败：{exc}，使用 Python 兜底")
            content = self._generate_er_fallback(tables, db_name, doc_markdown)

        # 5. 构建资源
        title = f"{db_name} ER图" if db_name else "数据库ER图"
        resource = self._build_resource(content, title, self.FORMAT_JSON)
        resource.extra_metadata["is_er_diagram"] = True
        resource.extra_metadata["table_count"] = len(tables)
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ ER 图生成完成：{title} ({len(tables)} 张表)")
        return self._build_result(new_resources)

    async def _llm_generate_er(
            self,
            tables: List[Dict[str, Any]],
            db_name: str,
            doc_markdown: str,
    ) -> str:
        """用 LLM 生成 ER 图思维导图 JSON"""
        # RAG 检索数据库设计最佳实践
        rag_query = f"数据库设计 ER图 {' '.join(t['name'] for t in tables)}"
        rag_context = await self._get_rag_context(rag_query, top_k=MINDMAP_ER_RAG_TOP_K)
        rag_text = rag_context if rag_context else "无参考资料"

        # 构造表结构摘要（传给 LLM）
        tables_summary = []
        for t in tables:
            summary = {
                "name": t["name"],
                "comment": t.get("comment", ""),
                "fields": [
                    {
                        "name": f["name"],
                        "type": f"{f['data_type']}({f['length']})" if f["length"] else f["data_type"],
                        "nullable": f["nullable"],
                        "default": f["default"],
                        "is_pk": f["is_primary_key"],
                        "is_auto": f["is_auto_increment"],
                        "comment": f.get("comment", ""),
                    }
                    for f in t.get("fields", [])
                ],
                "primary_keys": t.get("primary_keys", []),
                "foreign_keys": t.get("foreign_keys", []),
                "indexes": t.get("indexes", []),
                "constraints": t.get("constraints", []),
            }
            tables_summary.append(summary)

        tables_json = json.dumps(tables_summary, ensure_ascii=False, indent=2)

        # 加载 prompt
        system_prompt = self._load_prompt(
            "mindmap_er_diagram_system", rag_context=rag_text
        )
        user_msg = self._load_prompt(
            "mindmap_er_diagram_user", db_name=db_name, tables_json=tables_json
        )

        # 调用 LLM
        import asyncio
        resp = await asyncio.wait_for(
            self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ]),
            timeout=MINDMAP_ER_GENERATE_TIMEOUT_SEC,
        )
        self.logger.info(f"🤖 ER 图 LLM 原始输出长度：{len(resp)}")

        cleaned = self._clean_code_block(resp, "json")
        if not cleaned.strip():
            raise ValueError("LLM 返回空内容")

        return cleaned

    @staticmethod
    def _generate_er_fallback(
            tables: List[Dict[str, Any]],
            db_name: str,
            doc_markdown: str,
    ) -> str:
        """LLM 失败时用 Python 直接构建 ER 图 JSON"""
        display_name = db_name or "数据库设计"
        root = {
            "id": "root",
            "topic": f"{display_name[:12]}ER图",
            "definition": f"基于SQL语句自动生成的实体关系图，包含{len(tables)}张数据表及其关联关系",
            "syntax": "",
            "examples": [doc_markdown],
            "pitfalls": ["SQL中未添加表注释", "部分字段未设置非空约束", "外键未建立索引"],
            "advice": ["建议为所有表和字段添加中文注释", "为外键字段建立索引提升查询性能", "统一字段命名规范"],
            "children": [],
        }

        for t_idx, table in enumerate(tables):
            tname = table["name"]
            tcomment = table.get("comment", "")
            table_topic = f"{tname}" if not tcomment else f"{tname[:8]}-{tcomment[:6]}"

            table_node = {
                "id": f"table_{t_idx}",
                "topic": table_topic[:15],
                "definition": f"业务用途：{tcomment or tname + '表'}；数据量预估：中等；读写频率：中",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }

            # 字段列表
            fields_node = {
                "id": f"table_{t_idx}_fields",
                "topic": "字段列表",
                "definition": f"{tname}表的所有字段定义",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }
            for f_idx, field in enumerate(table.get("fields", [])):
                nullable_text = "是" if field["nullable"] else "否"
                default_text = str(field["default"]) if field["default"] is not None else "无"
                type_text = f"{field['data_type']}({field['length']})" if field.get("length") else field["data_type"]
                field_node = {
                    "id": f"table_{t_idx}_f{f_idx}",
                    "topic": field["name"][:15],
                    "definition": f"含义：{field.get('comment', '') or field['name']}；类型：{type_text}；可为空：{nullable_text}；默认值：{default_text}",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": ["自增字段无需手动赋值"] if field["is_auto_increment"] else [],
                    "children": [],
                }
                fields_node["children"].append(field_node)
            table_node["children"].append(fields_node)

            # 主键
            pk_node = {
                "id": f"table_{t_idx}_pk",
                "topic": "主键",
                "definition": f"{tname}表的主键约束",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }
            for pk in table.get("primary_keys", []):
                pk_node["children"].append({
                    "id": f"table_{t_idx}_pk_{pk}",
                    "topic": pk[:15],
                    "definition": f"主键字段：{pk}，唯一标识每条记录",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": ["主键建议使用自增整数或UUID"],
                    "children": [],
                })
            table_node["children"].append(pk_node)

            # 外键
            fk_node = {
                "id": f"table_{t_idx}_fk",
                "topic": "外键",
                "definition": f"{tname}表的外键约束",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }
            for fk in table.get("foreign_keys", []):
                fk_node["children"].append({
                    "id": f"table_{t_idx}_fk_{fk['local_column']}",
                    "topic": fk["local_column"][:15],
                    "definition": f"引用 {fk['reference_table']}.{fk['reference_column']}；{fk.get('description', '')}",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": ["外键未建立索引可能影响查询性能"],
                    "advice": ["为外键字段建立索引"],
                    "children": [],
                })
            table_node["children"].append(fk_node)

            # 索引
            idx_node = {
                "id": f"table_{t_idx}_idx",
                "topic": "索引",
                "definition": f"{tname}表的索引信息",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }
            for idx in table.get("indexes", []):
                idx_node["children"].append({
                    "id": f"table_{t_idx}_idx_{idx['name']}",
                    "topic": idx["name"][:15],
                    "definition": f"类型：{idx['type']}；字段：{', '.join(idx['columns'])}",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": [],
                    "children": [],
                })
            table_node["children"].append(idx_node)

            # 约束
            const_node = {
                "id": f"table_{t_idx}_const",
                "topic": "约束",
                "definition": f"{tname}表的约束信息",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": [],
                "children": [],
            }
            for c in table.get("constraints", []):
                const_node["children"].append({
                    "id": f"table_{t_idx}_const_{c['name']}",
                    "topic": c["name"][:15],
                    "definition": f"类型：{c['type']}；说明：{c['description']}",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": [],
                    "advice": [],
                    "children": [],
                })
            table_node["children"].append(const_node)

            root["children"].append(table_node)

        return json.dumps({"nodeData": root}, ensure_ascii=False)

    @staticmethod
    def _generate_sql_error_json(error: str, suggestion: str) -> str:
        """SQL 解析失败时生成错误提示思维导图 JSON"""
        root = {
            "id": "root",
            "topic": "SQL解析失败",
            "definition": f"错误原因：{error}",
            "syntax": "",
            "examples": [suggestion] if suggestion else [],
            "pitfalls": [
                "SQL语句不完整，缺少字段定义",
                "语法错误，括号不匹配",
                "使用了不支持的SQL方言",
            ],
            "advice": [
                "确保 CREATE TABLE 语句完整",
                "检查括号是否匹配",
                "使用标准 SQL 语法",
                "为表和字段添加中文注释",
            ],
            "children": [
                {
                    "id": "child_fix",
                    "topic": "修正建议",
                    "definition": suggestion or "请检查SQL语法后重试",
                    "syntax": "",
                    "examples": [
                        "CREATE TABLE users (\n  id INT PRIMARY KEY AUTO_INCREMENT,\n  name VARCHAR(100) NOT NULL COMMENT '用户名',\n  email VARCHAR(200) COMMENT '邮箱'\n) COMMENT='用户表';"
                    ],
                    "pitfalls": [],
                    "advice": ["参考以上示例修正SQL语句"],
                    "children": [],
                },
                {
                    "id": "child_tips",
                    "topic": "SQL编写提示",
                    "definition": "编写规范的SQL建表语句的要点",
                    "syntax": "",
                    "examples": [],
                    "pitfalls": ["忘记设置主键", "字段类型选择不当", "缺少必要的非空约束"],
                    "advice": ["每张表必须有主键", "合理选择数据类型", "关键字段设置NOT NULL"],
                    "children": [],
                },
            ],
        }
        return json.dumps({"nodeData": root}, ensure_ascii=False)

    async def expand_node(
            self,
            node_topic: str,
            node_definition: str = "",
            node_syntax: str = "",
            node_examples: Optional[List[str]] = None,
            node_pitfalls: Optional[List[str]] = None,
            node_advice: str = "",
            parent_node_id: str = "",
            context: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        按需展开思维导图节点：为三级节点生成第四级子节点。
        使用 RAG 检索增强 + LLM 生成，失败时降级为模板生成。
        """
        self.logger.info(f"🔍 展开节点: topic={node_topic}, parent_id={parent_node_id}")

        # 检测是否为 ER 图节点
        node_type = self._detect_er_node_type(node_definition)

        # 1. RAG 检索（用节点主题+定义作为查询）
        query = f"{node_topic} {node_definition}" if node_definition else node_topic
        rag_context = await self._get_rag_context(query, top_k=MINDMAP_EXPAND_RAG_TOP_K)
        rag_text = rag_context if rag_context else "无参考资料"

        # 2. 构造 Prompt
        examples_text = "\n".join(f"  - {ex}" for ex in (node_examples or [])) or "无"
        pitfalls_text = "\n".join(f"  - {p}" for p in (node_pitfalls or [])) or "无"

        if node_type:
            # ER 节点使用专用 prompt
            system_prompt = self._load_prompt(
                "mindmap_er_expand_system",
                node_topic=node_topic,
                node_definition=node_definition or "无",
                node_type=node_type,
            )
            user_msg = (
                f"请展开以下 ER 图节点，生成详细子节点。\n\n"
                f"节点主题：{node_topic}\n"
                f"节点描述：{node_definition or '无'}\n"
                f"节点类型：{node_type}\n\n"
                f"【参考内容】\n{rag_text}\n\n"
                f"要求：返回纯JSON数组，每个元素包含topic、definition、syntax、examples、pitfalls、advice、children（空数组）。"
            )
        else:
            system_prompt = self._load_prompt("mindmap_expand_node_system")
            user_msg = (
            f"请对以下知识点节点进行详细展开，生成2-3个第四级子节点。\n\n"
            f"当前节点主题：{node_topic}\n"
            f"详细解释：{node_definition or '无'}\n"
            f"语法：{node_syntax or '无'}\n"
            f"示例：\n{examples_text}\n"
            f"常见陷阱：\n{pitfalls_text}\n"
            f"建议：{node_advice or '无'}\n\n"
            f"【参考教材内容】\n{rag_text}\n\n"
            f"要求：返回纯JSON数组，每个元素包含topic、definition、syntax、examples、pitfalls、advice、children（空数组）。"
        )

        try:
            # 3. 调用 LLM（带内部超时）
            import asyncio
            resp = await asyncio.wait_for(
                self._call_llm([
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ]),
                timeout=MINDMAP_EXPAND_TIMEOUT_SEC,
            )
            self.logger.info(f"🤖 节点展开 LLM 原始输出长度：{len(resp)}")

            # 4. 清理代码块包裹
            cleaned = self._clean_code_block(resp, "json")
            if not cleaned.strip():
                raise ValueError("LLM 返回空内容")

            # 5. 解析 JSON 数组
            children = self._validate_expand_json(cleaned)

            # 6. 为每个子节点生成 id
            for idx, child in enumerate(children):
                child["id"] = f"{parent_node_id}_{idx + 1}" if parent_node_id else f"expand_{idx + 1}"
                if "children" not in child:
                    child["children"] = []

            self.logger.info(f"✅ 节点展开成功，生成 {len(children)} 个子节点")
            return children

        except Exception as exc:
            self.logger.warning(f"⚠️ 节点展开 LLM 失败：{exc}，使用模板兜底")
            return self._generate_expand_fallback(node_topic, parent_node_id)

    @staticmethod
    def _detect_er_node_type(definition: str) -> Optional[str]:
        """检测节点是否为 ER 图节点，返回节点类型或 None"""
        if not definition:
            return None
        # 表节点：definition 包含 "业务用途"
        if "业务用途" in definition and "数据量预估" in definition:
            return "table"
        # 字段节点：definition 包含 "类型" 和 "可为空"
        if "类型" in definition and "可为空" in definition:
            return "field"
        # 外键节点：definition 包含 "引用" 和 "."
        if "引用" in definition and "." in definition:
            return "foreign_key"
        return None

    @staticmethod
    def _validate_expand_json(text: str) -> List[Dict[str, Any]]:
        """校验并修复节点展开返回的 JSON 数组"""
        import logging
        logger = logging.getLogger("agent.mindmap")

        # 去掉注释和尾部逗号
        text = re.sub(r'//[^\n]*', '', text)
        text = re.sub(r',\s*([}\]])', r'\1', text)

        # 尝试直接解析
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            # 如果是对象且包含数组字段，尝试提取
            if isinstance(data, dict):
                for key in ("children", "nodes", "items", "data"):
                    if key in data and isinstance(data[key], list):
                        return data[key]
            raise ValueError("JSON 不是数组格式")
        except json.JSONDecodeError:
            pass

        # 正则提取 [...]
        match = re.search(r'\[[\s\S]*\]', text)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass

            # 截断修复
            candidate = match.group(0)
            for i in range(len(candidate) - 1, len(candidate) // 2, -1):
                if candidate[i] == ']':
                    chunk = candidate[:i + 1]
                    open_b = chunk.count('[') - chunk.count(']')
                    chunk += ']' * max(0, open_b)
                    try:
                        data = json.loads(chunk)
                        if isinstance(data, list):
                            logger.info(f"截断修复成功（位置 {i + 1}）")
                            return data
                    except json.JSONDecodeError:
                        continue

        logger.warning(f"JSON 数组解析失败，原始输出前 500 字符: {text[:500]}")
        raise ValueError("LLM 返回的 JSON 数组格式不正确")

    @staticmethod
    def _generate_expand_fallback(topic: str, parent_id: str = "") -> List[Dict[str, Any]]:
        """节点展开失败时的兜底模板"""
        base_id = parent_id or "expand"
        return [
            {
                "id": f"{base_id}_1",
                "topic": f"{topic[:6]}要点",
                "definition": f"关于{topic}的核心知识点和关键要点。",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": f"重点理解{topic}的核心概念。",
                "children": [],
            },
            {
                "id": f"{base_id}_2",
                "topic": f"{topic[:6]}示例",
                "definition": f"通过具体示例来理解{topic}的实际应用。",
                "syntax": "",
                "examples": [],
                "pitfalls": [],
                "advice": f"多动手练习{topic}相关代码。",
                "children": [],
            },
        ]

    @staticmethod
    def _generate_generic_json(kp: str) -> str:
        """LLM 失败时的兜底：按主题生成通用思维导图 JSON 结构"""
        root = {
            "id": "root",
            "topic": kp[:MINDMAP_TOPIC_MAX_LENGTH],
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

    # ============================================================
    # LLM 生成（主力模式）
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
        rag_text = rag_context if rag_context else "无参考资料"
        if fmt == self.FORMAT_JSON:
            system_prompt = self._build_json_prompt(kp, rag_context)
            user_msg = self._load_prompt("mindmap_generation_json_user", kp=kp)
        elif fmt == self.FORMAT_MERMAID:
            system_prompt = self._load_prompt("mindmap_generation_mermaid_system", kp=kp, rag_context=rag_text)
            user_msg = self._load_prompt("mindmap_generation_mermaid_user", kp=kp)
        else:
            system_prompt = self._load_prompt("mindmap_generation_markdown_system", kp=kp, rag_context=rag_text)
            user_msg = self._load_prompt("mindmap_generation_markdown_user", kp=kp)

        try:
            # 3. 调用 LLM
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ])
            self.logger.info(f"🤖 LLM 原始输出长度：{len(resp)}")

            # 4. 清理可能的代码块包裹
            cleaned = self._clean_code_block(resp, fmt)
            if not cleaned.strip():
                raise ValueError("LLM 返回空内容")

            self.logger.info(f"🧹 清理后前 500 字符: {cleaned[:500]}")

            # 5. JSON 格式校验
            if fmt == self.FORMAT_JSON:
                cleaned = self._validate_json(cleaned)
                cleaned = self._ensure_depth(cleaned)

            self.logger.info(f"🤖 LLM 思维导图生成成功，清理后长度：{len(cleaned)}")
            return cleaned

        except Exception as exc:
            self.logger.warning(f"⚠️ LLM 思维导图生成失败：{exc}，使用通用结构兜底")
            if fmt == self.FORMAT_JSON:
                return self._generate_generic_json(kp)
            return json.dumps({"nodeData": {"id": "root", "topic": kp, "definition": f"{kp}是Python中的重要知识点。", "children": []}}, ensure_ascii=False)

    def _build_json_prompt(self, kp: str, rag_context: str) -> str:
        rag_text = rag_context if rag_context else "无参考资料"
        return self._load_prompt("mindmap_generation_json_system", kp=kp, rag_context=rag_text)

    @staticmethod
    def _validate_json(text: str) -> str:
        """校验并修复 JSON 格式，自动处理 LLM 输出的各种变体"""
        import logging
        logger = logging.getLogger("agent.mindmap")

        def fix_json_string(s):
            """修复 JSON 中常见的字符串问题"""
            # 去掉 // 注释
            s = re.sub(r'//[^\n]*', '', s)
            # 去掉尾部逗号
            s = re.sub(r',\s*([}\]])', r'\1', s)
            # 修复未转义的换行符（在字符串值中）
            # 先尝试解析，如果失败再做更激进的修复
            return s

        def try_parse(t):
            t = fix_json_string(t)
            return json.loads(t)

        def try_parse_with_fixes(t):
            """尝试多种修复策略"""
            # 策略1: 基本清理
            try:
                return try_parse(t)
            except json.JSONDecodeError:
                pass

            # 策略2: 修复未转义的控制字符
            fixed = t
            # 在字符串值中，将实际的换行符替换为 \n
            fixed = re.sub(r'(?<=: ")(.*?)(?=",\s*")', lambda m: m.group(0).replace('\n', '\\n'), fixed, flags=re.DOTALL)
            # 更简单的方法：将所有不在转义序列中的实际换行符替换掉
            result = []
            in_string = False
            escape_next = False
            for ch in fixed:
                if escape_next:
                    result.append(ch)
                    escape_next = False
                    continue
                if ch == '\\':
                    result.append(ch)
                    escape_next = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    result.append(ch)
                    continue
                if in_string and ch == '\n':
                    result.append('\\n')
                    continue
                if in_string and ch == '\t':
                    result.append('\\t')
                    continue
                result.append(ch)
            fixed = ''.join(result)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

            # 策略3: 使用正则提取 key-value 并重建
            raise json.JSONDecodeError("无法修复", t, 0)

        def ensure_node_data(data):
            """确保数据有 nodeData 包装"""
            if "nodeData" in data:
                return json.dumps(data, ensure_ascii=False)
            if "topic" in data or "children" in data:
                logger.info("JSON 缺少 nodeData 包装，自动补充")
                if "id" not in data:
                    data["id"] = "root"
                return json.dumps({"nodeData": data}, ensure_ascii=False)
            return None

        # 1. 直接解析
        try:
            data = try_parse_with_fixes(text)
            result = ensure_node_data(data)
            if result:
                return result
        except (json.JSONDecodeError, Exception) as e:
            logger.info(f"直接解析失败: {e}")

        # 2. 正则提取 JSON 块
        json_match = re.search(r'(\{[\s\S]*\})', text)
        if json_match:
            candidate = json_match.group(1)
            try:
                data = try_parse_with_fixes(candidate)
                result = ensure_node_data(data)
                if result:
                    return result
            except (json.JSONDecodeError, Exception) as e:
                logger.info(f"正则提取后解析失败: {e}")

                # 3. 尝试截断到最后一个 } 再解析（处理 LLM 输出被截断的情况）
                for i in range(len(candidate) - 1, len(candidate) // 2, -1):
                    if candidate[i] == '}':
                        # 先去掉不完整的字符串尾部
                        chunk = candidate[:i+1]
                        # 如果引号数量是奇数，去掉最后一个引号后的内容
                        if chunk.count('"') % 2 != 0:
                            last_q = chunk.rfind('"')
                            if last_q > 0:
                                chunk = chunk[:last_q]
                        # 补全缺失的括号
                        open_b = chunk.count('{') - chunk.count('}')
                        open_s = chunk.count('[') - chunk.count(']')
                        chunk += ']' * max(0, open_s) + '}' * max(0, open_b)
                        try:
                            data = json.loads(chunk)
                            result = ensure_node_data(data)
                            if result:
                                logger.info(f"截断修复成功（位置 {i+1}）")
                                return result
                        except json.JSONDecodeError:
                            continue

        logger.warning(f"JSON 解析失败，LLM 原始输出前 500 字符: {text[:500]}")
        raise ValueError("LLM 返回的 JSON 格式不正确")

    # ============================================================
    # 6. 工具方法
    # ============================================================
    @staticmethod
    def _ensure_depth(json_str: str) -> str:
        """确保思维导图至少有2层深度，为空children的节点自动补充子节点（仅在必要时）"""
        try:
            data = json.loads(json_str)
            node = data.get("nodeData", {})

            def enrich(n, level=0):
                children = n.get("children", [])
                # 只有一级子节点（level=1）且没有children时才补充
                # 更深层的叶子节点保持原样，避免千篇一律
                if not children and level == 1:
                    topic = n.get("topic", "知识点")
                    definition = n.get("definition", "")
                    # 如果节点已经有详细definition，说明是有内容的叶子，不需要补充
                    if definition and len(definition) > MINDMAP_DEFINITION_MIN_LENGTH:
                        return
                    n["children"] = [
                        {
                            "id": f"{n.get('id', 'node')}_a",
                            "topic": f"{topic}要点",
                            "definition": f"关于{topic}的核心知识点。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "",
                            "children": [],
                        },
                        {
                            "id": f"{n.get('id', 'node')}_b",
                            "topic": f"{topic}示例",
                            "definition": f"通过示例理解{topic}。",
                            "syntax": "",
                            "examples": [],
                            "pitfalls": [],
                            "advice": "",
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
        """优先使用统一路由提取的纯主题，兜底用用户输入"""
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC

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
        支持 ```mermaid ... ``` 或 ```markdown ... ``` 或 ```json ... ``` 或 ``` ... ```
        """
        # 1. 尝试匹配带格式的代码块（json, markdown, mermaid 等）
        pattern = r"```(?:json|markdown|mermaid)?\s*\n(.*?)\n\s*```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
            return cleaned

        # 2. 如果只有开头的 ``` 没有结尾，也尝试去掉
        lines = text.split('\n')
        if lines and lines[0].strip().startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith('```'):
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
            status=RESOURCE_STATUS_COMPLETED,
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