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
from typing import Optional, Dict, Any, AsyncGenerator
import uuid
import contextvars
import asyncio
import random
from datetime import datetime

from api.schemas import (
    BaseResponse,
    ResourceResponse,
    ResourceRequest,
    ResourceMetadata,
    ExpandNodeRequest,
)
from models.database import AsyncSessionLocal
from models.resource import Resource
from models.user import User
from models.profile import UserProfile
from models.quiz_attempt import QuizAttempt
from agents.quiz_agent import QuizAgent
from agents.code_agent import CodeAgent
from agents.mindmap_agent import MindmapAgent
from agents.doc_agent import DocAgent
from agents.video_agent import VideoAgent
from agents.base_agent import BaseAgent
from utils.agent_helpers import match_knowledge_point
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from utils.logger import get_logger
from config.settings import settings
from config.constants import (
    DEFAULT_RESOURCE_LIMIT, MAX_RESOURCE_LIMIT, RESOURCE_GENERATE_TIMEOUT_SEC,
    RESOURCE_PROGRESS_COMPLETE, HTTP_OK, HTTP_BAD_REQUEST, HTTP_NOT_FOUND,
    HTTP_SERVER_ERROR, HTTP_GATEWAY_TIMEOUT,
    QUIZ_PARALLEL_CONCURRENCY, QUIZ_DEDUP_MAX_ROUNDS,
    MAX_QUIZ_QUESTION_COUNT, QUIZ_GEN_RETRY_COUNT, DEDUP_CONTENT_TRUNCATE_LENGTH,
    PROFILE_GENERATE_TIMEOUT_SEC, DIFFICULTY_RECOMMEND_SAMPLE_SIZE,
    DIFFICULTY_HARD_THRESHOLD, DIFFICULTY_MEDIUM_THRESHOLD, DIFFICULTY_MEDIUM,
    DIFFICULTY_HARD, DIFFICULTY_EASY, DIFFICULTY_AUTO,
    DEFAULT_KNOWLEDGE_LEVEL, DEFAULT_LEARNING_GOAL, DEFAULT_LEARNING_STYLE,
    QUIZ_TYPE_CHOICE, QUIZ_TYPE_MULTI, RESOURCE_TYPE_QUIZ, RESOURCE_TYPE_MINDMAP,
    DEFAULT_TOPIC, RESOURCE_ID_TRUNCATE_LENGTH, MINDMAP_EXPAND_TIMEOUT_SEC,
)
from config.messages import (
    MSG_SUCCESS, MSG_SERVER_ERROR, MSG_RESOURCE_NOT_FOUND,
    MSG_GENERATE_NO_DATA, MSG_GENERATE_TIMEOUT, MSG_DELETE_SUCCESS,
    MSG_DELETE_FAILED, MSG_INVALID_USER_ID, MSG_REQUEST_PARAM_ERROR,
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
                if resource_type == RESOURCE_TYPE_MINDMAP:
                    _agents[resource_type] = _AGENT_REGISTRY[resource_type](output_format="json")
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
    profile: Optional[UserProfile] = await session.get(UserProfile, user_id)
    if not profile:
        try:
            from agents.profile_agent import ProfileAgent
            agent = ProfileAgent()
            result = await asyncio.wait_for(
                agent.process("", {"user_id": str(user_id), "profile_data": {}}),
                timeout=PROFILE_GENERATE_TIMEOUT_SEC,
            )
            default_data = result.get("profile_data", {})
            profile = UserProfile(user_id=user_id, **default_data)
            session.add(profile)
            await session.commit()
            logger.info(f"✅ 为用户 {user_id} 创建默认画像")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ 创建默认画像超时，使用兜底数据")
            profile = UserProfile(
                user_id=user_id,
                knowledge_level=DEFAULT_KNOWLEDGE_LEVEL,
                learning_goal=DEFAULT_LEARNING_GOAL,
                learning_style=DEFAULT_LEARNING_STYLE,
                weak_points=[],
                mastered_points=[],
            )
            session.add(profile)
            await session.commit()
    return {
        "knowledge_level": profile.knowledge_level,
        "learning_goal": profile.learning_goal,
        "learning_style": profile.learning_style,
        "weak_points": profile.weak_points,
        "mastered_points": profile.mastered_points,
    }

async def _recommend_difficulty(session: AsyncSession, user_id: int, topic: str) -> str:
    """根据用户能力自适应推荐难度（IRT 贝叶斯估计 + 准确率兜底）"""
    try:
        from ai.adaptive_difficulty import AdaptiveDifficultyEngine
        engine = AdaptiveDifficultyEngine(session)
        return await engine.select_difficulty_for_topic(user_id, topic)
    except Exception:
        # 兜底：简单准确率统计
        try:
            from sqlalchemy import select
            stmt = (
                select(QuizAttempt.is_correct)
                .where(QuizAttempt.user_id == user_id)
                .order_by(QuizAttempt.created_at.desc())
                .limit(DIFFICULTY_RECOMMEND_SAMPLE_SIZE)
            )
            result = await session.execute(stmt)
            rows = result.scalars().all()
            if not rows:
                return DIFFICULTY_MEDIUM
            accuracy = sum(1 for r in rows if r) / len(rows)
            if accuracy >= DIFFICULTY_HARD_THRESHOLD:
                return DIFFICULTY_HARD
            elif accuracy >= DIFFICULTY_MEDIUM_THRESHOLD:
                return DIFFICULTY_MEDIUM
            else:
                return DIFFICULTY_EASY
        except Exception:
            return DIFFICULTY_MEDIUM

# ====================== 接口 ======================
@router.get("/health", response_model=BaseResponse)
async def health(request_id: str = Depends(get_request_id)):
    return BaseResponse(
        code=HTTP_OK,
        message=MSG_SUCCESS,
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
                message=MSG_RESOURCE_NOT_FOUND,
                data=None,
                request_id=request_id
            )
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=resource_to_response(r),
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"获取资源失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_SERVER_ERROR,
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
            message=MSG_SUCCESS,
            data=data,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"获取列表失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_SERVER_ERROR,
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
        logger.info(f"🔵 生成请求: topic={req.topic!r}, type={req.resource_type}, config={req.config}")
        if not req.user_id.isdigit():
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message=MSG_INVALID_USER_ID,
                data=None,
                request_id=request_id
            )
        uid = int(req.user_id)

        # 用户存在性与画像
        await get_user_or_404(session, uid)
        profile_ctx = await load_profile_context(session, uid)

        # 从 config 中提取生成参数
        cfg = req.config or {}
        question_count = cfg.get("questionCount", 1) if req.resource_type == RESOURCE_TYPE_QUIZ else 1
        question_count = max(1, min(question_count, MAX_QUIZ_QUESTION_COUNT))
        allowed_types = cfg.get("questionTypes", None)  # 如 ["choice", "fill", "code"]
        difficulty = cfg.get("difficulty", DIFFICULTY_MEDIUM)
        include_explanation = cfg.get("includeExplanation", True)
        custom_prompt = cfg.get("customPrompt", "")

        # 自适应难度：difficulty 为 "auto" 时根据历史表现推荐
        if difficulty == DIFFICULTY_AUTO:
            difficulty = await _recommend_difficulty(session, uid, req.topic)
            logger.info(f"自适应难度推荐: {difficulty}")

        # Agent 生成
        agent = await get_agent(req.resource_type)

        if req.resource_type == RESOURCE_TYPE_QUIZ and question_count > 1:
            # 多题模式：预计算知识点 + 并行生成 + 去重
            questions_meta = []
            content_parts = [f"# {req.topic} 练习题（共 {question_count} 题）"]
            knowledge_points = []

            # 标准化知识点：优先匹配标准知识点名，兜底用原始输入
            raw_topic = req.topic.strip()
            target_kp = match_knowledge_point(raw_topic) or raw_topic or DEFAULT_TOPIC
            logger.info(f"多题生成目标知识点: {target_kp} (输入: {req.topic})")
            logger.info(f"🔵 Agent LLM模式: {agent.use_llm}, 熔断状态: disabled_until={agent._llm_disabled_until}")

            # 题型轮转：确保三种题型均匀分布
            if allowed_types:
                type_cycle = []
                while len(type_cycle) < question_count:
                    type_cycle.extend(allowed_types)
                type_cycle = type_cycle[:question_count]
                random.shuffle(type_cycle)
            else:
                type_cycle = [None] * question_count

            sem = asyncio.Semaphore(QUIZ_PARALLEL_CONCURRENCY)

            async def gen_one(idx: int, q_type):
                """并行生成单题（带信号量限流 + 内部重试 + 知识点验证）"""
                async with sem:
                    ctx = {
                        "user_id": req.user_id,
                        "profile_data": profile_ctx,
                        "topic": target_kp,  # 使用预计算的知识点
                        "resource_list": [],
                    }
                    for attempt in range(QUIZ_GEN_RETRY_COUNT):
                        try:
                            result = await asyncio.wait_for(
                                agent.process(
                                    user_input=target_kp, context=ctx, quiz_type=q_type,
                                    difficulty=difficulty, include_explanation=include_explanation,
                                    custom_prompt=custom_prompt,
                                    force_knowledge_point=target_kp,  # 强制使用目标知识点
                                ),
                                timeout=getattr(settings, "RESOURCE_GENERATE_TIMEOUT", RESOURCE_GENERATE_TIMEOUT_SEC)
                            )
                            items = result.get("resource_list", [])
                            if items:
                                item = items[0]
                                # 验证题目知识点是否匹配
                                item_meta = item.extra_metadata or {}
                                item_kp = item_meta.get("knowledge_point", "")
                                if item_kp and item_kp != target_kp:
                                    logger.warning(f"第 {idx+1} 题知识点不匹配: 预期={target_kp}, 实际={item_kp}, 重试")
                                    continue
                                return item
                        except asyncio.TimeoutError:
                            logger.warning(f"第 {idx+1} 题超时 (attempt {attempt+1})")
                        except Exception as e:
                            logger.warning(f"第 {idx+1} 题异常: {e}")
                    return None

            # 第一轮：并行生成所有题目
            tasks = [gen_one(i, type_cycle[i]) for i in range(question_count)]
            raw_items = await asyncio.gather(*tasks)

            # 去重（用 question_hash，fallback 到 content[:100]）
            seen_hashes = set()
            valid_items = []
            for item in raw_items:
                if item is None:
                    continue
                meta = item.extra_metadata or {}
                dedup_key = meta.get("question_hash") or item.content[:DEDUP_CONTENT_TRUNCATE_LENGTH]
                if dedup_key not in seen_hashes:
                    seen_hashes.add(dedup_key)
                    valid_items.append(item)

            # 补生成：去重后不足则再补几轮
            for round_i in range(QUIZ_DEDUP_MAX_ROUNDS):
                if len(valid_items) >= question_count:
                    break
                missing = question_count - len(valid_items)
                logger.info(f"去重后不足，补生成 {missing} 题（第 {round_i+1} 轮）")
                fill_types = [random.choice(allowed_types) if allowed_types else None for _ in range(missing)]
                fill_tasks = [gen_one(question_count + j, fill_types[j]) for j in range(missing)]
                fill_results = await asyncio.gather(*fill_tasks)
                for item in fill_results:
                    if item is None:
                        continue
                    meta = item.extra_metadata or {}
                    dedup_key = meta.get("question_hash") or item.content[:DEDUP_CONTENT_TRUNCATE_LENGTH]
                    if dedup_key not in seen_hashes:
                        seen_hashes.add(dedup_key)
                        valid_items.append(item)

            # 组装最终内容
            for idx, item in enumerate(valid_items[:question_count]):
                meta = item.extra_metadata or {}
                questions_meta.append({
                    "index": len(questions_meta) + 1,
                    "quiz_type": meta.get("quiz_type", QUIZ_TYPE_CHOICE),
                    "answer": meta.get("answer", ""),
                    "explanation": meta.get("explanation", ""),
                })
                raw = item.content
                lines = raw.split("\n")
                body_lines = []
                skip_first = True
                for line in lines:
                    if skip_first and line.startswith("# "):
                        skip_first = False
                        continue
                    body_lines.append(line)
                body = "\n".join(body_lines).strip()

                content_parts.append(f"\n---\n\n## 第 {len(questions_meta)} 题")
                content_parts.append(body)

                if item.knowledge_points:
                    knowledge_points.extend(item.knowledge_points)

            if not content_parts or len(questions_meta) == 0:
                return BaseResponse(
                    code=HTTP_SERVER_ERROR,
                    message=MSG_GENERATE_NO_DATA,
                    data=None,
                    request_id=request_id
                )

            combined_content = "\n".join(content_parts)
            unique_kp = list(dict.fromkeys(knowledge_points))  # 去重保序
            combined_meta = {
                "quiz_type": QUIZ_TYPE_MULTI,
                "question_count": len(questions_meta),
                "questions": questions_meta,
            }

            ts = datetime.now().strftime("%m%d%H%M")
            db_resource = Resource(
                user_id=uid,
                task_id=str(uuid.uuid4()),
                resource_type=req.resource_type,
                title=f"{req.topic} 练习题（{len(questions_meta)}道）{ts}",
                content=combined_content,
                knowledge_points=unique_kp,
                status="completed",
                progress_percent=RESOURCE_PROGRESS_COMPLETE,
                extra_metadata=combined_meta,
            )
            session.add(db_resource)

        else:
            # 单题模式 - 标准化知识点
            raw_topic = req.topic.strip()
            # SQL 建表语句跳过知识点匹配，保留原始输入
            if req.resource_type == RESOURCE_TYPE_MINDMAP and "CREATE TABLE" in raw_topic.upper()[:200]:
                single_kp = raw_topic
            # 视频类型跳过知识点匹配，直接用用户原始输入（视频是展示性的，不需要严格匹配标准知识点）
            elif req.resource_type == "video":
                single_kp = raw_topic or DEFAULT_TOPIC
            else:
                single_kp = match_knowledge_point(raw_topic) or raw_topic or DEFAULT_TOPIC
            context = {
                "user_id": req.user_id,
                "profile_data": profile_ctx,
                "topic": single_kp,
                "resource_list": [],
                "config": cfg,  # 传递前端配置（duration/style/voice_rate等）
            }
            # 只有 QuizAgent 接受 difficulty/include_explanation/custom_prompt/force_knowledge_point 参数
            process_kwargs: Dict[str, Any] = {}
            if req.resource_type == RESOURCE_TYPE_QUIZ:
                process_kwargs = {
                    "difficulty": difficulty,
                    "include_explanation": include_explanation,
                    "custom_prompt": custom_prompt,
                    "force_knowledge_point": single_kp,
                }
            result = await asyncio.wait_for(
                agent.process(
                    user_input=single_kp or req.topic, context=context,
                    **process_kwargs,
                ),
                timeout=getattr(settings, "RESOURCE_GENERATE_TIMEOUT", RESOURCE_GENERATE_TIMEOUT_SEC)
            )
            new_items = result.get("resource_list", [])
            if not new_items:
                return BaseResponse(
                    code=HTTP_SERVER_ERROR,
                    message=MSG_GENERATE_NO_DATA,
                    data=None,
                    request_id=request_id
                )
            item = new_items[0]
            # 添加时间戳避免标题唯一约束冲突
            ts = datetime.now().strftime("%m%d%H%M%S")
            title = f"{item.title} {ts}"
            db_resource = Resource(
                user_id=uid,
                task_id=str(uuid.uuid4()),
                resource_type=req.resource_type,
                title=title,
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
        except IntegrityError:
            # 唯一约束冲突：用 task_id 后缀重试
            await session.rollback()
            db_resource.title = f"{db_resource.title} {uuid.uuid4().hex[:RESOURCE_ID_TRUNCATE_LENGTH]}"
            session.add(db_resource)
            try:
                await session.commit()
                await session.refresh(db_resource)
            except Exception as retry_err:
                await session.rollback()
                logger.error(f"保存资源重试失败: {retry_err}")
                return BaseResponse(
                    code=HTTP_SERVER_ERROR,
                    message=f"保存失败: {retry_err}",
                    data=None,
                    request_id=request_id
                )
        except Exception as db_err:
            await session.rollback()
            logger.error(f"保存资源失败: {db_err}")
            return BaseResponse(
                code=HTTP_SERVER_ERROR,
                message=f"保存失败: {db_err}",
                data=None,
                request_id=request_id
            )

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data=resource_to_response(db_resource),
            request_id=request_id
        )

    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_GATEWAY_TIMEOUT,
            message=MSG_GENERATE_TIMEOUT,
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
            message=f"生成失败: {e}",
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
                message=MSG_RESOURCE_NOT_FOUND,
                data=None,
                request_id=request_id
            )
        r.is_active = False
        await session.commit()
        return BaseResponse(
            code=HTTP_OK,
            message=MSG_DELETE_SUCCESS,
            data=None,
            request_id=request_id
        )
    except Exception as e:
        logger.error(f"删除失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_DELETE_FAILED,
            data=None,
            request_id=request_id
        )


