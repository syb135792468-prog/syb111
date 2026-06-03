"""
agents/path_agent.py - 软件杯A3 学习路径规划智能体
- 基于知识依赖关系图生成个性化学习路径
- 返回 learning_path 列表，含 prerequisites 和 difficulty
- 支持动态路径调整（根据掌握度跳过/插入节点）
"""
from __future__ import annotations

from typing import Dict, Any, Optional, List, Set
import json

from agents.base_agent import BaseAgent
from config.settings import settings
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import (
    DEFAULT_ESTIMATED_TIME_MIN, EXTENDED_ESTIMATED_TIME_MIN,
    MAX_LEARNING_PATH_STEPS, DEFAULT_START_KNOWLEDGE_POINT,
    PATH_FALLBACK_KP_COUNT, LP_MASTERY_THRESHOLD,
)
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
        knowledge_mastery = profile.get("knowledge_mastery", {})

        # 确定起始知识点
        start_kp = self._determine_start_point(weak_points, mastered)

        self.logger.info(f"🗺️ 生成学习路径 | 起始知识点：{start_kp}")

        # 生成路径列表
        raw_path = self._generate_path(start_kp, mastered)

        # 计算每个知识点的难度（基于依赖深度）
        difficulty_map = self._calculate_difficulties()

        # 格式化为前端可直接展示的结构
        learning_path = []
        for i, kp in enumerate(raw_path, 1):
            prerequisites = self.dependency_graph.get(kp, [])
            # 只保留也在路径中的前置条件
            path_kps = set(raw_path)
            relevant_prereqs = [p for p in prerequisites if p in path_kps]

            learning_path.append({
                "order": i,
                "knowledge_point": kp,
                "estimated_time_min": DEFAULT_ESTIMATED_TIME_MIN if "基础" in kp else EXTENDED_ESTIMATED_TIME_MIN,
                "type": "review" if kp in mastered else "new",
                "prerequisites": relevant_prereqs,
                "difficulty": difficulty_map.get(kp, 0.5),
            })

        self.logger.info(f"✅ 生成 {len(learning_path)} 步学习路径")
        return {
            "learning_path": learning_path,
            "current_step": "path",
            "updated_at": self._get_current_utc_time(),
        }

    def _determine_start_point(
        self, weak_points: List[str], mastered: Set[str]
    ) -> str:
        """确定路径起始知识点"""
        if weak_points:
            return weak_points[0]
        if mastered:
            return next(iter(mastered))
        return DEFAULT_START_KNOWLEDGE_POINT

    def _calculate_difficulties(self) -> Dict[str, float]:
        """
        基于依赖图的拓扑深度计算知识点难度。
        依赖链越深，难度越高（0.1-0.9）。
        """
        if not self.dependency_graph:
            return {}

        # 计算每个知识点的最大依赖深度
        depth_cache: Dict[str, int] = {}

        def get_depth(node: str) -> int:
            if node in depth_cache:
                return depth_cache[node]
            deps = self.dependency_graph.get(node, [])
            if not deps:
                depth_cache[node] = 0
                return 0
            max_dep_depth = max(get_depth(d) for d in deps if d in self.dependency_graph)
            depth_cache[node] = max_dep_depth + 1
            return depth_cache[node]

        for kp in self.dependency_graph:
            get_depth(kp)

        if not depth_cache:
            return {}

        max_depth = max(depth_cache.values()) or 1

        # 映射到 0.1-0.9 的难度范围
        return {
            kp: round(0.1 + (depth / max_depth) * 0.8, 2)
            for kp, depth in depth_cache.items()
        }

    def _generate_path(self, start: str, mastered: set) -> List[str]:
        """基于依赖图生成拓扑排序路径"""
        if not self.dependency_graph:
            return PYTHON_KNOWLEDGE_POINTS[:PATH_FALLBACK_KP_COUNT]

        path = []
        visited = set()

        def add_with_deps(node):
            if node in visited or node not in self.dependency_graph:
                return
            visited.add(node)
            for dep in self.dependency_graph.get(node, []):
                if dep not in mastered and dep not in visited:
                    add_with_deps(dep)
            if node not in mastered:
                path.append(node)

        add_with_deps(start)

        for kp in PYTHON_KNOWLEDGE_POINTS:
            if kp not in visited and kp not in mastered:
                path.append(kp)

        return path[:MAX_LEARNING_PATH_STEPS]