"""
api/routes/conversation.py - 对话会话管理接口
- 创建/列出/获取/删除对话
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import (
    BaseResponse, ConversationCreateRequest, ConversationResponse,
)
from api.routes.auth import get_current_user
from models.user import User
from models.conversation import Conversation
from models.chat_message import ChatMessage
from models.database import get_db
from config.constants import HTTP_OK, HTTP_BAD_REQUEST
from utils.logger import get_logger

logger = get_logger(__name__, task_id="conversation")
router = APIRouter(prefix="/conversation", tags=["对话会话"])


@router.post("", response_model=BaseResponse, summary="创建新对话")
async def create_conversation(
    req: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = Conversation(
        user_id=current_user.id,
        title=req.title or "新对话",
    )
    db.add(conv)
    await db.flush()
    await db.refresh(conv)

    logger.info(f"创建对话: user={current_user.username}, conv_id={conv.id}")
    return BaseResponse(
        code=HTTP_OK,
        message="对话已创建",
        data=ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=0,
        ).model_dump(mode="json"),
    )


@router.get("", response_model=BaseResponse, summary="获取对话列表")
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户的所有对话，按更新时间倒序"""
    # 查询对话列表
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(desc(Conversation.updated_at))
    )
    convs = result.scalars().all()

    # 为每个对话查询消息数量和最后一条消息
    conv_list = []
    for conv in convs:
        # 消息数量
        count_result = await db.execute(
            select(func.count()).where(ChatMessage.conversation_id == conv.id)
        )
        msg_count = count_result.scalar() or 0

        # 最后一条消息预览
        last_msg_result = await db.execute(
            select(ChatMessage.content)
            .where(ChatMessage.conversation_id == conv.id)
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        last_msg = last_msg_result.scalar_one_or_none()

        conv_list.append(ConversationResponse(
            id=conv.id,
            title=conv.title,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
            last_message=last_msg[:50] + "..." if last_msg and len(last_msg) > 50 else last_msg,
        ).model_dump(mode="json"))

    return BaseResponse(code=HTTP_OK, message="success", data=conv_list)


@router.get("/{conversation_id}", response_model=BaseResponse, summary="获取对话详情")
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取指定对话的消息列表"""
    # 验证对话存在且属于当前用户
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="对话不存在")

    # 获取对话下的所有消息
    msg_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = msg_result.scalars().all()

    return BaseResponse(
        code=HTTP_OK,
        message="success",
        data={
            "conversation": ConversationResponse(
                id=conv.id,
                title=conv.title,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
                message_count=len(messages),
            ).model_dump(mode="json"),
            "messages": [
                {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None}
                for m in messages
            ],
        },
    )


@router.put("/{conversation_id}", response_model=BaseResponse, summary="更新对话标题")
async def update_conversation(
    conversation_id: int,
    req: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="对话不存在")

    if req.title:
        conv.title = req.title
    await db.commit()

    return BaseResponse(code=HTTP_OK, message="更新成功")


@router.delete("/{conversation_id}", response_model=BaseResponse, summary="删除对话")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, Conversation.user_id == current_user.id)
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        raise HTTPException(status_code=HTTP_BAD_REQUEST, detail="对话不存在")

    await db.delete(conv)
    await db.commit()

    logger.info(f"删除对话: user={current_user.username}, conv_id={conversation_id}")
    return BaseResponse(code=HTTP_OK, message="对话已删除")
