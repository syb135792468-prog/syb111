"""
test_socratic.py - 苏格拉底导学模式 2.0 自动化测试
验证：工作流编译、节点完整性、路由逻辑、状态定义、JSON 解析
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def test_workflow_compile():
    """测试 1：工作流编译与节点完整性"""
    print("=" * 60)
    print("🧪 测试 1：工作流编译")
    print("=" * 60)

    from agents.socratic_workflow import build_socratic_workflow, get_socratic_workflow

    wf = build_socratic_workflow()
    nodes = list(wf.nodes.keys())
    print(f"  节点 ({len(nodes)}): {nodes}")

    expected_nodes = [
        "analyze_problem", "teaching_decision_engine",
        "ask_question", "rephrase_question", "relate_knowledge",
        "explain_concept", "code_demo", "practice_exercise",
        "evaluate_answer", "generate_hint", "generate_summary_and_save",
    ]
    for n in expected_nodes:
        assert n in nodes, f"缺失节点: {n}"
    assert len(nodes) == len(expected_nodes), f"期望 {len(expected_nodes)} 个节点，实际 {len(nodes)}"

    # 测试编译版本
    app = await get_socratic_workflow()
    print(f"  编译成功: {app is not None}")
    assert app is not None

    print("✅ 测试 1 通过\n")


async def test_state_definition():
    """测试 2：状态定义完整性"""
    print("=" * 60)
    print("🧪 测试 2：状态定义完整性")
    print("=" * 60)

    from agents.socratic_state import SocraticState

    required_fields = [
        "user_id", "conversation_id", "original_query", "chat_history",
        "profile_data", "knowledge_points", "current_topic", "difficulty",
        "current_stage", "next_action", "action_reason", "action_target",
        "recent_actions", "user_misconceptions", "covered_points", "pending_points",
        "asked_questions", "user_answers", "mastery_level", "mastery_changes",
        "need_hint", "hint_level", "hints_given", "consecutive_errors", "consecutive_correct",
        "conversation_ended", "current_response", "current_response_type",
        "error_book_entries", "summary",
    ]

    annotations = SocraticState.__annotations__
    missing = [f for f in required_fields if f not in annotations]
    for field in required_fields:
        status = "✅" if field in annotations else "❌"
        print(f"  {status} {field}")

    assert not missing, f"缺失字段: {missing}"
    print("✅ 测试 2 通过\n")


async def test_decision_engine():
    """测试 3：教学决策引擎"""
    print("=" * 60)
    print("🧪 测试 3：教学决策引擎")
    print("=" * 60)

    from agents.socratic_workflow import route_decision

    # 测试正常路由
    state = {"next_action": "ask_question", "conversation_ended": False, "consecutive_errors": 0}
    assert route_decision(state) == "ask_question"

    state["next_action"] = "explain_concept"
    assert route_decision(state) == "explain_concept"

    state["next_action"] = "code_demo"
    assert route_decision(state) == "code_demo"

    state["next_action"] = "summarize"
    assert route_decision(state) == "summarize"

    # 测试连续错误安全阀
    state = {"next_action": "ask_question", "conversation_ended": False, "consecutive_errors": 3}
    assert route_decision(state) == "explain_concept", "连续3次错误应路由到 explain_concept"

    # 测试结束路由
    state = {"next_action": "ask_question", "conversation_ended": True, "consecutive_errors": 0}
    assert route_decision(state) == "generate_summary_and_save"

    print("✅ 测试 3 通过\n")


async def test_json_parser():
    """测试 4：JSON 解析容错"""
    print("=" * 60)
    print("🧪 测试 4：JSON 解析容错")
    print("=" * 60)

    from agents.socratic_workflow import _parse_json_response

    test_cases = [
        ('{"key": "value"}', {"key": "value"}),
        ('```json\n{"key": "value"}\n```', {"key": "value"}),
        ('{"key": "value",}', {"key": "value"}),
        ("invalid json", {}),
        ('', {}),
        ('Some text {"key": "value"} more text', {"key": "value"}),
    ]

    for input_str, expected in test_cases:
        result = _parse_json_response(input_str)
        status = "✅" if result == expected else "❌"
        print(f"  {status} 输入: {input_str[:40]}... → {result}")

    print("✅ 测试 4 完成\n")


async def test_schema_validation():
    """测试 5：Schema 验证"""
    print("=" * 60)
    print("🧪 测试 5：Schema 验证")
    print("=" * 60)

    from api.schemas import SocraticChatRequest, StreamEvent

    req1 = SocraticChatRequest(message="我想学列表推导式", action="start")
    print(f"  ✅ start: {req1.model_dump()}")

    req2 = SocraticChatRequest(message="我的回答", action="answer", thread_id="test-123")
    print(f"  ✅ answer: {req2.model_dump()}")

    req3 = SocraticChatRequest(message="", action="hint", thread_id="test-123")
    print(f"  ✅ hint: {req3.model_dump()}")

    req4 = SocraticChatRequest(message="", action="end", thread_id="test-123")
    print(f"  ✅ end: {req4.model_dump()}")

    req5 = SocraticChatRequest(message="", action="confused", thread_id="test-123")
    print(f"  ✅ confused: {req5.model_dump()}")

    # 测试新事件类型
    for evt in ["socratic_explain", "socratic_demo", "socratic_practice", "socratic_relate"]:
        event = StreamEvent(event=evt, data={"content": "test"})
        print(f"  ✅ StreamEvent: {event.event}")

    print("✅ 测试 5 完成\n")


async def test_prompt_imports():
    """测试 6：Prompt 模块导入"""
    print("=" * 60)
    print("🧪 测试 6：Prompt 模块导入")
    print("=" * 60)

    from ai.prompts.socratic_prompts import (
        PROBLEM_ANALYSIS_PROMPT, TEACHING_DECISION_PROMPT,
        QUESTION_GENERATION_PROMPT, ANSWER_EVALUATION_PROMPT,
        HINT_GENERATION_PROMPT, CONCEPT_EXPLANATION_PROMPT,
        CODE_DEMO_PROMPT, PRACTICE_EXERCISE_PROMPT, SUMMARY_PROMPT,
        LEARNING_STATE_GUIDES, QUESTION_STAGES, LEVEL_GUIDES, DIFFICULTY_DESC,
    )

    prompts = [
        ("PROBLEM_ANALYSIS_PROMPT", PROBLEM_ANALYSIS_PROMPT),
        ("TEACHING_DECISION_PROMPT", TEACHING_DECISION_PROMPT),
        ("QUESTION_GENERATION_PROMPT", QUESTION_GENERATION_PROMPT),
        ("ANSWER_EVALUATION_PROMPT", ANSWER_EVALUATION_PROMPT),
        ("HINT_GENERATION_PROMPT", HINT_GENERATION_PROMPT),
        ("CONCEPT_EXPLANATION_PROMPT", CONCEPT_EXPLANATION_PROMPT),
        ("CODE_DEMO_PROMPT", CODE_DEMO_PROMPT),
        ("PRACTICE_EXERCISE_PROMPT", PRACTICE_EXERCISE_PROMPT),
        ("SUMMARY_PROMPT", SUMMARY_PROMPT),
    ]

    for name, prompt in prompts:
        assert isinstance(prompt, str) and len(prompt) > 0, f"{name} 为空"
        print(f"  ✅ {name}: {len(prompt)} chars")

    assert len(LEARNING_STATE_GUIDES) == 5
    assert len(QUESTION_STAGES) == 3
    assert len(LEVEL_GUIDES) == 3
    assert len(DIFFICULTY_DESC) == 5

    print("✅ 测试 6 通过\n")


async def main():
    print("[TEST] Socratic 2.0 Workflow Full Test")
    print("=" * 60)
    print()

    await test_state_definition()
    await test_schema_validation()
    await test_json_parser()
    await test_prompt_imports()
    await test_workflow_compile()
    await test_decision_engine()

    print("=" * 60)
    print("[DONE] All tests completed!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
