"""
api/routes/chat.py - 智能辅导对话接口（最终提交版）
- ✅ 直接迭代 LangGraph astream 生成器
- ✅ 客户端断开立即取消流
- ✅ 标准 SSE 格式，打字效果可配置
- ✅ 请求 ID 全链路日志追踪
- ✅ 智能字段过滤，轻量传输
- ✅ 修复所有潜在边缘情况
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator, Optional, Any
import asyncio
import uuid
import contextvars

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    ChatRequest,
    BaseResponse,
    ChatResponseData,
    StreamEvent,
)
from api.routes.auth import get_current_user
from models.user import User
from models.chat_message import ChatMessage
from models.conversation import Conversation
from models.database import get_db
from graph.workflow import build_workflow
from utils.logger import get_logger
from config.settings import settings
from config.constants import (
    DEFAULT_RECURSION_LIMIT, TYPING_CHUNK_SIZE, TYPING_DELAY_MS,
    SYNC_CHAT_TIMEOUT_SEC, HTTP_OK, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE, HTTP_GATEWAY_TIMEOUT,
)

request_id_var = contextvars.ContextVar("request_id", default="unknown")

router = APIRouter(prefix="/chat", tags=["智能辅导"])
logger = get_logger(__name__, task_id="chat_api")

# ---------- 工作流单例 ----------
_workflow: Optional[Any] = None
_workflow_init_lock = asyncio.Lock()  # 🔴 优化1：统一变量名，更清晰


async def get_workflow() -> Any:
    global _workflow
    if _workflow is None:
        async with _workflow_init_lock:
            if _workflow is None:
                _workflow = build_workflow()
                logger.info("✅ LangGraph 工作流初始化成功")
    return _workflow


# ---------- 辅助函数 ----------
def build_initial_state(req: ChatRequest) -> dict:
    """构建工作流初始状态，与 graph/state.py 完全对齐"""
    return {
        "user_id": req.user_id,
        "chat_history": [{"role": "user", "content": req.message}],
        "profile_data": {},
        "learning_path": [],
        "resource_list": [],
        "current_step": "start",
        "user_intent": None,
        "updated_at": None,
        "error_message": None,
    }


def filter_node_output(node: str, output: dict) -> dict:
    """精简节点输出，只保留前端需要的数据"""
    if node == "intent":
        return {"user_intent": output.get("user_intent")}
    if node == "profile":
        return {"profile_data": output.get("profile_data")}
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


# ---------- 流式 SSE 接口 ----------
@router.post("/stream", response_class=StreamingResponse)
async def chat_stream(
    request: ChatRequest,
    fastapi_request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    流式对话 SSE 接口
    事件: intent, profile, path, tutor, token, end, error
    """
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)

    # 使用认证用户的 ID
    user_id = str(current_user.id)
    workflow = await get_workflow()
    request.user_id = user_id
    state = build_initial_state(request)
    thread_id = request.thread_id or user_id

    # 处理对话关联
    conversation_id = request.conversation_id
    if not conversation_id:
        # 自动创建新对话，用用户消息前20个字符作为标题
        title = request.message[:20] + ("..." if len(request.message) > 20 else "")
        conv = Conversation(user_id=current_user.id, title=title)
        db.add(conv)
        await db.flush()
        conversation_id = conv.id
        logger.info(f"自动创建对话: conv_id={conversation_id}, title={title!r}")

    # 保存用户消息到数据库
    user_msg = ChatMessage(
        user_id=current_user.id,
        conversation_id=conversation_id,
        role="user",
        content=request.message,
    )
    db.add(user_msg)
    await db.commit()

    # 收集 AI 回复用于持久化（使用独立session，避免StreamingResponse生命周期问题）
    collected_reply = ""
    _conversation_id = conversation_id
    _user_id = current_user.id

    async def event_generator() -> AsyncGenerator[str, None]:
        nonlocal collected_reply
        try:
            logger.info(f"🚀 开始流式对话 | {user_id}", extra={"request_id": request_id})

            async for event in workflow.astream(
                state,
                stream_mode="updates",
                config={
                    "configurable": {"thread_id": thread_id},
                    "recursion_limit": DEFAULT_RECURSION_LIMIT
                }
            ):
                for node_name, node_output in event.items():
                    clean_name = node_name.replace("_agent", "")
                    filtered = filter_node_output(clean_name, node_output)

                    # 打字效果：对 tutor 的回复逐字发送（token事件替代完整tutor事件）
                    if clean_name == "tutor" and "reply" in filtered:
                        reply = filtered["reply"]
                        if reply:
                            collected_reply = reply
                            chunk_size = getattr(settings, "TYPING_CHUNK_SIZE", TYPING_CHUNK_SIZE)
                            delay = getattr(settings, "TYPING_DELAY_MS", TYPING_DELAY_MS) / 1000
                            for i in range(0, len(reply), chunk_size):
                                chunk = reply[i:i+chunk_size]
                                token_event = StreamEvent(event="token", data=chunk, current_step="tutor")
                                yield f"event: token\ndata: {token_event.model_dump_json()}\n\n"
                                await asyncio.sleep(delay)
                        else:
                            # 空回复时发送tutor事件
                            se = StreamEvent(event=clean_name, data=filtered, current_step=clean_name)
                            yield f"event: {clean_name}\ndata: {se.model_dump_json()}\n\n"
                    else:
                        # 非tutor节点正常发送事件
                        se = StreamEvent(event=clean_name, data=filtered, current_step=clean_name)
                        yield f"event: {clean_name}\ndata: {se.model_dump_json()}\n\n"

            # 正常结束
            end_event = StreamEvent(event="end", data={"request_id": request_id, "conversation_id": _conversation_id}, current_step="completed")
            yield f"event: end\ndata: {end_event.model_dump_json()}\n\n"
            logger.info(f"✅ 流式对话完成", extra={"request_id": request_id})

        except Exception as e:
            logger.error(f"❌ 流式异常: {e}", exc_info=True, extra={"request_id": request_id})
            err = StreamEvent(event="error", data={"error": str(e)}, current_step="error")
            yield f"event: error\ndata: {err.model_dump_json()}\n\n"
        finally:
            # 使用独立session保存AI回复，避免StreamingResponse生命周期问题
            if collected_reply:
                try:
                    from models.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as save_db:
                        ai_msg = ChatMessage(
                            user_id=_user_id,
                            conversation_id=_conversation_id,
                            role="assistant",
                            content=collected_reply,
                        )
                        save_db.add(ai_msg)
                        await save_db.commit()
                        logger.info(f"✅ AI回复已保存到对话 {_conversation_id}")
                except Exception as save_err:
                    logger.error(f"保存聊天记录失败: {save_err}", extra={"request_id": request_id})

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


# ---------- 同步接口（备用） ----------
@router.post("/sync", response_model=BaseResponse)
async def chat_sync(request: ChatRequest):
    """同步对话接口"""
    request_id = str(uuid.uuid4())
    request_id_var.set(request_id)
    try:
        workflow = await get_workflow()
        state = build_initial_state(request)
        # 添加超时控制，防止请求卡住
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
        return BaseResponse(code=HTTP_GATEWAY_TIMEOUT, message="请求超时", request_id=request_id)
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
        message="success",
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
    return BaseResponse(code=HTTP_OK, message="聊天记录已清空")


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