"""
api/routes/daily.py - 每日编程接口
- GET  /api/daily/today
- POST /api/daily/submit
- GET  /api/daily/streak
- POST /api/daily/hint
- GET  /api/daily/next-challenge
- POST /api/daily/next-challenge/hint
- POST /api/daily/next-challenge/submit
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.routes.auth import get_current_user
from api.routes.quiz import _parse_single_question
from api.schemas import BaseResponse
from services.grading_service import grade_code_with_llm
from config.constants import (
    DAILY_CHALLENGE_DATE_FORMAT,
    DAILY_CHALLENGE_QUESTION_TYPE,
    DAILY_CHALLENGE_STREAK_RECOVERY_COUNT,
    HTTP_BAD_REQUEST,
    HTTP_NOT_FOUND,
    HTTP_OK,
    HTTP_SERVER_ERROR,
    MAX_ANSWER_STORE_LENGTH,
    QUIZ_CORRECT_SCORE,
    RESOURCE_PROGRESS_COMPLETE,
    RESOURCE_TYPE_DAILY_CHALLENGE,
    RESOURCE_TYPE_DAILY_EXTRA,
)
from config.messages import MSG_SERVER_ERROR, MSG_SUCCESS
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from models.daily_challenge import DailyChallenge
from models.database import AsyncSessionLocal
from models.profile import UserProfile
from models.quiz_attempt import QuizAttempt
from models.resource import Resource
from models.user import User
from utils.logger import get_logger

router = APIRouter(prefix="/daily", tags=["每日一题"])
logger = get_logger(__name__, task_id="daily_api")


def _classify_daily_generation_error(exc: Exception) -> tuple[str, str]:
    """将每日题目生成异常映射为稳定错误码与用户可读提示。"""
    msg = str(exc).strip()
    if not msg:
        return "daily_unknown", "题目生成失败，请稍后重试"

    if "本地题库中没有可用的编程题" in msg:
        return "daily_bank_empty", "当前题库里没有可用的编程题"
    if "题目资源不存在" in msg:
        return "daily_resource_missing", "题目资源不存在，请重新加载"
    if "并发生成冲突" in msg:
        return "daily_conflict", "题目生成发生冲突，请重新加载"

    return "daily_generation_failed", msg


def _daily_error_response(error_code: str, user_message: str, *, detail: Optional[str] = None) -> BaseResponse:
    return BaseResponse(
        code=HTTP_SERVER_ERROR,
        message=user_message,
        data=None,
        error_code=error_code,
        error_detail=detail or user_message,
    )


def _today_str() -> str:
    return datetime.now().strftime(DAILY_CHALLENGE_DATE_FORMAT)


@lru_cache(maxsize=1)
def _load_question_bank() -> dict[str, list[dict[str, Any]]]:
    bank_path = Path(__file__).resolve().parent.parent.parent / "data" / "question_bank.json"
    with open(bank_path, "r", encoding="utf-8") as f:
        return json.load(f)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def _pick_knowledge_point(profile: Optional[UserProfile]) -> str:
    weak = profile.weak_points if profile and profile.weak_points else []
    if weak:
        return random.choice(weak)
    if profile and profile.current_topic:
        return profile.current_topic
    return random.choice(PYTHON_KNOWLEDGE_POINTS)


def _pick_difficulty(profile: Optional[UserProfile]) -> str:
    if profile and profile.knowledge_level == "beginner":
        return "easy"
    if profile and profile.knowledge_level == "advanced":
        return "hard"
    return "medium"


def _build_question_content(question: dict[str, Any]) -> str:
    parts = [
        f"# {question['title']}",
        f"## 题目 ({DAILY_CHALLENGE_QUESTION_TYPE})",
        question["question"],
        "",
        "## 答案",
        question["answer"],
        "",
        "## 解析",
        question.get("explanation", ""),
    ]
    return "\n".join(parts)


def _build_hints(question: dict[str, Any]) -> list[str]:
    explanation = (question.get("explanation") or "").strip()
    answer = (question.get("answer") or "").strip()
    answer_first_line = answer.splitlines()[0].strip() if answer else ""
    first_sentence = explanation.split("。")[0].strip() if explanation else ""

    hint1 = "先明确题目需要你返回什么结果，再用最直接的 Python 写法完成它。"
    hint2 = first_sentence or "优先把核心逻辑拆成 1 到 2 步，再决定是否需要函数、条件或循环。"
    hint3 = (
        f"可以围绕这段核心写法继续完善：{answer_first_line[:80]}"
        if answer_first_line
        else "先写出最小可运行版本，再补齐边界情况。"
    )
    return [hint1, hint2, hint3]


def _question_to_resource_fields(question: dict[str, Any], knowledge_point: str, difficulty: str) -> tuple[str, dict[str, Any]]:
    normalized_difficulty = question.get("difficulty") or difficulty
    metadata: dict[str, Any] = {
        "quiz_type": DAILY_CHALLENGE_QUESTION_TYPE,
        "answer": question["answer"],
        "explanation": question.get("explanation", ""),
        "difficulty": normalized_difficulty,
        "knowledge_point": knowledge_point,
        "question_title": question["title"],
        "hints": _build_hints(question),
    }
    if question.get("test_cases"):
        metadata["test_cases"] = question["test_cases"]
    return _build_question_content(question), metadata


def _pick_code_question(
    profile: Optional[UserProfile],
    difficulty: str,
    exclude_titles: Optional[set[str]] = None,
) -> tuple[str, dict[str, Any]]:
    bank = _load_question_bank()
    exclude_titles = exclude_titles or set()
    preferred_kp = _pick_knowledge_point(profile)

    def select_from_bank(knowledge_point: str, allow_exclude: bool) -> Optional[dict[str, Any]]:
        candidates = [
            item for item in bank.get(knowledge_point, [])
            if item.get("type") == DAILY_CHALLENGE_QUESTION_TYPE
        ]
        if allow_exclude:
            candidates = [item for item in candidates if item.get("title") not in exclude_titles]
        if not candidates:
            return None
        same_difficulty = [item for item in candidates if item.get("difficulty") == difficulty]
        return random.choice(same_difficulty or candidates)

    question = select_from_bank(preferred_kp, allow_exclude=True) or select_from_bank(preferred_kp, allow_exclude=False)
    if question:
        return preferred_kp, question

    all_candidates: list[tuple[str, dict[str, Any]]] = []
    for knowledge_point, items in bank.items():
        for item in items:
            if item.get("type") != DAILY_CHALLENGE_QUESTION_TYPE:
                continue
            if item.get("title") in exclude_titles:
                continue
            all_candidates.append((knowledge_point, item))
    if not all_candidates:
        for knowledge_point, items in bank.items():
            for item in items:
                if item.get("type") == DAILY_CHALLENGE_QUESTION_TYPE:
                    all_candidates.append((knowledge_point, item))
    if not all_candidates:
        raise ValueError("本地题库中没有可用的编程题")

    same_difficulty = [item for item in all_candidates if item[1].get("difficulty") == difficulty]
    return random.choice(same_difficulty or all_candidates)


def _extract_used_question_titles(resources: list[Resource]) -> set[str]:
    titles = set()
    for resource in resources:
        meta = resource.extra_metadata or {}
        title = meta.get("question_title")
        if isinstance(title, str) and title:
            titles.add(title)
    return titles


def _diff_days(date_str: str, base_str: str) -> int:
    left = datetime.strptime(date_str, DAILY_CHALLENGE_DATE_FORMAT)
    right = datetime.strptime(base_str, DAILY_CHALLENGE_DATE_FORMAT)
    return (left - right).days


def _refresh_streak_status(profile: Optional[UserProfile], today_str: str) -> None:
    if not profile or not profile.last_challenge_date:
        return
    if _diff_days(today_str, profile.last_challenge_date) <= 1:
        return
    profile.streak_status = "broken"
    profile.recovery_progress = max(profile.recovery_progress or 0, 0)


async def _update_streak(profile: UserProfile, today_str: str, is_correct: bool) -> None:
    _refresh_streak_status(profile, today_str)
    yesterday = (datetime.strptime(today_str, DAILY_CHALLENGE_DATE_FORMAT) - timedelta(days=1)).strftime(DAILY_CHALLENGE_DATE_FORMAT)

    if profile.streak_status == "broken":
        if profile.last_challenge_date == yesterday:
            profile.recovery_progress = (profile.recovery_progress or 0) + 1 if is_correct else 0
        else:
            profile.recovery_progress = 1 if is_correct else 0

        if profile.recovery_progress >= DAILY_CHALLENGE_STREAK_RECOVERY_COUNT:
            profile.streak_status = "active"
            profile.current_streak = DAILY_CHALLENGE_STREAK_RECOVERY_COUNT
            profile.recovery_progress = 0
            profile.longest_streak = max(profile.longest_streak or 0, profile.current_streak)
    else:
        profile.current_streak = (profile.current_streak or 0) + 1 if profile.last_challenge_date == yesterday else 1
        profile.longest_streak = max(profile.longest_streak or 0, profile.current_streak)

    profile.last_challenge_date = today_str


def _streak_data(profile: Optional[UserProfile]) -> dict[str, Any]:
    if not profile:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "streak_status": "active",
            "recovery_progress": 0,
        }
    return {
        "current_streak": profile.current_streak or 0,
        "longest_streak": profile.longest_streak or 0,
        "streak_status": profile.streak_status or "active",
        "recovery_progress": profile.recovery_progress or 0,
    }


def _serialize_daily_challenge(challenge: DailyChallenge, resource: Resource, today: str) -> dict[str, Any]:
    meta = resource.extra_metadata or {}
    parsed = _parse_single_question(resource.content, meta)
    return {
        "id": challenge.id,
        "resource_id": challenge.resource_id,
        "date": today,
        "questionText": parsed.get("questionText", ""),
        "options": parsed.get("options", []),
        "type": meta.get("quiz_type", DAILY_CHALLENGE_QUESTION_TYPE),
        "title": resource.title,
        "completed": challenge.is_correct is not None,
        "is_correct": challenge.is_correct,
        "difficulty": meta.get("difficulty", "medium"),
        "knowledge_point": (resource.knowledge_points or [None])[0] if resource.knowledge_points else None,
    }


def _serialize_extra_challenge(resource: Resource) -> dict[str, Any]:
    meta = resource.extra_metadata or {}
    parsed = _parse_single_question(resource.content, meta)
    return {
        "id": resource.id,
        "resource_id": resource.id,
        "questionText": parsed.get("questionText", ""),
        "options": parsed.get("options", []),
        "type": meta.get("quiz_type", DAILY_CHALLENGE_QUESTION_TYPE),
        "title": resource.title,
        "difficulty": meta.get("difficulty", "medium"),
        "knowledge_point": (resource.knowledge_points or [None])[0] if resource.knowledge_points else None,
    }


def _extract_hint(meta: dict[str, Any], hint_index: int) -> str:
    hints = meta.get("hints") or []
    if hint_index < len(hints):
        return str(hints[hint_index])
    explanation = str(meta.get("explanation") or "").strip()
    if explanation:
        return explanation.split("。")[0].strip() or explanation[:120]
    return "先从题目的输入、输出和核心逻辑入手。"


async def _grade_daily_code(question_text: str, user_answer: str, meta: dict[str, Any]) -> tuple[bool, str]:
    correct_answer = str(meta.get("answer") or "")
    explanation = str(meta.get("explanation") or "")
    test_cases = meta.get("test_cases")
    return await grade_code_with_llm(
        question_text,
        user_answer,
        correct_answer,
        explanation,
        test_cases=test_cases,
    )


# ==================== 接口 ====================

@router.get("/today", response_model=BaseResponse)
async def get_today_challenge(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取今日题目，不存在则自动生成。"""
    try:
        today = _today_str()
        result = await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id,
                DailyChallenge.challenge_date == today,
            )
        )
        challenge = result.scalar_one_or_none()

        if challenge:
            resource = await session.get(Resource, challenge.resource_id)
            if not resource:
                return BaseResponse(code=HTTP_SERVER_ERROR, message="题目资源不存在", data=None)
            profile = (await session.execute(
                select(UserProfile).where(UserProfile.user_id == user.id)
            )).scalar_one_or_none()
            _refresh_streak_status(profile, today)
            stats = await _completion_stats(session, today)
            return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
                "challenge": _serialize_daily_challenge(challenge, resource, today),
                "streak": _streak_data(profile),
                "completion_stats": stats,
            })

        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )).scalar_one_or_none()
        _refresh_streak_status(profile, today)
        difficulty = _pick_difficulty(profile)
        knowledge_point, question = _pick_code_question(profile, difficulty)
        content, metadata = _question_to_resource_fields(question, knowledge_point, difficulty)

        db_resource = Resource(
            user_id=user.id,
            task_id=str(uuid.uuid4()),
            resource_type=RESOURCE_TYPE_DAILY_CHALLENGE,
            title=f"每日一题 - {today} - {question['title']}",
            content=content,
            knowledge_points=[knowledge_point],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            extra_metadata=metadata,
        )
        dc = DailyChallenge(
            user_id=user.id,
            challenge_date=today,
            resource_id=0,
        )

        try:
            session.add(db_resource)
            await session.flush()
            dc.resource_id = db_resource.id
            session.add(dc)
            await session.commit()
            await session.refresh(dc)
            await session.refresh(db_resource)
        except IntegrityError:
            await session.rollback()
            logger.warning(f"今日题目并发生成冲突，回退到已存在题目: user_id={user.id}, date={today}")

            existing = (await session.execute(
                select(DailyChallenge).where(
                    DailyChallenge.user_id == user.id,
                    DailyChallenge.challenge_date == today,
                )
            )).scalar_one_or_none()
            if not existing:
                return _daily_error_response(
                    "daily_conflict",
                    "题目生成发生冲突，请重新加载",
                    detail="并发生成冲突后未找到可回退的每日题目",
                )

            existing_resource = await session.get(Resource, existing.resource_id)
            if not existing_resource:
                return BaseResponse(code=HTTP_SERVER_ERROR, message="题目资源不存在", data=None)

            profile = (await session.execute(
                select(UserProfile).where(UserProfile.user_id == user.id)
            )).scalar_one_or_none()
            stats = await _completion_stats(session, today)
            return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
                "challenge": _serialize_daily_challenge(existing, existing_resource, today),
                "streak": _streak_data(profile),
                "completion_stats": stats,
            })

        stats = await _completion_stats(session, today)
        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "challenge": _serialize_daily_challenge(dc, db_resource, today),
            "streak": _streak_data(profile),
            "completion_stats": stats,
        })

    except Exception as e:
        error_code, user_message = _classify_daily_generation_error(e)
        logger.error(f"[{error_code}] 获取今日题目失败: {e}", exc_info=True)
        return _daily_error_response(error_code, user_message, detail=str(e))


