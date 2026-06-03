"""
agents/socratic_workflow.py - 苏格拉底导学工作流 2.0
动态决策引擎架构：teaching_decision_engine 根据用户表现实时选择教学动作
"""
from __future__ import annotations

import json
import random
import re
from datetime import datetime
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt, Command

from agents.socratic_state import SocraticState
from ai.learning_state import LearningState
from ai.real_time_adaptation import real_time_adaptation_engine
from ai.prompts.socratic_prompts import (
    PROBLEM_ANALYSIS_PROMPT, TEACHING_DECISION_PROMPT,
    EVALUATE_AND_DECIDE_PROMPT,
    QUESTION_GENERATION_PROMPT, QUESTION_STAGES, LEVEL_GUIDES, DIFFICULTY_DESC,
    ANSWER_EVALUATION_PROMPT, HINT_GENERATION_PROMPT,
    CONCEPT_EXPLANATION_PROMPT, CODE_DEMO_PROMPT, CODE_DEMO_EXPLAIN_PROMPT,
    PRACTICE_EXERCISE_PROMPT, SUMMARY_PROMPT, LEARNING_STATE_GUIDES,
)
from utils.llm_client import get_async_llm_client
from utils.logger import get_logger

logger = get_logger(__name__, task_id="socratic_workflow")


