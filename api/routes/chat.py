"""
api/routes/chat.py - 智能辅导对话接口（最终提交版）
- ✅ 直接迭代 LangGraph astream 生成器
- ✅ 客户端断开立即取消流
- ✅ 标准 SSE 格式，打字效果可配置
- ✅ 请求 ID 全链路日志追踪
- ✅ 智能字段过滤，轻量传输
- ✅ 修复所有潜在边缘情况
"""
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Optional, Any, Tuple
import asyncio
import uuid
import contextvars

from langgraph.types import Command

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    ChatRequest,
    SocraticChatRequest,
    BaseResponse,
    ChatResponseData,
    StreamEvent,
    ContentBlockStartData,
    ContentBlockDeltaData,
    ContentBlockStopData,
)
from utils.content_blocks import (
    parse_response_to_blocks,
    build_resource_map,
    content_blocks_to_flat_text,
    legacy_to_content_blocks,
)
from api.routes.auth import get_current_user
from models.user import User
from models.chat_message import ChatMessage
from models.conversation import Conversation
from models.database import get_db
from models.resource import Resource
from graph.workflow import build_workflow, build_deep_thinking_workflow
from utils.logger import get_logger
from config.settings import settings
from config.constants import (
    DEFAULT_RECURSION_LIMIT, TYPING_CHUNK_SIZE, TYPING_DELAY_MS,
    SYNC_CHAT_TIMEOUT_SEC, HTTP_OK, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT,
    CHAT_HISTORY_LOAD_LIMIT, CONVERSATION_TITLE_MAX_LENGTH, DEFAULT_CONVERSATION_TITLE, DEFAULT_CURRENT_STEP,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_REQUEST_TIMEOUT,
    MSG_CHAT_HISTORY_CLEARED,
)

request_id_var = contextvars.ContextVar("request_id", default="unknown")

router = APIRouter(prefix="/chat", tags=["智能辅导"])
logger = get_logger(__name__, task_id="chat_api")

# ---------- 工作流单例 ----------
_workflow: Optional[Any] = None
_workflow_init_lock = asyncio.Lock()

_deep_workflow: Optional[Any] = None

_socratic_workflow: Optional[Any] = None


async def get_workflow() -> Any:
    """获取工作流实例（单例模式，开发环境自动重建）"""
    global _workflow
    if _workflow is None:
        async with _workflow_init_lock:
            if _workflow is None:
                _workflow = build_workflow()
                logger.info("✅ LangGraph 工作流初始化成功")
    return _workflow


async def get_deep_workflow() -> Any:
    """获取深度思考工作流实例"""
    global _deep_workflow
    if _deep_workflow is None:
        _deep_workflow = build_deep_thinking_workflow()
        logger.info("✅ 深度思考工作流初始化成功")
    return _deep_workflow


async def get_socratic_workflow() -> Any:
    """获取苏格拉底导学工作流实例"""
    global _socratic_workflow
    if _socratic_workflow is None:
        from agents.socratic_workflow import get_socratic_workflow as _build
        _socratic_workflow = await _build()
        logger.info("✅ 苏格拉底导学工作流初始化成功")
    return _socratic_workflow


# ---------- 辅助函数 ----------
def build_initial_state(
    req: ChatRequest,
    profile_data: Optional[dict] = None,
    recent_history: Optional[list] = None,
) -> dict:
    """构建工作流初始状态，与 graph/state.py 完全对齐"""
    # 构建对话历史：历史消息 + 当前用户消息
    chat_history = (recent_history or []) + [{"role": "user", "content": req.message}]

    return {
        "user_id": req.user_id,
        "chat_history": chat_history,
        "profile_data": profile_data or {},
        "learning_path": [],
        "resource_list": [],
        "current_step": DEFAULT_CURRENT_STEP,
        "user_intent": None,
        "resource_type": None,
        "topic": None,
        "updated_at": None,
        "error_message": None,
    }


async def load_user_context(user_id: int, conversation_id: Optional[int], db: AsyncSession) -> tuple:
    """
    从数据库加载用户画像和对话历史，实现跨会话记忆。
    返回 (profile_data, recent_history)
    """
    # 1. 加载用户画像
    from models.profile import UserProfile
    profile_result = await db.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = profile_result.scalar_one_or_none()

    profile_data = {}
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
            "last_study_at": profile.last_study_at.isoformat() if profile.last_study_at else None,
        }

    # 2. 加载最近对话历史（最多20条，用于上下文连贯）
    recent_history = []
    logger.info(f"🔍 Loading context: user_id={user_id}, conversation_id={conversation_id}")
    if conversation_id:
        history_query = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(CHAT_HISTORY_LOAD_LIMIT)
        )
    else:
        history_query = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(CHAT_HISTORY_LOAD_LIMIT)
        )

    history_result = await db.execute(history_query)
    history_msgs = history_result.scalars().all()

    # 反转为时间正序，转为工作流格式
    for msg in reversed(history_msgs):
        recent_history.append({"role": msg.role, "content": msg.content})

    logger.info(f"📚 加载了 {len(recent_history)} 条历史消息")

    return profile_data, recent_history


async def _persist_profile(db: AsyncSession, user_id: int, profile_data: dict, request_id: str = "unknown"):
    """将工作流更新后的画像持久化到数据库"""
    try:
        from models.profile import UserProfile
        from utils.api_helpers import get_current_utc_time

        uid = int(user_id) if str(user_id).isdigit() else None
        if not uid:
            return

        result = await db.execute(
            select(UserProfile).where(UserProfile.user_id == uid)
        )
        profile = result.scalar_one_or_none()
        if profile:
            for key in ("knowledge_level", "learning_goal", "learning_style",
                        "duration_preference", "weak_points", "mastered_points",
                        "motivation_level", "current_topic"):
                if key in profile_data and profile_data[key] is not None:
                    setattr(profile, key, profile_data[key])
            profile.updated_at = get_current_utc_time()
            await db.commit()
            logger.info(f"✅ 画像已持久化到数据库 | user_id={uid}", extra={"request_id": request_id})
    except Exception as e:
        logger.warning(f"⚠️ 画像持久化失败（不影响流程）: {e}", extra={"request_id": request_id})


