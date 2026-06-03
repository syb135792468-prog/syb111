"""
agents/resource_agent.py - 学习路径资源生成智能体（软件杯A3赛题核心功能）
- 为学习路径节点生成多类型关联资源（doc/quiz/mindmap）
- 复用现有 DocAgent、QuizAgent、MindmapAgent
- 支持并发生成多种资源
- 返回结构化资源数据，供 API 层存储到 LearningPathNodeResource 表
"""
from __future__ import annotations

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, UTC

from agents.base_agent import BaseAgent
from agents.doc_agent import DocAgent
from agents.quiz_agent import QuizAgent
from agents.mindmap_agent import MindmapAgent
from utils.agent_helpers import get_profile_from_context
from config.constants import (
    RESOURCE_PROGRESS_COMPLETE,
    DIFFICULTY_MEDIUM,
)


class ResourceAgent(BaseAgent):
    """为学习路径节点生成多类型资源的协调智能体"""

    def __init__(self, user_id=None, task_id=None):
        super().__init__(
            agent_name="resource",
            scene_name="document_generation",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )
        self._agents: Dict[str, BaseAgent] = {}

    def _get_sub_agent(self, resource_type: str) -> BaseAgent:
        """懒加载子Agent单例"""
        if resource_type not in self._agents:
            if resource_type == "doc":
                self._agents[resource_type] = DocAgent(user_id=self.user_id)
            elif resource_type == "quiz":
                self._agents[resource_type] = QuizAgent(user_id=self.user_id)
            elif resource_type == "mindmap":
                self._agents[resource_type] = MindmapAgent(
                    user_id=self.user_id, output_format="json"
                )
            else:
                raise ValueError(f"不支持的资源类型: {resource_type}")
        return self._agents[resource_type]

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        为指定知识点生成资源。

        Args:
            user_input: 知识点名称
            context: 上下文信息，需包含:
                - resource_types: 要生成的资源类型列表（默认 ["doc", "quiz", "mindmap"]）
                - profile_data: 用户画像
                - config: 额外配置（difficulty等）

        Returns:
            dict: {"resources": [...], "current_step": "resource"}
        """
        knowledge_point = user_input.strip()
        resource_types = (context or {}).get("resource_types", ["doc", "quiz", "mindmap"])
        profile = get_profile_from_context(context)
        config = (context or {}).get("config", {})

        self.logger.info(f"📦 为知识点生成资源 | {knowledge_point} | 类型: {resource_types}")

        # 并发生成多种资源
        tasks = []
        for rtype in resource_types:
            tasks.append(
                self._generate_single_resource(
                    knowledge_point=knowledge_point,
                    resource_type=rtype,
                    profile=profile,
                    config=config,
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 组装结果
        resources = []
        for rtype, result in zip(resource_types, results):
            if isinstance(result, Exception):
                self.logger.error(f"生成{rtype}资源失败: {result}")
                resources.append({
                    "resource_type": rtype,
                    "title": f"{knowledge_point} - {rtype}",
                    "status": "failed",
                    "error": str(result),
                })
            else:
                resources.append(result)

        self.logger.info(f"✅ 资源生成完成 | 成功: {sum(1 for r in resources if r.get('status') == 'completed')}/{len(resources)}")

        return {
            "resources": resources,
            "current_step": "resource",
            "updated_at": datetime.now(UTC).replace(tzinfo=None),
        }

    async def _generate_single_resource(
        self,
        knowledge_point: str,
        resource_type: str,
        profile: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """生成单个类型的资源"""
        agent = self._get_sub_agent(resource_type)

        context = {
            "user_id": self.user_id or "",
            "profile_data": profile,
            "topic": knowledge_point,
            "resource_list": [],
        }

        try:
            if resource_type == "quiz":
                result = await asyncio.wait_for(
                    agent.process(
                        user_input=knowledge_point,
                        context=context,
                        difficulty=config.get("difficulty", DIFFICULTY_MEDIUM),
                        include_explanation=True,
                        force_knowledge_point=knowledge_point,
                    ),
                    timeout=60,
                )
            else:
                result = await asyncio.wait_for(
                    agent.process(
                        user_input=knowledge_point,
                        context=context,
                    ),
                    timeout=60,
                )

            items = result.get("resource_list", [])
            if items:
                item = items[0]
                return {
                    "resource_type": resource_type,
                    "title": item.title,
                    "content": item.content,
                    "knowledge_points": item.knowledge_points or [knowledge_point],
                    "extra_metadata": item.extra_metadata,
                    "status": "completed",
                }
            else:
                return {
                    "resource_type": resource_type,
                    "title": f"{knowledge_point} - {resource_type}",
                    "status": "failed",
                    "error": "生成结果为空",
                }

        except asyncio.TimeoutError:
            return {
                "resource_type": resource_type,
                "title": f"{knowledge_point} - {resource_type}",
                "status": "failed",
                "error": "生成超时",
            }
        except Exception as e:
            return {
                "resource_type": resource_type,
                "title": f"{knowledge_point} - {resource_type}",
                "status": "failed",
                "error": str(e),
            }