# ============================================================
# JSON 解析工具
# ============================================================
def _parse_json_response(text: str) -> dict:
    """健壮的 JSON 解析，处理 LLM 输出的常见问题"""
    if not text:
        return {}
    match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
    if match:
        text = match.group(1)
    text = text.strip()
    text = re.sub(r',\s*([}\]])', r'\1', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    return {}


# ============================================================
# 共享辅助函数
# ============================================================
def _build_qa_context(state: SocraticState) -> str:
    """构建最近对话上下文摘要"""
    user_answers = state.get("user_answers", [])
    recent_qa = user_answers[-3:] if user_answers else []
    if not recent_qa:
        return ""
    lines = []
    for qa in recent_qa:
        status = "正确" if qa.get("correct") else "错误"
        lines.append(f"- [{status}] {qa.get('question', '')[:50]} → {qa.get('answer', '')[:50]}")
    return "最近对话（参考上下文）：\n" + "\n".join(lines)


def _handle_user_response(state: SocraticState, new_asked: list, new_chat_history: list,
                          content_label: str) -> dict:
    """处理 interrupt 恢复后的用户回复（所有动作节点共享）"""
    user_answer = interrupt({
        "type": state.get("next_action", "question"),
        "content": content_label,
        "stage": state.get("current_stage", ""),
        "difficulty": state.get("difficulty", 3),
        "hint_level": state.get("hint_level", 1),
        "consecutive_errors": state.get("consecutive_errors", 0),
        "consecutive_correct": state.get("consecutive_correct", 0),
        "learning_state": state.get("learning_state", "normal"),
        "user_ability": state.get("user_ability", 0.0),
    })

    if user_answer == "__HINT__":
        return {
            "asked_questions": new_asked,
            "chat_history": new_chat_history,
            "need_hint": True,
            "conversation_ended": False,
        }

    if user_answer == "__CONFUSED__":
        return {
            "asked_questions": new_asked,
            "chat_history": new_chat_history,
            "need_hint": False,
            "need_rephrase": True,
            "conversation_ended": False,
        }

    if user_answer == "__END__":
        return {
            "asked_questions": new_asked,
            "chat_history": new_chat_history,
            "conversation_ended": True,
            "need_hint": False,
        }

    if user_answer == "__GIVE_UP__":
        return {
            "asked_questions": new_asked,
            "chat_history": new_chat_history,
            "conversation_ended": True,
            "need_hint": False,
        }

    # 普通回答
    new_chat_history = new_chat_history + [
        {"role": "user", "content": user_answer}
    ]
    return {
        "asked_questions": new_asked,
        "chat_history": new_chat_history,
        "need_hint": False,
        "conversation_ended": False,
    }


def _update_learning_state(state: SocraticState, is_correct: bool) -> str:
    """更新实时学习状态，返回 learning_state value"""
    session_id = state.get("session_id", "")
    user_id_int = 0
    try:
        user_id_int = int(state.get("user_id", 0))
    except (ValueError, TypeError):
        pass
    if session_id and user_id_int:
        ls = real_time_adaptation_engine.update_state_with_answer(
            user_id_int, session_id, is_correct=is_correct, response_time_ms=5000,
        )
        return ls.value
    return state.get("learning_state", "normal")


# ============================================================
# 节点 1: analyze_problem
# ============================================================
async def analyze_problem(state: SocraticState) -> dict:
    """分析用户问题，提取知识点，初始化教学状态"""
    llm = get_async_llm_client()
    query = state.get("original_query", "")

    try:
        response = await llm.call(
            messages=[
                {"role": "system", "content": PROBLEM_ANALYSIS_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.1, max_tokens=256,
        )
        analysis = _parse_json_response(response)
    except Exception as e:
        logger.warning(f"analyze_problem LLM 失败: {e}")
        analysis = {}

    knowledge_points = analysis.get("knowledge_points", [query])
    if not knowledge_points:
        knowledge_points = [query]

    # 标准化知识点名称（映射到 15 个标准名称）
    from utils.knowledge_base import normalize_to_backend
    knowledge_points = [normalize_to_backend(kp) or kp for kp in knowledge_points]
    # 去重
    knowledge_points = list(dict.fromkeys(knowledge_points))

    mastery_level = {kp: 0.0 for kp in knowledge_points}

    # IRT 自适应
    user_ability = 0.0
    ability_se = 1.0
    initial_difficulty = analysis.get("difficulty", 2)
    try:
        from models.database import AsyncSessionLocal
        from ai.adaptive_difficulty import AdaptiveDifficultyEngine
        uid = state.get("user_id")
        if uid and str(uid).isdigit():
            async with AsyncSessionLocal() as db:
                engine = AdaptiveDifficultyEngine(db)
                abilities = []
                for kp in knowledge_points:
                    a, se = await engine.estimate_user_ability(int(uid), kp)
                    abilities.append(a)
                if abilities:
                    user_ability = sum(abilities) / len(abilities)
                    ability_se = se
                    if user_ability < -0.5:
                        initial_difficulty = max(initial_difficulty - 1, 1)
                    elif user_ability > 0.5:
                        initial_difficulty = min(initial_difficulty + 1, 5)
                    logger.info(f"IRT 能力估计: ability={user_ability:.3f}, difficulty→{initial_difficulty}")
    except Exception as e:
        logger.debug(f"IRT 估计跳过: {e}")

    # 实时学习状态
    session_id = state.get("session_id", "")
    user_id_int = 0
    try:
        user_id_int = int(state.get("user_id", 0))
    except (ValueError, TypeError):
        pass
    learning_state = LearningState.NORMAL.value
    if session_id and user_id_int:
        ls = real_time_adaptation_engine.get_or_create_state(user_id_int, session_id)
        learning_state = ls.current_state.value

    return {
        "knowledge_points": knowledge_points,
        "difficulty": initial_difficulty,
        "current_stage": f"{query}-开始",
        "mastery_level": mastery_level,
        "asked_questions": [],
        "user_answers": [],
        "hints_given": [],
        "consecutive_errors": 0,
        "hint_count": 0,
        "consecutive_correct": 0,
        "error_book_entries": [],
        "hint_level": 1,
        "need_hint": False,
        "conversation_ended": False,
        "user_ability": user_ability,
        "ability_se": ability_se,
        "learning_state": learning_state,
        "recent_actions": [],
        "user_misconceptions": [],
        "covered_points": [],
        "pending_points": list(knowledge_points),
    }


# ============================================================
# 节点 2: teaching_decision_engine（核心决策）
# ============================================================
async def teaching_decision_engine(state: SocraticState) -> dict:
    """教学决策引擎：根据当前教学上下文决定下一步动作"""
    llm = get_async_llm_client()

    learning_state = state.get("learning_state", "normal")
    state_guide = LEARNING_STATE_GUIDES.get(learning_state, "")

    misconceptions = state.get("user_misconceptions", [])
    misconceptions_str = json.dumps(misconceptions, ensure_ascii=False) if misconceptions else "无"

    recent_actions = state.get("recent_actions", [])
    recent_str = json.dumps(recent_actions[-5:], ensure_ascii=False) if recent_actions else "无"

    prompt = TEACHING_DECISION_PROMPT.format(
        learning_state_guide=f"学习状态指导：{state_guide}" if state_guide else "",
        topic=state.get("original_query", ""),
        knowledge_points=state.get("knowledge_points", []),
        pending_points=state.get("pending_points", []),
        covered_points=state.get("covered_points", []),
        mastery_level=state.get("mastery_level", {}),
        consecutive_errors=state.get("consecutive_errors", 0),
        consecutive_correct=state.get("consecutive_correct", 0),
        misconceptions=misconceptions_str,
        recent_actions=recent_str,
    )

    try:
        response = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3, max_tokens=128,
        )
        decision = _parse_json_response(response)
    except Exception as e:
        logger.warning(f"teaching_decision LLM 失败: {e}")
        decision = {}

    action = decision.get("action", "ask_question")
    reason = decision.get("reason", "")
    target = decision.get("target", state.get("pending_points", [""])[0] if state.get("pending_points") else "")

    # 验证 action 合法性
    valid_actions = {"ask_question", "explain_concept", "code_demo", "practice_exercise",
                     "rephrase_question", "relate_knowledge", "summarize"}
    if action not in valid_actions:
        action = "ask_question"

    # 安全检查：如果所有知识点都已覆盖且掌握度高，强制 summarize
    pending = state.get("pending_points", [])
    mastery = state.get("mastery_level", {})
    if not pending and all(v >= 0.7 for v in mastery.values()):
        action = "summarize"

    # 新会话第一轮必须先教后问（explain_concept 包含讲解+引导问题）
    user_answers = state.get("user_answers", [])
    if not user_answers:
        action = "explain_concept"

    logger.info(f"🎯 教学决策 | action={action} | reason={reason[:50]} | target={target} | user_answers={len(user_answers)}")

    # 更新 recent_actions
    new_recent = recent_actions + [{
        "action": action, "target": target, "reason": reason,
        "ts": datetime.now().isoformat(),
    }]

    return {
        "next_action": action,
        "action_reason": reason,
        "action_target": target,
        "current_stage": f"{state.get('original_query', '')}-{action}",
        "recent_actions": new_recent,
    }


# ============================================================
# 节点 3: ask_question
# ============================================================
async def ask_question(state: SocraticState) -> dict:
    """生成引导问题，暂停等待用户回答"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    knowledge_level = state.get("profile_data", {}).get("knowledge_level", "beginner")
    mastery = state.get("mastery_level", {})
    topic = state.get("original_query", "")
    asked = state.get("asked_questions", [])
    difficulty = state.get("difficulty", 3)
    learning_state = state.get("learning_state", "normal")

    stage_guide = QUESTION_STAGES.get("ask_question", "")
    level_desc = LEVEL_GUIDES.get(knowledge_level, LEVEL_GUIDES["beginner"])
    diff_desc = DIFFICULTY_DESC.get(difficulty, DIFFICULTY_DESC[3])
    weak_points = [kp for kp, score in mastery.items() if score < 0.5]
    state_hint = LEARNING_STATE_GUIDES.get(learning_state, "")

    prompt = QUESTION_GENERATION_PROMPT.format(
        action_context=f"目标知识点：{target}\n{stage_guide}",
        knowledge_points=state.get("knowledge_points", []),
        topic=topic,
        asked=asked,
        knowledge_level=knowledge_level,
        level_desc=level_desc,
        mastery=mastery,
        difficulty=difficulty,
        diff_desc=diff_desc,
        qa_context=_build_qa_context(state),
        weak_hint=f"用户薄弱点：{weak_points}，可适当引导巩固" if weak_points else "",
        state_hint=f"实时学习状态：{state_hint}" if state_hint else "",
    )

    try:
        question = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7, max_tokens=128,
        )
        question = question.strip()
    except Exception as e:
        logger.warning(f"ask_question LLM 失败: {e}")
        question = f"你能解释一下 {topic} 是什么吗？"

    new_asked = asked + [question]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": question}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, question)


# ============================================================
# 节点 4: rephrase_question
# ============================================================
async def rephrase_question(state: SocraticState) -> dict:
    """换角度重新提问"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    knowledge_level = state.get("profile_data", {}).get("knowledge_level", "beginner")
    mastery = state.get("mastery_level", {})
    topic = state.get("original_query", "")
    asked = state.get("asked_questions", [])
    difficulty = state.get("difficulty", 3)

    stage_guide = QUESTION_STAGES.get("rephrase_question", "")
    level_desc = LEVEL_GUIDES.get(knowledge_level, LEVEL_GUIDES["beginner"])
    diff_desc = DIFFICULTY_DESC.get(difficulty, DIFFICULTY_DESC[3])

    prompt = QUESTION_GENERATION_PROMPT.format(
        action_context=f"目标知识点：{target}\n{stage_guide}",
        knowledge_points=state.get("knowledge_points", []),
        topic=topic,
        asked=asked,
        knowledge_level=knowledge_level,
        level_desc=level_desc,
        mastery=mastery,
        difficulty=difficulty,
        diff_desc=diff_desc,
        qa_context=_build_qa_context(state),
        weak_hint="",
        state_hint="",
    )

    try:
        question = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8, max_tokens=128,
        )
        question = question.strip()
    except Exception as e:
        logger.warning(f"rephrase_question LLM 失败: {e}")
        question = f"让我换个方式问你：关于 {target}，你能举一个生活中的例子吗？"

    new_asked = asked + [question]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": question}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, question)


# ============================================================
# 节点 5: relate_knowledge
# ============================================================
async def relate_knowledge(state: SocraticState) -> dict:
    """关联已学知识点"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    covered = state.get("covered_points", [])
    topic = state.get("original_query", "")
    asked = state.get("asked_questions", [])

    stage_guide = QUESTION_STAGES.get("relate_knowledge", "")
    knowledge_level = state.get("profile_data", {}).get("knowledge_level", "beginner")
    level_desc = LEVEL_GUIDES.get(knowledge_level, LEVEL_GUIDES["beginner"])

    prompt = QUESTION_GENERATION_PROMPT.format(
        action_context=f"目标知识点：{target}\n已学知识点：{covered}\n{stage_guide}",
        knowledge_points=state.get("knowledge_points", []),
        topic=topic,
        asked=asked,
        knowledge_level=knowledge_level,
        level_desc=level_desc,
        mastery=state.get("mastery_level", {}),
        difficulty=state.get("difficulty", 3),
        diff_desc=DIFFICULTY_DESC.get(state.get("difficulty", 3), ""),
        qa_context=_build_qa_context(state),
        weak_hint="",
        state_hint="",
    )

    try:
        question = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7, max_tokens=128,
        )
        question = question.strip()
    except Exception as e:
        logger.warning(f"relate_knowledge LLM 失败: {e}")
        question = f"{target} 和你之前学的 {covered[0] if covered else '内容'} 有什么关系？"

    new_asked = asked + [question]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": question}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, question)


# ============================================================
# 节点 6: explain_concept
# ============================================================
async def explain_concept(state: SocraticState) -> dict:
    """讲解概念，暂停等待用户确认"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    topic = state.get("original_query", "")
    mastery = state.get("mastery_level", {})
    learning_state = state.get("learning_state", "normal")
    misconceptions = state.get("user_misconceptions", [])

    state_guide = LEARNING_STATE_GUIDES.get(learning_state, "")
    misconception_guide = ""
    if misconceptions:
        recent = misconceptions[-2:]
        misconception_guide = "用户存在以下误解，请在讲解中纠正：\n" + "\n".join(
            [f"- {m['point']}: {m['misconception']}" for m in recent]
        )

    prompt = CONCEPT_EXPLANATION_PROMPT.format(
        topic=topic,
        target=target,
        mastery=mastery,
        consecutive_errors=state.get("consecutive_errors", 0),
        learning_state_guide=f"学习状态：{state_guide}" if state_guide else "",
        misconception_guide=misconception_guide,
    )

    try:
        explanation = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3, max_tokens=256,
        )
        explanation = (explanation or "").strip()
    except Exception as e:
        logger.warning(f"explain_concept LLM 失败: {e}")
        explanation = f"{target} 是 Python 中的一个重要概念。让我用一个简单的类比来解释：它就像生活中的一个工具箱，帮你高效地完成特定任务。你知道它在代码中怎么使用吗？"

    new_asked = state.get("asked_questions", []) + [explanation]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": explanation}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, explanation)


