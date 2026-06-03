"""
ai/experiment_config.py - 预定义 A/B 测试实验配置
启动时自动 upsert 到数据库，确保实验始终存在。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.experiment import Experiment
from utils.logger import get_logger

logger = get_logger(__name__, task_id="experiment_config")

PREDEFINED_EXPERIMENTS = [
    {
        "name": "teaching_mode",
        "description": "教学模式对比：苏格拉底式引导 vs 直接讲解",
        "variants": {
            "socratic": {"workflow": "socratic", "prompt_style": "guided"},
            "direct": {"workflow": "direct", "prompt_style": "explain"},
        },
        "traffic_allocation": 1.0,
    },
    {
        "name": "difficulty_adaptation",
        "description": "难度调节对比：IRT 自适应 vs 固定中等难度",
        "variants": {
            "adaptive": {"difficulty_mode": "auto"},
            "fixed": {"difficulty_mode": "fixed", "fixed_level": "medium"},
        },
        "traffic_allocation": 1.0,
    },
    {
        "name": "realtime_adaptation",
        "description": "实时适应对比：注入学习状态机提示词 vs 不注入",
        "variants": {
            "with_adaptation": {"inject_learning_state": True},
            "without_adaptation": {"inject_learning_state": False},
        },
        "traffic_allocation": 1.0,
    },
]


async def ensure_experiments_exist(db: AsyncSession) -> None:
    """启动时 upsert 预定义实验（幂等操作）"""
    for exp_def in PREDEFINED_EXPERIMENTS:
        result = await db.execute(
            select(Experiment).where(Experiment.name == exp_def["name"])
        )
        existing = result.scalar_one_or_none()
        if existing:
            # 更新变体配置（允许运行时调整）
            existing.description = exp_def["description"]
            existing.variants = exp_def["variants"]
            existing.traffic_allocation = exp_def["traffic_allocation"]
            logger.info(f"实验已更新: {exp_def['name']}")
        else:
            db.add(Experiment(
                name=exp_def["name"],
                description=exp_def["description"],
                status="draft",
                variants=exp_def["variants"],
                traffic_allocation=exp_def["traffic_allocation"],
            ))
            logger.info(f"实验已创建: {exp_def['name']}")
    await db.commit()
    logger.info("预定义实验初始化完成")
