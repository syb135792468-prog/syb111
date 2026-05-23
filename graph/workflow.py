"""
graph/workflow.py - 软件杯A3 全流程智能学习工作流（最终稳定版）
- 统一 user_intent 字段，与 IntentAgent 完全对齐
- 路径规划结果自动合并到 state.learning_path，避免非法资源类型
- 所有节点安全合并状态，异常兜底完善
"""
from __future__ import annotations
import asyncio
import logging
from typing import TypedDict, List, Dict, Any, Optional
from functools import partial

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from agents.intent_agent import IntentAgent
from agents.profile_agent import ProfileAgent
from agents.quiz_agent import QuizAgent
from agents.code_agent import CodeAgent
from agents.doc_agent import DocAgent
from agents.mindmap_agent import MindmapAgent
from agents.video_agent import VideoAgent
from agents.path_agent import PathAgent
from agents.tutor_agent import TutorAgent
from agents.evaluation_agent import EvaluationAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# 注意：此 TypedDict 是 LangGraph StateGraph 专用的状态结构。
# 与 graph/state.py 的 WorkflowState (Pydantic BaseModel) 不同：
# - GraphState: LangGraph 运行时内部状态（TypedDict，LangGraph 要求）
# - WorkflowState: 业务层状态模型（Pydantic，序列化/校验/ORM互转）
# 两者字段保持同步，但服务于不同层次，不可合并。
class GraphState(TypedDict, total=False):
    user_id: Optional[str]
    chat_history: List[Dict[str, str]]
    profile_data: Dict[str, Any]
    learning_path: List[Dict[str, Any]]  # 路径规划结果存这里
    resource_list: List[Dict[str, Any]]
    current_step: str
    user_intent: Optional[str]            # 与所有Agent输出对齐
    updated_at: Optional[str]
    error_message: Optional[str]


_agents_cache: Optional[Dict[str, Any]] = None

def get_or_create_agents() -> Dict[str, Any]:
    global _agents_cache
    if _agents_cache is None:
        _agents_cache = {
            "intent": IntentAgent(),
            "profile": ProfileAgent(),
            "tutor": TutorAgent(use_llm=True),
            "quiz": QuizAgent(),
            "code": CodeAgent(),
            "doc": DocAgent(),
            "mindmap": MindmapAgent(),
            "video": VideoAgent(),
            "path": PathAgent(),
            "evaluation": EvaluationAgent(use_llm=True),
        }
        logger.info("✅ 所有智能体初始化完成")
    return _agents_cache


async def run_intent_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["intent"].process(last_msg, state)
        intent = result.get("user_intent", "tutoring")
        logger.info(f"🎯 识别用户意图: {intent}")
        return {**state, **result, "current_step": "intent"}
    except Exception as e:
        logger.error(f"❌ 意图识别失败: {e}", exc_info=True)
        return {**state, "user_intent": "tutoring", "current_step": "intent", "error_message": str(e)}

async def run_profile_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        result = await agents["profile"].process("", state)
        logger.info("📋 用户画像更新完成")
        return {**state, **result, "current_step": "profile"}
    except Exception as e:
        logger.error(f"❌ 画像更新失败: {e}", exc_info=True)
        return {**state, "profile_data": state.get("profile_data", {}), "current_step": "profile", "error_message": str(e)}

async def run_path_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        # PathAgent.process 返回 {"learning_path": [...], ...}
        result = await agents["path"].process("", state)
        logger.info("🛤️ 学习路径规划完成")
        # 只合并 learning_path 等非资源字段，避免向 resource_list 写入非法项目
        safe_result = {
            "learning_path": result.get("learning_path", []),
            "current_step": "path"
        }
        return {**state, **safe_result}
    except Exception as e:
        logger.error(f"❌ 路径规划失败: {e}", exc_info=True)
        return {**state, "learning_path": [], "current_step": "path", "error_message": str(e)}

async def run_tutor_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["tutor"].process(last_msg, state)
        logger.info("🧑‍🏫 智能辅导完成")
        return {**state, **result, "current_step": "tutor"}
    except Exception as e:
        logger.error(f"❌ 辅导失败: {e}", exc_info=True)
        msg = "抱歉，我暂时无法回答这个问题。请稍后重试或联系管理员。"
        new_chat = state.get("chat_history", []) + [{"role": "assistant", "content": msg}]
        return {**state, "chat_history": new_chat, "current_step": "tutor", "error_message": str(e)}

async def run_quiz_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        result = await agents["quiz"].process("", state)
        logger.info("📝 练习题生成完成")
        return {**state, **result, "current_step": "quiz"}
    except Exception as e:
        logger.error(f"❌ 出题失败: {e}", exc_info=True)
        return {**state, "current_step": "quiz", "error_message": str(e)}

async def run_evaluation_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        result = await agents["evaluation"].process("", state)
        logger.info("📊 学习效果评估完成")
        return {**state, **result, "current_step": "evaluation"}
    except Exception as e:
        logger.error(f"❌ 评估失败: {e}", exc_info=True)
        return {**state, "current_step": "evaluation", "error_message": str(e)}


async def run_code_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["code"].process(last_msg, state)
        logger.info("💻 代码资源生成完成")
        return {**state, **result, "current_step": "code"}
    except Exception as e:
        logger.error(f"❌ 代码生成失败: {e}", exc_info=True)
        return {**state, "current_step": "code", "error_message": str(e)}

async def run_doc_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["doc"].process(last_msg, state)
        logger.info("📄 文档资源生成完成")
        return {**state, **result, "current_step": "doc"}
    except Exception as e:
        logger.error(f"❌ 文档生成失败: {e}", exc_info=True)
        return {**state, "current_step": "doc", "error_message": str(e)}

