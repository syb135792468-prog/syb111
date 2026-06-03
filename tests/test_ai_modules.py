"""
AI 交互体验智能优化模块 - 单元测试
覆盖：置信度校准、学习状态机、实时适应引擎、自适应难度引擎
"""
import math
import pytest


# ==================== ConfidenceCalibrator ====================

class TestConfidenceCalibrator:
    """置信度校准器测试"""

    def test_extract_confidence_with_tag(self):
        from ai.confidence_calibrator import ConfidenceCalibrator
        response = "这是回答内容\nConfidence: 0.9"
        cleaned, confidence = ConfidenceCalibrator.extract_confidence(response)
        assert "Confidence" not in cleaned
        assert 0.0 <= confidence <= 1.0
        # 校准公式：0.9 * 0.8 + 0.1 = 0.82
        assert abs(confidence - 0.82) < 0.01

    def test_extract_confidence_no_tag(self):
        from ai.confidence_calibrator import ConfidenceCalibrator
        response = "这是回答内容，没有置信度标签"
        cleaned, confidence = ConfidenceCalibrator.extract_confidence(response)
        assert cleaned == response
        assert confidence == 0.5

    def test_extract_confidence_case_insensitive(self):
        from ai.confidence_calibrator import ConfidenceCalibrator
        response = "回答\nconfidence: 0.7"
        _, confidence = ConfidenceCalibrator.extract_confidence(response)
        # 0.7 * 0.8 + 0.1 = 0.66
        assert abs(confidence - 0.66) < 0.01

    def test_calibrate_clamps_to_range(self):
        from ai.confidence_calibrator import ConfidenceCalibrator
        # 超高置信度：1.0 * 0.8 + 0.1 = 0.9
        _, c = ConfidenceCalibrator.extract_confidence("x\nConfidence: 1.0")
        assert c <= 1.0
        # 超低置信度：0.0 * 0.8 + 0.1 = 0.1
        _, c = ConfidenceCalibrator.extract_confidence("x\nConfidence: 0.0")
        assert c >= 0.0

    def test_should_use_fallback(self):
        from ai.confidence_calibrator import ConfidenceCalibrator
        assert ConfidenceCalibrator.should_use_fallback(0.5, threshold=0.6) is True
        assert ConfidenceCalibrator.should_use_fallback(0.7, threshold=0.6) is False

    def test_singleton(self):
        from ai.confidence_calibrator import confidence_calibrator
        assert confidence_calibrator is not None


# ==================== LearningState ====================

class TestLearningState:
    """学习状态机测试"""

    def _make_state(self):
        from ai.learning_state import RealTimeLearningState
        return RealTimeLearningState(user_id=1, session_id="test-session")

    def test_initial_state_is_normal(self):
        state = self._make_state()
        from ai.learning_state import LearningState
        assert state.current_state == LearningState.NORMAL

    def test_confused_after_2_incorrect(self):
        from ai.learning_state import LearningState
        state = self._make_state()
        state.update_with_answer(False, 5000)
        assert state.current_state == LearningState.NORMAL
        state.update_with_answer(False, 5000)
        assert state.current_state == LearningState.CONFUSED

    def test_struggling_after_3_incorrect(self):
        from ai.learning_state import LearningState
        state = self._make_state()
        for _ in range(3):
            state.update_with_answer(False, 5000)
        assert state.current_state == LearningState.STRUGGLING

    def test_mastering_after_3_correct_normal_speed(self):
        from ai.learning_state import LearningState
        state = self._make_state()
        for _ in range(3):
            state.update_with_answer(True, 10000)  # 10s，不算快
        assert state.current_state == LearningState.MASTERING

    def test_bored_after_3_correct_fast(self):
        from ai.learning_state import LearningState
        state = self._make_state()
        for _ in range(3):
            state.update_with_answer(True, 1000)  # 1s，很快
        assert state.current_state == LearningState.BORED

    def test_resets_on_correct_after_incorrect(self):
        from ai.learning_state import LearningState
        state = self._make_state()
        state.update_with_answer(False, 5000)
        state.update_with_answer(False, 5000)
        assert state.current_state == LearningState.CONFUSED
        state.update_with_answer(True, 10000)
        assert state.current_state == LearningState.NORMAL
        assert state.consecutive_incorrect == 0
        assert state.consecutive_correct == 1

    def test_response_time_window(self):
        state = self._make_state()
        for i in range(8):
            state.update_with_answer(True, 1000 * i)
        assert len(state.last_response_times) == 5  # 窗口大小 = 5

    def test_serialization_roundtrip(self):
        from ai.learning_state import RealTimeLearningState, LearningState
        state = self._make_state()
        state.update_with_answer(True, 1000)
        state.update_with_answer(False, 2000)
        d = state.to_dict()
        restored = RealTimeLearningState.from_dict(d)
        assert restored.current_state == state.current_state
        assert restored.consecutive_correct == state.consecutive_correct
        assert restored.consecutive_incorrect == state.consecutive_incorrect
        assert restored.last_response_times == state.last_response_times