# ============================================================
# 节点 7: code_demo
# ============================================================
async def code_demo(state: SocraticState) -> dict:
    """生成代码演示，执行并展示结果"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    topic = state.get("original_query", "")
    knowledge_level = state.get("profile_data", {}).get("knowledge_level", "beginner")
    misconceptions = state.get("user_misconceptions", [])

    misconception_guide = ""
    if misconceptions:
        recent = misconceptions[-1:]
        misconception_guide = "用户误解：" + "; ".join([f"{m['point']}: {m['misconception']}" for m in recent])

    # 生成代码
    prompt = CODE_DEMO_PROMPT.format(
        target=target,
        topic=topic,
        knowledge_level=knowledge_level,
        misconception_guide=misconception_guide,
    )

    try:
        code = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.2, max_tokens=128,
        )
        code = code.strip()
        # 清理 markdown 代码块
        code = re.sub(r'^```(?:python)?\s*', '', code)
        code = re.sub(r'\s*```$', '', code)
        code = code.strip()
    except Exception as e:
        logger.warning(f"code_demo 代码生成失败: {e}")
        code = f"print('Hello, {target}!')"

    # 执行代码
    output = ""
    try:
        from utils.code_executor import execute_python_code
        result = await execute_python_code(code, timeout=10)
        if result.get("success"):
            output = result.get("stdout", "").strip()
        else:
            output = result.get("stderr", result.get("error", "执行失败")).strip()
    except Exception as e:
        logger.warning(f"code_demo 执行失败: {e}")
        output = f"(代码执行服务不可用: {e})"

    # 生成解释
    explain_prompt = CODE_DEMO_EXPLAIN_PROMPT.format(
        code=code, output=output, target=target,
    )
    try:
        explanation = await llm.call(
            messages=[{"role": "system", "content": explain_prompt}],
            temperature=0.3, max_tokens=128,
        )
        explanation = explanation.strip()
    except Exception as e:
        logger.warning(f"code_demo 解释生成失败: {e}")
        explanation = f"以上代码演示了 {target} 的用法。"

    # 组合响应：代码 + 输出 + 解释
    full_response = f"**代码演示：{target}**\n\n```python\n{code}\n```\n\n**运行结果：**\n```\n{output}\n```\n\n{explanation}"

    new_asked = state.get("asked_questions", []) + [full_response]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": full_response}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, full_response)


# ============================================================
# 节点 8: practice_exercise
# ============================================================
async def practice_exercise(state: SocraticState) -> dict:
    """生成巩固练习题"""
    llm = get_async_llm_client()
    target = state.get("action_target", "")
    mastery = state.get("mastery_level", {})
    knowledge_level = state.get("profile_data", {}).get("knowledge_level", "beginner")
    difficulty = state.get("difficulty", 3)

    prompt = PRACTICE_EXERCISE_PROMPT.format(
        target=target,
        mastery=mastery,
        knowledge_level=knowledge_level,
        difficulty=difficulty,
    )

    try:
        question = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7, max_tokens=128,
        )
        question = question.strip()
    except Exception as e:
        logger.warning(f"practice_exercise LLM 失败: {e}")
        question = f"请用 {target} 写一个简单的例子。"

    question = f"**巩固练习：** {question}"
    new_asked = state.get("asked_questions", []) + [question]
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": question}
    ]

    return _handle_user_response(state, new_asked, new_chat_history, question)


# ============================================================
# 节点 9: evaluate_answer（保留用于 hint 流程）
# ============================================================
async def evaluate_answer(state: SocraticState) -> dict:
    """评估用户回答（仅用于 hint 流程的轻量评估）"""
    llm = get_async_llm_client()

    asked = state.get("asked_questions", [])
    chat_history = state.get("chat_history", [])

    if not asked:
        return {"current_response": "没有待评估的问题。", "current_response_type": "feedback", "conversation_ended": True}

    current_question = asked[-1]
    latest_answer = ""
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            latest_answer = msg["content"]
            break

    if not latest_answer:
        return {"current_response": "未检测到你的回答。", "current_response_type": "feedback"}

    user_answers = state.get("user_answers", [])
    recent_qa = user_answers[-3:] if user_answers else []
    qa_summary = ""
    if recent_qa:
        lines = [f"  {'✓' if qa.get('correct') else '✗'} {qa.get('question', '')[:40]} → {qa.get('answer', '')[:40]}" for qa in recent_qa]
        qa_summary = "\n".join(lines)

    prompt = ANSWER_EVALUATION_PROMPT.format(
        question=current_question, answer=latest_answer,
        knowledge_points=state.get("knowledge_points", []),
        mastery=state.get("mastery_level", {}),
        qa_summary=f"历史：\n{qa_summary}" if qa_summary else "",
    )

    try:
        response = await llm.call(messages=[{"role": "system", "content": prompt}], temperature=0.1, max_tokens=256)
        evaluation = _parse_json_response(response)
    except Exception as e:
        logger.warning(f"evaluate_answer LLM 失败: {e}")
        evaluation = {}

    return _apply_evaluation(state, evaluation, current_question, latest_answer)


# ============================================================
# 节点 9b: evaluate_and_decide（合并评估+决策，省一次LLM调用）
# ============================================================
async def evaluate_and_decide(state: SocraticState) -> dict:
    """评估用户回答并决定下一步教学动作（单次LLM调用完成两个任务）"""
    # 安全阀（Duolingo 模式）：错误>=4 OR hint>=8 → 强制结束
    errors = state.get("consecutive_errors", 0)
    hints = state.get("hint_count", 0)
    if errors >= 4 or hints >= 8:
        reason = "连续错误过多" if errors >= 4 else "提示请求过多"
        return {
            "next_action": "summarize",
            "action_reason": f"{reason}，强制结束",
            "action_target": "",
            "current_stage": f"{state.get('original_query', '')}-安全结束",
            "conversation_ended": True,
            "pending_feedback": "",
            "recent_actions": state.get("recent_actions", []) + [{
                "action": "summarize", "target": "",
                "reason": f"安全阀：errors={errors}, hints={hints}", "ts": datetime.now().isoformat(),
            }],
        }

    # 短路：用户请求提示，跳过评估直接路由（hint_count 在 generate_hint 中递增）
    if state.get("need_hint"):
        return {
            "next_action": "generate_hint",
            "action_reason": "用户请求提示",
            "action_target": state.get("action_target", ""),
            "current_stage": f"{state.get('original_query', '')}-hint",
            "need_hint": True,
            "pending_feedback": "",  # 清除旧反馈
            "recent_actions": state.get("recent_actions", []) + [{
                "action": "generate_hint", "target": state.get("action_target", ""),
                "reason": "用户请求提示", "ts": datetime.now().isoformat(),
            }],
        }
    if state.get("need_rephrase"):
        target = state.get("action_target", "")
        return {
            "next_action": "rephrase_question",
            "action_reason": "用户没听懂，换个角度讲解",
            "action_target": target,
            "current_stage": f"{state.get('original_query', '')}-rephrase",
            "need_rephrase": False,
            "pending_feedback": "",  # 清除旧反馈
            "recent_actions": state.get("recent_actions", []) + [{
                "action": "rephrase_question", "target": target,
                "reason": "用户没听懂", "ts": datetime.now().isoformat(),
            }],
        }
    if state.get("conversation_ended"):
        return {
            "next_action": "generate_summary_and_save",
            "action_reason": "用户结束学习",
            "action_target": "",
            "current_stage": f"{state.get('original_query', '')}-结束",
            "conversation_ended": True,
            "pending_feedback": "",
            "recent_actions": state.get("recent_actions", []) + [{
                "action": "summarize", "target": "",
                "reason": "用户结束学习", "ts": datetime.now().isoformat(),
            }],
        }

    llm = get_async_llm_client()

    asked = state.get("asked_questions", [])
    chat_history = state.get("chat_history", [])

    if not asked:
        return {"current_response": "没有待评估的问题。", "current_response_type": "feedback", "conversation_ended": True}

    current_question = asked[-1]
    latest_answer = ""
    for msg in reversed(chat_history):
        if msg.get("role") == "user":
            latest_answer = msg["content"]
            break

    if not latest_answer:
        # hint 流程：没有新答案，直接路由到下一个动作
        logger.info("📊 evaluate_and_decide: 无新答案（hint流程），跳过评估")
        pending = state.get("pending_points", [])
        target = pending[0] if pending else state.get("original_query", "")
        return {
            "next_action": "ask_question",
            "action_reason": "hint后继续提问",
            "action_target": target,
            "current_stage": f"{state.get('original_query', '')}-ask_question",
            "recent_actions": state.get("recent_actions", []) + [{"action": "ask_question", "target": target, "reason": "hint后继续", "ts": datetime.now().isoformat()}],
        }

    # 构建对话历史摘要
    user_answers = state.get("user_answers", [])
    recent_qa = user_answers[-3:] if user_answers else []
    qa_summary = ""
    if recent_qa:
        lines = [f"  {'✓' if qa.get('correct') else '✗'} {qa.get('question', '')[:40]} → {qa.get('answer', '')[:40]}" for qa in recent_qa]
        qa_summary = "\n".join(lines)

    # 学习状态指南
    learning_state = state.get("learning_state", "normal")
    state_guide = LEARNING_STATE_GUIDES.get(learning_state, "")

    misconceptions = state.get("user_misconceptions", [])
    misconceptions_str = json.dumps(misconceptions, ensure_ascii=False) if misconceptions else "无"
    recent_actions = state.get("recent_actions", [])
    recent_str = json.dumps(recent_actions[-5:], ensure_ascii=False) if recent_actions else "无"

    prompt = EVALUATE_AND_DECIDE_PROMPT.format(
        question=current_question, answer=latest_answer,
        knowledge_points=state.get("knowledge_points", []),
        mastery=state.get("mastery_level", {}),
        qa_summary=f"历史：\n{qa_summary}" if qa_summary else "",
        learning_state_guide=f"学习状态：{state_guide}" if state_guide else "",
        pending_points=state.get("pending_points", []),
        covered_points=state.get("covered_points", []),
        consecutive_errors=state.get("consecutive_errors", 0),
        consecutive_correct=state.get("consecutive_correct", 0),
        misconceptions=misconceptions_str,
        recent_actions=recent_str,
    )

    try:
        response = await llm.call(messages=[{"role": "system", "content": prompt}], temperature=0.2, max_tokens=384)
        result = _parse_json_response(response)
    except Exception as e:
        logger.warning(f"evaluate_and_decide LLM 失败: {e}")
        result = {}

    # 提取评估部分
    evaluation_result = _apply_evaluation(state, result, current_question, latest_answer)

    # 提取决策部分
    action = result.get("action", "ask_question")
    reason = result.get("reason", "")
    target = result.get("target", state.get("pending_points", [""])[0] if state.get("pending_points") else "")

    valid_actions = {"ask_question", "explain_concept", "code_demo", "practice_exercise",
                     "rephrase_question", "relate_knowledge", "summarize"}
    if action not in valid_actions:
        action = "ask_question"

    # 安全检查
    pending = evaluation_result.get("pending_points", state.get("pending_points", []))
    mastery = evaluation_result.get("mastery_level", state.get("mastery_level", {}))
    if not pending and all(v >= 0.7 for v in mastery.values()):
        action = "summarize"

    # 连续错误安全阀
    errors = evaluation_result.get("consecutive_errors", 0)
    if errors >= 3 and action == "ask_question":
        action = "explain_concept"

    # 连续 4 次错误 → 强制结束
    if errors >= 4:
        action = "summarize"

    ended = evaluation_result.get("conversation_ended", False)
    if ended:
        action = "summarize"

    logger.info(f"🎯 评估+决策 | action={action} | reason={reason[:50]} | target={target}")

    # 更新 recent_actions
    new_recent = recent_actions + [{"action": action, "target": target, "reason": reason, "ts": datetime.now().isoformat()}]

    # 持久化
    try:
        persist_state = {**state, **evaluation_result}
        await _persist_learning_data(persist_state)
    except Exception as e:
        logger.warning(f"evaluate_and_decide 持久化失败: {e}")

    # 合并评估结果和决策结果
    evaluation_result["next_action"] = action
    evaluation_result["action_reason"] = reason
    evaluation_result["action_target"] = target
    evaluation_result["current_stage"] = f"{state.get('original_query', '')}-{action}"
    evaluation_result["recent_actions"] = new_recent

    return evaluation_result


def _apply_evaluation(state: SocraticState, evaluation: dict, current_question: str, latest_answer: str) -> dict:
    """共享的评估结果应用逻辑（evaluate_answer 和 evaluate_and_decide 共用）"""
    correctness = evaluation.get("correctness", "部分正确")
    feedback = evaluation.get("feedback", "你的回答有一定道理，但还可以更全面。")
    mastery_updates = evaluation.get("mastery_updates", {})
    new_kps = evaluation.get("new_knowledge_points", [])
    new_misconceptions = evaluation.get("misconceptions", [])

    # 鼓励
    if correctness == "是":
        consecutive_correct = state.get("consecutive_correct", 0) + 1
        encouragements = ["太棒了！", "完全正确！", "很好！", "回答得很准确！"]
        if consecutive_correct >= 3:
            encouragement = "你已经连续答对多题，完全掌握了！"
        elif consecutive_correct >= 2:
            encouragement = "连续正确，继续保持！"
        else:
            encouragement = random.choice(encouragements)
        feedback = f"{encouragement} {feedback}"

    user_answer_entry = {
        "question": current_question, "answer": latest_answer,
        "correct": correctness == "是", "feedback": feedback,
    }

    # 更新掌握度
    new_mastery = dict(state.get("mastery_level", {}))
    mastery_changes = {}
    for kp, score in mastery_updates.items():
        if kp in new_mastery:
            old_score = new_mastery[kp]
            new_score = max(old_score, float(score))
            if new_score != old_score:
                mastery_changes[kp] = {"from": round(old_score, 2), "to": round(new_score, 2)}
            new_mastery[kp] = new_score

    # 连续错误/正确计数
    consecutive_errors = state.get("consecutive_errors", 0)
    consecutive_correct = state.get("consecutive_correct", 0)
    if correctness != "是":
        consecutive_errors += 1
        consecutive_correct = 0
    else:
        consecutive_errors = 0
        consecutive_correct += 1

    # 更新学习状态（记录变化）
    old_learning_state = state.get("learning_state", "normal")
    learning_state = _update_learning_state(state, correctness == "是")
    learning_state_changes = list(state.get("learning_state_changes", []))
    if learning_state != old_learning_state:
        learning_state_changes.append({"from": old_learning_state, "to": learning_state, "ts": datetime.now().isoformat()})

    # 难度自适应
    difficulty = state.get("difficulty", 3)
    ls = LearningState(learning_state) if learning_state else LearningState.NORMAL
    if ls in (LearningState.STRUGGLING, LearningState.CONFUSED):
        difficulty = max(difficulty - 1, 1)
    elif ls in (LearningState.BORED, LearningState.MASTERING):
        difficulty = min(difficulty + 1, 5)
    elif correctness == "是" and consecutive_correct >= 2:
        difficulty = min(difficulty + 1, 5)
    elif correctness != "是" and consecutive_errors >= 2:
        difficulty = max(difficulty - 1, 1)

    # 错题本
    error_book_entries = list(state.get("error_book_entries", []))
    if correctness != "是":
        error_book_entries.append({
            "question_text": current_question, "user_answer": latest_answer,
            "correct_answer": "", "knowledge_point": state.get("knowledge_points", ["未知"])[0],
            "user_id": state.get("user_id", ""),
        })

    # 动态知识点追踪
    pending_points = list(state.get("pending_points", []))
    covered_points = list(state.get("covered_points", []))
    target = state.get("action_target", "")
    if target and correctness == "是":
        if target in pending_points:
            pending_points.remove(target)
        if target not in covered_points:
            covered_points.append(target)
    for kp in new_kps:
        if kp not in pending_points and kp not in covered_points and kp not in state.get("knowledge_points", []):
            pending_points.append(kp)

    # 记录误解
    misconceptions = list(state.get("user_misconceptions", []))
    misconceptions.extend(new_misconceptions)

    # 连续 4 次错误 → 强制结束
    conversation_ended = False
    if consecutive_errors >= 4:
        conversation_ended = True
        feedback = f"{feedback}\n\n这个问题可能需要你回去复习一下相关知识点。"

    return {
        "user_answers": state.get("user_answers", []) + [user_answer_entry],
        "mastery_level": new_mastery,
        "mastery_changes": mastery_changes,
        "difficulty": difficulty,
        "consecutive_errors": consecutive_errors,
        "consecutive_correct": consecutive_correct,
        "error_book_entries": error_book_entries,
        "current_response": feedback,
        "current_response_type": "feedback",
        "pending_feedback": feedback,
        "pending_feedback_type": "feedback",
        "conversation_ended": conversation_ended,
        "need_hint": False,
        "learning_state": learning_state,
        "learning_state_changes": learning_state_changes,
        "pending_points": pending_points,
        "covered_points": covered_points,
        "user_misconceptions": misconceptions,
    }


# ============================================================
# 节点 10: generate_hint
# ============================================================
async def generate_hint(state: SocraticState) -> dict:
    """生成分级提示"""
    llm = get_async_llm_client()
    hint_level = min(state.get("hint_level", 1), 3)

    asked = state.get("asked_questions", [])
    current_question = asked[-1] if asked else "未知问题"

    user_answers = state.get("user_answers", [])
    last_answer = user_answers[-1]["answer"] if user_answers else "无"

    hints_given = state.get("hints_given", [])
    prev_hints = "\n".join([f"- {h}" for h in hints_given]) if hints_given else "无"

    prompt = HINT_GENERATION_PROMPT.format(
        question=current_question, answer=last_answer,
        hint_level=hint_level, prev_hints=prev_hints,
    )

    try:
        hint = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.5, max_tokens=128,
        )
        hint = hint.strip()
    except Exception as e:
        logger.warning(f"generate_hint LLM 失败: {e}")
        kp = state.get("knowledge_points", [""])[0]
        level_prompts = {
            1: f"想想看，{kp} 的基本概念是什么？",
            2: f"你应该从 {current_question} 的核心语法入手。",
            3: f"试试这样的结构：先写基本框架，然后填充关键逻辑。",
        }
        hint = level_prompts.get(hint_level, "再想想看？")

    new_hints = hints_given + [hint]
    new_hint_level = min(hint_level + 1, 3)
    new_hint_count = state.get("hint_count", 0) + 1

    # 显示提示后，暂停等待用户回答同一问题
    new_chat_history = state.get("chat_history", []) + [
        {"role": "assistant", "content": f"[提示] {hint}"}
    ]

    # 直接调用 interrupt，不用 _handle_user_response（避免 spread 覆盖 chat_history）
    user_answer = interrupt({
        "type": "hint",
        "content": hint,
        "stage": state.get("current_stage", ""),
        "difficulty": state.get("difficulty", 3),
        "hint_level": new_hint_level,
        "consecutive_errors": state.get("consecutive_errors", 0),
        "learning_state": state.get("learning_state", "normal"),
    })

    base = {
        "hints_given": new_hints,
        "hint_level": new_hint_level,
        "hint_count": new_hint_count,
        "current_response": hint,
        "current_response_type": "hint",
        "chat_history": new_chat_history,
    }

    if user_answer == "__HINT__":
        return {**base, "need_hint": True, "conversation_ended": False}
    if user_answer == "__END__":
        return {**base, "conversation_ended": True, "need_hint": False}

    # 普通回答：追加到 chat_history
    return {
        **base,
        "chat_history": new_chat_history + [{"role": "user", "content": user_answer}],
        "need_hint": False,
        "conversation_ended": False,
    }


# ============================================================
# 节点 11: generate_summary_and_save
# ============================================================
async def generate_summary_and_save(state: SocraticState) -> dict:
    """生成学习总结，持久化数据"""
    llm = get_async_llm_client()

    qa_summary = ""
    for qa in state.get("user_answers", []):
        status = "正确" if qa.get("correct") else "错误"
        qa_summary += f"[{status}] {qa.get('question', '')[:40]} → {qa.get('answer', '')[:40]}\n"

    prompt = SUMMARY_PROMPT.format(
        topic=state.get("original_query", ""),
        knowledge_points=state.get("knowledge_points", []),
        mastery_level=state.get("mastery_level", {}),
        qa_summary=qa_summary or "无",
    )

    try:
        summary = await llm.call(
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3, max_tokens=256,
        )
        summary = summary.strip()
    except Exception as e:
        logger.warning(f"generate_summary LLM 失败: {e}")
        kps = ", ".join(state.get("knowledge_points", []))
        summary = f"本次学习了 {kps}，请继续巩固练习。"

    try:
        await _persist_learning_data(state)
    except Exception as e:
        logger.error(f"持久化学习数据失败: {e}")

    # 保存教学会话数据
    try:
        end_reason = "max_errors" if state.get("consecutive_errors", 0) >= 4 else "completed"
        await _save_socratic_session(state, end_reason=end_reason)
    except Exception as e:
        logger.warning(f"保存教学会话数据失败: {e}")

    return {
        "summary": summary,
        "current_response": summary,
        "current_response_type": "summary",
        "conversation_ended": True,
    }


# ============================================================
# 数据采集：教学会话指标
# ============================================================
async def _save_socratic_session(state: SocraticState, end_reason: str = "completed") -> None:
    """保存教学会话数据到 socratic_sessions 表"""
    from models.database import AsyncSessionLocal
    from models.socratic_session import SocraticSession
    from sqlalchemy import select

    user_id = state.get("user_id")
    thread_id = state.get("session_id", "") or ""
    if not user_id or not thread_id:
        return

    try:
        uid = int(user_id) if str(user_id).isdigit() else None
        if not uid:
            return

        user_answers = state.get("user_answers", [])
        recent_actions = state.get("recent_actions", [])

        # 构建动作序列
        action_sequence = []
        for i, qa in enumerate(user_answers):
            action_entry = {
                "question": qa.get("question", "")[:100],
                "answer": qa.get("answer", "")[:100],
                "correct": qa.get("correct", False),
                "feedback": qa.get("feedback", "")[:100],
            }
            if i < len(recent_actions):
                action_entry["action"] = recent_actions[i].get("action", "")
                action_entry["target"] = recent_actions[i].get("target", "")
                action_entry["reason"] = recent_actions[i].get("reason", "")[:80]
            action_sequence.append(action_entry)

        # 动作分布统计
        action_dist = {}
        for ra in recent_actions:
            act = ra.get("action", "unknown")
            action_dist[act] = action_dist.get(act, 0) + 1

        async with AsyncSessionLocal() as session:
            # 查找或创建会话记录
            result = await session.execute(
                select(SocraticSession).where(SocraticSession.thread_id == thread_id)
            )
            record = result.scalar_one_or_none()

            if not record:
                record = SocraticSession(
                    user_id=uid,
                    thread_id=thread_id,
                    conversation_id=state.get("conversation_id"),
                    topic=state.get("original_query", ""),
                    knowledge_points=state.get("knowledge_points", []),
                    initial_mastery={kp: 0.0 for kp in state.get("knowledge_points", [])},
                )
                session.add(record)

            # 更新统计
            record.total_actions = len(user_answers)
            record.total_correct = sum(1 for qa in user_answers if qa.get("correct"))
            record.total_wrong = sum(1 for qa in user_answers if not qa.get("correct"))
            record.total_hints = len(state.get("hints_given", []))
            record.action_sequence = action_sequence
            record.final_mastery = state.get("mastery_level", {})
            record.action_distribution = action_dist
            record.end_reason = end_reason
            record.summary = state.get("summary", "")[:500]

            # 学习状态变化
            record.learning_state_changes = state.get("learning_state_changes", [])

            await session.commit()
            logger.info(f"📊 教学会话数据已保存: thread={thread_id}, actions={len(user_answers)}")

    except Exception as e:
        logger.warning(f"保存教学会话数据失败: {e}")


# ============================================================
# 数据持久化
# ============================================================
async def _persist_learning_data(state: SocraticState) -> None:
    """持久化学习数据到数据库"""
    from models.database import AsyncSessionLocal
    from models.profile import UserProfile
    from models.error_book import ErrorBook
    from models.progress import LearningProgress
    from sqlalchemy import select

    user_id = state.get("user_id")
    if not user_id:
        return

    try:
        uid = int(user_id) if str(user_id).isdigit() else None
        if not uid:
            return

        async with AsyncSessionLocal() as session:
            # 1. 更新学习画像
            result = await session.execute(select(UserProfile).where(UserProfile.user_id == uid))
            profile = result.scalar_one_or_none()
            if profile:
                mastered = set(profile.mastered_points or [])
                weak = set(profile.weak_points or [])
                for kp, score in state.get("mastery_level", {}).items():
                    if score >= 0.8:
                        mastered.add(kp)
                        weak.discard(kp)
                    elif score < 0.3:
                        weak.add(kp)
                profile.mastered_points = list(mastered)
                profile.weak_points = list(weak)

                # 推断学习风格：统计交互类型分布
                action_counts = {"kinesthetic": 0, "visual": 0, "auditory": 0}
                for action in state.get("recent_actions", []):
                    atype = action.get("action", "")
                    if atype in ("code_demo", "practice_exercise"):
                        action_counts["kinesthetic"] += 1
                    elif atype in ("explain_concept", "relate_knowledge", "summarize"):
                        action_counts["visual"] += 1
                    elif atype in ("ask_question", "rephrase_question"):
                        action_counts["auditory"] += 1
                # 也统计当前响应类型（值与 recent_actions 不同，用原始分类）
                resp_type = state.get("current_response_type", "")
                if resp_type in ("demo", "practice"):
                    action_counts["kinesthetic"] += 1
                elif resp_type in ("explain", "relate", "summary"):
                    action_counts["visual"] += 1
                elif resp_type in ("question", "answer", "feedback", "hint"):
                    action_counts["auditory"] += 1

                total_actions = sum(action_counts.values())
                if total_actions > 0:
                    dominant = max(action_counts, key=action_counts.get)
                    if action_counts[dominant] > 0:
                        profile.learning_style = dominant

            # 2. 错题本（含间隔重复初始化）
            from ai.spaced_repetition import get_next_review_time, INITIAL_INTERVAL_DAYS, DEFAULT_EASINESS_FACTOR
            for entry in state.get("error_book_entries", []):
                existing = await session.execute(
                    select(ErrorBook).where(
                        ErrorBook.user_id == uid,
                        ErrorBook.question_text == entry.get("question_text", ""),
                    )
                )
                if not existing.scalar_one_or_none():
                    next_at, _, _, _ = get_next_review_time(
                        quality=1, repetition_count=0,
                        easiness_factor=DEFAULT_EASINESS_FACTOR,
                        current_interval_days=INITIAL_INTERVAL_DAYS,
                    )
                    session.add(ErrorBook(
                        user_id=uid, resource_id=None, question_text=entry.get("question_text", ""),
                        question_type="fill", user_answer=entry.get("user_answer", ""),
                        correct_answer="", explanation="",
                        knowledge_point=entry.get("knowledge_point", ""),
                        difficulty="medium", error_count=1,
                        next_review_at=next_at,
                        review_interval_days=INITIAL_INTERVAL_DAYS,
                        easiness_factor=DEFAULT_EASINESS_FACTOR,
                        repetition_count=0,
                    ))

            # 3. 学习进度
            for kp in state.get("knowledge_points", []):
                result = await session.execute(
                    select(LearningProgress).where(
                        LearningProgress.user_id == uid,
                        LearningProgress.topic == kp,
                        LearningProgress.is_active == True,
                    )
                )
                progress = result.scalar_one_or_none()
                mastery = state.get("mastery_level", {}).get(kp, 0)
                if progress:
                    progress.score = max(progress.score or 0, mastery * 100)
                else:
                    session.add(LearningProgress(
                        user_id=uid, topic=kp, status="in_progress",
                        score=mastery * 100, duration=0,
                    ))

            # 先提交画像+错题本+进度，确保核心数据不丢失
            await session.commit()

            # 4. IRT 能力估计（独立 try，失败不影响已提交的数据）
            try:
                from ai.adaptive_difficulty import AdaptiveDifficultyEngine
                from models.quiz_attempt import QuizAttempt
                engine = AdaptiveDifficultyEngine(session)
                difficulty_str = {1: "easy", 2: "easy", 3: "medium", 4: "hard", 5: "hard"}.get(
                    state.get("difficulty", 3), "medium"
                )
                for kp in state.get("knowledge_points", []):
                    mastery_score = state.get("mastery_level", {}).get(kp, 0)
                    session.add(QuizAttempt(
                        user_id=uid, resource_id=0, question_index=0,
                        question_type="socratic", difficulty=difficulty_str,
                        knowledge_point=kp, user_answer=str(mastery_score),
                        correct_answer="", is_correct=mastery_score >= 0.6,
                        score=int(mastery_score * 10), spent_time=0,
                    ))
                await session.commit()
                for kp in state.get("knowledge_points", []):
                    await engine.estimate_user_ability(uid, kp)
                logger.info(f"IRT 能力估计持久化成功: user={uid}")
            except Exception as irt_err:
                logger.debug(f"IRT 持久化跳过: {irt_err}")

            logger.info(f"学习数据持久化成功: user={uid}")

    except Exception as e:
        logger.error(f"持久化学习数据异常: {e}")


# ============================================================
# 路由函数
# ============================================================
def route_decision(state: SocraticState) -> str:
    """教学决策引擎的条件路由"""
    action = state.get("next_action", "ask_question")
    ended = state.get("conversation_ended", False)
    errors = state.get("consecutive_errors", 0)
    need_hint = state.get("need_hint", False)

    logger.info(f"🔀 路由决策 | action={action} | ended={ended} | errors={errors} | need_hint={need_hint}")

    if ended:
        return "generate_summary_and_save"

    # 用户请求提示 → 直接生成提示
    if need_hint or action == "generate_hint":
        return "generate_hint"

    # 安全检查：连续错误过多 → 强制讲解
    if errors >= 3 and action == "ask_question":
        return "explain_concept"

    return action


# ============================================================
# 工作流构建
# ============================================================
def build_socratic_workflow() -> StateGraph:
    """构建苏格拉底导学 2.0 工作流（优化版：合并评估+决策，省一次LLM调用）"""
    workflow = StateGraph(SocraticState)

    # 节点
    workflow.add_node("analyze_problem", analyze_problem)
    workflow.add_node("teaching_decision_engine", teaching_decision_engine)
    workflow.add_node("ask_question", ask_question)
    workflow.add_node("rephrase_question", rephrase_question)
    workflow.add_node("relate_knowledge", relate_knowledge)
    workflow.add_node("explain_concept", explain_concept)
    workflow.add_node("code_demo", code_demo)
    workflow.add_node("practice_exercise", practice_exercise)
    workflow.add_node("evaluate_and_decide", evaluate_and_decide)
    workflow.add_node("generate_hint", generate_hint)
    workflow.add_node("generate_summary_and_save", generate_summary_and_save)

    # 入口：分析问题 → 决策引擎（第一轮）
    workflow.set_entry_point("analyze_problem")
    workflow.add_edge("analyze_problem", "teaching_decision_engine")

    # 决策引擎 → 条件路由（仅用于第一轮和 hint 后）
    workflow.add_conditional_edges(
        "teaching_decision_engine",
        route_decision,
        {
            "ask_question": "ask_question",
            "explain_concept": "explain_concept",
            "code_demo": "code_demo",
            "practice_exercise": "practice_exercise",
            "rephrase_question": "rephrase_question",
            "relate_knowledge": "relate_knowledge",
            "generate_hint": "generate_hint",
            "summarize": "generate_summary_and_save",
            "generate_summary_and_save": "generate_summary_and_save",
        },
    )

    # 所有动作节点 → 合并评估+决策（核心优化：单次LLM调用）
    for node in ["ask_question", "rephrase_question", "relate_knowledge",
                 "explain_concept", "code_demo", "practice_exercise"]:
        workflow.add_edge(node, "evaluate_and_decide")

    # 合并节点 → 条件路由到下一个动作
    workflow.add_conditional_edges(
        "evaluate_and_decide",
        route_decision,
        {
            "ask_question": "ask_question",
            "explain_concept": "explain_concept",
            "code_demo": "code_demo",
            "practice_exercise": "practice_exercise",
            "rephrase_question": "rephrase_question",
            "relate_knowledge": "relate_knowledge",
            "generate_hint": "generate_hint",
            "summarize": "generate_summary_and_save",
            "generate_summary_and_save": "generate_summary_and_save",
        },
    )

    # 提示 → 合并评估+决策（提示后等待用户回答，然后评估）
    workflow.add_edge("generate_hint", "evaluate_and_decide")

    # 总结 → END
    workflow.add_edge("generate_summary_and_save", END)

    return workflow


# ============================================================
# 全局实例
# ============================================================
_socratic_app: Optional[Any] = None


async def get_socratic_workflow() -> Any:
    """获取编译后的苏格拉底工作流（单例）"""
    global _socratic_app
    if _socratic_app is None:
        from graph.checkpointer import get_checkpointer
        checkpointer = await get_checkpointer()
        workflow = build_socratic_workflow()
        _socratic_app = workflow.compile(checkpointer=checkpointer)
        logger.info("✅ 苏格拉底 2.0 工作流初始化完成")
    return _socratic_app
