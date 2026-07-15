from models.progress import LearningProgress


def test_quiz_evidence_mastery_requires_repeated_success():
    from api.routes.quiz import _calculate_evidence_mastery
    from models.quiz_attempt import QuizAttempt

    def attempt(score: int, difficulty: str = "medium") -> QuizAttempt:
        return QuizAttempt(
            user_id=1,
            resource_id=1,
            question_index=0,
            question_type="choice",
            difficulty=difficulty,
            user_answer="a",
            correct_answer="a",
            is_correct=score == 10,
            score=score,
            spent_time=10,
        )

    assert _calculate_evidence_mastery([attempt(10)]) == 60.0
    assert _calculate_evidence_mastery([attempt(10), attempt(10), attempt(10)]) == 76.0
    assert _calculate_evidence_mastery([attempt(10)] * 6) == 85.0


def test_quiz_evidence_mastery_uses_difficulty_weight():
    from api.routes.quiz import _calculate_evidence_mastery
    from models.quiz_attempt import QuizAttempt

    easy = QuizAttempt(score=10, difficulty="easy")
    hard = QuizAttempt(score=10, difficulty="hard")

    assert _calculate_evidence_mastery([hard]) > _calculate_evidence_mastery([easy])


def test_progress_score_keeps_historical_best():
    record = LearningProgress(user_id=1, topic="list-topic", status="in_progress", score=40.0, duration=0)

    record.update_progress(status="in_progress", score=20.0, duration=0)

    assert record.score == 40.0


def test_progress_status_does_not_regress_from_completed():
    record = LearningProgress(user_id=1, topic="list-topic", status="completed", score=100.0, duration=0)

    record.update_progress(status="in_progress", duration=0)

    assert record.status == "completed"


def test_progress_can_upgrade_after_failed_attempt():
    record = LearningProgress(user_id=1, topic="list-topic", status="failed", score=20.0, duration=0)

    record.update_progress(status="in_progress", score=45.0, duration=0)

    assert record.status == "in_progress"
    assert record.score == 45.0