def _merge_children_into_tree(content: str, node_id: str, children: list) -> str:
    """将新生成的子节点合并到思维导图 JSON 树中指定 node_id 的 children 字段"""
    import json
    try:
        data = json.loads(content)
        node_data = data.get("nodeData", data)

        def find_and_merge(node: dict) -> bool:
            if node.get("id") == node_id:
                node["children"] = children
                return True
            for child in node.get("children", []):
                if find_and_merge(child):
                    return True
            return False

        find_and_merge(node_data)
        if "nodeData" in data:
            data["nodeData"] = node_data
        return json.dumps(data, ensure_ascii=False)
    except Exception:
        return content


@router.post("/expand-node", response_model=BaseResponse)
async def expand_mindmap_node(
    req: ExpandNodeRequest,
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    try:
        if not req.user_id.isdigit():
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message=MSG_INVALID_USER_ID,
                data=None,
                request_id=request_id
            )
        uid = int(req.user_id)

        # 用户存在性检查
        await get_user_or_404(session, uid)

        # 获取资源并验证归属
        resource: Optional[Resource] = await session.get(Resource, req.resource_id)
        if not resource or resource.user_id != uid or not resource.is_active:
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message=MSG_RESOURCE_NOT_FOUND,
                data=None,
                request_id=request_id
            )

        # 调用 MindmapAgent 展开节点
        agent = await get_agent("mindmap")
        children = await asyncio.wait_for(
            agent.expand_node(
                node_topic=req.node_topic,
                node_definition=req.node_definition,
                node_syntax=req.node_syntax,
                node_examples=req.node_examples,
                node_pitfalls=req.node_pitfalls,
                node_advice=req.node_advice,
                parent_node_id=req.node_id,
            ),
            timeout=MINDMAP_EXPAND_TIMEOUT_SEC,
        )

        # 将新子树合并到原 resource.content 中持久化
        resource.content = _merge_children_into_tree(
            resource.content, req.node_id, children
        )
        await session.commit()

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={"children": children},
            request_id=request_id,
        )

    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_GATEWAY_TIMEOUT,
            message="节点展开超时，请重试",
            data=None,
            request_id=request_id,
        )
    except ValueError as e:
        return BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=str(e),
            data=None,
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"节点展开失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"节点展开失败: {e}",
            data=None,
            request_id=request_id,
        )