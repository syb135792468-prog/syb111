"""
api/routes/quiz.py - 练习题专用接口（Phase 1.2 智能判分）
- GET  /api/quiz/{resource_id}                    获取题目
- POST /api/quiz/{resource_id}/submit             提交答案（智能判分）
- POST /api/quiz/{resource_id}/generate-answer    生成答案与解析
- POST /api/quiz/stats                            更新统计
"""
from __future__ import annotations

import re
import asyncio
from typing import Optional, AsyncGenerator
from datetime import datetime, UTC
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import BaseResponse
from models.database import AsyncSessionLocal
from models.resource import Resource
from models.quiz_attempt import QuizAttempt
from models.error_book import ErrorBook
from config.constants import (
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND, HTTP_SERVER_ERROR,
    QUIZ_CORRECT_SCORE, MAX_ANSWER_STORE_LENGTH, QUIZ_TYPE_CHOICE, QUIZ_TYPE_FILL,
    QUIZ_TYPE_MULTI, RESOURCE_TYPE_QUIZ,
    CODE_EXEC_DEFAULT_TIMEOUT, QUIZ_FILL_CORRECT_THRESHOLD,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_QUIZ_NOT_FOUND,
    MSG_NOT_QUIZ_RESOURCE,
)
from services.grading_service import (
    normalize_answer, grade_choice, grade_fill,
    compare_execution, classify_error, grade_code_with_llm,
)
from utils.logger import get_logger

router = APIRouter(prefix="/quiz", tags=["练习题"])
logger = get_logger(__name__, task_id="quiz_api")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ==================== 内容解析 ====================

def _parse_single_question(content, meta):
    """解析单题内容"""
    qtype = meta.get("quiz_type", QUIZ_TYPE_CHOICE)
    section = content
    m = re.search(r"##\s*题目[\s\S]*?\n([\s\S]*?)(?=\n##\s*答案|$)", content)
    if m:
        section = m.group(1).strip()

    options = []
    if qtype == QUIZ_TYPE_CHOICE:
        for line in section.split("\n"):
            line = line.strip()
            if re.match(r"^[A-D]\.\s", line):
                options.append(line)

    question_text = section
    if options:
        question_text = "\n".join(
            l for l in section.split("\n") if not re.match(r"^[A-D]\.\s", l.strip())
        ).strip()
    question_text = re.sub(r"^\(.*?\)\s*\n?", "", question_text).strip()

    return {
        "questionText": question_text,
        "options": options,
        "type": qtype,
        "answer": meta.get("answer", ""),
        "explanation": meta.get("explanation", ""),
    }


def _parse_multi_questions(content, meta):
    """解析多题内容"""
    questions = meta.get("questions", [])
    if not questions:
        return []

    sections = re.split(r"\n---\n+\s*##\s*第\s*\d+\s*题\s*\n?", content)
    if len(sections) > 1:
        sections = sections[1:]

    result = []
    for i, q_meta in enumerate(questions):
        section = sections[i].strip() if i < len(sections) else ""
        qtype = q_meta.get("quiz_type", QUIZ_TYPE_CHOICE)

        options = []
        if qtype == QUIZ_TYPE_CHOICE:
            for line in section.split("\n"):
                line = line.strip()
                if re.match(r"^[A-D]\.\s", line):
                    options.append(line)

        q_match = re.search(r"##\s*题目.*?\n([\s\S]*?)(?=\n##\s*答案|\n##\s*解析|$)", section)
        if q_match:
            question_text = q_match.group(1).strip()
        else:
            question_text = section

        if options:
            question_text = "\n".join(
                l for l in question_text.split("\n") if not re.match(r"^[A-D]\.\s", l.strip())
            ).strip()
        question_text = re.sub(r"^\(.*?\)\s*\n?", "", question_text).strip()

        result.append({
            "index": q_meta.get("index", i + 1),
            "questionText": question_text,
            "options": options,
            "type": qtype,
            "answer": q_meta.get("answer", ""),
            "explanation": q_meta.get("explanation", ""),
        })

    return result


def _get_question_meta(meta: dict, question_index: int) -> tuple[str, str, str, str]:
    """从 metadata 中提取指定题目的 quiz_type, answer, explanation, question_text"""
    if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
        questions = meta.get("questions", [])
        if question_index < len(questions):
            q = questions[question_index]
            return (
                q.get("quiz_type", QUIZ_TYPE_CHOICE),
                q.get("answer", ""),
                q.get("explanation", ""),
                "",  # question_text 从 content 解析
            )
    return (
        meta.get("quiz_type", QUIZ_TYPE_CHOICE),
        meta.get("answer", ""),
        meta.get("explanation", ""),
        "",
    )


