"""
api/routes/profile.py - 用户画像接口（零警告最终版）
- ✅ 所有类型警告已消除
- ✅ SQLAlchemy 异步 ORM 持久化
- ✅ 首次访问自动创建默认画像
- ✅ FastAPI 依赖注入
- ✅ 统一错误返回格式
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import asyncio

from api.schemas import (
    BaseResponse,
    ProfileResponse,
    ProfileUpdateRequest,
    ProfileData,  # 🔴 新增导入
)
from agents.profile_agent import ProfileAgent
from models.database import get_db
from models.profile import UserProfile, ProfileChangeLog
from models.user import User
from utils.logger import get_logger
from config.constants import HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE
from config.messages import (
    MSG_SUCCESS, MSG_PROFILE_GET_FAILED, MSG_PROFILE_UPDATE_SUCCESS,
    MSG_PROFILE_UPDATE_FAILED, MSG_PROFILE_RESET_SUCCESS,
    MSG_PROFILE_RESET_FAILED, MSG_PROFILE_SERVICE_ERROR,
)
from utils.api_helpers import generate_request_id, get_current_utc_time

router = APIRouter(prefix="/profile", tags=["用户画像"])
logger = get_logger(__name__, task_id="profile_api")

# ---------- Agent 单例 ----------
_profile_agent: Optional[ProfileAgent] = None
_agent_init_lock = asyncio.Lock()


async def get_profile_agent() -> ProfileAgent:
    """线程安全的 ProfileAgent 单例获取"""
    global _profile_agent
    if _profile_agent is None:
        async with _agent_init_lock:
            if _profile_agent is None:
                _profile_agent = ProfileAgent()
                logger.info("✅ ProfileAgent 初始化成功")
    return _profile_agent


async def get_valid_user_id(user_id: str) -> int:
    """用户ID校验依赖，自动转换为整数"""
    if not user_id.isdigit():
        raise ValueError("user_id 必须为数字格式")
    return int(user_id)


# ---------- 公共辅助函数（修复类型转换） ----------
async def _generate_default_profile(user_id: int) -> ProfileData:
    """调用 Agent 生成默认7维用户画像，返回 ProfileData 对象"""
    agent = await get_profile_agent()
    state = {"user_id": str(user_id), "profile_data": {}}
    result = await agent.process("", state)
    # 🔴 显式转换为 ProfileData 对象，消除类型警告
    return ProfileData(**result.get("profile_data", {}))


async def _get_or_create_profile(
    session: AsyncSession,
    user_id: int
) -> UserProfile:
    """获取数据库画像，不存在则自动创建默认画像（并发安全）"""
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()

    if profile is not None:
        return profile

    # 确保用户存在（外键约束要求 users 表有对应记录）
    user_result = await session.execute(
        select(User).where(User.id == user_id)
    )
    if user_result.scalar_one_or_none() is None:
        user = User(id=user_id, username=f"learner_{user_id:03d}")
        session.add(user)
        await session.flush()

    # 生成默认画像并入库
    default_data = await _generate_default_profile(user_id)
    profile = UserProfile(user_id=user_id, **default_data.model_dump())
    session.add(profile)
    try:
        await session.commit()
        logger.info(f"✅ 为用户 {user_id} 创建默认画像")
    except IntegrityError:
        await session.rollback()
        result = await session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            raise

    return profile


# ---------- 接口实现（修复所有 BaseResponse 参数） ----------
@router.get("/health", response_model=BaseResponse, description="画像服务健康检查")
async def health():
    request_id = generate_request_id()

    try:
        agent = await get_profile_agent()
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "status": "ok",
                "agent_initialized": agent is not None,
                "service": "profile"
            },
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"❌ 画像服务异常: {str(e)}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVICE_UNAVAILABLE,
            message=MSG_PROFILE_SERVICE_ERROR,
            data=None,
            request_id=request_id
        )


@router.get("/{user_id}", response_model=BaseResponse[ProfileResponse], description="获取用户7维学习画像")
async def get_profile(
    user_id: int = Depends(get_valid_user_id),
    session: AsyncSession = Depends(get_db)
):
    request_id = generate_request_id()

    try:
        logger.info(f"📋 获取用户画像 | 用户ID: {user_id}", extra={"request_id": request_id})

        profile = await _get_or_create_profile(session, user_id)

        # 🔴 显式构造 ProfileData 对象
        profile_data = ProfileData(
            knowledge_level=profile.knowledge_level,
            learning_goal=profile.learning_goal,
            learning_style=profile.learning_style,
            duration_preference=profile.duration_preference,
            weak_points=profile.weak_points,
            mastered_points=profile.mastered_points,
            motivation_level=profile.motivation_level,
            current_topic=profile.current_topic,
            last_study_at=profile.last_study_at,
        )

        response_data = ProfileResponse(
            user_id=str(user_id),
            profile=profile_data,
            updated_at=profile.updated_at.isoformat() if profile.updated_at else None
        )

        # 🔴 显式传入所有 BaseResponse 参数
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=response_data,
            request_id=request_id
        )

    except ValueError as e:
        logger.warning(f"⚠️ 无效的用户ID: {e}", extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"❌ 获取画像失败: {str(e)}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_PROFILE_GET_FAILED,
            data=None,
            request_id=request_id
        )


@router.put("/{user_id}/update", response_model=BaseResponse, description="增量更新用户画像")
async def update_profile(
    update_data: ProfileUpdateRequest,
    user_id: int = Depends(get_valid_user_id),
    session: AsyncSession = Depends(get_db)
):
    request_id = generate_request_id()

    try:
        logger.info(f"📝 更新用户画像 | 用户ID: {user_id}", extra={"request_id": request_id})

        profile = await _get_or_create_profile(session, user_id)

        # 增量更新：只更新传入的非空字段，同时记录变更
        update_dict = update_data.model_dump(exclude_unset=True, exclude_none=True)
        changed = {}
        for field, value in update_dict.items():
            if hasattr(profile, field):
                old_val = getattr(profile, field)
                if old_val != value:
                    changed[field] = {"old": old_val, "new": value}
                setattr(profile, field, value)

        # 更新修改时间
        profile.updated_at = get_current_utc_time()

        # 写入变更日志
        if changed:
            log_entry = ProfileChangeLog(
                user_id=user_id,
                changed_fields=changed,
                source="api",
            )
            session.add(log_entry)

        session.add(profile)
        await session.commit()

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_PROFILE_UPDATE_SUCCESS,
            data=None,
            request_id=request_id
        )

    except ValueError as e:
        logger.warning(f"⚠️ 无效的用户ID: {e}", extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"❌ 更新画像失败: {str(e)}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_PROFILE_UPDATE_FAILED,
            data=None,
            request_id=request_id
        )


@router.delete("/{user_id}", response_model=BaseResponse, description="重置用户画像为默认值")
async def reset_profile(
    user_id: int = Depends(get_valid_user_id),
    session: AsyncSession = Depends(get_db)
):
    request_id = generate_request_id()

    try:
        logger.info(f"🔄 重置用户画像 | 用户ID: {user_id}", extra={"request_id": request_id})

        profile = await _get_or_create_profile(session, user_id)

        # 恢复为Agent生成的默认值
        default_data = await _generate_default_profile(user_id)
        for field, value in default_data.model_dump().items():
            if hasattr(profile, field):
                setattr(profile, field, value)

        profile.updated_at = get_current_utc_time()

        session.add(profile)
        await session.commit()

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_PROFILE_RESET_SUCCESS,
            data=None,
            request_id=request_id
        )

    except ValueError as e:
        logger.warning(f"⚠️ 无效的用户ID: {e}", extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"❌ 重置画像失败: {str(e)}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_PROFILE_RESET_FAILED,
            data=None,
            request_id=request_id
        )


@router.post("/{user_id}/refresh", response_model=BaseResponse, description="手动刷新用户画像（基于最近对话历史）")
async def refresh_profile(
    user_id: int = Depends(get_valid_user_id),
    db: AsyncSession = Depends(get_db),
):
    """手动刷新用户画像，基于最近20条对话历史重新分析"""
    request_id = generate_request_id()

    try:
        logger.info(f"🔄 手动刷新画像 | 用户ID: {user_id}", extra={"request_id": request_id})

        # 加载最近对话历史
        from models.chat_message import ChatMessage
        from config.constants import CHAT_HISTORY_LOAD_LIMIT

        history_query = (
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(CHAT_HISTORY_LOAD_LIMIT)
        )
        history_result = await db.execute(history_query)
        history_msgs = history_result.scalars().all()
        chat_history = [{"role": m.role, "content": m.content} for m in reversed(history_msgs)]

        if not chat_history:
            return BaseResponse(
                code=HTTP_OK,
                message="暂无对话历史，无法刷新画像",
                data=None,
                request_id=request_id,
            )

        # 加载当前画像
        profile = await _get_or_create_profile(db, user_id)
        old_profile = {
            "knowledge_level": profile.knowledge_level,
            "learning_style": profile.learning_style,
            "learning_goal": profile.learning_goal,
            "duration_preference": profile.duration_preference,
            "weak_points": profile.weak_points or [],
            "mastered_points": profile.mastered_points or [],
            "motivation_level": profile.motivation_level,
            "current_topic": profile.current_topic,
        }

        # 用统一路由 Agent 做画像提取（只取画像部分）
        from agents.unified_router_agent import UnifiedRouterAgent
        agent = UnifiedRouterAgent()

        # 把所有历史合并为一段文本，让 LLM 分析
        history_text = "\n".join([f"{m['role']}: {m['content']}" for m in chat_history[-10:]])
        combined_input = f"以下是用户最近的对话历史，请分析其中的学习画像信息：\n\n{history_text}"

        result = await agent.process(combined_input, {"profile_data": old_profile, "chat_history": chat_history})
        profile_update = result.get("_profile_update")

        if profile_update and isinstance(profile_update, dict) and len(profile_update) > 0:
            # 持久化更新
            for key, value in profile_update.items():
                if hasattr(profile, key) and value is not None:
                    setattr(profile, key, value)
            profile.updated_at = get_current_utc_time()

            # 审计日志
            log_entry = ProfileChangeLog(
                user_id=user_id,
                changed_fields=profile_update,
                source="manual_refresh",
                raw_llm_output=profile_update,
                confidence=result.get("_profile_confidence", 1.0),
            )
            db.add(log_entry)
            await db.commit()

            # 返回更新后的画像
            updated = ProfileData(
                knowledge_level=profile.knowledge_level,
                learning_goal=profile.learning_goal,
                learning_style=profile.learning_style,
                duration_preference=profile.duration_preference,
                weak_points=profile.weak_points,
                mastered_points=profile.mastered_points,
                motivation_level=profile.motivation_level,
                current_topic=profile.current_topic,
                last_study_at=profile.last_study_at,
            )
            return BaseResponse(
                code=HTTP_OK,
                message="画像已刷新",
                data=updated,
                request_id=request_id,
            )
        else:
            return BaseResponse(
                code=HTTP_OK,
                message="对话历史中未发现新的画像信息",
                data=None,
                request_id=request_id,
            )

    except Exception as e:
        logger.error(f"❌ 刷新画像失败: {str(e)}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"刷新失败: {str(e)}",
            data=None,
            request_id=request_id,
        )

