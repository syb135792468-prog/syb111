"""
agents/doc_agent.py - 讲解文档生成智能体
LLM 主力生成 | RAG 防幻觉 | 输出 Markdown 格式文档
"""
from __future__ import annotations

from typing import Dict, Any, Optional

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.constants import DEFAULT_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED


class DocAgent(BaseAgent):
    """讲解文档生成智能体：LLM 生成结构化 Python 知识点学习文档"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        super().__init__(
            agent_name="doc",
            scene_name="document_generation",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"目标知识点：{target_kp}")

        content = await self._llm_generate(target_kp)

        resource = ResourceItem(
            resource_type="doc",
            title=f"{target_kp} 学习文档",
            content=content,
            knowledge_points=[target_kp],
            status=RESOURCE_STATUS_COMPLETED,
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={"rag_used": self.enable_rag},
        )

        new_resources = self._append_resource(context, resource)
        self.logger.info(f"文档生成完成：{resource.title}")
        return self._build_result(new_resources)

    async def _llm_generate(self, kp: str) -> str:
        rag_context = await self._get_rag_context(kp, top_k=DEFAULT_RAG_TOP_K)

        system_prompt = self._load_prompt(
            "document_generation_system",
            kp=kp,
            rag_context=rag_context if rag_context else "无参考资料",
        )

        try:
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._load_prompt("document_generation_user", kp=kp)},
            ])
            if not resp.strip():
                raise ValueError("LLM返回空内容")
            return resp
        except Exception as e:
            self.logger.warning(f"LLM文档生成失败，使用通用结构兜底: {e}")
            return self._fallback_generate(kp)

    def _fallback_generate(self, kp: str) -> str:
        """LLM 失败时的兜底：按主题生成通用文档结构"""
        return self._load_prompt("document_generation_fallback", kp=kp)

    def _get_target_knowledge_point(
        self, user_input: str, context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """优先使用统一路由提取的纯主题，兜底用用户输入"""
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC
