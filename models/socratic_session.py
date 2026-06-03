"""
models/socratic_session.py - 苏格拉底教学会话数据采集
记录每次教学会话的动作序列、响应时间、掌握度变化，用于教学效果分析
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, JSON
from models.database import Base


class SocraticSession(Base):
    """苏格拉底教学会话记录"""
    __tablename__ = "socratic_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(String(64), nullable=False, unique=True, index=True)
    conversation_id = Column(Integer, nullable=True)

    # 主题与知识点
    topic = Column(String(200), nullable=False)
    knowledge_points = Column(JSON, nullable=True)  # ["知识点1", "知识点2"]

    # 会话统计
    total_actions = Column(Integer, default=0)        # 总动作数
    total_correct = Column(Integer, default=0)        # 正确回答数
    total_wrong = Column(Integer, default=0)          # 错误回答数
    total_hints = Column(Integer, default=0)          # 提示使用数
    total_duration_sec = Column(Float, default=0.0)   # 总时长（秒）

    # 动作序列（JSON数组）
    action_sequence = Column(JSON, nullable=True)
    # [{"action": "ask_question", "target": "列表推导式", "correct": true,
    #   "response_time_ms": 15000, "mastery_before": 0.0, "mastery_after": 0.6, "ts": "..."}]

    # 掌握度变化
    initial_mastery = Column(JSON, nullable=True)     # 初始掌握度 {"知识点": 0.0}
    final_mastery = Column(JSON, nullable=True)       # 最终掌握度 {"知识点": 0.8}

    # 性能指标
    avg_response_time_ms = Column(Float, default=0.0) # 平均LLM响应时间
    max_response_time_ms = Column(Float, default=0.0) # 最大LLM响应时间
    llm_call_count = Column(Integer, default=0)       # LLM调用总次数

    # 教学决策统计
    action_distribution = Column(JSON, nullable=True) # {"ask_question": 5, "explain_concept": 2, ...}
    decision_reasons = Column(JSON, nullable=True)    # 决策原因汇总

    # 学习状态变化
    learning_state_changes = Column(JSON, nullable=True)
    # [{"from": "normal", "to": "confused", "ts": "..."}]

    # 结束信息
    end_reason = Column(String(50), nullable=True)    # completed/user_ended/max_errors/timeout
    summary = Column(Text, nullable=True)             # 学习总结

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<SocraticSession user={self.user_id} topic={self.topic} actions={self.total_actions}>"
