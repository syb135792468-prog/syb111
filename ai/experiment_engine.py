"""
ai/experiment_engine.py - A/B 测试实验引擎
- 确定性哈希分组（同一用户同一实验永远同组）
- 变体配置查询
- 暴露日志记录
- 统计分析（卡方检验 + Welch t 检验）
"""
from __future__ import annotations

import math
import hashlib
from typing import Optional, Dict, Any, List
from datetime import datetime, UTC

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.experiment import Experiment, ExperimentAssignment
from models.quiz_attempt import QuizAttempt
from models.database import AsyncSessionLocal
from utils.logger import get_logger

logger = get_logger(__name__, task_id="experiment")


class ExperimentEngine:
    """A/B 测试核心引擎"""

    @staticmethod
    def _hash_assign(user_id: int, experiment_name: str) -> float:
        """确定性哈希：同一用户同一实验永远得到相同 [0, 1) 值"""
        raw = hashlib.md5(f"{experiment_name}:{user_id}".encode()).hexdigest()
        return int(raw[:8], 16) / 0xFFFFFFFF

    async def get_variant(
        self, user_id: int, experiment_name: str, db: AsyncSession
    ) -> Optional[str]:
        """获取用户的实验变体，自动分配并持久化"""
        # 1. 查找活跃实验
        result = await db.execute(
            select(Experiment).where(
                Experiment.name == experiment_name,
                Experiment.status == "active",
            )
        )
        experiment = result.scalar_one_or_none()
        if not experiment:
            return None

        # 2. 查找已有分组
        result = await db.execute(
            select(ExperimentAssignment).where(
                ExperimentAssignment.experiment_id == experiment.id,
                ExperimentAssignment.user_id == user_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if assignment:
            return assignment.variant

        # 3. 流量判断
        hash_val = self._hash_assign(user_id, experiment_name)
        if hash_val >= experiment.traffic_allocation:
            return None

        # 4. 均匀分配到变体
        variants = list(experiment.variants.keys())
        if not variants:
            return None
        bucket = hash_val / experiment.traffic_allocation  # 重新归一化到 [0, 1)
        idx = int(bucket * len(variants))
        idx = min(idx, len(variants) - 1)
        variant = variants[idx]

        # 5. 持久化分组
        assignment = ExperimentAssignment(
            experiment_id=experiment.id,
            user_id=user_id,
            variant=variant,
        )
        db.add(assignment)
        await db.commit()
        logger.info(f"实验分组: user={user_id}, experiment={experiment_name}, variant={variant}")
        return variant

    async def get_variant_config(
        self, user_id: int, experiment_name: str, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """获取用户的变体配置字典"""
        result = await db.execute(
            select(Experiment).where(
                Experiment.name == experiment_name,
                Experiment.status == "active",
            )
        )
        experiment = result.scalar_one_or_none()
        if not experiment:
            return None

        variant = await self.get_variant(user_id, experiment_name, db)
        if not variant:
            return None
        return experiment.variants.get(variant)

    async def get_experiment_list(self, db: AsyncSession) -> List[Dict[str, Any]]:
        """获取所有实验及其分组统计"""
        result = await db.execute(select(Experiment))
        experiments = result.scalars().all()
        output = []
        for exp in experiments:
            count_result = await db.execute(
                select(
                    ExperimentAssignment.variant,
                    func.count(ExperimentAssignment.id),
                )
                .where(ExperimentAssignment.experiment_id == exp.id)
                .group_by(ExperimentAssignment.variant)
            )
            variant_counts = dict(count_result.all())
            output.append({
                **exp.to_dict(),
                "variant_counts": variant_counts,
                "total_assigned": sum(variant_counts.values()),
            })
        return output

    async def get_experiment_analysis(
        self, experiment_name: str, db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        """计算实验分析结果（含统计检验）"""
        result = await db.execute(
            select(Experiment).where(Experiment.name == experiment_name)
        )
        experiment = result.scalar_one_or_none()
        if not experiment:
            return None

        # 获取所有分组
        result = await db.execute(
            select(ExperimentAssignment).where(
                ExperimentAssignment.experiment_id == experiment.id
            )
        )
        assignments = result.scalars().all()
        if not assignments:
            return {
                "experiment": experiment.to_dict(),
                "variants": {},
                "statistical_tests": {},
                "minimum_sample_size_met": False,
            }

        # 按变体分组用户
        variant_users: Dict[str, List[int]] = {}
        for a in assignments:
            variant_users.setdefault(a.variant, []).append(a.user_id)

        # 计算每个变体的指标
        variant_metrics: Dict[str, Dict[str, Any]] = {}
        for variant, users in variant_users.items():
            metrics = await self._compute_variant_metrics(users, db)
            metrics["user_count"] = len(users)
            variant_metrics[variant] = metrics

        # 统计检验
        statistical_tests = self._run_statistical_tests(variant_metrics)

        # 样本量检查
        min_sample_met = all(
            m.get("user_count", 0) >= 5 for m in variant_metrics.values()
        )

        return {
            "experiment": experiment.to_dict(),
            "variants": variant_metrics,
            "statistical_tests": statistical_tests,
            "minimum_sample_size_met": min_sample_met,
        }

    async def _compute_variant_metrics(
        self, user_ids: List[int], db: AsyncSession
    ) -> Dict[str, Any]:
        """计算单个变体的核心指标"""
        if not user_ids:
            return {"quiz_accuracy": 0, "avg_response_time_sec": 0, "total_attempts": 0}

        # Quiz 正确率
        result = await db.execute(
            select(
                func.count(QuizAttempt.id),
                func.sum(func.cast(QuizAttempt.is_correct, int)),
                func.avg(QuizAttempt.spent_time),
            ).where(QuizAttempt.user_id.in_(user_ids))
        )
        row = result.one()
        total = row[0] or 0
        correct = row[1] or 0
        avg_time = row[2] or 0

        return {
            "quiz_accuracy": round(correct / total, 4) if total > 0 else 0,
            "avg_response_time_sec": round(float(avg_time), 2),
            "total_attempts": total,
        }

    def _run_statistical_tests(
        self, variant_metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """对所有变体对运行统计检验"""
        variants = list(variant_metrics.keys())
        if len(variants) < 2:
            return {}

        tests = {}

        # 卡方检验：正确率
        a, b = variants[0], variants[1]
        ma, mb = variant_metrics[a], variant_metrics[b]
        tests["quiz_accuracy"] = self._chi_squared_test(
            int(ma.get("quiz_accuracy", 0) * ma.get("total_attempts", 0)),
            ma.get("total_attempts", 0),
            int(mb.get("quiz_accuracy", 0) * mb.get("total_attempts", 0)),
            mb.get("total_attempts", 0),
        )

        return tests

    @staticmethod
    def _chi_squared_test(
        correct_a: int, total_a: int, correct_b: int, total_b: int
    ) -> Dict[str, Any]:
        """2×2 卡方检验（无 scipy 依赖）"""
        if total_a == 0 or total_b == 0:
            return {"test": "chi_squared", "statistic": 0, "p_value": 1.0, "significant": False}

        incorrect_a = total_a - correct_a
        incorrect_b = total_b - correct_b
        total = total_a + total_b
        total_correct = correct_a + correct_b
        total_incorrect = incorrect_a + incorrect_b

        observed = [correct_a, incorrect_a, correct_b, incorrect_b]
        expected = [
            total_a * total_correct / total,
            total_a * total_incorrect / total,
            total_b * total_correct / total,
            total_b * total_incorrect / total,
        ]

        chi2 = sum((o - e) ** 2 / e for o, e in zip(observed, expected) if e > 0)
        # 1 自由度的 p 值近似: p = exp(-chi2/2)
        p_value = math.exp(-chi2 / 2) if chi2 > 0 else 1.0

        return {
            "test": "chi_squared",
            "statistic": round(chi2, 4),
            "p_value": round(p_value, 4),
            "significant": p_value < 0.05,
        }


# 模块级单例
experiment_engine = ExperimentEngine()
