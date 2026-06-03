"""
ai/spaced_repetition.py - 艾宾浩斯遗忘曲线间隔重复引擎
基于 SM-2 (SuperMemo 2) 算法，根据用户复习表现动态调整下次复习时间。
"""
from __future__ import annotations

from datetime import datetime, timedelta, UTC
from typing import Tuple


# SM-2 标准间隔序列（天）：首次答错后 1天 → 2天 → 6天 → 15天 → 30天 ...
# 实际由 easiness_factor 动态计算，此为默认 EF=2.5 时的近似值
DEFAULT_EASINESS_FACTOR = 2.5
MIN_EASINESS_FACTOR = 1.3
INITIAL_INTERVAL_DAYS = 1.0
MASTERED_REPETITION_THRESHOLD = 5


def calculate_next_review(
    quality: int,
    repetition_count: int,
    easiness_factor: float,
    current_interval_days: float,
) -> Tuple[float, float, int]:
    """
    SM-2 核心算法：根据本次复习质量计算下次复习参数。

    Args:
        quality: 复习质量评分 0-5
            0 = 完全忘记
            1 = 错误，但看到答案后记起
            2 = 错误，但答案很熟悉
            3 = 正确，但很费力
            4 = 正确，略有犹豫
            5 = 完美回忆
        repetition_count: 当前连续正确次数
        easiness_factor: 当前难度因子（>= 1.3）
        current_interval_days: 当前间隔天数

    Returns:
        (new_interval_days, new_easiness_factor, new_repetition_count)
    """
    quality = max(0, min(5, quality))

    # 更新 easiness_factor (EF)
    # EF' = EF + (0.1 - (5-q) * (0.08 + (5-q) * 0.02))
    ef_delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    new_ef = max(MIN_EASINESS_FACTOR, easiness_factor + ef_delta)

    if quality < 3:
        # 回答错误或太困难 → 重置间隔，从头开始
        new_interval = INITIAL_INTERVAL_DAYS
        new_repetition = 0
    else:
        # 回答正确 → 递增间隔
        new_repetition = repetition_count + 1
        if new_repetition == 1:
            new_interval = 1.0
        elif new_repetition == 2:
            new_interval = 3.0
        else:
            new_interval = current_interval_days * new_ef

    return new_interval, new_ef, new_repetition


def get_next_review_time(
    quality: int,
    repetition_count: int,
    easiness_factor: float,
    current_interval_days: float,
) -> Tuple[datetime, float, float, int]:
    """
    计算下次复习的绝对时间。

    Returns:
        (next_review_at, new_interval, new_ef, new_repetition)
    """
    new_interval, new_ef, new_repetition = calculate_next_review(
        quality, repetition_count, easiness_factor, current_interval_days
    )
    next_review_at = datetime.now(UTC) + timedelta(days=new_interval)
    return next_review_at, new_interval, new_ef, new_repetition


def is_due_for_review(next_review_at: datetime | None) -> bool:
    """判断是否到了复习时间。"""
    if next_review_at is None:
        return True
    return datetime.now(UTC) >= next_review_at


def quality_from_correctness(is_correct: bool, spent_seconds: float = 0) -> int:
    """
    将简单的对错判断映射为 SM-2 质量评分。

    Args:
        is_correct: 是否答对
        spent_seconds: 答题耗时（秒）

    Returns:
        quality: 0-5
    """
    if not is_correct:
        return 1  # 错误但有印象
    if spent_seconds < 10:
        return 5  # 快速正确 = 完美
    elif spent_seconds < 30:
        return 4  # 正确略有犹豫
    else:
        return 3  # 正确但费力
