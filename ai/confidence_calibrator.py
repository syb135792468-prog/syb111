"""
LLM 置信度校准器
- 从 LLM 响应中提取自报置信度
- 校准 LLM 过于自信的倾向（乘 0.8 + 0.1 偏移）
- 低于阈值时触发关键词兜底
"""
from __future__ import annotations

import re
from typing import Tuple


class ConfidenceCalibrator:
    """校准 LLM 自报置信度，降低过度自信带来的误判"""

    # 校准公式：calibrated = raw * SCALE + OFFSET
    _SCALE = 0.8
    _OFFSET = 0.1

    @staticmethod
    def extract_confidence(response: str) -> Tuple[str, float]:
        """
        从 LLM 响应中提取置信度并返回 (清理后响应, 校准后置信度)

        要求 LLM 在响应末尾附加 "Confidence: 0.XX" 格式
        若未找到，返回默认置信度 0.5
        """
        pattern = r"Confidence:\s*(\d+\.?\d*)"
        match = re.search(pattern, response, re.IGNORECASE)

        if match:
            try:
                raw = float(match.group(1))
                calibrated = max(0.0, min(1.0, raw * ConfidenceCalibrator._SCALE + ConfidenceCalibrator._OFFSET))
                cleaned = re.sub(pattern, "", response, flags=re.IGNORECASE).strip()
                return cleaned, calibrated
            except ValueError:
                pass

        return response, 0.5

    @staticmethod
    def should_use_fallback(confidence: float, threshold: float = 0.6) -> bool:
        """判断置信度是否低于阈值，应使用关键词兜底"""
        return confidence < threshold


# 全局单例
confidence_calibrator = ConfidenceCalibrator()