async def _sync_profile_to_progress(bg_db: AsyncSession, user_id: int, profile_update: dict, request_id: str):
    """将画像中的 mastered_points/weak_points 同步写入 learning_progress 表"""
    try:
        from models.progress import LearningProgress
        from utils.knowledge_base import normalize_to_backend

        uid = int(user_id) if str(user_id).isdigit() else None
        if not uid:
            return

        mastered_points = profile_update.get("mastered_points", [])
        weak_points = profile_update.get("weak_points", [])

        for point in mastered_points:
            std = normalize_to_backend(point)
            if not std:
                continue
            result = await bg_db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.topic == std,
                    LearningProgress.is_active == True,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = LearningProgress(user_id=uid, topic=std)
                bg_db.add(record)
            record.update_progress(status="completed", score=100.0, duration=0)

        for point in weak_points:
            std = normalize_to_backend(point)
            if not std:
                continue
            result = await bg_db.execute(
                select(LearningProgress).where(
                    LearningProgress.user_id == uid,
                    LearningProgress.topic == std,
                    LearningProgress.is_active == True,
                )
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = LearningProgress(user_id=uid, topic=std)
                bg_db.add(record)
            record.update_progress(status="in_progress", score=20.0, duration=0)

        logger.info(f"✅ 画像->进度同步完成 | user_id={uid}", extra={"request_id": request_id})
    except Exception as e:
        logger.warning(f"⚠️ 画像->进度同步失败（不影响流程）: {e}", extra={"request_id": request_id})


async def _sync_topic_to_progress(bg_db: AsyncSession, user_id: int, topic: str, request_id: str):
    """将对话主题作为知识点进度记录写入 learning_progress 表"""
    try:
        from models.progress import LearningProgress
        from utils.agent_helpers import match_knowledge_point

        uid = int(user_id) if str(user_id).isdigit() else None
        if not uid or not topic:
            return

        kp = match_knowledge_point(topic)
        if not kp:
            return

        result = await bg_db.execute(
            select(LearningProgress).where(
                LearningProgress.user_id == uid,
                LearningProgress.topic == kp,
                LearningProgress.is_active == True,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = LearningProgress(user_id=uid, topic=kp)
            bg_db.add(record)
        record.update_progress(status="in_progress", duration=0)
        logger.info(f"✅ 主题进度同步: {kp}", extra={"request_id": request_id})
    except Exception as e:
        logger.warning(f"⚠️ 主题进度同步失败: {e}", extra={"request_id": request_id})


async def _sync_topic_to_progress_task(user_id: int, topic: str, request_id: str):
    """独立的后台任务：仅同步主题到进度表"""
    try:
        from models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            await _sync_topic_to_progress(bg_db, user_id, topic, request_id)
            await bg_db.commit()
    except Exception as e:
        logger.warning(f"⚠️ 主题进度同步任务失败: {e}", extra={"request_id": request_id})


async def _background_profile_update(user_id: int, profile_update: dict, raw_output: dict, confidence: float, request_id: str, topic: str = ""):
    """后台异步更新画像，不阻塞主流程"""
    try:
        from models.database import AsyncSessionLocal
        from models.profile import ProfileChangeLog
        from utils.api_helpers import get_current_utc_time

        async with AsyncSessionLocal() as bg_db:
            # 持久化画像字段
            await _persist_profile(bg_db, user_id, profile_update, request_id)

            # 同步 mastered_points/weak_points 到 learning_progress 表
            await _sync_profile_to_progress(bg_db, user_id, profile_update, request_id)

            # 将本次对话主题同步到 progress 表（确保雷达图有数据）
            if topic:
                await _sync_topic_to_progress(bg_db, user_id, topic, request_id)

            # 写入审计日志
            log_entry = ProfileChangeLog(
                user_id=user_id,
                changed_fields=raw_output,
                source="llm",
                raw_llm_output=raw_output,
                confidence=confidence,
            )
            bg_db.add(log_entry)
            await bg_db.commit()
            logger.info(f"✅ 后台画像更新完成 | user_id={user_id}", extra={"request_id": request_id})
    except Exception as e:
        logger.warning(f"⚠️ 后台画像更新失败: {e}", extra={"request_id": request_id})


async def _fast_chat_handler(
    request: ChatRequest,
    user_id: str,
    profile_data: dict,
    recent_history: list,
    collected_reply_ref: list,
    content_blocks_ref: list,
    request_id: str,
) -> AsyncGenerator[str, None]:
    """
    快速模式优化处理器：
    - 直接 RAG + Tutor 流式输出（1-2s 首字符）
    - 后台异步调用 UnifiedRouterAgent 分析画像（不阻塞回答）
    - LLM 流结束后，若检测到 generate_resource 意图，生成资源并发射 SSE 事件
    """
    import time as _time
    from graph.workflow import get_or_create_agents
    from config.constants import DEFAULT_RAG_TOP_K, TUTOR_HISTORY_WINDOW
    from utils.agent_helpers import get_profile_from_context

    agents = get_or_create_agents()
    message = request.message
    topic = message.strip()
    t0 = _time.monotonic()
    print(f"⚡ [FAST-PERF] 快速模式开始: {message[:30]}...", flush=True)

    # ========== 阶段1：仅 RAG 检索（跳过 Router，节省 7-8s） ==========
    rag_context = ""
    try:
        tutor_agent = agents["tutor"]
        if tutor_agent.vector_db:
            docs = await tutor_agent.vector_db.query(query_text=message, top_k=1)
            if docs:
                rag_context = docs[0]["content"][:300]
    except Exception as e:
        logger.warning(f"⚠️ 快速模式RAG检索失败: {e}", extra={"request_id": request_id})

    t1 = _time.monotonic()
    print(f"⚡ [FAST-PERF] RAG完成: {(t1-t0)*1000:.0f}ms, {'有结果' if rag_context else '无结果'}", flush=True)

    # 共享引用：后台分析结果（intent/resource_type/topic），供资源生成使用
    bg_result_ref: Dict[str, Any] = {"intent": None, "resource_type": None, "topic": None, "done": False}
    # 当前 text block 的 ID（流式追踪用）
    current_block_id_ref: list = [None]

    # 后台异步：LLM 分析用户输入 → 画像更新 + 主题进度同步（不阻塞回答）
    async def _background_llm_analyze():
        """后台异步调用 UnifiedRouterAgent 分析用户输入，更新画像"""
        from models.database import AsyncSessionLocal
        try:
            router_result = await agents["unified_router"].process(
                message,
                {"profile_data": profile_data, "chat_history": recent_history},
            )
            profile_update = router_result.get("_profile_update", {}) or {}
            raw_output = router_result.get("_profile_raw_output", {}) or {}
            confidence = router_result.get("_profile_confidence", 0.0) or 0.0

            # 存储意图分析结果，供后续资源生成
            bg_result_ref["intent"] = router_result.get("user_intent")
            bg_result_ref["resource_type"] = router_result.get("resource_type")
            bg_result_ref["topic"] = router_result.get("topic", topic)

            if profile_update or topic:
                await _background_profile_update(
                    int(user_id), profile_update, raw_output, confidence, request_id, topic=topic
                )
                logger.info(
                    f"✅ [FAST-PROFILE] 后台画像分析完成: {profile_update}",
                    extra={"request_id": request_id},
                )
            else:
                # 仅同步主题到进度表
                async with AsyncSessionLocal() as bg_db:
                    if topic:
                        await _sync_topic_to_progress(bg_db, user_id, topic, request_id)
                    await bg_db.commit()
        except Exception as e:
            logger.warning(f"⚠️ [FAST-PROFILE] 后台画像分析失败: {e}", extra={"request_id": request_id})
        finally:
            bg_result_ref["done"] = True

    bg_task = asyncio.create_task(_background_llm_analyze())

    # ========== 阶段2：直接调用 TutorAgent LLM（跳过 LangGraph） ==========
    try:
        # 构建用户画像文本
        profile = get_profile_from_context({"profile_data": profile_data})
        profile_text = ""
        if profile:
            level_map = {"beginner": "零基础初学者", "intermediate": "有一定基础", "advanced": "进阶学习者"}
            goal_map = {"exam": "考试备考", "interest": "兴趣学习", "employment": "就业求职", "competition": "竞赛提升"}
            style_map = {"visual": "视觉型（喜欢看图/视频）", "auditory": "听觉型（喜欢听讲解）", "kinesthetic": "动手型（喜欢练习）", "mixed": "混合型"}
            profile_text = f"""
【用户画像】
- 水平：{level_map.get(profile.get('knowledge_level', ''), '未知')}
- 目标：{goal_map.get(profile.get('learning_goal', ''), '未知')}
- 风格：{style_map.get(profile.get('learning_style', ''), '未知')}
- 薄弱点：{', '.join(profile.get('weak_points', [])) or '暂无'}
- 已掌握：{', '.join(profile.get('mastered_points', [])) or '暂无'}
"""

        # 构建对话历史文本
        chat_history = recent_history + [{"role": "user", "content": message}]
        recent = chat_history[-TUTOR_HISTORY_WINDOW:]
        history_text = "\n".join(
            f"{'学生' if m['role'] == 'user' else '老师'}: {m['content']}" for m in recent
        )

        # 精简 Prompt（快速模式专用，减少首token延迟）
        rag_section = f"\n参考知识：{rag_context}" if rag_context else ""

        # A/B 实验：教学模式变体影响 prompt
        _teaching_variant = None
        try:
            from ai.experiment_engine import experiment_engine
            from models.database import AsyncSessionLocal as _SessionLocal
            async with _SessionLocal() as _exp_db:
                _tc = await experiment_engine.get_variant_config(
                    int(user_id), "teaching_mode", _exp_db
                )
            if _tc:
                _teaching_variant = _tc.get("prompt_style")
        except Exception:
            pass

        if _teaching_variant == "guided":
            # 苏格拉底式引导 prompt：提问引导而非直接给答案
            system_prompt = (
                f"你是Python一对一辅导老师，采用苏格拉底式教学法。"
                f"不要直接给出答案，而是通过提问引导学生思考，帮助他们自己发现答案。"
                f"如果学生答错了，给出提示而非正确答案，让学生继续尝试。"
                f"用通俗易懂的中文交流。{rag_section}"
            )
        else:
            system_prompt = f"你是Python一对一辅导老师。用通俗易懂的中文回答，可附带简单示例。{rag_section}"
        user_prompt = message

        t2 = _time.monotonic()
        print(f"⚡ [FAST-PERF] Prompt构建完成: {(t2-t1)*1000:.0f}ms", flush=True)

        # 流式调用 LLM
        tutor = agents["tutor"]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        collected_reply_ref[0] = ""
        first_token_time = None
        chunk_count = 0
        first_token_emitted = False

        # 快速模式直接用 DeepSeek（首token 1.4s vs MiMo 5.2s）
        from config.model_config import DEEPSEEK_MODEL_CONFIG
        from openai import AsyncOpenAI
        ds_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_MODEL_CONFIG.base_url,
            timeout=30,
        )

        stream = await ds_client.chat.completions.create(
            model=DEEPSEEK_MODEL_CONFIG.model_name,
            messages=messages,
            temperature=0.7,
            max_tokens=2048,
            stream=True,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                if first_token_time is None:
                    first_token_time = _time.monotonic()
                    print(f"⚡ [FAST-PERF] 首token延迟: {(first_token_time-t0)*1000:.0f}ms (LLM: {(first_token_time-t2)*1000:.0f}ms)", flush=True)
                # 首个 token：发射 content_block_start
                if not first_token_emitted:
                    first_token_emitted = True
                    current_block_id_ref[0] = str(uuid.uuid4())
                    start_data = ContentBlockStartData(block_type="text", block_id=current_block_id_ref[0])
                    start_event = StreamEvent(event="content_block_start", data=start_data.model_dump(), current_step="tutor")
                    yield f"event: content_block_start\ndata: {start_event.model_dump_json()}\n\n"

                collected_reply_ref[0] += delta.content
                chunk_count += 1
                # 发射 content_block_data
                delta_data = ContentBlockDeltaData(block_id=current_block_id_ref[0], delta=delta.content)
                delta_event = StreamEvent(event="content_block_data", data=delta_data.model_dump(), current_step="tutor")
                yield f"event: content_block_data\ndata: {delta_event.model_dump_json()}\n\n"

        # LLM 流结束：关闭当前 text block
        if first_token_emitted and current_block_id_ref[0]:
            content_blocks_ref.append({"type": "text", "text": collected_reply_ref[0]})
            stop_data = ContentBlockStopData(block_id=current_block_id_ref[0])
            stop_event = StreamEvent(event="content_block_stop", data=stop_data.model_dump(), current_step="tutor")
            yield f"event: content_block_stop\ndata: {stop_event.model_dump_json()}\n\n"

        t3 = _time.monotonic()
        print(f"⚡ [FAST-PERF] 完成: 总{(t3-t0)*1000:.0f}ms, {chunk_count}个chunk, 长度{len(collected_reply_ref[0])}", flush=True)

        # ========== 阶段3：资源生成（若后台分析检测到 generate_resource 意图） ==========
        try:
            await asyncio.wait_for(bg_task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("⚠️ 后台分析超时，跳过资源生成", extra={"request_id": request_id})

        if bg_result_ref.get("intent") == "generate_resource" and bg_result_ref.get("resource_type"):
            res_type = bg_result_ref["resource_type"]
            res_topic = bg_result_ref.get("topic", topic)
            logger.info(f"🎯 [FAST-RESOURCE] 检测到资源生成意图: {res_type} - {res_topic}", extra={"request_id": request_id})
            try:
                agent = agents.get(res_type)
                if agent:
                    result = await agent.process(
                        res_topic,
                        {"user_id": user_id, "profile_data": profile_data, "chat_history": recent_history},
                    )
                    res_list = result.get("resource_list", [])
                    if res_list:
                        from models.database import AsyncSessionLocal
                        async with AsyncSessionLocal() as res_db:
                            for resource in res_list:
                                res_dict = resource.model_dump() if hasattr(resource, "model_dump") else resource
                                persist_result = await _persist_and_build_resource_event(res_dict, int(user_id), res_db)
                                if persist_result:
                                    sse_str, card_type, db_id = persist_result
                                    # 发射旧格式事件（向后兼容）
                                    yield sse_str
                                    # 发射 content_block 事件
                                    card_block_id = str(uuid.uuid4())
                                    card_block = {
                                        "type": "card",
                                        "card_type": card_type,
                                        "card_id": db_id,
                                        "title": res_dict.get("title", "学习资源"),
                                        "data": res_dict.get("content"),
                                    }
                                    content_blocks_ref.append(card_block)
                                    cb_start = ContentBlockStartData(
                                        block_type="card", block_id=card_block_id,
                                        card_type=card_type, card_id=db_id,
                                        title=res_dict.get("title", "学习资源"),
                                    )
                                    yield f"event: content_block_start\ndata: {StreamEvent(event='content_block_start', data=cb_start.model_dump(), current_step='tutor').model_dump_json()}\n\n"
                                    import json as _json
                                    cb_delta = ContentBlockDeltaData(block_id=card_block_id, delta=_json.dumps(card_block, ensure_ascii=False))
                                    yield f"event: content_block_data\ndata: {StreamEvent(event='content_block_data', data=cb_delta.model_dump(), current_step='tutor').model_dump_json()}\n\n"
                                    cb_stop = ContentBlockStopData(block_id=card_block_id)
                                    yield f"event: content_block_stop\ndata: {StreamEvent(event='content_block_stop', data=cb_stop.model_dump(), current_step='tutor').model_dump_json()}\n\n"
                            await res_db.commit()
            except Exception as res_err:
                logger.warning(f"⚠️ [FAST-RESOURCE] 资源生成失败（不阻塞主流程）: {res_err}", extra={"request_id": request_id})

    except Exception as e:
        logger.error(f"❌ 快速模式Tutor LLM失败: {e}", exc_info=True, extra={"request_id": request_id})
        # 降级：使用同步调用
        try:
            tutor = agents["tutor"]
            answer = await tutor._llm_answer(message, rag_context, {
                "chat_history": recent_history + [{"role": "user", "content": message}],
                "profile_data": profile_data,
            })
            if answer:
                collected_reply_ref[0] = answer
                content_blocks_ref.append({"type": "text", "text": answer})
                block_id = str(uuid.uuid4())
                start_data = ContentBlockStartData(block_type="text", block_id=block_id)
                yield f"event: content_block_start\ndata: {StreamEvent(event='content_block_start', data=start_data.model_dump(), current_step='tutor').model_dump_json()}\n\n"
                chunk_size = getattr(settings, "TYPING_CHUNK_SIZE", TYPING_CHUNK_SIZE)
                delay = getattr(settings, "TYPING_DELAY_MS", TYPING_DELAY_MS) / 1000
                for i in range(0, len(answer), chunk_size):
                    chunk = answer[i:i + chunk_size]
                    delta_data = ContentBlockDeltaData(block_id=block_id, delta=chunk)
                    yield f"event: content_block_data\ndata: {StreamEvent(event='content_block_data', data=delta_data.model_dump(), current_step='tutor').model_dump_json()}\n\n"
                    if delay > 0:
                        await asyncio.sleep(delay)
                stop_data = ContentBlockStopData(block_id=block_id)
                yield f"event: content_block_stop\ndata: {StreamEvent(event='content_block_stop', data=stop_data.model_dump(), current_step='tutor').model_dump_json()}\n\n"
        except Exception as fallback_err:
            logger.error(f"❌ 降级调用也失败: {fallback_err}", extra={"request_id": request_id})
            error_msg = "抱歉，AI辅导服务暂时不可用，请稍后再试。"
            collected_reply_ref[0] = error_msg
            err = StreamEvent(event="error", data={"error": str(fallback_err)}, current_step="error")
            yield f"event: error\ndata: {err.model_dump_json()}\n\n"


def filter_node_output(node: str, output: dict) -> dict:
    """精简节点输出，只保留前端需要的数据"""
    if node == "unified_router":
        return {
            "user_intent": output.get("user_intent"),
            "resource_type": output.get("resource_type"),
            "topic": output.get("topic"),
        }
    if node == "path":
        return {"learning_path": output.get("learning_path")}
    if node == "tutor":
        # 提取最后一条助手消息作为回复
        history = output.get("chat_history", [])
        if history and history[-1]["role"] == "assistant":
            return {"reply": history[-1]["content"]}
        return {"reply": output.get("reply", "")}
    if node in ("quiz", "resource"):
        return {"resource": output.get("resource")}
    # 默认只保留步骤状态
    return {k: v for k, v in output.items() if k in ("current_step", "error_message")}


async def _persist_and_build_resource_event(
    resource: dict,
    user_id: int,
    db: AsyncSession,
) -> Optional[Tuple[str, str, int]]:
    """将资源持久化到数据库并构建 SSE 事件字符串。返回 (事件字符串, 资源类型, 数据库ID) 或 None。"""
    import uuid as _uuid
    from config.constants import RESOURCE_PROGRESS_COMPLETE

    res_type = resource.get("resource_type", "resource")
    if res_type not in ("doc", "code", "quiz", "mindmap", "video"):
        return None

    content = resource.get("content", "")
    title = resource.get("title", "学习资源")
    kps = resource.get("knowledge_points", [])
    meta = resource.get("extra_metadata")

    # 持久化到数据库
    db_resource = Resource(
        user_id=user_id,
        task_id=str(_uuid.uuid4()),
        resource_type=res_type,
        title=title,
        content=content,
        knowledge_points=kps,
        status="completed",
        progress_percent=RESOURCE_PROGRESS_COMPLETE,
        extra_metadata=meta,
    )
    db.add(db_resource)
    await db.flush()
    await db.refresh(db_resource)

    event_data = {
        "id": db_resource.id,
        "resource_type": res_type,
        "title": title,
        "content": content,
        "knowledge_points": kps,
        "extra_metadata": meta,
    }
    res_event = StreamEvent(event=res_type, data=event_data, current_step=res_type)
    return (f"event: {res_type}\ndata: {res_event.model_dump_json()}\n\n", res_type, db_resource.id)


# ---------- 流式 SSE 接口 ----------
@router.post("/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    快速模式流式对话 SSE 接口
    - Router + RAG 并行执行，跳过 LangGraph 开销
    事件: token, end, error
    """
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)

    # 使用认证用户的 ID
    user_id = str(current_user.id)
    request.user_id = user_id

    # 处理对话关联
    conversation_id = request.conversation_id
    is_new_conversation = not conversation_id
    if is_new_conversation:
        # 自动创建新对话，用用户消息前20个字符作为标题
        title = request.message[:CONVERSATION_TITLE_MAX_LENGTH] + ("..." if len(request.message) > CONVERSATION_TITLE_MAX_LENGTH else "")
        conv = Conversation(user_id=current_user.id, title=title)
        db.add(conv)
        await db.flush()
        conversation_id = conv.id
        logger.info(f"自动创建对话: conv_id={conversation_id}, title={title!r}")

    # 加载用户画像和对话历史（跨会话记忆）
    # 始终加载所有对话的历史，实现真正的跨会话记忆
    profile_data, recent_history = await load_user_context(
        current_user.id, None, db  # None = 加载所有对话的历史
    )

    # 保存用户消息到数据库
    user_msg = ChatMessage(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.commit()

    # 收集 AI 回复用于持久化
    collected_reply = [""]
    content_blocks_ref = []  # 内容块追踪（content_block 架构）
    _conversation_id = conversation_id
    _user_id = current_user.id

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            logger.info(f"🚀 开始快速模式流式对话 | {user_id}", extra={"request_id": request_id})

            async for event_str in _fast_chat_handler(
                request, user_id, profile_data, recent_history, collected_reply, content_blocks_ref, request_id
            ):
                yield event_str

            end_event = StreamEvent(event="end", data={"request_id": request_id, "conversation_id": _conversation_id, "content_blocks": content_blocks_ref}, current_step="completed")
            yield f"event: end\ndata: {end_event.model_dump_json()}\n\n"
            logger.info(f"✅ 快速模式流式对话完成", extra={"request_id": request_id})

        except Exception as e:
            logger.error(f"❌ 流式异常: {e}", exc_info=True, extra={"request_id": request_id})
            err = StreamEvent(event="error", data={"error": str(e)}, current_step="error")
            yield f"event: error\ndata: {err.model_dump_json()}\n\n"
        finally:
            # 保存AI回复（画像已由后台任务处理）
            try:
                import json as _json
                from models.database import AsyncSessionLocal
                async with AsyncSessionLocal() as save_db:
                    reply_text = collected_reply[0] if collected_reply else ""
                    if reply_text:
                        ai_msg = ChatMessage(
                            user_id=_user_id,
                            conversation_id=_conversation_id,
                            role="assistant",
                            content=reply_text,
                            content_blocks_json=_json.dumps(content_blocks_ref, ensure_ascii=False) if content_blocks_ref else None,
                        )
                        save_db.add(ai_msg)
                        await save_db.commit()
                        logger.info(f"✅ AI回复已保存到对话 {_conversation_id}")
            except Exception as save_err:
                logger.error(f"保存记录失败: {save_err}", extra={"request_id": request_id})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
            "Access-Control-Expose-Headers": "X-Request-ID",
        },
    )


# ---------- 深度思考模式 SSE 接口 ----------
@router.post("/deep-stream", response_class=StreamingResponse)
async def deep_chat_stream(
    request: ChatRequest,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    深度思考模式：并行调用5个Agent，实时展示进度
    事件: thinking, clear, token, end, error
    """
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    user_id = str(current_user.id)

    # 处理对话关联
    conversation_id = request.conversation_id
    is_new_conversation = not conversation_id
    if is_new_conversation:
        title = request.message[:CONVERSATION_TITLE_MAX_LENGTH] + ("..." if len(request.message) > CONVERSATION_TITLE_MAX_LENGTH else "")
        conv = Conversation(user_id=current_user.id, title=title)
        db.add(conv)
        await db.flush()
        conversation_id = conv.id

    # 加载用户画像
    profile_data, recent_history = await load_user_context(current_user.id, None, db)

    # 使用 UnifiedRouterAgent 提取 topic 和画像更新
    topic = ""
    profile_update = {}
    try:
        from graph.workflow import get_or_create_agents
        agents = get_or_create_agents()
        router_result = await agents["unified_router"].process(
            request.message,
            {"profile_data": profile_data, "chat_history": recent_history + [{"role": "user", "content": request.message}]},
        )
        topic = router_result.get("topic", "") or ""
        profile_update = router_result.get("_profile_update", {}) or {}
        if profile_update:
            logger.info(f"📝 深度模式画像更新: {profile_update}", extra={"request_id": request_id})
    except Exception as e:
        logger.warning(f"⚠️ 深度模式路由提取失败，使用原始消息作为 topic: {e}")
        topic = request.message.strip()

    if not topic:
        topic = request.message.strip()

    # 保存用户消息
    user_msg = ChatMessage(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.commit()

    collected_reply = ""
    _conversation_id = conversation_id
    _user_id = current_user.id

    async def deep_event_generator() -> AsyncGenerator[str, None]:
        nonlocal collected_reply
        try:
            deep_workflow = await get_deep_workflow()

            # 初始思考事件
            thinking_event = StreamEvent(event="thinking", data="🧠 正在分析你的学习需求...", current_step="thinking")
            yield f"event: thinking\ndata: {thinking_event.model_dump_json()}\n\n"

            # 共享思维队列（Agent 节点 → 此处 SSE 输出）
            import asyncio as _aio
            thinking_queue: _aio.Queue = _aio.Queue()

            initial_state = {
                "user_id": user_id,
                "message": request.message,
                "profile_data": profile_data,
                "topic": topic,
                "thinking_queue": thinking_queue,
            }

            # 用于在 workflow 和 queue 消费者之间共享最终结果
            final_result = {"response": None, "resource_list": [], "done": False}

            async def run_workflow():
                """后台运行 LangGraph 工作流"""
                async for event in deep_workflow.astream(
                    initial_state,
                    stream_mode="updates",
                ):
                    for node_name, node_output in event.items():
                        if node_name == "deep_start":
                            continue
                        if node_name == "deep_aggregator":
                            final_result["response"] = node_output.get("final_response", "")
                            final_result["resource_list"] = node_output.get("resource_list", [])
                final_result["done"] = True

            async def consume_thinking_queue():
                """实时消费 Agent 的思维过程事件"""
                while not final_result["done"]:
                    try:
                        item = await _aio.wait_for(thinking_queue.get(), timeout=0.3)
                        text = item.get("text", "")
                        if text:
                            te = StreamEvent(event="thinking", data=text, current_step="thinking")
                            yield f"event: thinking\ndata: {te.model_dump_json()}\n\n"
                    except _aio.TimeoutError:
                        continue

                # 排空队列中剩余的事件
                while not thinking_queue.empty():
                    try:
                        item = thinking_queue.get_nowait()
                        text = item.get("text", "")
                        if text:
                            te = StreamEvent(event="thinking", data=text, current_step="thinking")
                            yield f"event: thinking\ndata: {te.model_dump_json()}\n\n"
                    except _aio.QueueEmpty:
                        break

            # 并发执行：工作流 + 思维过程消费
            workflow_task = _aio.create_task(run_workflow())

            async for sse_str in consume_thinking_queue():
                yield sse_str

            # 等待工作流彻底完成
            await workflow_task

            # 流式输出最终回答
            final_response = final_result["response"]
            if final_response:
                collected_reply = final_response
                # 发送完成事件，前端折叠思考面板
                clear_event = StreamEvent(event="clear", data="", current_step="aggregator")
                yield f"event: clear\ndata: {clear_event.model_dump_json()}\n\n"

                # 发射资源事件（先持久化到数据库，前端可保存到资源库）
                resource_list = final_result.get("resource_list", [])
                type_to_id_map: dict[str, int] = {}
                if resource_list:
                    from models.database import AsyncSessionLocal
                    try:
                        async with AsyncSessionLocal() as res_db:
                            for resource in resource_list:
                                result = await _persist_and_build_resource_event(resource, _user_id, res_db)
                                if result:
                                    sse_str, res_type, db_id = result
                                    yield sse_str
                                    type_to_id_map[res_type] = db_id
                            await res_db.commit()
                    except Exception as res_err:
                        logger.warning(f"⚠️ 资源持久化失败: {type(res_err).__name__}: {res_err}", extra={"request_id": request_id})

                # 替换占位标记 {{card:TYPE}} → {{card:DB_ID}}
                import re
                def _replace_card_marker(match):
                    card_type = match.group(1)
                    return f'{{{{card:{type_to_id_map.get(card_type, card_type)}}}}}'
                final_response = re.sub(r'\{\{card:(\w+)\}\}', _replace_card_marker, final_response)

                # 解析为 content_blocks 并以 block 级别流式输出
                resource_map = build_resource_map(resource_list)
                content_blocks = parse_response_to_blocks(final_response, resource_map)

                chunk_size = getattr(settings, "TYPING_CHUNK_SIZE", TYPING_CHUNK_SIZE)
                delay = getattr(settings, "TYPING_DELAY_MS", TYPING_DELAY_MS) / 1000

                for block in content_blocks:
                    block_id = str(uuid.uuid4())
                    # content_block_start
                    start_data = ContentBlockStartData(
                        block_type=block["type"],
                        block_id=block_id,
                        card_type=block.get("card_type"),
                        card_id=block.get("card_id"),
                        title=block.get("title"),
                    )
                    start_event = StreamEvent(event="content_block_start", data=start_data.model_dump(), current_step="aggregator")
                    yield f"event: content_block_start\ndata: {start_event.model_dump_json()}\n\n"

                    # content_block_data
                    if block["type"] == "text":
                        text = block["text"]
                        for i in range(0, len(text), chunk_size):
                            chunk = text[i:i + chunk_size]
                            delta_data = ContentBlockDeltaData(block_id=block_id, delta=chunk)
                            delta_event = StreamEvent(event="content_block_data", data=delta_data.model_dump(), current_step="aggregator")
                            yield f"event: content_block_data\ndata: {delta_event.model_dump_json()}\n\n"
                            await _aio.sleep(delay)
                    elif block["type"] == "card":
                        import json as _json
                        delta_data = ContentBlockDeltaData(
                            block_id=block_id,
                            delta=_json.dumps(block, ensure_ascii=False),
                        )
                        delta_event = StreamEvent(event="content_block_data", data=delta_data.model_dump(), current_step="aggregator")
                        yield f"event: content_block_data\ndata: {delta_event.model_dump_json()}\n\n"

                    # content_block_stop
                    stop_data = ContentBlockStopData(block_id=block_id)
                    stop_event = StreamEvent(event="content_block_stop", data=stop_data.model_dump(), current_step="aggregator")
                    yield f"event: content_block_stop\ndata: {stop_event.model_dump_json()}\n\n"

            end_event = StreamEvent(event="end", data={"request_id": request_id, "conversation_id": _conversation_id, "content_blocks": content_blocks if final_response else []}, current_step="completed")
            yield f"event: end\ndata: {end_event.model_dump_json()}\n\n"
            logger.info(f"✅ 深度思考模式完成", extra={"request_id": request_id})

        except Exception as e:
            logger.error(f"❌ 深度思考异常: {e}", exc_info=True, extra={"request_id": request_id})
            err = StreamEvent(event="error", data={"error": str(e)}, current_step="error")
            yield f"event: error\ndata: {err.model_dump_json()}\n\n"
        finally:
            # 保存AI回复 + 画像更新
            try:
                import json as _json
                from models.database import AsyncSessionLocal
                async with AsyncSessionLocal() as save_db:
                    if collected_reply:
                        # 构建 content_blocks 用于持久化
                        _cb = content_blocks if final_response else legacy_to_content_blocks(collected_reply, [])
                        ai_msg = ChatMessage(
                            user_id=_user_id,
                            conversation_id=_conversation_id,
                            role="assistant",
                            content=collected_reply,
                            content_blocks_json=_json.dumps(_cb, ensure_ascii=False),
                        )
                        save_db.add(ai_msg)
                        await save_db.commit()

                    # 持久化画像更新 + 同步到进度表
                    if profile_update and isinstance(profile_update, dict) and len(profile_update) > 0:
                        await _persist_profile(save_db, _user_id, profile_update, request_id)
                        await _sync_profile_to_progress(save_db, _user_id, profile_update, request_id)
                    if topic:
                        await _sync_topic_to_progress(save_db, _user_id, topic, request_id)
            except Exception as save_err:
                logger.error(f"保存记录失败: {save_err}", extra={"request_id": request_id})

    return StreamingResponse(
        deep_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
            "Access-Control-Expose-Headers": "X-Request-ID",
        },
    )


# ---------- 苏格拉底导学模式 SSE 接口 ----------
@router.post("/socratic-stream", response_class=StreamingResponse)
async def socratic_chat_stream(
    request: SocraticChatRequest,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    苏格拉底导学模式：通过 interrupt() 机制实现多轮引导式学习
    事件: socratic_question, socratic_hint, socratic_feedback, socratic_answer, socratic_summary, socratic_end, error
    """
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    user_id = str(current_user.id)

    # 验证 start/answer 操作必须有消息内容
    if request.action in ("start", "answer") and not request.message:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="start/answer 操作需要 message 内容")

    # 处理对话关联
    conversation_id = request.conversation_id
    is_new_conversation = not conversation_id
    if is_new_conversation:
        title = f"苏格拉底导学：{request.message[:CONVERSATION_TITLE_MAX_LENGTH]}"
        conv = Conversation(user_id=current_user.id, title=title)
        db.add(conv)
        await db.flush()
        conversation_id = conv.id

    # 保存用户消息
    user_msg = ChatMessage(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.commit()

    # 加载用户画像
    profile_data, _ = await load_user_context(current_user.id, None, db)

    # 构建 thread_id（用于 LangGraph checkpoint）
    thread_id = request.thread_id or f"socratic-{user_id}-{uuid.uuid4().hex[:8]}"
    config = {
        "configurable": {
            "thread_id": thread_id,
            "user_id": user_id,
        }
    }

    _conversation_id = conversation_id
    _user_id = current_user.id

    async def socratic_event_generator() -> AsyncGenerator[str, None]:
        collected_reply = ""
        try:
            socratic_app = await get_socratic_workflow()

            # 节点 → 思考提示映射
            _thinking_map = {
                "analyze_problem": "🧠 正在分析你的问题，提取知识点...",
                "teaching_decision_engine": "🤔 正在思考最佳引导方式...",
                "ask_question": "💬 正在设计引导问题...",
                "explain_concept": "📖 正在准备概念讲解...",
                "code_demo": "💻 正在生成代码示例...",
                "practice_exercise": "✏️ 正在设计练习题...",
                "rephrase_question": "🔄 正在换个角度思考...",
                "relate_knowledge": "🔗 正在关联已有知识...",
                "evaluate_answer": "📊 正在评估你的回答...",
                "evaluate_and_decide": "📊 正在评估回答并规划下一步...",
                "generate_hint": "💡 正在准备提示...",
                "generate_summary_and_save": "📝 正在生成学习总结...",
            }

            # 从 astream 流中收集的状态和 interrupt 数据
            accumulated_state: dict = {}
            interrupt_info: dict = {}
            has_interrupt = False

            if request.action == "start":
                initial_state = {
                    "user_id": user_id,
                    "conversation_id": _conversation_id,
                    "original_query": request.message,
                    "chat_history": [{"role": "user", "content": request.message}],
                    "profile_data": profile_data,
                    "current_topic": request.message,
                    "session_id": thread_id,
                }
                logger.info(f"🎓 苏格拉底新会话 | thread={thread_id}", extra={"request_id": request_id})

                async for event in socratic_app.astream(initial_state, config, stream_mode="updates"):
                    for node_name, node_output in event.items():
                        if node_name == "__interrupt__":
                            # interrupt 事件：提取暂停时的问题数据
                            has_interrupt = True
                            if isinstance(node_output, tuple) and node_output:
                                intr = node_output[0]
                                if hasattr(intr, "value"):
                                    interrupt_info = intr.value
                        else:
                            # 普通节点完成：发送思考提示 + 累积状态
                            thinking_text = _thinking_map.get(node_name)
                            if thinking_text:
                                te = StreamEvent(event="thinking", data=thinking_text, current_step="socratic")
                                yield f"event: thinking\ndata: {te.model_dump_json()}\n\n"
                            if isinstance(node_output, dict):
                                accumulated_state.update(node_output)

            elif request.action in ("answer", "hint", "give_up", "end", "confused"):
                logger.info(
                    f"🎓 苏格拉底恢复 | action={request.action} | thread={thread_id}",
                    extra={"request_id": request_id},
                )

                if request.action == "hint":
                    resume_value = "__HINT__"
                elif request.action == "confused":
                    resume_value = "__CONFUSED__"
                elif request.action == "give_up":
                    resume_value = "__GIVE_UP__"
                elif request.action == "end":
                    resume_value = "__END__"
                else:
                    resume_value = request.message

                async for event in socratic_app.astream(Command(resume=resume_value), config, stream_mode="updates"):
                    for node_name, node_output in event.items():
                        if node_name == "__interrupt__":
                            has_interrupt = True
                            if isinstance(node_output, tuple) and node_output:
                                intr = node_output[0]
                                if hasattr(intr, "value"):
                                    interrupt_info = intr.value
                        else:
                            thinking_text = _thinking_map.get(node_name)
                            if thinking_text:
                                te = StreamEvent(event="thinking", data=thinking_text, current_step="socratic")
                                yield f"event: thinking\ndata: {te.model_dump_json()}\n\n"
                            if isinstance(node_output, dict):
                                accumulated_state.update(node_output)
            else:
                error_event = StreamEvent(event="error", data={"error": f"未知操作: {request.action}"}, current_step="error")
                yield f"event: error\ndata: {error_event.model_dump_json()}\n\n"
                return

            # 持久化当前学习数据（无论 interrupt 还是正常结束都保存）
            try:
                from agents.socratic_workflow import _persist_learning_data
                persist_state = {
                    "user_id": user_id,
                    "knowledge_points": accumulated_state.get("knowledge_points", []),
                    "mastery_level": accumulated_state.get("mastery_level", {}),
                    "error_book_entries": accumulated_state.get("error_book_entries", []),
                    "current_response_type": accumulated_state.get("current_response_type", ""),
                    "recent_actions": accumulated_state.get("recent_actions", []),
                }
                if persist_state["knowledge_points"]:
                    await _persist_learning_data(persist_state)
            except Exception as persist_err:
                logger.warning(f"苏格拉底中间持久化失败（不影响流程）: {persist_err}")

            # 发送掌握度更新事件
            mastery_changes = accumulated_state.get("mastery_changes", {})
            if mastery_changes:
                mastery_event = StreamEvent(
                    event="mastery_update",
                    data={
                        "mastery_level": accumulated_state.get("mastery_level", {}),
                        "changes": mastery_changes,
                        "current_stage": accumulated_state.get("current_stage", ""),
                    },
                    current_step="socratic",
                )
                yield f"event: mastery_update\ndata: {mastery_event.model_dump_json()}\n\n"

            # 清除思考步骤，准备展示最终内容
            clear_event = StreamEvent(event="clear", data="", current_step="socratic")
            yield f"event: clear\ndata: {clear_event.model_dump_json()}\n\n"

            if has_interrupt:
                # 先发送 evaluate_answer 的反馈（如果有）
                pending_feedback = accumulated_state.get("pending_feedback", "")
                if pending_feedback:
                    feedback_event = StreamEvent(
                        event="socratic_feedback",
                        data={
                            "content": pending_feedback,
                            "thread_id": thread_id,
                            "type": "feedback",
                            "mastery_level": accumulated_state.get("mastery_level", {}),
                            "consecutive_errors": accumulated_state.get("consecutive_errors", 0),
                            "ended": False,
                        },
                        current_step="socratic",
                    )
                    yield f"event: socratic_feedback\ndata: {feedback_event.model_dump_json()}\n\n"

                # 工作流被 interrupt 暂停，发送问题给用户
                question_text = interrupt_info.get("content", interrupt_info.get("question", ""))
                collected_reply = question_text

                interrupt_type = interrupt_info.get("type", "question")
                interrupt_event_map = {
                    "question": "socratic_question",
                    "explain": "socratic_explain",
                    "demo": "socratic_demo",
                    "practice": "socratic_practice",
                    "relate": "socratic_relate",
                }
                sse_event_type = interrupt_event_map.get(interrupt_type, "socratic_question")

                sse_event = StreamEvent(
                    event=sse_event_type,
                    data={
                        "content": question_text,
                        "thread_id": thread_id,
                        "stage": interrupt_info.get("stage", accumulated_state.get("current_stage", "")),
                        "type": interrupt_type,
                        "difficulty": interrupt_info.get("difficulty", accumulated_state.get("difficulty", 3)),
                        "hint_level": interrupt_info.get("hint_level", accumulated_state.get("hint_level", 1)),
                        "consecutive_errors": interrupt_info.get("consecutive_errors", accumulated_state.get("consecutive_errors", 0)),
                        "learning_state": interrupt_info.get("learning_state", accumulated_state.get("learning_state", "normal")),
                        "ended": False,
                    },
                    current_step="socratic",
                )
                yield f"event: {sse_event_type}\ndata: {sse_event.model_dump_json()}\n\n"
            else:
                # 工作流正常完成（到了 END），发送最终结果
                response_text = accumulated_state.get("current_response", "")
                response_type = accumulated_state.get("current_response_type", "summary")
                collected_reply = response_text

                event_name = {
                    "question": "socratic_question",
                    "hint": "socratic_hint",
                    "feedback": "socratic_feedback",
                    "answer": "socratic_answer",
                    "summary": "socratic_summary",
                    "explain": "socratic_explain",
                    "demo": "socratic_demo",
                    "practice": "socratic_practice",
                    "relate": "socratic_relate",
                }.get(response_type, "socratic_summary")

                sse_event = StreamEvent(
                    event=event_name,
                    data={
                        "content": response_text,
                        "thread_id": thread_id,
                        "mastery_level": accumulated_state.get("mastery_level", {}),
                        "current_stage": accumulated_state.get("current_stage", ""),
                        "consecutive_errors": accumulated_state.get("consecutive_errors", 0),
                        "ended": True,
                    },
                    current_step="socratic",
                )
                yield f"event: {event_name}\ndata: {sse_event.model_dump_json()}\n\n"

                end_event = StreamEvent(
                    event="socratic_end",
                    data={"request_id": request_id, "conversation_id": _conversation_id, "thread_id": thread_id},
                    current_step="completed",
                )
                yield f"event: socratic_end\ndata: {end_event.model_dump_json()}\n\n"
            logger.info(f"✅ 苏格拉底导学完成 | action={request.action}", extra={"request_id": request_id})

        except Exception as e:
            logger.error(f"❌ 苏格拉底导学异常: {e}", exc_info=True, extra={"request_id": request_id})
            err = StreamEvent(event="error", data={"error": str(e)}, current_step="error")
            yield f"event: error\ndata: {err.model_dump_json()}\n\n"
        finally:
            # 保存 AI 回复
            try:
                import json as _json
                from models.database import AsyncSessionLocal
                async with AsyncSessionLocal() as save_db:
                    if collected_reply:
                        _cb = [{"type": "text", "text": collected_reply}]
                        ai_msg = ChatMessage(
                            user_id=_user_id,
                            conversation_id=_conversation_id,
                            role="assistant",
                            content=collected_reply,
                            content_blocks_json=_json.dumps(_cb, ensure_ascii=False),
                        )
                        save_db.add(ai_msg)
                        await save_db.commit()
            except Exception as save_err:
                logger.error(f"保存苏格拉底记录失败: {save_err}", extra={"request_id": request_id})

    return StreamingResponse(
        socratic_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-ID": request_id,
            "Access-Control-Expose-Headers": "X-Request-ID",
        },
    )


# ---------- 苏格拉底教学分析接口 ----------
@router.get("/socratic/sessions/{user_id}", response_model=BaseResponse)
async def get_socratic_sessions(
    user_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询用户的苏格拉底教学会话记录"""
    from models.socratic_session import SocraticSession
    result = await db.execute(
        select(SocraticSession)
        .where(SocraticSession.user_id == user_id)
        .order_by(SocraticSession.created_at.desc())
        .limit(limit)
    )
    sessions = result.scalars().all()
    data = [{
        "id": s.id,
        "thread_id": s.thread_id,
        "topic": s.topic,
        "knowledge_points": s.knowledge_points,
        "total_actions": s.total_actions,
        "total_correct": s.total_correct,
        "total_wrong": s.total_wrong,
        "total_hints": s.total_hints,
        "final_mastery": s.final_mastery,
        "action_distribution": s.action_distribution,
        "end_reason": s.end_reason,
        "summary": s.summary,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    } for s in sessions]
    return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data=data)


@router.get("/socratic/stats/{user_id}", response_model=BaseResponse)
async def get_socratic_stats(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询用户的苏格拉底学习统计数据"""
    from models.socratic_session import SocraticSession
    result = await db.execute(
        select(SocraticSession).where(SocraticSession.user_id == user_id)
    )
    sessions = result.scalars().all()

    if not sessions:
        return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
            "total_sessions": 0, "total_actions": 0, "accuracy_rate": 0,
            "top_topics": [], "common_actions": {},
        })

    total_sessions = len(sessions)
    total_actions = sum(s.total_actions or 0 for s in sessions)
    total_correct = sum(s.total_correct or 0 for s in sessions)
    total_wrong = sum(s.total_wrong or 0 for s in sessions)
    accuracy_rate = round(total_correct / max(total_correct + total_wrong, 1), 2)

    # 高频主题
    topic_counts = {}
    for s in sessions:
        t = s.topic or "未知"
        topic_counts[t] = topic_counts.get(t, 0) + 1
    top_topics = sorted(topic_counts.items(), key=lambda x: -x[1])[:5]

    # 动作分布汇总
    action_totals = {}
    for s in sessions:
        if s.action_distribution:
            for act, cnt in s.action_distribution.items():
                action_totals[act] = action_totals.get(act, 0) + cnt

    return BaseResponse(code=HTTP_OK, message=MSG_SUCCESS, data={
        "total_sessions": total_sessions,
        "total_actions": total_actions,
        "accuracy_rate": accuracy_rate,
        "total_hints": sum(s.total_hints or 0 for s in sessions),
        "top_topics": [{"topic": t, "count": c} for t, c in top_topics],
        "common_actions": action_totals,
    })


# ---------- 同步接口（备用） ----------
@router.post("/sync", response_model=BaseResponse)
async def chat_sync(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """同步对话接口"""
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    try:
        workflow = await get_workflow()
        request.user_id = str(current_user.id)

        # 处理对话关联
        conversation_id = request.conversation_id
        if not conversation_id:
            title = request.message[:CONVERSATION_TITLE_MAX_LENGTH] + ("..." if len(request.message) > CONVERSATION_TITLE_MAX_LENGTH else "")
            conv = Conversation(user_id=current_user.id, title=title)
            db.add(conv)
            await db.flush()
            conversation_id = conv.id

        # 保存用户消息
        user_msg = ChatMessage(
            user_id=current_user.id,
            conversation_id=conversation_id,
            role="user",
            content=request.message,
        )
        db.add(user_msg)
        await db.commit()

        profile_data, recent_history = await load_user_context(
            current_user.id, None, db  # None = 加载所有对话的历史
        )
        state = build_initial_state(request, profile_data, recent_history)
        final = await asyncio.wait_for(
            workflow.ainvoke(
                state,
                config={
                    "configurable": {"thread_id": request.thread_id or request.user_id},
                    "recursion_limit": DEFAULT_RECURSION_LIMIT
                }
            ),
            timeout=getattr(settings, "SYNC_CHAT_TIMEOUT", SYNC_CHAT_TIMEOUT_SEC)
        )
        history = final.get("chat_history", [])
        reply = ""
        if history and history[-1]["role"] == "assistant":
            reply = history[-1]["content"]

        # 保存AI回复
        if reply:
            ai_msg = ChatMessage(
                user_id=current_user.id,
                conversation_id=conversation_id,
                role="assistant",
                content=reply,
            )
            db.add(ai_msg)
            await db.commit()

        # 持久化画像到数据库（从路由输出中提取）
        profile_update = final.get("_profile_update")
        if profile_update and isinstance(profile_update, dict) and len(profile_update) > 0:
            raw_output = final.get("_profile_raw_output", {})
            confidence = final.get("_profile_confidence", 0.0)
            await _persist_profile(db, current_user.id, profile_update, request_id)
            await _sync_profile_to_progress(db, current_user.id, profile_update, request_id)
            # 同步主题到进度表
            topic = final.get("topic") or ""
            if topic:
                await _sync_topic_to_progress(db, current_user.id, topic, request_id)
            # 审计日志
            try:
                from models.profile import ProfileChangeLog
                log_entry = ProfileChangeLog(
                    user_id=current_user.id,
                    changed_fields=raw_output,
                    source="llm",
                    raw_llm_output=raw_output,
                    confidence=confidence,
                )
                db.add(log_entry)
                await db.commit()
            except Exception as log_err:
                logger.debug(f"审计日志跳过: {log_err}")

        return BaseResponse(
            data=ChatResponseData(
                reply=reply,
                user_intent=final.get("user_intent"),
                current_step=final.get("current_step", "completed"),
                learning_path=final.get("learning_path", []),
                resources_generated=len(final.get("resource_list", [])),
            ),
            request_id=request_id,
        )
    except asyncio.TimeoutError:
        logger.error(f"⏱️ 同步对话超时", extra={"request_id": request_id})
        return BaseResponse(code=HTTP_GATEWAY_TIMEOUT, message=MSG_REQUEST_TIMEOUT, request_id=request_id)
    except Exception as e:
        logger.error(f"同步对话失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=f"服务器错误: {str(e)}", request_id=request_id)


# ---------- 聊天历史 ----------
@router.get("/history", response_model=BaseResponse)
async def get_history(
    limit: int = 100,
    conversation_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前用户的聊天记录，可按对话ID过滤"""
    query = select(ChatMessage).where(ChatMessage.user_id == current_user.id)
    if conversation_id:
        query = query.where(ChatMessage.conversation_id == conversation_id)
    query = query.order_by(ChatMessage.created_at.asc()).limit(limit)

    result = await db.execute(query)
    messages = result.scalars().all()

    return BaseResponse(
        code=HTTP_OK,
        message=MSG_SUCCESS,
        data=[
            {
                "role": m.role,
                "content": m.content,
                "conversation_id": m.conversation_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ],
    )


@router.delete("/history", response_model=BaseResponse)
async def clear_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空当前用户的聊天记录"""
    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(ChatMessage).where(ChatMessage.user_id == current_user.id))
    await db.commit()
    return BaseResponse(code=HTTP_OK, message=MSG_CHAT_HISTORY_CLEARED)


# ---------- 健康检查 ----------
@router.get("/health", response_model=BaseResponse)
async def health():
    """服务健康检查"""
    try:
        wf = await get_workflow()
        return BaseResponse(data={
            "status": "ok",
            "workflow_initialized": wf is not None,
            "service": "chat"
        })
    except Exception as e:
        return BaseResponse(code=HTTP_SERVICE_UNAVAILABLE, message=f"服务异常: {str(e)}")