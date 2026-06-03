"""
会话内实时学习状态管理
- 基于有限状态机定义 5 种学习状态
- 根据连续答题结果和响应时间驱动状态转换
- 序列化/反序列化支持跨进程持久化
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, Any, List
from datetime import datetime


class LearningState(Enum):
    """学习状态枚举"""
    NORMAL = "normal"           # 正常学习
    CONFUSED = "confused"       # 困惑（连续答错 2 题）
    STRUGGLING = "struggling"   # 困难（连续答错 3+ 题）
    MASTERING = "mastering"     # 掌握（连续答对 3+ 题，正常速度）
    BORED = "bored"             # 无聊（连续答对 3+ 题且答题过快）


class RealTimeLearningState:
    """单次会话的实时学习状态跟踪"""

    # 状态转换阈值
    CONFUSED_THRESHOLD = 2
    STRUGGLING_THRESHOLD = 3
    MASTERING_THRESHOLD = 3
    FAST_ANSWER_MS = 3000       # 答题时间 < 3s 视为"过快"
    HISTORY_WINDOW = 5          # 保留最近 5 次答题时间

    def __init__(self, user_id: int, session_id: str) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.consecutive_correct: int = 0
        self.consecutive_incorrect: int = 0
        self.last_response_times: List[int] = []  # 毫秒
        self.current_state: LearningState = LearningState.NORMAL
        self.last_state_change: float = datetime.now().timestamp()

    def update_with_answer(self, is_correct: bool, response_time_ms: int) -> None:
        """根据答题结果更新状态"""
        if is_correct:
            self.consecutive_correct += 1
            self.consecutive_incorrect = 0
        else:
            self.consecutive_incorrect += 1
            self.consecutive_correct = 0

        # 维护滑动窗口
        self.last_response_times.append(response_time_ms)
        if len(self.last_response_times) > self.HISTORY_WINDOW:
            self.last_response_times.pop(0)

        # 状态转换
        old_state = self.current_state
        self._transition()

        if self.current_state != old_state:
            self.last_state_change = datetime.now().timestamp()

    def _transition(self) -> None:
        """状态转换逻辑"""
        if self.consecutive_incorrect >= self.STRUGGLING_THRESHOLD:
            self.current_state = LearningState.STRUGGLING
        elif self.consecutive_incorrect >= self.CONFUSED_THRESHOLD:
            self.current_state = LearningState.CONFUSED
        elif self.consecutive_correct >= self.MASTERING_THRESHOLD and self._is_answering_fast():
            self.current_state = LearningState.BORED
        elif self.consecutive_correct >= self.MASTERING_THRESHOLD:
            self.current_state = LearningState.MASTERING
        else:
            self.current_state = LearningState.NORMAL

    def _is_answering_fast(self) -> bool:
        """判断是否答题过快（最近 3 次平均 < 3s）"""
        if len(self.last_response_times) < 3:
            return False
        avg = sum(self.last_response_times[-3:]) / 3
        return avg < self.FAST_ANSWER_MS

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "session_id": self.session_id,
            "consecutive_correct": self.consecutive_correct,
            "consecutive_incorrect": self.consecutive_incorrect,
            "last_response_times": self.last_response_times,
            "current_state": self.current_state.value,
            "last_state_change": self.last_state_change,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RealTimeLearningState:
        state = cls(data["user_id"], data["session_id"])
        state.consecutive_correct = data["consecutive_correct"]
        state.consecutive_incorrect = data["consecutive_incorrect"]
        state.last_response_times = data["last_response_times"]
        state.current_state = LearningState(data["current_state"])
        state.last_state_change = data["last_state_change"]
        return state
