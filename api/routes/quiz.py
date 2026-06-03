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
    CODE_EXEC_DEFAULT_TIMEOUT, LLM_GRADING_TIMEOUT_SEC,
    QUIZ_OUTPUT_TRUNCATE_LENGTH, QUIZ_ERROR_TRUNCATE_LENGTH,
    QUIZ_LLM_FEEDBACK_MAX_CHARS, QUIZ_FILL_CORRECT_THRESHOLD,
    QUIZ_PARTIAL_MATCH_MIN_RATIO, QUIZ_PARTIAL_MATCH_MAX_RATIO,
    QUIZ_PARTIAL_MATCH_SCORE,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_QUIZ_NOT_FOUND,
    MSG_NOT_QUIZ_RESOURCE,
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


# ==================== 智能判分 ====================

def _normalize_answer(text: str) -> str:
    """标准化答案文本：去除首尾空白、多余空格、统一大小写"""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def _grade_choice(user_answer: str, correct_answer: str) -> bool:
    """选择题判分：忽略大小写和空白"""
    return user_answer.strip().upper() == correct_answer.strip().upper()


def _grade_fill(user_answer: str, correct_answer: str) -> tuple[bool, float]:
    """
    填空题智能判分：
    1. 完全匹配（标准化后）
    2. 多答案支持（| 分隔，任意一个正确即对）
    3. 忽略首尾空白和多余空格
    4. 部分匹配（用户答案包含在正确答案中，或反之）
    返回 (is_exact_correct, score_percent)
    """
    user_norm = _normalize_answer(user_answer)
    correct_norm = _normalize_answer(correct_answer)

    if not user_norm:
        return False, 0.0

    # 多答案支持：用 | 或 ；或 ; 分隔
    correct_variants = re.split(r"[|；;]", correct_norm)
    correct_variants = [v.strip() for v in correct_variants if v.strip()]

    # 完全匹配（任一变体）
    for variant in correct_variants:
        if user_norm == variant:
            return True, 1.0
        # 忽引号匹配
        if user_norm.strip('"\'`') == variant.strip('"\'`'):
            return True, 1.0

    # 大小写不敏感匹配
    for variant in correct_variants:
        if user_norm.lower() == variant.lower():
            return True, 1.0

    # 部分匹配：用户答案是正确答案的子串（宽松模式，给部分分）
    for variant in correct_variants:
        if user_norm.lower() in variant.lower() or variant.lower() in user_norm.lower():
            # 长度差异太大不算
            if len(user_norm) >= len(variant) * QUIZ_PARTIAL_MATCH_MIN_RATIO and len(user_norm) <= len(variant) * QUIZ_PARTIAL_MATCH_MAX_RATIO:
                return False, QUIZ_PARTIAL_MATCH_SCORE

    return False, 0.0


async def _compare_execution(user_code: str, ref_code: str, timeout: int = CODE_EXEC_DEFAULT_TIMEOUT) -> dict:
    """
    对比执行：同时运行用户代码和参考答案，比较输出
    返回 {"match": bool, "user_stdout": str, "ref_stdout": str, "user_stderr": str}
    """
    from utils.code_executor import execute_python_code
    try:
        user_task = execute_python_code(user_code, timeout=timeout)
        ref_task = execute_python_code(ref_code, timeout=timeout)
        user_result, ref_result = await asyncio.gather(user_task, ref_task)
        user_out = user_result.get("stdout", "").strip()
        ref_out = ref_result.get("stdout", "").strip()
        return {
            "match": user_out == ref_out and user_result.get("success", False),
            "user_stdout": user_out,
            "ref_stdout": ref_out,
            "user_stderr": user_result.get("stderr", ""),
            "user_success": user_result.get("success", False),
            "ref_success": ref_result.get("success", False),
        }
    except Exception as e:
        return {"match": False, "error": str(e)}


def _classify_error(syntax_ok: bool, exec_result: dict, compare_result: dict) -> str:
    """错误类型分类"""
    if not syntax_ok:
        return "syntax_error"
    if exec_result.get("timed_out"):
        return "timeout"
    if not exec_result.get("success"):
        return "runtime_error"
    if not compare_result.get("match"):
        return "logic_error"
    return "correct"


