"""
agents/path_agent.py - 软件杯A3 学习路径规划智能体
- 基于知识依赖关系图生成个性化学习路径
- 返回 learning_path 列表，不再生成为 ResourceItem（避免非法资源类型）
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List
import json
from pathlib import Path

from agents.base_agent import BaseAgent
from config.settings import settings
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import DEFAULT_ESTIMATED_TIME_MIN, EXTENDED_ESTIMATED_TIME_MIN, MAX_LEARNING_PATH_STEPS
from utils.agent_helpers import get_profile_from_context


class PathAgent(BaseAgent):
    """学习路径规划智能体，根据画像和知识依赖生成学习顺序"""

    def __init__(self, user_id=None, task_id=None):
        super().__init__(
            agent_name="path",
            scene_name="path_planning",
            enable_rag=False,
            user_id=user_id,
            task_id=task_id,
        )
        self.dependency_graph = self._load_dependency_graph()

    def _load_dependency_graph(self) -> Dict[str, Any]:
        """加载知识点依赖关系JSON"""
        dep_file = settings.BASE_DIR / "data" / "knowledge_dependency.json"
        try:
            with open(dep_file, "r", encoding="utf-8") as f:
                graph = json.load(f)
                self.logger.info(f"📊 知识依赖图加载成功 | 总节点数：{len(graph)}")
                return graph
        except Exception as e:
            self.logger.error(f"加载知识依赖图失败: {e}")
            return {}

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        生成个性化学习路径。

        Returns:
            dict: {"learning_path": [...], "current_step": "path", ...}
        """
        profile = get_profile_from_context(context)
        weak_points = profile.get("weak_points", [])
        mastered = set(profile.get("mastered_points", []))

        # 确定起始知识点
        start_kp = None
        if weak_points:
            start_kp = weak_points[0]
        elif mastered:
            # 从已掌握中选一个作为起点（复习路径）
            start_kp = next(iter(mastered))
        else:
            start_kp = "变量与数据类型"  # 默认最基础知识

        self.logger.info(f"🗺️ 生成学习路径 | 起始知识点：{start_kp}")

        # 生成路径列表
        raw_path = self._generate_path(start_kp, mastered)

        # 格式化为前端可直接展示的结构
        learning_path = []
        for i, kp in enumerate(raw_path, 1):
            learning_path.append({
                "order": i,
                "knowledge_point": kp,
                "estimated_time_min": DEFAULT_ESTIMATED_TIME_MIN if "基础" in kp else EXTENDED_ESTIMATED_TIME_MIN,
                "type": "review" if kp in mastered else "new",
            })

        self.logger.info(f"✅ 生成 {len(learning_path)} 步学习路径")
        return {
            "learning_path": learning_path,
            "current_step": "path",
            "updated_at": self._get_current_utc_time(),
        }

    def _generate_path(self, start: str, mastered: set) -> List[str]:
        """基于依赖图生成拓扑排序路径（简单实现）"""
        # 如果没有依赖图，返回基础顺序
        if not self.dependency_graph:
            return PYTHON_KNOWLEDGE_POINTS[:5]

        # 简化逻辑：从起始节点出发，收集依赖链
        path = []
        visited = set()

        def add_with_deps(node):
            if node in visited or node not in self.dependency_graph:
                return
            visited.add(node)
            # 先添加前置依赖
            for dep in self.dependency_graph.get(node, []):
                if dep not in mastered and dep not in visited:
                    add_with_deps(dep)
            if node not in mastered:
                path.append(node)

        add_with_deps(start)

        # 补充未覆盖的其他基础知识点
        for kp in PYTHON_KNOWLEDGE_POINTS:
            if kp not in visited and kp not in mastered:
                path.append(kp)

        return path[:MAX_LEARNING_PATH_STEPS]  # 限制路径长度