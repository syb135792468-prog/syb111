"""
graph/workflow.py - 全流程智能学习工作流（统一路由版）
- 单次 LLM 调用完成意图识别 + 资源类型判断 + 主题提取
- 删除硬编码关键词匹配，彻底解决答非所问问题
- 保留所有原有 Agent 功能
"""
from __future__ import annotations
import asyncio
import logging
from typing import TypedDict, List, Dict, Any, Optional
from functools import partial

from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph
from langgraph.constants import Send

from agents.unified_router_agent import UnifiedRouterAgent
from agents.quiz_agent import QuizAgent
from agents.code_agent import CodeAgent
from agents.doc_agent import DocAgent
from agents.mindmap_agent import MindmapAgent
from agents.video_agent import VideoAgent
from agents.path_agent import PathAgent
from agents.tutor_agent import TutorAgent
from agents.evaluation_agent import EvaluationAgent
from models.database import AsyncSessionLocal
from utils.behavior_tracker import behavior_tracker, BehaviorType
from utils.agent_helpers import match_knowledge_point
from models.profile import UserProfile
from sqlalchemy import select
from config.constants import (
    DEFAULT_INTENT, DEFAULT_CURRENT_STEP,
    INTENT_GENERATE_RESOURCE, INTENT_START_LEARNING, INTENT_ASK_QUESTION,
    INTENT_TUTORING, INTENT_DO_QUIZ, INTENT_VIEW_PATH, INTENT_EVALUATE,
    MILESTONE_COMPLETED_RESOURCES,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class GraphState(TypedDict, total=False):
    user_id: Optional[str]
    chat_history: List[Dict[str, str]]
    profile_data: Dict[str, Any]
    learning_path: List[Dict[str, Any]]
    resource_list: List[Dict[str, Any]]
    current_step: str
    user_intent: Optional[str]
    resource_type: Optional[str]
    topic: Optional[str]
    updated_at: Optional[str]
    error_message: Optional[str]


_agents_cache: Optional[Dict[str, Any]] = None

def get_or_create_agents() -> Dict[str, Any]:
    global _agents_cache
    if _agents_cache is None:
        _agents_cache = {
            "unified_router": UnifiedRouterAgent(),
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


# ============================================================
# 节点函数
# ============================================================

async def run_unified_router(state: GraphState, agents: Dict) -> GraphState:
    """统一路由：单次 LLM 调用完成意图+资源类型+主题+画像提取"""
    try:
        result = await agents["unified_router"].process(
            state["chat_history"][-1]["content"], state
        )
        logger.info(f"🎯 路由结果: intent={result.get('user_intent')}, resource_type={result.get('resource_type')}, topic={result.get('topic')}")
        # 画像更新数据（_profile_update）附加在结果中，由 chat.py 后台处理
        return {**state, **result, "current_step": "unified_router"}
    except Exception as e:
        logger.error(f"❌ 统一路由失败: {e}", exc_info=True)
        return {
            **state,
            "user_intent": DEFAULT_INTENT,
            "resource_type": None,
            "topic": "",
            "current_step": "unified_router",
            "error_message": str(e),
        }


async def run_path_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        result = await agents["path"].process("", state)
        logger.info("🛤️ 学习路径规划完成")
        safe_result = {"learning_path": result.get("learning_path", []), "current_step": "path"}
        return {**state, **safe_result}
    except Exception as e:
        logger.error(f"❌ 路径规划失败: {e}", exc_info=True)
        return {**state, "learning_path": [], "current_step": "path", "error_message": str(e)}


async def _save_progress(user_id: int, topic: str, status: str = "in_progress", score: float = None):
    """创建或更新知识点学习进度记录"""
    try:
        from models.progress import LearningProgress
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == user_id,
                    LearningProgress.topic == topic,
                    LearningProgress.is_active == True,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = LearningProgress(user_id=user_id, topic=topic)
                session.add(record)
            record.update_progress(status=status, score=score, duration=0)
            await session.commit()
    except Exception as e:
        logger.warning(f"⚠️ 进度记录跳过: {e}")


async def run_tutor_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        result = await agents["tutor"].process(last_msg, state)
        logger.info("🧑‍🏫 智能辅导完成")

        # 记录提问行为 + 进度
        uid = state.get("user_id")
        if uid and str(uid).isdigit():
            topic = state.get("topic") or ""
            kp = match_knowledge_point(topic) if topic else None
            await behavior_tracker.log(
                user_id=int(uid),
                behavior_type=BehaviorType.ASK_QUESTION,
                knowledge_point=kp,
            )
            if kp:
                await _save_progress(int(uid), kp, status="in_progress")

        return {**state, **result, "current_step": "tutor"}
    except Exception as e:
        logger.error(f"❌ 辅导失败: {e}", exc_info=True)
        msg = "抱歉，我暂时无法回答这个问题。请稍后重试或联系管理员。"
        new_chat = state.get("chat_history", []) + [{"role": "assistant", "content": msg}]
        return {**state, "chat_history": new_chat, "current_step": "tutor", "error_message": str(e)}


async def run_quiz_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        ctx = {**state, "topic": state.get("topic", "")}
        result = await agents["quiz"].process("", ctx)
        logger.info("📝 练习题生成完成")

        # 记录练习行为 + 进度
        uid = state.get("user_id")
        if uid and str(uid).isdigit():
            topic = state.get("topic") or ""
            kp = match_knowledge_point(topic) if topic else None
            await behavior_tracker.log(
                user_id=int(uid),
                behavior_type=BehaviorType.COMPLETE_QUIZ,
                knowledge_point=kp,
            )
            if kp:
                await _save_progress(int(uid), kp, status="completed", score=70.0)

            # 里程碑检测：连续完成N个资源后即时更新动力水平
            try:
                stats = await behavior_tracker.get_user_stats(int(uid), days=1)
                today_completed = stats.get("quizzes_completed", 0) + stats.get("resources_viewed", 0)
                if today_completed >= MILESTONE_COMPLETED_RESOURCES:
                    from agents.evaluation_agent import EvaluationAgent
                    eval_agent = agents.get("evaluation") or EvaluationAgent()
                    await eval_agent.update_motivation_on_milestone(int(uid))
            except Exception as milestone_err:
                logger.debug(f"里程碑检测跳过: {milestone_err}")

        return {**state, **result, "current_step": "quiz"}
    except Exception as e:
        logger.error(f"❌ 出题失败: {e}", exc_info=True)
        return {**state, "current_step": "quiz", "error_message": str(e)}


async def run_evaluation_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        result = await agents["evaluation"].process("", state)
        logger.info("📊 学习效果评估完成")

        # 持久化评估后的画像到数据库
        updated_profile = result.get("profile_data")
        user_id = state.get("user_id")
        if updated_profile and user_id:
            try:
                async with AsyncSessionLocal() as session:
                    uid = int(user_id) if str(user_id).isdigit() else None
                    if uid:
                        db_result = await session.execute(
                            select(UserProfile).where(UserProfile.user_id == uid)
                        )
                        profile = db_result.scalar_one_or_none()
                        if profile:
                            for key in ("weak_points", "mastered_points", "motivation_level",
                                        "knowledge_level", "learning_goal", "learning_style",
                                        "duration_preference", "current_topic"):
                                if key in updated_profile:
                                    setattr(profile, key, updated_profile[key])
                            from utils.api_helpers import get_current_utc_time
                            profile.updated_at = get_current_utc_time()
                            await session.commit()
                            logger.info("✅ 评估结果已持久化到数据库")
            except Exception as db_err:
                logger.warning(f"⚠️ 评估画像持久化失败（不影响流程）: {db_err}")

        return {**state, **result, "current_step": "evaluation"}
    except Exception as e:
        logger.error(f"❌ 评估失败: {e}", exc_info=True)
        return {**state, "current_step": "evaluation", "error_message": str(e)}


async def run_code_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        ctx = {**state, "topic": state.get("topic", "")}
        result = await agents["code"].process(last_msg, ctx)
        logger.info("💻 代码资源生成完成")
        uid = state.get("user_id")
        topic = state.get("topic") or ""
        if uid and str(uid).isdigit() and topic:
            kp = match_knowledge_point(topic)
            if kp:
                await _save_progress(int(uid), kp, status="in_progress")
        return {**state, **result, "current_step": "code"}
    except Exception as e:
        logger.error(f"❌ 代码生成失败: {e}", exc_info=True)
        return {**state, "current_step": "code", "error_message": str(e)}


async def run_doc_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        ctx = {**state, "topic": state.get("topic", "")}
        result = await agents["doc"].process(last_msg, ctx)
        logger.info("📄 文档资源生成完成")
        uid = state.get("user_id")
        topic = state.get("topic") or ""
        if uid and str(uid).isdigit() and topic:
            kp = match_knowledge_point(topic)
            if kp:
                await _save_progress(int(uid), kp, status="in_progress")
        return {**state, **result, "current_step": "doc"}
    except Exception as e:
        logger.error(f"❌ 文档生成失败: {e}", exc_info=True)
        return {**state, "current_step": "doc", "error_message": str(e)}


async def run_mindmap_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        ctx = {**state, "topic": state.get("topic", "")}
        result = await agents["mindmap"].process(last_msg, ctx)
        logger.info("🧠 思维导图生成完成")
        uid = state.get("user_id")
        topic = state.get("topic") or ""
        if uid and str(uid).isdigit() and topic:
            kp = match_knowledge_point(topic)
            if kp:
                await _save_progress(int(uid), kp, status="in_progress")
        return {**state, **result, "current_step": "mindmap"}
    except Exception as e:
        logger.error(f"❌ 思维导图生成失败: {e}", exc_info=True)
        return {**state, "current_step": "mindmap", "error_message": str(e)}


async def run_video_agent(state: GraphState, agents: Dict) -> GraphState:
    try:
        last_msg = state["chat_history"][-1]["content"]
        ctx = {**state, "topic": state.get("topic", "")}
        result = await agents["video"].process(last_msg, ctx)
        logger.info("🎬 视频资源生成完成")
        uid = state.get("user_id")
        topic = state.get("topic") or ""
        if uid and str(uid).isdigit() and topic:
            kp = match_knowledge_point(topic)
            if kp:
                await _save_progress(int(uid), kp, status="in_progress")
        return {**state, **result, "current_step": "video"}
    except Exception as e:
        logger.error(f"❌ 视频生成失败: {e}", exc_info=True)
        return {**state, "current_step": "video", "error_message": str(e)}


# ============================================================
# 路由逻辑
# ============================================================

def route_after_profile(state: GraphState) -> str:
    """统一路由：根据 user_intent 和 resource_type 决定下一步"""
    intent = state.get("user_intent", DEFAULT_INTENT)
    resource_type = state.get("resource_type")

    logger.info(f"🔀 路由分发: intent={intent}, resource_type={resource_type}")

    if intent == INTENT_GENERATE_RESOURCE and resource_type:
        target = f"{resource_type}_agent"
        logger.info(f"🔀 → 资源生成: {target}")
        return target

    intent_map = {
        INTENT_START_LEARNING: "path_agent",
        INTENT_ASK_QUESTION: "tutor_agent",
        INTENT_TUTORING: "tutor_agent",
        INTENT_DO_QUIZ: "quiz_agent",
        INTENT_VIEW_PATH: "path_agent",
        INTENT_EVALUATE: "evaluation_agent",
    }
    target = intent_map.get(intent, "tutor_agent")
    logger.info(f"🔀 → {target}")
    return target


# ============================================================
# 工作流构建
# ============================================================

def build_workflow() -> CompiledStateGraph:
    agents = get_or_create_agents()
    workflow = StateGraph(GraphState)

    # 注册节点（画像更新已移至路由Agent内部+后台异步，不占用工作流）
    workflow.add_node("unified_router", partial(run_unified_router, agents=agents))
    workflow.add_node("path_agent", partial(run_path_agent, agents=agents))
    workflow.add_node("tutor_agent", partial(run_tutor_agent, agents=agents))
    workflow.add_node("quiz_agent", partial(run_quiz_agent, agents=agents))
    workflow.add_node("code_agent", partial(run_code_agent, agents=agents))
    workflow.add_node("doc_agent", partial(run_doc_agent, agents=agents))
    workflow.add_node("mindmap_agent", partial(run_mindmap_agent, agents=agents))
    workflow.add_node("video_agent", partial(run_video_agent, agents=agents))
    workflow.add_node("evaluation_agent", partial(run_evaluation_agent, agents=agents))

    # 入口
    workflow.set_entry_point("unified_router")

    # 统一路由 → 条件分发（不再经过 profile_agent）
    workflow.add_conditional_edges(
        "unified_router",
        route_after_profile,
        {
            "tutor_agent": "tutor_agent",
            "quiz_agent": "quiz_agent",
            "path_agent": "path_agent",
            "evaluation_agent": "evaluation_agent",
            "code_agent": "code_agent",
            "doc_agent": "doc_agent",
            "mindmap_agent": "mindmap_agent",
            "video_agent": "video_agent",
        }
    )

    # start_learning 路径：path_agent 后继续到 tutor_agent
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

    # 从数据库加载用户画像（与 chat 路由行为一致）
    profile_data = {}
    try:
        async with AsyncSessionLocal() as session:
            uid = int(user_id) if user_id.isdigit() else None
            if uid:
                result = await session.execute(
                    select(UserProfile).where(UserProfile.user_id == uid)
                )
                profile = result.scalar_one_or_none()
                if profile:
                    profile_data = {
                        "knowledge_level": profile.knowledge_level,
                        "learning_style": profile.learning_style,
                        "learning_goal": profile.learning_goal,
                        "duration_preference": profile.duration_preference,
                        "weak_points": profile.weak_points or [],
                        "mastered_points": profile.mastered_points or [],
                        "motivation_level": profile.motivation_level,
                        "current_topic": profile.current_topic,
                    }
    except Exception as e:
        logger.warning(f"⚠️ 加载画像失败，使用空画像: {e}")

    initial_state: GraphState = {
        "user_id": user_id,
        "chat_history": [{"role": "user", "content": user_message}],
        "profile_data": profile_data,
        "learning_path": [],
        "resource_list": [],
        "current_step": DEFAULT_CURRENT_STEP,
        "user_intent": None,
        "resource_type": None,
        "topic": None,
        "updated_at": None,
        "error_message": None,
    }
    logger.info("🚀 启动全流程工作流")
    final_state = await app.ainvoke(initial_state)

    print("\n" + "="*60)
    print("✅ 全流程执行完成！")
    print(f"🎯 最终识别意图: {final_state.get('user_intent')}")
    print(f"📦 资源类型: {final_state.get('resource_type')}")
    print(f"📌 提取主题: {final_state.get('topic')}")
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


# ============================================================
# 深度思考模式子图（并行多Agent协作）
# ============================================================

class DeepThinkingState(TypedDict, total=False):
    """深度思考模式状态"""
    user_id: str
    message: str
    profile_data: Dict[str, Any]
    topic: str
    # 各 Agent 的结果
    doc_result: Dict[str, Any]
    code_result: Dict[str, Any]
    quiz_result: Dict[str, Any]
    eval_result: Dict[str, Any]
    path_result: Dict[str, Any]
    # 最终整合结果
    final_response: str
    # 收集所有 Agent 产生的资源（用于 SSE 资源事件发射）
    resource_list: List[Dict[str, Any]]
    # 实时思维过程队列（Agent → SSE 生成器）
    thinking_queue: Any  # asyncio.Queue, 用 Any 避免 TypedDict 限制


def deep_start_node(state: DeepThinkingState) -> Dict[str, Any]:
    """扇出节点：并行分发到所有5个Agent"""
    return {}


def route_to_all_agents(state: DeepThinkingState) -> list:
    """使用 Send API 并行分发到所有Agent，并注入共享思维队列"""
    import asyncio
    # 创建共享的思维过程队列（所有 Agent 节点往里写，SSE 生成器往外读）
    if "thinking_queue" not in state or state["thinking_queue"] is None:
        state["thinking_queue"] = asyncio.Queue()
    return [
        Send("deep_doc_agent", state),
        Send("deep_code_agent", state),
        Send("deep_quiz_agent", state),
        Send("deep_eval_agent", state),
        Send("deep_path_agent", state),
    ]


async def _emit_thinking(state: DeepThinkingState, text: str):
    """向共享队列发送思维过程事件"""
    queue = state.get("thinking_queue")
    if queue:
        await queue.put({"type": "thinking", "text": text})


async def deep_doc_node(state: DeepThinkingState) -> Dict[str, Any]:
    """DocAgent 包装节点（带实时思维过程）"""
    agents = get_or_create_agents()
    topic = state.get("topic", "")
    ctx = {
        "profile_data": state.get("profile_data", {}),
        "topic": topic,
        "resource_list": [],
    }
    try:
        await _emit_thinking(state, f"📄 DocAgent 正在为「{topic}」检索知识库...")
        result = await agents["doc"].process(state["message"], ctx)
        await _emit_thinking(state, f"📄 DocAgent 已生成概念讲解文档")
        return {"doc_result": result}
    except Exception as e:
        logger.error(f"❌ 深度模式 DocAgent 失败: {e}")
        await _emit_thinking(state, f"📄 DocAgent 遇到问题: {str(e)[:50]}")
        return {"doc_result": {"resource_list": [], "error": str(e)}}


async def deep_code_node(state: DeepThinkingState) -> Dict[str, Any]:
    """CodeAgent 包装节点（带实时思维过程）"""
    agents = get_or_create_agents()
    topic = state.get("topic", "")
    ctx = {
        "profile_data": state.get("profile_data", {}),
        "topic": topic,
        "resource_list": [],
    }
    try:
        await _emit_thinking(state, f"💻 CodeAgent 正在为「{topic}」编写代码示例...")
        result = await agents["code"].process(state["message"], ctx)
        await _emit_thinking(state, f"💻 CodeAgent 已生成代码示例")
        return {"code_result": result}
    except Exception as e:
        logger.error(f"❌ 深度模式 CodeAgent 失败: {e}")
        await _emit_thinking(state, f"💻 CodeAgent 遇到问题: {str(e)[:50]}")
        return {"code_result": {"resource_list": [], "error": str(e)}}


async def deep_quiz_node(state: DeepThinkingState) -> Dict[str, Any]:
    """QuizAgent 包装节点（带实时思维过程）"""
    agents = get_or_create_agents()
    topic = state.get("topic", "")
    ctx = {
        "profile_data": state.get("profile_data", {}),
        "topic": topic,
        "resource_list": [],
    }
    try:
        await _emit_thinking(state, f"✏️ QuizAgent 正在设计配套练习题...")
        result = await agents["quiz"].process("", ctx)
        await _emit_thinking(state, f"✏️ QuizAgent 已生成练习题")
        return {"quiz_result": result}
    except Exception as e:
        logger.error(f"❌ 深度模式 QuizAgent 失败: {e}")
        await _emit_thinking(state, f"✏️ QuizAgent 遇到问题: {str(e)[:50]}")
        return {"quiz_result": {"resource_list": [], "error": str(e)}}


async def deep_eval_node(state: DeepThinkingState) -> Dict[str, Any]:
    """EvaluationAgent 包装节点（带实时思维过程）"""
    agents = get_or_create_agents()
    ctx = {
        "profile_data": state.get("profile_data", {}),
        "chat_history": [{"role": "user", "content": state["message"]}],
        "resource_list": [],
    }
    try:
        await _emit_thinking(state, f"🧐 EvaluationAgent 正在分析常见误区...")
        result = await agents["evaluation"].process("", ctx)
        await _emit_thinking(state, f"🧐 EvaluationAgent 已完成误区分析")
        return {"eval_result": result}
    except Exception as e:
        logger.error(f"❌ 深度模式 EvaluationAgent 失败: {e}")
        await _emit_thinking(state, f"🧐 EvaluationAgent 遇到问题: {str(e)[:50]}")
        return {"eval_result": {"error": str(e)}}


async def deep_path_node(state: DeepThinkingState) -> Dict[str, Any]:
    """PathAgent 包装节点（带实时思维过程）"""
    agents = get_or_create_agents()
    ctx = {
        "profile_data": state.get("profile_data", {}),
    }
    try:
        await _emit_thinking(state, f"🛤️ PathAgent 正在规划学习路径...")
        result = await agents["path"].process("", ctx)
        await _emit_thinking(state, f"🛤️ PathAgent 已规划学习路径")
        return {"path_result": result}
    except Exception as e:
        logger.error(f"❌ 深度模式 PathAgent 失败: {e}")
        await _emit_thinking(state, f"🛤️ PathAgent 遇到问题: {str(e)[:50]}")
        return {"path_result": {"learning_path": [], "error": str(e)}}


def _extract_agent_content(result: Dict[str, Any], agent_type: str) -> str:
    """从 Agent 返回结果中提取文本内容"""
    if not result or result.get("error"):
        return ""

    if agent_type in ("doc", "code", "quiz"):
        resource_list = result.get("resource_list", [])
        if resource_list:
            last_resource = resource_list[-1]
            if hasattr(last_resource, "content"):
                return last_resource.content
            elif isinstance(last_resource, dict):
                return last_resource.get("content", "")
    elif agent_type == "eval":
        chat_history = result.get("chat_history", [])
        if chat_history and chat_history[-1].get("role") == "assistant":
            return chat_history[-1]["content"]
    elif agent_type == "path":
        learning_path = result.get("learning_path", [])
        if learning_path:
            lines = ["### 🎯 推荐学习路径\n"]
            for step in learning_path:
                order = step.get("order", "")
                kp = step.get("knowledge_point", "")
                est = step.get("estimated_time_min", "")
                step_type = "复习" if step.get("type") == "review" else "新学"
                lines.append(f"{order}. **{kp}** — 预计 {est} 分钟（{step_type}）")
            return "\n".join(lines)
    return ""


async def deep_aggregator_node(state: DeepThinkingState) -> Dict[str, Any]:
    """结果整合节点：拼接所有Agent的输出"""
    topic = state.get("topic", "Python")
    final_response = f"# 🎓 深度解析：{topic}\n\n"

    doc_content = _extract_agent_content(state.get("doc_result", {}), "doc")
    if doc_content:
        final_response += f"## 📚 概念讲解\n\n{{{{card:doc}}}}\n\n{doc_content}\n\n"

    code_content = _extract_agent_content(state.get("code_result", {}), "code")
    if code_content:
        final_response += f"## 💻 代码示例\n\n{{{{card:code}}}}\n\n```python\n{code_content}\n```\n\n"

    eval_content = _extract_agent_content(state.get("eval_result", {}), "eval")
    if eval_content:
        final_response += f"## ⚠️ 常见误区与学习建议\n\n{eval_content}\n\n"

    quiz_content = _extract_agent_content(state.get("quiz_result", {}), "quiz")
    if quiz_content:
        final_response += f"## ✏️ 小试牛刀\n\n{{{{card:quiz}}}}\n\n{quiz_content}\n\n"

    path_content = _extract_agent_content(state.get("path_result", {}), "path")
    if path_content:
        final_response += f"## 🛤️ 下一步学习\n\n{path_content}\n\n"

    final_response += "---\n\n*本回答由 5 个智能 Agent 协作生成，基于权威教材内容，确保知识准确无误。*"

    # 收集所有 Agent 产生的资源，用于前端内联卡片渲染
    resource_list: List[Dict[str, Any]] = []
    for result_key in ["doc_result", "code_result", "quiz_result", "eval_result", "path_result"]:
        result = state.get(result_key, {})
        if result and isinstance(result, dict):
            resources = result.get("resource_list", [])
            for r in resources:
                if hasattr(r, "model_dump"):
                    resource_list.append(r.model_dump())
                elif isinstance(r, dict):
                    resource_list.append(r)

    return {"final_response": final_response, "resource_list": resource_list}


def build_deep_thinking_workflow() -> CompiledStateGraph:
    """构建深度思考子图（并行多Agent协作）"""
    workflow = StateGraph(DeepThinkingState)

    workflow.add_node("deep_start", deep_start_node)
    workflow.add_node("deep_doc_agent", deep_doc_node)
    workflow.add_node("deep_code_agent", deep_code_node)
    workflow.add_node("deep_quiz_agent", deep_quiz_node)
    workflow.add_node("deep_eval_agent", deep_eval_node)
    workflow.add_node("deep_path_agent", deep_path_node)
    workflow.add_node("deep_aggregator", deep_aggregator_node)

    workflow.set_entry_point("deep_start")
    workflow.add_conditional_edges("deep_start", route_to_all_agents)
    workflow.add_edge("deep_doc_agent", "deep_aggregator")
    workflow.add_edge("deep_code_agent", "deep_aggregator")
    workflow.add_edge("deep_quiz_agent", "deep_aggregator")
    workflow.add_edge("deep_eval_agent", "deep_aggregator")
    workflow.add_edge("deep_path_agent", "deep_aggregator")
    workflow.add_edge("deep_aggregator", END)

    return workflow.compile()


if __name__ == "__main__":
    asyncio.run(run_full_workflow("我想学习Python循环", user_id="test_001"))
