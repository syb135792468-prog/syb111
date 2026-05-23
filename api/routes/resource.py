"""
api/routes/resource.py - 学习资源接口（零警告最终版）
- 修正 ResourceItem 对象访问错误（使用属性，非字典方法）
- 移除无工作的泛型响应模型
- 简化分页计数查询
- 保留所有安全与超时机制
- 消除所有PyCharm类型警告
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from typing import Optional, Dict, AsyncGenerator  # 🔴 修复1：删除未使用的Any
import uuid
import contextvars
import asyncio

from api.schemas import (
    BaseResponse,
    ResourceResponse,
    ResourceRequest,
    ResourceMetadata,
)
from models.database import AsyncSessionLocal
from models.resource import Resource
from models.user import User
from models.profile import UserProfile
from agents.quiz_agent import QuizAgent
from agents.code_agent import CodeAgent
from agents.mindmap_agent import MindmapAgent
from agents.doc_agent import DocAgent
from agents.video_agent import VideoAgent
from agents.base_agent import BaseAgent
from utils.logger import get_logger
from config.settings import settings
from config.constants import (
    DEFAULT_RESOURCE_LIMIT, MAX_RESOURCE_LIMIT, RESOURCE_GENERATE_TIMEOUT_SEC,
    RESOURCE_PROGRESS_COMPLETE, HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND,
    HTTP_SERVER_ERROR, HTTP_GATEWAY_TIMEOUT,
)

request_id_var = contextvars.ContextVar("request_id", default="unknown")

router = APIRouter(prefix="/resource", tags=["学习资源"])
logger = get_logger(__name__, task_id="resource_api")

# ---------- Agent 注册表与单例 ----------
_AGENT_REGISTRY: Dict[str, type[BaseAgent]] = {
    "quiz": QuizAgent,
    "code": CodeAgent,
    "mindmap": MindmapAgent,
    "doc": DocAgent,
    "video": VideoAgent,
}
_agents: Dict[str, BaseAgent] = {}
_agent_lock = asyncio.Lock()

async def get_agent(resource_type: str) -> BaseAgent:
    if resource_type not in _AGENT_REGISTRY:
        raise ValueError(f"不支持的资源类型: {resource_type}")
    if resource_type not in _agents:
        async with _agent_lock:
            if resource_type not in _agents:
                if resource_type == "mindmap":
                    _agents[resource_type] = _AGENT_REGISTRY[resource_type](use_llm=True, output_format="json")
                else:
                    _agents[resource_type] = _AGENT_REGISTRY[resource_type]()
                logger.info(f"✅ {resource_type} Agent 初始化成功")
    return _agents[resource_type]

# ---------- FastAPI 依赖 ----------
# 🔴 修复2：修正get_db的返回类型注解
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

async def get_request_id() -> str:
    rid = str(uuid.uuid4())
    request_id_var.set(rid)
    return rid

# ---------- 辅助函数 ----------
def resource_to_response(r: Resource) -> ResourceResponse:
    meta = ResourceMetadata(**r.extra_metadata) if r.extra_metadata else None
    return ResourceResponse(
        id=r.id,
        resource_type=r.resource_type,
        title=r.title,
        content=r.content,
        knowledge_points=r.knowledge_points,
        status=r.status,
        progress_percent=r.progress_percent,
        extra_metadata=meta,
        created_at=r.created_at.isoformat() if r.created_at else None,
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
    )

async def get_user_or_404(session: AsyncSession, user_id: int) -> User:
    user: Optional[User] = await session.get(User, user_id)  # 🔴 修复3：添加类型注解
    if not user:
        raise ValueError(f"用户 {user_id} 不存在")
    return user

async def load_profile_context(session: AsyncSession, user_id: int) -> dict:
    # 获取画像，不存在则自动创建默认画像
    profile: Optional[UserProfile] = await session.get(UserProfile, user_id)  # 🔴 修复3：添加类型注解
    if not profile:
        from agents.profile_agent import ProfileAgent
        agent = ProfileAgent()
        result = await agent.process("", {"user_id": str(user_id), "profile_data": {}})
        default_data = result.get("profile_data", {})
        profile = UserProfile(user_id=user_id, **default_data)
        session.add(profile)
        await session.commit()
        logger.info(f"✅ 为用户 {user_id} 创建默认画像")
    return {
        "knowledge_level": profile.knowledge_level,
        "learning_goal": profile.learning_goal,
        "learning_style": profile.learning_style,
        "weak_points": profile.weak_points,
        "mastered_points": profile.mastered_points,
    }

# ====================== 接口 ======================
@router.get("/health", response_model=BaseResponse)
async def health(request_id: str = Depends(get_request_id)):
    return BaseResponse(
        code=HTTP_OK,
        message="success",
        data={
            "status": "ok",
            "supported_types": list(_AGENT_REGISTRY.keys()),
            "agents_initialized": len(_agents) == len(_AGENT_REGISTRY),
        },
        request_id=request_id,
    )

@router.get("/{resource_id}", response_model=BaseResponse)
async def get_resource(
    resource_id: int,
    user_id: int = Query(..., description="用户ID"),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)  # 🔴 修复3：添加类型注解
        if not r or r.user_id != user_id or not r.is_active:
            # 🔴 修复4：显式传入所有BaseResponse参数
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message="资源不存在",
                data=None,
                request_id=request_id
            )
        return BaseResponse(
            code=HTTP_OK,
            message="success",
            data=resource_to_response(r),
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"获取资源失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message="服务器错误",
            data=None,
            request_id=request_id
        )

@router.get("/", response_model=BaseResponse)
async def list_resources(
    user_id: int = Query(...),
    resource_type: Optional[str] = Query(None),
    status: Optional[str] = Query("completed"),
    limit: int = Query(DEFAULT_RESOURCE_LIMIT, ge=1, le=MAX_RESOURCE_LIMIT),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    try:
        # 统一条件
        conditions = [Resource.user_id == user_id, Resource.is_active == True]
        if resource_type:
            conditions.append(Resource.resource_type == resource_type)
        if status:
            conditions.append(Resource.status == status)

        # 计数
        count_stmt = select(func.count(Resource.id)).where(*conditions)
        total = (await session.execute(count_stmt)).scalar() or 0

        # 数据查询
        stmt = select(Resource).where(*conditions).order_by(Resource.created_at.desc()).offset(offset).limit(limit)
        result = await session.execute(stmt)
        resources = result.scalars().all()

        data = {
            "resources": [resource_to_response(r) for r in resources],
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
        }
        return BaseResponse(
            code=HTTP_OK,
            message="success",
            data=data,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"获取列表失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message="服务器错误",
            data=None,
            request_id=request_id
        )

@router.post("/generate", response_model=BaseResponse)
async def generate_resource(
    req: ResourceRequest,
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    try:
        if not req.user_id.isdigit():
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message="user_id 非法",
                data=None,
                request_id=request_id
            )
        uid = int(req.user_id)

        # 用户存在性与画像
        await get_user_or_404(session, uid)
        profile_ctx = await load_profile_context(session, uid)

        # Agent 生成
        agent = await get_agent(req.resource_type)
        context = {
            "user_id": req.user_id,
            "profile_data": profile_ctx,
            "topic": req.topic,
            "resource_list": [],
        }
        result = await asyncio.wait_for(
            agent.process(user_input=req.topic, context=context),
            timeout=getattr(settings, "RESOURCE_GENERATE_TIMEOUT", RESOURCE_GENERATE_TIMEOUT_SEC)
        )

        new_items = result.get("resource_list", [])
        if not new_items:
            return BaseResponse(
                code=HTTP_SERVER_ERROR,
                message="生成失败，无数据",
                data=None,
                request_id=request_id
            )

        # 关键修正：使用属性访问而非 .get()
        item = new_items[0]  # ResourceItem 对象
        db_resource = Resource(
            user_id=uid,
            task_id=str(uuid.uuid4()),
            resource_type=req.resource_type,
            title=item.title,
            content=item.content,
            knowledge_points=item.knowledge_points,
            status="completed",
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            extra_metadata=item.extra_metadata,
        )
        session.add(db_resource)

        try:
            await session.commit()
            await session.refresh(db_resource)
        except (IntegrityError, Exception) as db_err:
            await session.rollback()
            # 查询已有资源（唯一约束冲突或FlushError）
            exist_stmt = select(Resource).where(
                Resource.user_id == uid,
                Resource.title == item.title,
                Resource.resource_type == req.resource_type,
                Resource.is_active == True,
            )
            exist_result = await session.execute(exist_stmt)
            existing: Optional[Resource] = exist_result.scalar_one_or_none()
            if existing:
                logger.info("资源已存在，返回已有记录")
                return BaseResponse(
                    code=HTTP_OK,
                    message="资源已存在",
                    data=resource_to_response(existing),
                    request_id=request_id
                )
            else:
                raise  # 重抛其他错误

        return BaseResponse(
            code=HTTP_OK,
            message="success",
            data=resource_to_response(db_resource),
            request_id=request_id
        )

    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_GATEWAY_TIMEOUT,
            message="生成超时",
            data=None,
            request_id=request_id
        )
    except ValueError as e:
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"生成失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message="生成失败",
            data=None,
            request_id=request_id
        )

@router.delete("/{resource_id}", response_model=BaseResponse)
async def delete_resource(
    resource_id: int,
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)  # 🔴 修复3：添加类型注解
        if not r or r.user_id != user_id or not r.is_active:
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message="资源不存在",
                data=None,
                request_id=request_id
            )
        r.is_active = False
        await session.commit()
        return BaseResponse(
            code=HTTP_OK,
            message="删除成功",
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"删除失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message="删除失败",
            data=None,
            request_id=request_id
        )