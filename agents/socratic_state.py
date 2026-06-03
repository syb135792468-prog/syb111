"""
agents/socratic_state.py - 苏格拉底导学模式 2.0 状态定义
动态决策引擎架构，移除固定阶段约束
"""
from typing import TypedDict, List, Optional


class SocraticState(TypedDict, total=False):
    # === 基础字段（与其他模式统一命名） ===
    user_id: str
    conversation_id: int
    original_query: str
    chat_history: List[dict]  # [{"role": "user"/"assistant", "content": str}, ...]

    # === 学习相关字段（复用现有系统） ===
    profile_data: dict       # 从 user_profiles 表获取
    knowledge_points: List[str]
    current_topic: str
    difficulty: int           # 1-5

    # === AI 自适应字段 ===
    session_id: str           # 会话 ID，用于实时学习状态跟踪
    learning_state: str       # 当前学习状态：normal/confused/struggling/mastering/bored
    user_ability: float       # IRT 能力估计值（-3 ~ +3）
    ability_se: float         # 能力估计标准误差

    # === 动态教学状态（2.0 新增） ===
    current_stage: str        # 当前教学阶段描述（动态，如 "列表推导式-概念理解"）
    next_action: str          # 教学决策引擎的动作决策
    action_reason: str        # 决策原因
    action_target: str        # 动作目标知识点
    recent_actions: List[dict]    # [{"action": str, "target": str, "reason": str}]
    user_misconceptions: List[dict]  # [{"point": str, "misconception": str}]
    covered_points: List[str]     # 已覆盖知识点
    pending_points: List[str]     # 待覆盖知识点

    # === 问答与掌握 ===
    question_plan: dict       # 保留用于初始提问计划
    asked_questions: List[str]
    user_answers: List[dict]  # {"question": str, "answer": str, "correct": bool, "feedback": str}
    mastery_level: dict       # {knowledge_point: float 0-1}
    mastery_changes: dict     # {knowledge_point: {"from": float, "to": float}} 用于前端实时反馈

    # === 提示与错误计数 ===
    need_hint: bool
    need_rephrase: bool
    hint_level: int           # 1-3
    hints_given: List[str]
    hint_count: int           # 总 hint 请求次数（独立于错误计数）
    consecutive_errors: int
    consecutive_correct: int  # 连续正确次数

    # === 控制字段 ===
    conversation_ended: bool
    current_response: str
    current_response_type: str  # question/feedback/hint/answer/summary/explain/demo/practice/relate
    pending_feedback: str        # evaluate_answer 的反馈，不被后续节点覆盖
    pending_feedback_type: str   # feedback/hint/answer
    error_book_entries: List[dict]
    summary: str
