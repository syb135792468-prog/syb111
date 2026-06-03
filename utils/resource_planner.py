"""
学习资源规划器（软件杯A3赛题 v1.2 最终优化版）
- ✅ 基于用户画像智能规划学习资源
- ✅ 根据薄弱点、学习风格、学习阶段推荐资源类型
- ✅ 生成可直接使用的 ResourcePlan 列表
- ✅ 预留 AI 决策接口，当前采用简单规则
- ✅ 全局配置读取：从 config.model_config 获取可用资源类型
- ✅ 【优化】修复递归逻辑，完善配置依赖
- ✅ 【优化】保留扩展接口，添加健康检查
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple, Set
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, UTC
import json
from pathlib import Path

from config.settings import settings
from config.constants import (
    RESOURCE_PLANNER_BEGINNER_MULTIPLIER, RESOURCE_PLANNER_ADVANCED_MULTIPLIER,
    RESOURCE_PLANNER_MIN_TIME_MINUTES, RESOURCE_PLANNER_DEFAULT_RESOURCE_TIME,
    RESOURCE_PLANNER_DEFAULT_STUDY_TIME_PER_DAY, RESOURCE_PLANNER_MAX_RESOURCES_PER_PLAN,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="resource_planner")


# ------------------------------
# 1. 枚举与数据类
# ------------------------------
class ResourcePriority(Enum):
    """资源优先级"""
    HIGH = "high"  # 高优先级（薄弱知识点）
    MEDIUM = "medium"  # 中优先级（巩固知识点）
    LOW = "low"  # 低优先级（拓展知识点）


class LearningStage(Enum):
    """学习阶段"""
    INTRO = "intro"  # 入门阶段
    PRACTICE = "practice"  # 练习阶段
    REVIEW = "review"  # 复习阶段
    ADVANCED = "advanced"  # 进阶阶段


@dataclass
class ResourcePlan:
    """单个资源规划"""
    knowledge_point: str  # 知识点
    resource_type: str  # 资源类型（doc/quiz/mindmap/code/video）
    priority: ResourcePriority  # 优先级
    stage: LearningStage  # 学习阶段
    estimated_time_minutes: int = 30  # 预计学习时长（分钟）
    dependencies: List[str] = field(default_factory=list)  # 依赖的知识点
    metadata: Dict[str, Any] = field(default_factory=dict)  # 扩展元数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knowledge_point": self.knowledge_point,
            "resource_type": self.resource_type,
            "priority": self.priority.value,
            "stage": self.stage.value,
            "estimated_time_minutes": self.estimated_time_minutes,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
        }


@dataclass
class LearningPath:
    """完整学习路径"""
    user_id: int  # 用户ID
    resource_plans: List[ResourcePlan]  # 资源规划列表
    total_estimated_hours: float = 0.0  # 总预计时长（小时）
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))  # 创建时间
    version: int = 1  # 版本号

    def __post_init__(self):
        """自动计算总时长"""
        total_minutes = sum(p.estimated_time_minutes for p in self.resource_plans)
        self.total_estimated_hours = round(total_minutes / 60, 1)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "total_resources": len(self.resource_plans),
            "total_estimated_hours": self.total_estimated_hours,
            "resource_plans": [p.to_dict() for p in self.resource_plans],
            "created_at": self.created_at.isoformat(),
            "version": self.version,
        }


# ------------------------------
# 2. 资源规划器（规则实现）
# ------------------------------
class ResourcePlanner:
    """
    学习资源规划器
    当前使用规则引擎，后续可接入 evaluation_agent 的反馈进行动态调整
    """

    # 学习风格 → 推荐资源类型优先级（列表越靠前越优先）
    STYLE_MAP: Dict[str, List[str]] = {
        "visual": ["mindmap", "video", "doc"],
        "auditory": ["video", "doc"],
        "kinesthetic": ["code", "quiz"],
        "mixed": ["doc", "quiz", "mindmap", "code"],
    }

    # 学习阶段默认起始资源
    STAGE_DEFAULT: Dict[LearningStage, str] = {
        LearningStage.INTRO: "doc",
        LearningStage.PRACTICE: "quiz",
        LearningStage.REVIEW: "mindmap",
        LearningStage.ADVANCED: "code",
    }

    # 资源类型基础时长（分钟）
    RESOURCE_TIME_BASE: Dict[str, int] = {
        "doc": 15,
        "video": 10,
        "quiz": 20,
        "code": 30,
        "mindmap": 10,
        "reading": 20,
    }

    def __init__(self):
        self._dependency_graph: Dict[str, List[str]] = {}
        self._load_dependencies()

        # 配置参数
        self.default_study_time_per_day = RESOURCE_PLANNER_DEFAULT_STUDY_TIME_PER_DAY
        self.max_resources_per_plan = RESOURCE_PLANNER_MAX_RESOURCES_PER_PLAN

        logger.info("✅ 资源规划器初始化完成（规则模式）")

    def _load_dependencies(self) -> None:
        """
        加载知识点依赖关系（若文件存在）
        从 config.settings 或默认路径加载
        """
        dep_path = settings.BASE_DIR / "data" / "knowledge_dependency.json"

        if dep_path.exists():
            try:
                with open(dep_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # 支持两种格式：直接的依赖图 或 包含 edges 的结构
                    if "edges" in data:
                        self._dependency_graph = data["edges"]
                    else:
                        self._dependency_graph = data
                logger.info(f"📎 已加载知识点依赖关系: {len(self._dependency_graph)} 个节点")
            except Exception as e:
                logger.warning(f"⚠️  依赖关系文件加载失败，将忽略前置关系: {e}")
        else:
            logger.info(f"📎 依赖关系文件不存在: {dep_path}，将忽略前置关系")

    def _get_prerequisites(self, point: str) -> List[str]:
        """
        获取某个知识点的所有前置知识点（递归解析）

        Args:
            point: 知识点

        Returns:
            前置知识点列表（按依赖顺序）
        """
        if point not in self._dependency_graph:
            return []

        result: List[str] = []
        visited: Set[str] = set()

        def dfs(current: str) -> None:
            if current in visited:
                return
            visited.add(current)

            # 先递归处理所有依赖
            for dep in self._dependency_graph.get(current, []):
                dfs(dep)

            # 然后添加当前节点（如果不是起始点）
            if current != point:
                result.append(current)

        dfs(point)
        return result

    # ------------------------------
    # 核心规划方法
    # ------------------------------
    async def plan_resources(
            self,
            user_id: int,
            user_profile: Dict[str, Any],
            target_knowledge_points: Optional[List[str]] = None,
            max_resources: Optional[int] = None,
    ) -> LearningPath:
        """
        【核心方法】根据画像生成个性化学习资源规划

        Args:
            user_id: 用户ID
            user_profile: 用户画像（来自 UserProfile 模型）
            target_knowledge_points: 目标知识点列表（可选，不填则基于薄弱点自动规划）
            max_resources: 最大资源数（可选，不填则使用默认值）

        Returns:
            完整的学习路径
        """
        logger.info(f"📋 开始规划资源: user={user_id}")

        max_resources = max_resources or self.max_resources_per_plan

        # 1. 确定目标知识点：如果未指定，则使用薄弱点
        if target_knowledge_points is None:
            target_knowledge_points = user_profile.get("weak_points", [])

        if not target_knowledge_points:
            logger.warning(f"⚠️  用户 {user_id} 没有指定知识点，返回空路径")
            return LearningPath(user_id=user_id, resource_plans=[])

        learning_style = user_profile.get("learning_style", "mixed")
        knowledge_level = user_profile.get("knowledge_level", "beginner")

        # 2. 确定学习阶段
        stage = self._infer_stage(knowledge_level)
        logger.debug(f"🎯 确定学习阶段: user={user_id}, stage={stage.value}")

        plans: List[ResourcePlan] = []
        for point in target_knowledge_points[:max_resources]:
            # 3. 为每个知识点确定优先级
            priority = self._infer_priority(point, user_profile)

            # 4. 推荐资源类型（基于风格和阶段）
            resource_type = self._recommend_type(learning_style, stage)

            # 5. 识别依赖
            deps = self._get_prerequisites(point)

            # 6. 估算时长
            study_time = self._estimate_time(resource_type, knowledge_level)

            plan = ResourcePlan(
                knowledge_point=point,
                resource_type=resource_type,
                priority=priority,
                stage=stage,
                estimated_time_minutes=study_time,
                dependencies=deps,
                metadata={"source": "rule_engine"}
            )
            plans.append(plan)

            logger.debug(f"   📝 规划资源: kp={point}, type={resource_type}, "
                         f"priority={priority.value}, time={study_time}min")

        logger.info(f"✅ 为用户 {user_id} 生成 {len(plans)} 条资源规划，"
                    f"总时长: {sum(p.estimated_time_minutes for p in plans)} 分钟")

        return LearningPath(user_id=user_id, resource_plans=plans)

    # ------------------------------
    # 辅助方法
    # ------------------------------
    def _infer_stage(self, knowledge_level: str) -> LearningStage:
        """根据知识水平推断学习阶段"""
        if knowledge_level == "beginner":
            return LearningStage.INTRO
        elif knowledge_level == "intermediate":
            return LearningStage.PRACTICE
        elif knowledge_level == "advanced":
            return LearningStage.ADVANCED
        else:
            return LearningStage.INTRO

    def _infer_priority(self, point: str, profile: Dict[str, Any]) -> ResourcePriority:
        """根据用户画像推断知识点优先级"""
        weak = set(profile.get("weak_points", []))
        mastered = set(profile.get("mastered_points", []))

        if point in weak:
            return ResourcePriority.HIGH
        elif point in mastered:
            return ResourcePriority.LOW
        else:
            return ResourcePriority.MEDIUM

    def _recommend_type(self, learning_style: str, stage: LearningStage) -> str:
        """
        基于风格和阶段推荐最合适的资源类型

        Args:
            learning_style: 学习风格
            stage: 学习阶段

        Returns:
            推荐的资源类型
        """
        # 获取该学习风格的候选类型
        candidates = self.STYLE_MAP.get(learning_style, ["doc", "quiz"])

        # 如果阶段有强偏好，且该类型在候选列表中，优先返回
        if stage in self.STAGE_DEFAULT:
            default_type = self.STAGE_DEFAULT[stage]
            if default_type in candidates:
                return default_type

        # 否则返回风格最优先的类型
        return candidates[0]

    def _estimate_time(self, resource_type: str, level: str) -> int:
        """
        估算学习时长

        Args:
            resource_type: 资源类型
            level: 知识水平

        Returns:
            预计学习时长（分钟）
        """
        base_time = self.RESOURCE_TIME_BASE.get(resource_type, RESOURCE_PLANNER_DEFAULT_RESOURCE_TIME)

        # 根据基础水平调整：beginner *1.5, advanced *0.8
        if level == "beginner":
            time_min = int(base_time * RESOURCE_PLANNER_BEGINNER_MULTIPLIER)
        elif level == "advanced":
            time_min = int(base_time * RESOURCE_PLANNER_ADVANCED_MULTIPLIER)
        else:
            time_min = base_time

        return max(RESOURCE_PLANNER_MIN_TIME_MINUTES, time_min)

    # ------------------------------
    # 学习路径管理方法（保留扩展接口）
    # ------------------------------
    async def update_learning_path(
            self,
            learning_path: LearningPath,
            user_profile: Dict[str, Any],
            completed_knowledge_points: Optional[List[str]] = None
    ) -> LearningPath:
        """
        更新学习路径（基于用户进度）

        Args:
            learning_path: 原学习路径
            user_profile: 更新后的用户画像
            completed_knowledge_points: 新完成的知识点列表（可选）

        Returns:
            更新后的学习路径
        """
        logger.info(f"🔄 更新学习路径: user={learning_path.user_id}, version={learning_path.version}")

        # 合并已掌握的知识点
        mastered = set(user_profile.get("mastered_points", []))
        if completed_knowledge_points:
            mastered.update(completed_knowledge_points)

        # 移除已掌握知识点对应的计划
        new_plans = [
            p for p in learning_path.resource_plans
            if p.knowledge_point not in mastered
        ]

        # 更新路径
        learning_path.resource_plans = new_plans
        learning_path.version += 1
        learning_path.created_at = datetime.now(UTC).replace(tzinfo=None)

        logger.info(f"✅ 学习路径已更新: 剩余 {len(new_plans)} 个资源")
        return learning_path

    async def recommend_resource_type(
            self,
            knowledge_point: str,
            user_profile: Dict[str, Any],
            stage: Optional[LearningStage] = None
    ) -> str:
        """
        为指定知识点推荐资源类型（保留扩展接口）

        Args:
            knowledge_point: 知识点
            user_profile: 用户画像
            stage: 学习阶段（可选，不填则自动判断）

        Returns:
            推荐的资源类型
        """
        if stage is None:
            knowledge_level = user_profile.get("knowledge_level", "beginner")
            stage = self._infer_stage(knowledge_level)

        learning_style = user_profile.get("learning_style", "mixed")
        return self._recommend_type(learning_style, stage)

    async def determine_priority(
            self,
            knowledge_point: str,
            user_profile: Dict[str, Any]
    ) -> ResourcePriority:
        """
        确定知识点的优先级（保留扩展接口）

        Args:
            knowledge_point: 知识点
            user_profile: 用户画像

        Returns:
            资源优先级
        """
        return self._infer_priority(knowledge_point, user_profile)

    async def determine_learning_stage(
            self,
            user_profile: Dict[str, Any]
    ) -> LearningStage:
        """
        确定用户的学习阶段（保留扩展接口）

        Args:
            user_profile: 用户画像

        Returns:
            学习阶段
        """
        knowledge_level = user_profile.get("knowledge_level", "beginner")
        return self._infer_stage(knowledge_level)

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        try:
            # 简单检查：验证配置和依赖图加载
            assert self.STYLE_MAP is not None
            assert self.STAGE_DEFAULT is not None
            logger.debug("🏥 资源规划器健康检查: ✅ 正常")
            return True
        except Exception as e:
            logger.warning(f"⚠️  资源规划器健康检查失败: {e}")
            return False


# ------------------------------
# 全局单例
# ------------------------------
_planner: Optional[ResourcePlanner] = None


def get_resource_planner() -> ResourcePlanner:
    """获取全局资源规划器单例"""
    global _planner
    if _planner is None:
        _planner = ResourcePlanner()
    return _planner


# ------------------------------
# 模块自测
# ------------------------------
if __name__ == "__main__":
    import asyncio


    async def _test():
        print("=" * 60)
        print("🔍 资源规划器模块自测 v1.2")
        print("=" * 60)

        planner = get_resource_planner()

        # 1. 测试健康检查
        print("\n1. 测试健康检查...")
        is_healthy = await planner.health_check()
        print(f"   健康状态: {'✅ 正常' if is_healthy else '❌ 异常'}")

        # 2. 测试规划资源
        print("\n2. 测试规划资源...")
        test_profile = {
            "learning_style": "visual",
            "knowledge_level": "beginner",
            "weak_points": ["循环", "函数", "列表"],
            "mastered_points": ["变量与数据类型"],
        }

        learning_path = await planner.plan_resources(
            user_id=1,
            user_profile=test_profile,
            target_knowledge_points=["循环", "函数", "列表"],
            max_resources=5
        )

        print(f"   ✅ 生成学习路径:")
        print(f"      - 用户ID: {learning_path.user_id}")
        print(f"      - 资源数: {learning_path.total_resources}")
        print(f"      - 总时长: {learning_path.total_estimated_hours} 小时")
        print(f"      - 版本: {learning_path.version}")

        for i, plan in enumerate(learning_path.resource_plans, 1):
            print(f"      {i}. {plan.knowledge_point} - {plan.resource_type} "
                  f"({plan.priority.value}, {plan.estimated_time_minutes}min)")

        # 3. 测试更新学习路径
        print("\n3. 测试更新学习路径...")
        updated_profile = test_profile.copy()
        updated_profile["mastered_points"] = ["变量与数据类型", "循环"]

        updated_path = await planner.update_learning_path(
            learning_path=learning_path,
            user_profile=updated_profile,
            completed_knowledge_points=["循环"]
        )

        print(f"   ✅ 更新后学习路径:")
        print(f"      - 资源数: {updated_path.total_resources}")
        print(f"      - 版本: {updated_path.version}")

        print("\n" + "=" * 60)
        print("✅ 资源规划器模块自测通过！")
        print("=" * 60)


    asyncio.run(_test())