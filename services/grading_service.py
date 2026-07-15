"""
services/grading_service.py - 统一判分服务
收口所有判分逻辑：选择题、填空题、代码题（执行对比 + LLM判分）
供 quiz / daily / chat 等路由共用
"""
from __future__ import annotations

import re
import json
import ast
import asyncio
from typing import Optional

from config.constants import (
    CODE_EXEC_DEFAULT_TIMEOUT,
    LLM_GRADING_TIMEOUT_SEC,
    QUIZ_OUTPUT_TRUNCATE_LENGTH,
    QUIZ_LLM_FEEDBACK_MAX_CHARS,
    QUIZ_PARTIAL_MATCH_MIN_RATIO,
    QUIZ_PARTIAL_MATCH_MAX_RATIO,
    QUIZ_PARTIAL_MATCH_SCORE,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="grading_service")


# ==================== 基础工具 ====================

def normalize_answer(text: str) -> str:
    """标准化答案文本：去除首尾空白、多余空格"""
    text = text.strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_code(text: str) -> str:
    """标准化代码：去行尾空白、去空行（用于代码题归一化比对）"""
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    return "\n".join(lines)


# ==================== 选择题判分 ====================

def grade_choice(user_answer: str, correct_answer: str) -> bool:
    """选择题判分：忽略大小写和空白"""
    return user_answer.strip().upper() == correct_answer.strip().upper()


# ==================== 填空题判分 ====================

def grade_fill(user_answer: str, correct_answer: str) -> tuple[bool, float]:
    """
    填空题智能判分：
    1. 完全匹配（标准化后）
    2. 多答案支持（| 分隔，任意一个正确即对）
    3. 忽略首尾空白和多余空格
    4. 部分匹配（用户答案包含在正确答案中，或反之）
    返回 (is_exact_correct, score_percent)
    """
    user_norm = normalize_answer(user_answer)
    correct_norm = normalize_answer(correct_answer)

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


# ==================== 代码判分 ====================

async def compare_execution(user_code: str, ref_code: str, timeout: int = CODE_EXEC_DEFAULT_TIMEOUT) -> dict:
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
            "match": bool(user_out) and user_out == ref_out and user_result.get("success", False),
            "user_stdout": user_out,
            "ref_stdout": ref_out,
            "user_stderr": user_result.get("stderr", ""),
            "user_success": user_result.get("success", False),
            "ref_success": ref_result.get("success", False),
        }
    except Exception as e:
        return {"match": False, "error": str(e)}


def classify_error(syntax_ok: bool, exec_result: dict, compare_result: dict) -> str:
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


async def grade_code_with_llm(
    question_text: str, user_code: str, correct_answer: str, explanation: str,
    test_cases: list[dict] | None = None,
) -> tuple[bool, str]:
    """
    编程题判分（增强版）：
    1. 语法检查（快速失败）
    2. 测试用例驱动判分（如有）
    3. 对比执行：同时运行用户代码和参考答案，输出一致直接判对
    4. LLM 逻辑等价判断（对比执行无法确定时的兜底）
    返回 (is_correct, feedback)
    """
    # Step 1: 语法检查（快速失败）
    syntax_ok = True
    try:
        compile(user_code, "<user_code>", "exec")
    except SyntaxError as e:
        syntax_ok = False
        return False, f"[语法错误] 第{e.lineno}行：{e.msg}"

    # Step 1.1: 代码归一化比对（用户代码与参考答案归一化后相等，直接判对）
    if correct_answer and normalize_code(user_code) == normalize_code(correct_answer):
        return True, "[代码匹配] 答案与参考实现一致"

    # Step 1.5: 测试用例驱动判分（如果元数据中定义了测试用例）
    if test_cases:
        from utils.code_executor import execute_python_code
        passed = 0
        total = len(test_cases)
        case_results = []
        for i, tc in enumerate(test_cases[:5]):  # 最多运行5个测试用例
            tc_input = tc.get("input", "")
            tc_expected = tc.get("output", "")
            # 校验 tc_input 是合法表达式，防止 LLM 生成非表达式（如 import 语句）注入
            try:
                ast.parse(tc_input, mode='eval')
            except SyntaxError:
                case_results.append(f"用例{i+1}: ✗ (输入格式非法)")
                continue
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
            compare_result = await compare_execution(user_code, correct_answer)
            if compare_result.get("match"):
                return True, "[对比执行] 输出与参考答案一致"
    except Exception as e:
        logger.debug(f"对比执行异常（不影响流程）: {e}")

    # 错误类型分类
    error_type = classify_error(syntax_ok, exec_result, compare_result)
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
            agent.llm_client.call(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=200,
            ),
            timeout=LLM_GRADING_TIMEOUT_SEC,
        )

        json_match = re.search(r'\{[^}]+\}', result)
        if json_match:
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