# ==================== 路径节点同步 ====================

async def _sync_learning_path_nodes(user_id: int, knowledge_point: str, score: int):
    """测验结果同步到学习路径节点：更新掌握度/状态，刷新路径进度"""
    try:
        from models.learning_path import LearningPath
        from sqlalchemy.orm import selectinload
        from config.constants import LP_NODE_STATUS_COMPLETED

        async with AsyncSessionLocal() as sync_db:
            stmt = (
                select(LearningPath)
                .where(LearningPath.user_id == user_id, LearningPath.status == "active")
                .options(selectinload(LearningPath.nodes))
            )
            result = await sync_db.execute(stmt)
            paths = result.scalars().all()

            if not paths:
                return

            # 计算掌握度：score 范围 0-10（QUIZ_CORRECT_SCORE=10）
            accuracy = score / 10.0
            if accuracy >= 0.9:
                mastery = min(1.0, accuracy * 1.1)
            elif accuracy >= 0.7:
                mastery = accuracy
            elif accuracy >= 0.5:
                mastery = accuracy * 0.9
            else:
                mastery = accuracy * 0.8

            updated_any = False
            for path in paths:
                path_updated = False
                for node in (path.nodes or []):
                    if node.knowledge_point != knowledge_point:
                        continue
                    node.update_mastery(mastery)
                    path_updated = True

                if path_updated:
                    completed_count = sum(
                        1 for n in (path.nodes or [])
                        if n.status == LP_NODE_STATUS_COMPLETED
                    )
                    path.completed_nodes = completed_count
                    path.update_progress()
                    updated_any = True

            if updated_any:
                await sync_db.commit()
                logger.info(f"✅ 路径节点同步: user={user_id}, kp={knowledge_point}, mastery={mastery:.2f}")
    except Exception as e:
        logger.warning(f"⚠️ 路径节点同步失败: {e}")


# ==================== 接口 ====================

@router.get("/{resource_id}", response_model=BaseResponse)
async def get_quiz(resource_id: int, session: AsyncSession = Depends(get_db)):
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r or not r.is_active:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_QUIZ_NOT_FOUND, data=None)
        if r.resource_type != RESOURCE_TYPE_QUIZ:
            return BaseResponse(code=HTTP_BAD_REQUEST, message=MSG_NOT_QUIZ_RESOURCE, data=None)

        meta = r.extra_metadata or {}
        is_multi = meta.get("quiz_type") == QUIZ_TYPE_MULTI

        if is_multi:
            questions = _parse_multi_questions(r.content, meta)
            data = {
                "id": r.id,
                "title": r.title,
                "is_multi": True,
                "question_count": meta.get("question_count", len(questions)),
                "questions": questions,
            }
        else:
            q = _parse_single_question(r.content, meta)
            data = {
                "id": r.id,
                "title": r.title,
                "is_multi": False,
                "question_count": 1,
                "questions": [{
                    "index": 1,
                    **q,
                }],
            }

        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data=data)
    except Exception as e:
        logger.error(f"获取题目失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{resource_id}/submit", response_model=BaseResponse)