async def _grade_code_with_llm(
    question_text: str, user_code: str, correct_answer: str, explanation: str,
    test_cases: list[dict] | None = None,
) -> tuple[bool, str]:
    """
    编程题判分（增强版）：
    1. 语法检查（快速失败）
    2. 对比执行：同时运行用户代码和参考答案，输出一致直接判对
    3. LLM 逻辑等价判断（对比执行无法确定时的兜底）
    返回 (is_correct, feedback)
    """
    # Step 1: 语法检查（快速失败）
    syntax_ok = True
    try:
        compile(user_code, "<user_code>", "exec")
    except SyntaxError as e:
        syntax_ok = False
        return False, f"[语法错误] 第{e.lineno}行：{e.msg}"

    # Step 1.5: 测试用例驱动判分（如果元数据中定义了测试用例）
    if test_cases:
        from utils.code_executor import execute_python_code
        passed = 0
        total = len(test_cases)
        case_results = []
        for i, tc in enumerate(test_cases[:5]):  # 最多运行5个测试用例
            tc_input = tc.get("input", "")
            tc_expected = tc.get("output", "")
            # 构造包装代码：运行用户函数，用测试输入调用
            wrapper = f"{user_code}\n\n# 测试用例执行\ntry:\n    result = {tc_input}\n    print(result)\nexcept Exception as e:\n    print(f'ERROR: {{e}}')"
            tc_result = await execute_python_code(wrapper, timeout=CODE_EXEC_DEFAULT_TIMEOUT)
            tc_output = tc_result.get("stdout", "").strip()
            if tc_output == tc_expected.strip():
                passed += 1
            case_results.append(f"用例{i+1}: {'✓' if tc_output == tc_expected.strip() else '✗'}")
        if passed == total:
            return True, f"[测试用例] 全部通过 ({passed}/{total})"
        elif passed > 0:
            return False, f"[测试用例] 部分通过 ({passed}/{total}): {'; '.join(case_results)}"
        else:
            return False, f"[测试用例] 全部失败 (0/{total}): {'; '.join(case_results)}"

    # Step 2: 对比执行（优先快速判分，跳过 LLM 调用）
    exec_result = {}
    compare_result = {}
    try:
        from utils.code_executor import execute_python_code
        exec_result = await execute_python_code(user_code, timeout=CODE_EXEC_DEFAULT_TIMEOUT)

        # 如果参考答案包含可执行代码，尝试对比执行
        if correct_answer and ("print(" in correct_answer or "def " in correct_answer or "=" in correct_answer):
            compare_result = await _compare_execution(user_code, correct_answer)
            if compare_result.get("match"):
                return True, "[对比执行] 输出与参考答案一致"
    except Exception as e:
        logger.debug(f"对比执行异常（不影响流程）: {e}")

    # 错误类型分类
    error_type = _classify_error(syntax_ok, exec_result, compare_result)
    if error_type == "timeout":
        return False, "[超时] 代码执行超时，请检查是否有死循环"
    if error_type == "runtime_error":
        stderr = exec_result.get("stderr", "")[:QUIZ_OUTPUT_TRUNCATE_LENGTH]
        return False, f"[运行错误] {stderr}"

    # Step 3: LLM 逻辑等价判断（兜底）
    try:
        from agents.quiz_agent import QuizAgent
        agent = QuizAgent(use_llm=True)

        exec_feedback = ""
        if exec_result.get("timed_out"):
            exec_feedback = "代码执行超时"
        elif not exec_result.get("success"):
            exec_feedback = f"运行错误：{exec_result.get('stderr', '')[:QUIZ_OUTPUT_TRUNCATE_LENGTH]}"
        else:
            stdout = exec_result.get("stdout", "")
            exec_feedback = f"运行输出：{stdout[:QUIZ_OUTPUT_TRUNCATE_LENGTH]}" if stdout else "运行成功（无输出）"

        compare_feedback = ""
        if compare_result.get("user_stdout") is not None:
            compare_feedback = f"\n## 输出对比\n用户输出：{compare_result['user_stdout'][:200]}\n参考输出：{compare_result.get('ref_stdout', 'N/A')[:200]}"

        prompt = f"""请判断以下Python编程题的用户答案是否正确。

## 题目
{question_text}

## 参考答案
{correct_answer}

## 参考解析
{explanation}

## 用户代码
```python
{user_code}
```

## 代码执行结果
{exec_feedback}{compare_feedback}

## 评分标准
请严格按以下标准判断：
1. 代码逻辑正确且能实现题目要求 → 正确
2. 代码逻辑正确但写法不同（如变量名、循环方式不同）→ 正确
3. 代码逻辑基本正确，只有小瑕疵（如缺少边界处理但核心逻辑对）→ 正确
4. 代码逻辑有明显错误或运行出错 → 不正确
5. 输出结果与参考答案一致 → 正确

请返回JSON格式：
{{"is_correct": true/false, "feedback": "简短评价（{QUIZ_LLM_FEEDBACK_MAX_CHARS}字内）"}}
只返回JSON，不要其他内容。"""

        result = await asyncio.wait_for(
            agent.llm.achat(prompt),
            timeout=LLM_GRADING_TIMEOUT_SEC,
        )

        json_match = re.search(r'\{[^}]+\}', result)
        if json_match:
            import json
            data = json.loads(json_match.group())
            fb = data.get("feedback", "判分完成")
            # 在 feedback 前加上错误类型标签
            if not data.get("is_correct", False) and error_type == "logic_error":
                fb = f"[逻辑错误] {fb}"
            return data.get("is_correct", False), fb
        return False, "LLM判分结果解析失败，建议手动检查"

    except asyncio.TimeoutError:
        return False, "LLM判分超时，建议手动检查代码"
    except Exception as e:
        logger.error(f"LLM判分异常: {e}")
        return False, f"LLM判分异常：{str(e)}"


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
            is_correct = _grade_choice(user_answer, correct_answer)
            score = QUIZ_CORRECT_SCORE if is_correct else 0

        elif q_type == QUIZ_TYPE_FILL:
            is_exact, score_ratio = _grade_fill(user_answer, correct_answer)
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
            is_correct, feedback = await _grade_code_with_llm(
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
