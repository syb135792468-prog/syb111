"""
自适应难度引擎（IRT 简化版）
- 基于项目反应理论估计用户能力值
- 选择信息函数最大的题目实现最优匹配
- 能力值持久化到 User.ability_estimates
"""
from __future__ import annotations

import math
import json
from typing import Tuple, Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.quiz_attempt import QuizAttempt
from models.user import User
from utils.logger import get_logger

logger = get_logger(__name__, task_id="adaptive_difficulty")

# IRT 三参数模型默认值
DEFAULT_DISCRIMINATION = 1.0  # 区分度 a
DEFAULT_GUESS_PROBABILITY = 0.25  # 猜测概率 c
ABILITY_MIN = -3.0
ABILITY_MAX = 3.0
DEFAULT_ABILITY = 0.0
DEFAULT_SE = 1.0


def _irt_probability(ability: float, difficulty: float,
                     discrimination: float = DEFAULT_DISCRIMINATION,
                     guess: float = DEFAULT_GUESS_PROBABILITY) -> float:
    """IRT 三参数模型：计算正确作答概率 P(theta)"""
    exponent = -discrimination * (ability - difficulty)
    exponent = max(-20.0, min(20.0, exponent))  # 防溢出
    return guess + (1 - guess) / (1 + math.exp(exponent))


def _item_information(ability: float, difficulty: float,
                      discrimination: float = DEFAULT_DISCRIMINATION,
                      guess: float = DEFAULT_GUESS_PROBABILITY) -> float:
    """计算题目信息函数 I(theta)"""
    p = _irt_probability(ability, difficulty, discrimination, guess)
    if p <= 0 or p >= 1:
        return 0.0
    numerator = discrimination ** 2 * (p - guess) ** 2 * (1 - p)
    denominator = (1 - guess) ** 2 * p
    return numerator / denominator if denominator > 0 else 0.0


class AdaptiveDifficultyEngine:
    """自适应难度引擎：估计用户能力 + 选择最优题目"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def estimate_user_ability(self, user_id: int, topic: str) -> Tuple[float, float]:
        """
        贝叶斯更新用户在指定主题的能力值
        返回 (ability_score, standard_error)
        """
        # 获取最近 10 次答题记录
        stmt = (
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.knowledge_point == topic,
            )
            .order_by(QuizAttempt.created_at.desc())
            .limit(10)
        )
        result = await self.db.execute(stmt)
        attempts = list(result.scalars().all())

        if not attempts:
            return (DEFAULT_ABILITY, DEFAULT_SE)

        # 读取先验
        user = await self.db.get(User, user_id)
        if not user:
            return (DEFAULT_ABILITY, DEFAULT_SE)

        priors = json.loads(user.ability_estimates or "{}")
        se_map = json.loads(user.ability_standard_errors or "{}")
        ability = priors.get(topic, DEFAULT_ABILITY)
        se = se_map.get(topic, DEFAULT_SE)

        # 贝叶斯更新（从旧到新）
        for attempt in reversed(attempts):
            difficulty = self._extract_difficulty(attempt)
            correct = 1.0 if attempt.is_correct else 0.0

            p = _irt_probability(ability, difficulty)
            info = _item_information(ability, difficulty)

            if info > 0:
                ability += (correct - p) / info
                se = 1.0 / math.sqrt(1.0 / (se ** 2) + info)

        ability = max(ABILITY_MIN, min(ABILITY_MAX, ability))

        # 持久化
        priors[topic] = round(ability, 4)
        se_map[topic] = round(se, 4)
        user.ability_estimates = json.dumps(priors, ensure_ascii=False)
        user.ability_standard_errors = json.dumps(se_map, ensure_ascii=False)
        await self.db.commit()

        logger.info(f"能力更新: user={user_id}, topic={topic}, ability={ability:.3f}, se={se:.3f}")
        return (ability, se)

    async def select_difficulty_for_topic(self, user_id: int, topic: str) -> str:
        """
        根据用户能力推荐难度等级
        返回 "easy" / "medium" / "hard"
        """
        ability, se = await self.estimate_user_ability(user_id, topic)

        # 能力值映射到难度：考虑标准误差的保守策略
        effective = ability - 0.5 * se  # 偏保守，避免太难

        if effective < -0.5:
            return "easy"
        elif effective > 0.5:
            return "hard"
        else:
            return "medium"

    async def get_user_ability_summary(self, user_id: int) -> Dict[str, Any]:
        """获取用户各主题能力摘要"""
        user = await self.db.get(User, user_id)
        if not user:
            return {}
        return {
            "abilities": json.loads(user.ability_estimates or "{}"),
            "standard_errors": json.loads(user.ability_standard_errors or "{}"),
        }

    @staticmethod
    def _extract_difficulty(attempt: QuizAttempt) -> float:
        """从答题记录中提取难度值（字符串 → IRT 数值）"""
        diff_map = {"easy": -1.0, "medium": 0.0, "hard": 1.0}
        return diff_map.get(attempt.difficulty, 0.0)