async def submit_quiz(resource_id: int, body: dict, session: AsyncSession = Depends(get_db)):
    """智能判分：选择题精确匹配，填空题模糊匹配，编程题LLM判分"""
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r or not r.is_active:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_QUIZ_NOT_FOUND, data=None)

        meta = r.extra_metadata or {}
        user_answer = body.get("user_answer", "")
        question_index = body.get("question_index", 0)
        spent_time = body.get("spent_time", 0)

        # 提取题目信息
        q_type, correct_answer, explanation, _ = _get_question_meta(meta, question_index)

        # 获取题目文本（用于 LLM 判分）
        if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
            parsed = _parse_multi_questions(r.content, meta)
            question_text = parsed[question_index]["questionText"] if question_index < len(parsed) else ""
        else:
            parsed = _parse_single_question(r.content, meta)
            question_text = parsed.get("questionText", "")

        # 根据题型选择判分策略
        is_correct = False
        score = 0
        feedback = ""

        if q_type == QUIZ_TYPE_CHOICE:
            is_correct = grade_choice(user_answer, correct_answer)
            score = QUIZ_CORRECT_SCORE if is_correct else 0

        elif q_type == QUIZ_TYPE_FILL:
            is_exact, score_ratio = grade_fill(user_answer, correct_answer)
            is_correct = is_exact or score_ratio >= QUIZ_FILL_CORRECT_THRESHOLD
            score = round(QUIZ_CORRECT_SCORE * score_ratio)
            if not is_correct and score_ratio > 0:
                feedback = f"部分正确（{int(score_ratio*100)}%），正确答案包含：{correct_answer}"

        elif q_type == QUIZ_TYPE_CODE:
            # 提取测试用例（如果元数据中定义了）
            test_cases = None
            if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
                q_list = meta.get("questions", [])
                if question_index < len(q_list):
                    test_cases = q_list[question_index].get("test_cases")
            else:
                test_cases = meta.get("test_cases")
            is_correct, feedback = await grade_code_with_llm(
                question_text, user_answer, correct_answer, explanation,
                test_cases=test_cases,
            )
            score = QUIZ_CORRECT_SCORE if is_correct else 0

        else:
            # 未知题型，退化为精确匹配
            is_correct = user_answer.strip() == correct_answer.strip()
            score = QUIZ_CORRECT_SCORE if is_correct else 0

        # 持久化答题记录
        try:
            kp = (r.knowledge_points or [None])[0] if r.knowledge_points else None
            difficulty_val = ""
            if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
                q_list = meta.get("questions", [])
                if question_index < len(q_list):
                    difficulty_val = q_list[question_index].get("difficulty", "")
            else:
                difficulty_val = meta.get("difficulty", "")

            attempt = QuizAttempt(
                user_id=r.user_id,
                resource_id=r.id,
                question_index=question_index,
                question_type=q_type,
                difficulty=difficulty_val,
                knowledge_point=kp,
                user_answer=user_answer[:MAX_ANSWER_STORE_LENGTH],
                correct_answer=correct_answer[:MAX_ANSWER_STORE_LENGTH],
                is_correct=is_correct,
                score=score,
                spent_time=spent_time,
            )
            session.add(attempt)
            await session.commit()
        except Exception as save_err:
            logger.warning(f"保存答题记录失败: {save_err}")

        # 答错时自动收录错题本（含间隔重复初始化）
        if not is_correct:
            try:
                from ai.spaced_repetition import get_next_review_time, INITIAL_INTERVAL_DAYS, DEFAULT_EASINESS_FACTOR

                existing = await session.execute(
                    select(ErrorBook).where(
                        ErrorBook.user_id == r.user_id,
                        ErrorBook.resource_id == r.id,
                        ErrorBook.question_index == question_index,
                    )
                )
                eb_item = existing.scalar_one_or_none()
                if eb_item:
                    eb_item.error_count += 1
                    eb_item.last_wrong_at = datetime.now(UTC).replace(tzinfo=None)
                    eb_item.user_answer = user_answer[:MAX_ANSWER_STORE_LENGTH]
                    # 再次答错 → 重置间隔重复状态，从头开始
                    eb_item.repetition_count = 0
                    eb_item.review_interval_days = INITIAL_INTERVAL_DAYS
                    next_at, _, _, _ = get_next_review_time(
                        quality=1,
                        repetition_count=0,
                        easiness_factor=eb_item.easiness_factor,
                        current_interval_days=INITIAL_INTERVAL_DAYS,
                    )
                    eb_item.next_review_at = next_at
                else:
                    kp = (r.knowledge_points or [None])[0] if r.knowledge_points else None
                    difficulty_val = ""
                    if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
                        q_list = meta.get("questions", [])
                        if question_index < len(q_list):
                            difficulty_val = q_list[question_index].get("difficulty", "")
                    else:
                        difficulty_val = meta.get("difficulty", "")
                    # 新错题：初始化间隔重复，1天后首次复习
                    next_at, _, _, _ = get_next_review_time(
                        quality=1,
                        repetition_count=0,
                        easiness_factor=DEFAULT_EASINESS_FACTOR,
                        current_interval_days=INITIAL_INTERVAL_DAYS,
                    )
                    eb_item = ErrorBook(
                        user_id=r.user_id,
                        resource_id=r.id,
                        question_index=question_index,
                        question_text=question_text[:MAX_ANSWER_STORE_LENGTH],
                        question_type=q_type,
                        user_answer=user_answer[:MAX_ANSWER_STORE_LENGTH],
                        correct_answer=correct_answer[:MAX_ANSWER_STORE_LENGTH],
                        explanation=explanation[:MAX_ANSWER_STORE_LENGTH],
                        knowledge_point=kp,
                        difficulty=difficulty_val,
                        next_review_at=next_at,
                        review_interval_days=INITIAL_INTERVAL_DAYS,
                        easiness_factor=DEFAULT_EASINESS_FACTOR,
                        repetition_count=0,
                    )
                    session.add(eb_item)
                await session.commit()
            except Exception as eb_err:
                logger.warning(f"错题本收录失败: {eb_err}")

        # 后台异步：更新实时学习状态 + 用户画像
        kp = (r.knowledge_points or [None])[0] if r.knowledge_points else None

        # 实时学习状态更新（同步，轻量级）
        session_id = body.get("session_id", "")
        if session_id:
            try:
                from utils.behavior_tracker import behavior_tracker
                await behavior_tracker.log_quiz_answer(
                    user_id=r.user_id,
                    session_id=session_id,
                    is_correct=is_correct,
                    response_time_ms=spent_time * 1000,
                    knowledge_point=kp,
                    resource_id=r.id,
                )
            except Exception as bt_err:
                logger.warning(f"实时状态更新失败: {bt_err}")

        if kp:
            async def _update_profile_from_quiz():
                try:
                    async with AsyncSessionLocal() as bg_db:
                        from models.profile import UserProfile
                        from utils.api_helpers import get_current_utc_time
                        from utils.knowledge_base import normalize_to_backend

                        std_kp = normalize_to_backend(kp) or kp
                        result = await bg_db.execute(
                            select(UserProfile).where(UserProfile.user_id == r.user_id)
                        )
                        profile = result.scalar_one_or_none()
                        if not profile:
                            return

                        mastered = list(profile.mastered_points or [])
                        weak = list(profile.weak_points or [])

                        if score >= 80 and std_kp not in mastered:
                            mastered.append(std_kp)
                            if std_kp in weak:
                                weak.remove(std_kp)
                        elif score < 40 and std_kp not in weak and std_kp not in mastered:
                            weak.append(std_kp)

                        profile.mastered_points = mastered
                        profile.weak_points = weak
                        profile.updated_at = get_current_utc_time()
                        await bg_db.commit()
                        logger.info(f"✅ 测验画像更新: topic={std_kp}, score={score}, mastered={mastered}, weak={weak}")

                        # 闭环：同步路径节点状态
                        await _sync_learning_path_nodes(r.user_id, std_kp, score)
                except Exception as e:
                    logger.warning(f"⚠️ 测验画像更新失败: {e}")

            asyncio.create_task(_update_profile_from_quiz())

        return BaseResponse(
            code=HTTP_OK, message=MSG_SUCCESS,
            data={
                "is_correct": is_correct,
                "correct_answer": correct_answer,
                "explanation": explanation,
                "score": score,
                "spent_time": spent_time,
                "feedback": feedback,
            },
        )
    except Exception as e:
        logger.error(f"提交答案失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/{resource_id}/generate-answer", response_model=BaseResponse)
async def generate_answer(resource_id: int, body: dict = None, session: AsyncSession = Depends(get_db)):
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r or not r.is_active:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_QUIZ_NOT_FOUND, data=None)

        meta = r.extra_metadata or {}
        question_index = (body or {}).get("question_index", 0)

        if meta.get("quiz_type") == QUIZ_TYPE_MULTI:
            questions = meta.get("questions", [])
            if question_index < len(questions):
                q = questions[question_index]
                return BaseResponse(
                    code=HTTP_OK, message=MSG_SUCCESS,
                    data={"correct_answer": q.get("answer", ""), "explanation": q.get("explanation", "")},
                )
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_QUIZ_NOT_FOUND, data=None)
        else:
            return BaseResponse(
                code=HTTP_OK, message=MSG_SUCCESS,
                data={"correct_answer": meta.get("answer", ""), "explanation": meta.get("explanation", "")},
            )
    except Exception as e:
        logger.error(f"生成答案失败: {e}", exc_info=True)
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None)


@router.post("/stats", response_model=BaseResponse)
async def update_stats(body: dict):
    return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data=None)