# ==================== RealTimeAdaptationEngine ====================

class TestRealTimeAdaptationEngine:
    """实时适应引擎测试"""

    def _make_engine(self):
        from ai.real_time_adaptation import RealTimeAdaptationEngine
        return RealTimeAdaptationEngine()

    def test_get_or_create_state(self):
        engine = self._make_engine()
        state = engine.get_or_create_state(1, "s1")
        assert state.user_id == 1
        assert state.session_id == "s1"
        # 同一 session 返回同一对象
        assert engine.get_or_create_state(1, "s1") is state

    def test_update_state_returns_new_state(self):
        from ai.learning_state import LearningState
        engine = self._make_engine()
        result = engine.update_state_with_answer(1, "s1", True, 5000)
        assert result == LearningState.NORMAL
        for _ in range(3):
            result = engine.update_state_with_answer(1, "s1", False, 5000)
        assert result == LearningState.STRUGGLING

    def test_explanation_prompt_changes_with_state(self):
        engine = self._make_engine()
        normal_prompt = engine.get_explanation_prompt(1, "s1")
        assert "清晰" in normal_prompt or "简洁" in normal_prompt

        # 触发困惑状态
        engine.update_state_with_answer(1, "s1", False, 5000)
        engine.update_state_with_answer(1, "s1", False, 5000)
        confused_prompt = engine.get_explanation_prompt(1, "s1")
        assert "简单" in confused_prompt or "基础" in confused_prompt

    def test_get_state_returns_none_for_unknown(self):
        engine = self._make_engine()
        assert engine.get_state("unknown") is None

    def test_remove_session(self):
        engine = self._make_engine()
        engine.get_or_create_state(1, "s1")
        engine.remove_session("s1")
        assert engine.get_state("s1") is None

    def test_singleton(self):
        from ai.real_time_adaptation import real_time_adaptation_engine
        assert real_time_adaptation_engine is not None


# ==================== AdaptiveDifficultyEngine (IRT) ====================

class TestAdaptiveDifficultyIRT:
    """IRT 数学函数测试（不需要数据库）"""

    def test_irt_probability_at_difficulty(self):
        """能力 = 难度时，正确概率 ≈ 0.5 + 0.5*guess"""
        from ai.adaptive_difficulty import _irt_probability
        p = _irt_probability(ability=0.0, difficulty=0.0)
        # P = 0.25 + 0.75 / (1 + exp(0)) = 0.25 + 0.375 = 0.625
        assert abs(p - 0.625) < 0.01

    def test_irt_probability_high_ability(self):
        """能力远高于难度时，正确概率接近 1"""
        from ai.adaptive_difficulty import _irt_probability
        p = _irt_probability(ability=3.0, difficulty=-1.0)
        assert p > 0.9

    def test_irt_probability_low_ability(self):
        """能力远低于难度时，正确概率接近猜测概率"""
        from ai.adaptive_difficulty import _irt_probability
        p = _irt_probability(ability=-3.0, difficulty=1.0)
        assert p < 0.35

    def test_item_information_peak(self):
        """信息函数在 ability ≈ difficulty 时最大"""
        from ai.adaptive_difficulty import _item_information
        info_at_match = _item_information(0.0, 0.0)
        info_far = _item_information(0.0, 2.0)
        assert info_at_match > info_far

    def test_difficulty_mapping(self):
        from ai.adaptive_difficulty import AdaptiveDifficultyEngine
        assert AdaptiveDifficultyEngine._extract_difficulty(type("A", (), {"difficulty": "easy"})()) == -1.0
        assert AdaptiveDifficultyEngine._extract_difficulty(type("A", (), {"difficulty": "medium"})()) == 0.0
        assert AdaptiveDifficultyEngine._extract_difficulty(type("A", (), {"difficulty": "hard"})()) == 1.0
        assert AdaptiveDifficultyEngine._extract_difficulty(type("A", (), {"difficulty": "unknown"})()) == 0.0

    def test_irt_probability_no_overflow(self):
        """极端值不溢出"""
        from ai.adaptive_difficulty import _irt_probability
        p = _irt_probability(ability=100.0, difficulty=-100.0)
        assert 0.0 <= p <= 1.0
        p = _irt_probability(ability=-100.0, difficulty=100.0)
        assert 0.0 <= p <= 1.0
