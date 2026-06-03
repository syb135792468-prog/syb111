"""
会话内实时适应引擎
- 管理活跃会话的 LearningState
- 根据当前状态生成 TutorAgent 的讲解策略提示词
- 自动清理过期会话状态
"""
from __future__ import annotations

from typing import Dict, Optional
from datetime import datetime, timedelta

from ai.learning_state import RealTimeLearningState, LearningState
from utils.logger import get_logger

logger = get_logger(__name__, task_id="adaptation")


# 各学习状态对应的讲解策略提示词
_EXPLANATION_PROMPTS: Dict[LearningState, str] = {
    LearningState.NORMAL: (
        "用清晰、简洁的语言解释概念，包含 1 个简单例子，保持中等难度。"
    ),
    LearningState.CONFUSED: (
        "用户似乎有些困惑。请用更简单、更基础的方式解释，避免专业术语"
        "（如必须使用请先定义）。分步骤讲解，每步都清晰，用日常生活例子，"
        "放慢节奏确保用户能跟上。"
    ),
    LearningState.STRUGGLING: (
        "用户正遇到很大困难。请从最基本的原理讲起，假设用户完全不了解此概念。"
        "大量使用类比和比喻，把复杂概念拆成多个小部分逐一讲解，"
        "每讲完一部分确认用户是否理解。"
    ),
    LearningState.MASTERING: (
        "用户已掌握基础知识，可适当提高难度。解释更深入的细节和高级用法，"
        "介绍实际应用场景，提及相关的进阶概念，鼓励尝试更复杂的问题。"
    ),
    LearningState.BORED: (
        "用户可能感到无聊。加快节奏，跳过基础部分直接进入核心内容，"
        "提供更具挑战性的例子，介绍有趣的技巧和最佳实践，保持简洁有力。"
    ),
}


class RealTimeAdaptationEngine:
    """管理所有活跃会话的实时学习状态"""

    def __init__(self, state_expiry: timedelta = timedelta(hours=1)) -> None:
        self.session_states: Dict[str, RealTimeLearningState] = {}
        self.state_expiry = state_expiry

    def get_or_create_state(self, user_id: int, session_id: str) -> RealTimeLearningState:
        """获取或创建会话的学习状态"""
        self._cleanup_expired()
        if session_id not in self.session_states:
            self.session_states[session_id] = RealTimeLearningState(user_id, session_id)
        return self.session_states[session_id]

    def update_state_with_answer(
        self, user_id: int, session_id: str, is_correct: bool, response_time_ms: int
    ) -> LearningState:
        """更新学习状态并返回新状态"""
        state = self.get_or_create_state(user_id, session_id)
        state.update_with_answer(is_correct, response_time_ms)
        logger.debug(
            f"状态更新: user={user_id}, session={session_id}, "
            f"state={state.current_state.value}, correct={is_correct}"
        )
        return state.current_state

    def get_explanation_prompt(self, user_id: int, session_id: str) -> str:
        """获取当前状态对应的讲解策略提示词"""
        state = self.get_or_create_state(user_id, session_id)
        return _EXPLANATION_PROMPTS[state.current_state]

    def get_state(self, session_id: str) -> Optional[LearningState]:
        """查询会话当前状态（不创建）"""
        state = self.session_states.get(session_id)
        return state.current_state if state else None

    def remove_session(self, session_id: str) -> None:
        """手动移除会话状态"""
        self.session_states.pop(session_id, None)

    def _cleanup_expired(self) -> None:
        """清理过期会话"""
        now = datetime.now()
        expired = [
            sid for sid, state in self.session_states.items()
            if now - datetime.fromtimestamp(state.last_state_change) > self.state_expiry
        ]
        for sid in expired:
            del self.session_states[sid]
        if expired:
            logger.info(f"清理 {len(expired)} 个过期会话状态")


# 全局单例
real_time_adaptation_engine = RealTimeAdaptationEngine()