@router.post("/submit", response_model=BaseResponse)
async def submit_daily_answer(
    body: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """提交今日答案"""
    try:
        today = _today_str()
        user_answer = body.get("user_answer", "")
        if not user_answer.strip():
            return BaseResponse(code=HTTP_BAD_REQUEST, message="答案不能为空", data=None)

        # 查询今日挑战
        result = await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id,
                DailyChallenge.challenge_date == today,
            )
        )
        challenge = result.scalar_one_or_none()
        if not challenge:
            return BaseResponse(code=HTTP_NOT_FOUND, message="今日挑战未找到", data=None)
        if challenge.is_correct is not None:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="今日挑战已完成", data=None)

        # 获取题目资源
        resource = await session.get(Resource, challenge.resource_id)
        if not resource:
            return BaseResponse(code=HTTP_SERVER_ERROR, message="题目资源不存在", data=None)

        meta = resource.extra_metadata or {}
        parsed = _parse_single_question(resource.content, meta)
        question_text = parsed.get("questionText", "")
        kp = (resource.knowledge_points or [None])[0] if resource.knowledge_points else None

        is_correct, feedback = await _grade_daily_code(question_text, user_answer, meta)
        score = QUIZ_CORRECT_SCORE if is_correct else 0

        challenge.is_correct = is_correct
        challenge.user_answer = user_answer[:MAX_ANSWER_STORE_LENGTH]
        challenge.completed_at = datetime.now()

        # 更新火花
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )).scalar_one_or_none()
        if profile:
            await _update_streak(profile, today, is_correct)

        # 写入 QuizAttempt（复用自适应难度系统）
        try:
            attempt = QuizAttempt(
                user_id=user.id,
                resource_id=resource.id,
                question_index=0,
                question_type=DAILY_CHALLENGE_QUESTION_TYPE,
                difficulty=meta.get("difficulty", "medium"),
                knowledge_point=kp,
                user_answer=user_answer[:MAX_ANSWER_STORE_LENGTH],
                correct_answer=str(meta.get("answer", ""))[:MAX_ANSWER_STORE_LENGTH],
                is_correct=is_correct,
                score=score,
                spent_time=0,
            )
            session.add(attempt)
        except Exception as e:
            logger.warning(f"保存答题记录失败: {e}")

        await session.commit()

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "is_correct": is_correct,
            "correct_answer": str(meta.get("answer", "")),
            "explanation": str(meta.get("explanation", "")),
            "feedback": feedback,
            "streak": _streak_data(profile),
        })

    except Exception as e:
        logger.error(f"提交答案失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/streak", response_model=BaseResponse)