async def run_mindmap_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["mindmap"].process(last_msg, state)
        logger.info("🧠 思维导图生成完成")
        return {**state, **result, "current_step": "mindmap"}
    except Exception as e:
        logger.error(f"❌ 思维导图生成失败: {e}", exc_info=True)
        return {**state, "current_step": "mindmap", "error_message": str(e)}

async def run_video_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["video"].process(last_msg, state)
        logger.info("🎬 视频资源生成完成")
        return {**state, **result, "current_step": "video"}
    except Exception as e:
        logger.error(f"❌ 视频生成失败: {e}", exc_info=True)
        return {**state, "current_step": "video", "error_message": str(e)}


async def run_resource_router(state: GraphState, agents: Dict) -> GraphState:
    """路由节点：不做任何处理，仅用于条件分发"""
    return state

def route_after_intent(state: GraphState) -> str:
    intent = state.get("user_intent", "tutoring")
    logger.info(f"🔀 意图路由: {intent}")
    if intent == "start_learning":
        return "profile_agent"
    if intent in ("ask_question", "tutoring"):
        return "tutor_agent"
    if intent == "do_quiz":
        return "quiz_agent"
    if intent == "view_path":
        return "path_agent"
    if intent == "generate_resource":
        return "resource_router"
    if intent == "evaluate":
        return "evaluation_agent"
    logger.warning(f"⚠️ 未知意图: {intent}，默认进入辅导模式")
    return "tutor_agent"


_RESOURCE_KEYWORDS = {
    "doc": ["文档", "doc", "讲解", "文章", "笔记"],
    "code": ["代码", "code", "示例", "案例", "程序"],
    "mindmap": ["思维导图", "mindmap", "脑图", "导图"],
    "video": ["视频", "video", "动画"],
}

def route_resource_type(state: GraphState) -> str:
    text = state["chat_history"][-1]["content"].lower()
    for rtype, keywords in _RESOURCE_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            logger.info(f"🔀 资源类型路由: {rtype}")
            return f"{rtype}_agent"
    logger.info("🔀 资源类型路由: quiz（默认）")
    return "quiz_agent"


def build_workflow() -> CompiledStateGraph:
    agents = get_or_create_agents()
    workflow = StateGraph(GraphState)

    workflow.add_node("intent_agent", partial(run_intent_agent, agents=agents))
    workflow.add_node("profile_agent", partial(run_profile_agent, agents=agents))
    workflow.add_node("path_agent", partial(run_path_agent, agents=agents))
    workflow.add_node("tutor_agent", partial(run_tutor_agent, agents=agents))
    workflow.add_node("quiz_agent", partial(run_quiz_agent, agents=agents))
    workflow.add_node("code_agent", partial(run_code_agent, agents=agents))
    workflow.add_node("doc_agent", partial(run_doc_agent, agents=agents))
    workflow.add_node("mindmap_agent", partial(run_mindmap_agent, agents=agents))
    workflow.add_node("video_agent", partial(run_video_agent, agents=agents))
    workflow.add_node("evaluation_agent", partial(run_evaluation_agent, agents=agents))
    workflow.add_node("resource_router", partial(run_resource_router, agents=agents))

    workflow.set_entry_point("intent_agent")

    workflow.add_conditional_edges(
        "intent_agent",
        route_after_intent,
        {
            "profile_agent": "profile_agent",
            "tutor_agent": "tutor_agent",
            "quiz_agent": "quiz_agent",
            "path_agent": "path_agent",
            "resource_router": "resource_router",
            "evaluation_agent": "evaluation_agent",
        }
    )

    # 资源生成路由：根据用户输入中的关键词分发到具体资源 Agent
    workflow.add_conditional_edges(
        "resource_router",
        route_resource_type,
        {
            "quiz_agent": "quiz_agent",
            "code_agent": "code_agent",
            "doc_agent": "doc_agent",
            "mindmap_agent": "mindmap_agent",
            "video_agent": "video_agent",
        }
    )

    # 核心闭环（仅 start_learning 会走此路径）
    workflow.add_edge("profile_agent", "path_agent")
    workflow.add_edge("path_agent", "tutor_agent")

    # 所有终端节点 → END
    workflow.add_edge("tutor_agent", END)
    workflow.add_edge("quiz_agent", END)
    workflow.add_edge("code_agent", END)
    workflow.add_edge("doc_agent", END)
    workflow.add_edge("mindmap_agent", END)
    workflow.add_edge("video_agent", END)
    workflow.add_edge("evaluation_agent", END)

    return workflow.compile()


async def run_full_workflow(user_message: str, user_id: str = "1"):
    app = build_workflow()
    initial_state: GraphState = {
        "user_id": user_id,
        "chat_history": [{"role": "user", "content": user_message}],
        "profile_data": {},
        "learning_path": [],
        "resource_list": [],
        "current_step": "start",
        "user_intent": None,
        "updated_at": None,
        "error_message": None,
    }
    logger.info("🚀 启动全流程工作流")
    final_state = await app.ainvoke(initial_state)

    print("\n" + "="*60)
    print("✅ 全流程执行完成！")
    print(f"🎯 最终识别意图: {final_state.get('user_intent')}")
    print(f"📍 执行步骤: {final_state.get('current_step')}")
    if final_state.get("learning_path"):
        print("🛤️ 您的学习路径：")
        for step in final_state.get("learning_path", []):
            print(f"  - {step}")
    if final_state.get("error_message"):
        print(f"⚠️ 异常信息: {final_state.get('error_message')}")
    if final_state.get("chat_history"):
        print(f"\n💬 系统回复:\n{final_state['chat_history'][-1]['content'][:200]}...")
    print("="*60)
    return final_state

if __name__ == "__main__":
    asyncio.run(run_full_workflow("我想学习Python循环", user_id="test_001"))