async def get_streak_info(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取火花(连续打卡)信息"""
    try:
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )).scalar_one_or_none()
        _refresh_streak_status(profile, _today_str())
        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data=_streak_data(profile))
    except Exception as e:
        logger.error(f"获取火花信息失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/hint", response_model=BaseResponse)
async def get_daily_hint(
    body: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取今日题目的分步提示（最多3次）"""
    try:
        today = _today_str()
        hint_index = body.get("hint_index", 0)

        if hint_index < 0 or hint_index > 2:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="提示索引无效", data=None)

        # 获取今日挑战
        result = await session.execute(
            select(DailyChallenge).where(
                DailyChallenge.user_id == user.id,
                DailyChallenge.challenge_date == today,
            )
        )
        challenge = result.scalar_one_or_none()
        if not challenge:
            return BaseResponse(code=HTTP_NOT_FOUND, message="今日挑战未找到", data=None)

        resource = await session.get(Resource, challenge.resource_id)
        if not resource:
            return BaseResponse(code=HTTP_SERVER_ERROR, message="题目资源不存在", data=None)

        meta = resource.extra_metadata or {}
        hint_text = _extract_hint(meta, hint_index)

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "hint": hint_text,
            "hint_index": hint_index,
            "remaining": 2 - hint_index,
        })

    except Exception as e:
        logger.error(f"获取提示失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.get("/next-challenge", response_model=BaseResponse)
async def get_next_challenge(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取下一道额外挑战题（每日一题完成后可继续练习）"""
    try:
        today = _today_str()
        profile = (await session.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        )).scalar_one_or_none()
        difficulty = _pick_difficulty(profile)

        used_resources = (await session.execute(
            select(Resource).where(
                Resource.user_id == user.id,
                Resource.resource_type.in_([RESOURCE_TYPE_DAILY_CHALLENGE, RESOURCE_TYPE_DAILY_EXTRA]),
                Resource.title.like(f"%{today}%"),
            )
        )).scalars().all()
        exclude_titles = _extract_used_question_titles(used_resources)
        knowledge_point, question = _pick_code_question(profile, difficulty, exclude_titles=exclude_titles)
        content, metadata = _question_to_resource_fields(question, knowledge_point, difficulty)

        db_resource = Resource(
            user_id=user.id,
            task_id=str(uuid.uuid4()),
            resource_type=RESOURCE_TYPE_DAILY_EXTRA,
            title=f"额外挑战 - {today} - {question['title']}",
            content=content,
            knowledge_points=[knowledge_point],
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            extra_metadata={**metadata, "is_extra_challenge": True},
        )
        session.add(db_resource)
        await session.commit()
        await session.refresh(db_resource)

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "challenge": _serialize_extra_challenge(db_resource),
        })

    except Exception as e:
        error_code, user_message = _classify_daily_generation_error(e)
        logger.error(f"[{error_code}] 获取额外挑战题失败: {e}", exc_info=True)
        return _daily_error_response(error_code, user_message, detail=str(e))


@router.post("/next-challenge/hint", response_model=BaseResponse)
async def get_next_challenge_hint(
    body: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """获取额外挑战题的分步提示（最多3次）"""
    try:
        resource_id = body.get("resource_id")
        hint_index = body.get("hint_index", 0)

        if not resource_id:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="缺少题目ID", data=None)
        if hint_index < 0 or hint_index > 2:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="提示索引无效", data=None)

        resource = await session.get(Resource, resource_id)
        if not resource or resource.user_id != user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message="题目未找到", data=None)

        meta = resource.extra_metadata or {}
        hint_text = _extract_hint(meta, hint_index)

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "hint": hint_text,
            "hint_index": hint_index,
            "remaining": 2 - hint_index,
        })

    except Exception as e:
        logger.error(f"获取额外挑战提示失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/next-challenge/submit", response_model=BaseResponse)
async def submit_next_challenge(
    body: dict,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """提交额外挑战题的答案"""
    try:
        user_answer = body.get("user_answer", "")
        resource_id = body.get("resource_id")
        if not user_answer.strip():
            return BaseResponse(code=HTTP_BAD_REQUEST, message="答案不能为空", data=None)
        if not resource_id:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="缺少题目ID", data=None)

        resource = await session.get(Resource, resource_id)
        if not resource or resource.user_id != user.id:
            return BaseResponse(code=HTTP_NOT_FOUND, message="题目未找到", data=None)

        meta = resource.extra_metadata or {}
        parsed = _parse_single_question(resource.content, meta)
        question_text = parsed.get("questionText", "")

        is_correct, feedback = await _grade_daily_code(question_text, user_answer, meta)

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "is_correct": is_correct,
            "correct_answer": str(meta.get("answer", "")),
            "explanation": str(meta.get("explanation", "")),
            "feedback": feedback,
        })

    except Exception as e:
        logger.error(f"提交额外挑战答案失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


async def _completion_stats(session: AsyncSession, challenge_date: str) -> dict:
    """获取今日题目完成统计"""
    total = (await session.execute(
        select(func.count()).select_from(DailyChallenge).where(
            DailyChallenge.challenge_date == challenge_date,
        )
    )).scalar() or 0
    completed = (await session.execute(
        select(func.count()).select_from(DailyChallenge).where(
            DailyChallenge.challenge_date == challenge_date,
            DailyChallenge.is_correct.isnot(None),
        )
    )).scalar() or 0
    correct = (await session.execute(
        select(func.count()).select_from(DailyChallenge).where(
            DailyChallenge.challenge_date == challenge_date,
            DailyChallenge.is_correct == True,
        )
    )).scalar() or 0
    return {
        "total_users": total,
        "completed_users": completed,
        "correct_users": correct,
        "correct_rate": round(correct / completed * 100, 1) if completed > 0 else 0,
    }
