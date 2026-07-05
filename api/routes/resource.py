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
import os
import contextvars
import asyncio
import random
import re
from collections import Counter
from datetime import datetime
import requests as http_requests

from api.schemas import (
    BaseResponse,
    ResourceResponse,
    ResourceRequest,
    ResourceMetadata,
    ExpandNodeRequest,
    SaveExternalVideoRequest,
)
from models.database import AsyncSessionLocal
from models.resource import Resource
from models.user import User
from models.profile import UserProfile
from models.quiz_attempt import QuizAttempt
from agents.quiz_agent import QuizAgent
from agents.code_agent import CodeAgent
from agents.mindmap_agent import MindmapAgent
from agents.content_agent import ContentAgent, ContentType
from agents.video_agent import VideoAgent
from agents.base_agent import BaseAgent
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
    VIDEO_OUTPUT_DIR,
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
    "doc": ContentAgent,
    "video": VideoAgent,
    "reading": ContentAgent,
    "slides": ContentAgent,
}
# ContentAgent 需要 content_type 参数的映射
_CONTENT_TYPE_MAP: Dict[str, ContentType] = {
    "doc": ContentType.DOCUMENT,
    "reading": ContentType.READING,
    "slides": ContentType.SLIDES,
}
_agents: Dict[str, BaseAgent] = {}
_agent_lock = asyncio.Lock()


def _is_retryable_quiz_generation_error(exc: Exception) -> bool:
    """区分可重试和不可重试的练习题生成错误，避免把确定性失败放大成多轮重试。"""
    if isinstance(exc, asyncio.TimeoutError):
        return True

    msg = str(exc).lower().strip()
    if not msg:
        return True

    non_retryable_markers = (
        "没有可用题目",
        "没有 choice 题型",
        "没有 fill 题型",
        "没有 code 题型",
        "题库无",
        "不支持的资源类型",
    )
    return not any(marker in msg for marker in non_retryable_markers)


def _build_quiz_failure_entry(index: int, code: str, detail: str) -> str:
    safe_detail = detail.strip() or "未知原因"
    return f"[{code}] 第 {index} 题: {safe_detail}"


def _summarize_quiz_failures(failures: list[str]) -> str:
    if not failures:
        return ""

    counter: Counter[str] = Counter()
    for failure in failures:
        match = re.match(r"\[([^\]]+)\]", failure)
        counter[match.group(1) if match else "unknown"] += 1
    return ", ".join(f"{code}={count}" for code, count in counter.items())

async def get_agent(resource_type: str) -> BaseAgent:
    if resource_type not in _AGENT_REGISTRY:
        raise ValueError(f"不支持的资源类型: {resource_type}")
    if resource_type not in _agents:
        async with _agent_lock:
            if resource_type not in _agents:
                if resource_type == RESOURCE_TYPE_MINDMAP:
                    _agents[resource_type] = _AGENT_REGISTRY[resource_type](output_format="json")
                elif resource_type in _CONTENT_TYPE_MAP:
                    _agents[resource_type] = _AGENT_REGISTRY[resource_type](
                        content_type=_CONTENT_TYPE_MAP[resource_type]
                    )
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
        in_library=r.in_library,
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

@router.get("/search-video", response_model=BaseResponse)
async def search_video(
    keyword: str = Query(..., min_length=1, max_length=200, description="搜索关键词"),
    page: int = Query(1, ge=1, le=10, description="页码"),
    request_id: str = Depends(get_request_id)
):
    """搜索B站视频，返回视频列表"""
    try:
        bilibili_results = []
        douyin_search_url = f"https://www.douyin.com/search/{keyword}?type=video"

        # 调用B站搜索API（Session + buvid cookie，避免 412 反爬）
        def _fetch_bilibili():
            sess = http_requests.Session()
            sess.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://search.bilibili.com/",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            })
            # 获取 buvid 指纹 cookie（B站要求携带，否则返回 412）
            try:
                spi = sess.get("https://api.bilibili.com/x/frontend/finger/spi", timeout=5).json()
                spi_data = spi.get("data", {})
                if spi_data.get("b_3"):
                    sess.cookies.set("buvid3", spi_data["b_3"], domain=".bilibili.com")
                if spi_data.get("b_4"):
                    sess.cookies.set("buvid4", spi_data["b_4"], domain=".bilibili.com")
            except Exception:
                pass
            resp = sess.get(
                "https://api.bilibili.com/x/web-interface/search/type",
                params={"search_type": "video", "keyword": keyword, "page": page, "pagesize": 12, "order": "totalrank"},
                timeout=10,
            )
            resp.raise_for_status()
            return resp.json()

        try:
            data = await asyncio.to_thread(_fetch_bilibili)
            if data.get("code") == 0 and data.get("data", {}).get("result"):
                for item in data["data"]["result"]:
                    # 清除HTML标签
                    title = re.sub(r"<.*?>", "", item.get("title", ""))
                    pic = item.get("pic", "")
                    if pic and pic.startswith("//"):
                        pic = "https:" + pic
                    bvid = item.get("bvid", "")
                    aid = item.get("aid", "")
                    video_url = f"https://www.bilibili.com/video/{bvid}" if bvid else f"https://www.bilibili.com/video/av{aid}" if aid else ""
                    if not video_url:
                        continue
                    bilibili_results.append({
                        "title": title,
                        "url": video_url,
                        "thumbnail": pic,
                        "author": item.get("author", ""),
                        "duration": item.get("duration", ""),
                        "play": item.get("play", 0),
                        "description": item.get("description", "")[:100],
                        "pubdate": item.get("pubdate", 0),
                    })
        except Exception as e:
            logger.warning(f"B站搜索失败: {e}")

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "bilibili": bilibili_results,
                "douyin_search_url": douyin_search_url,
                "keyword": keyword,
            },
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"视频搜索失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"搜索失败: {e}",
            data=None,
            request_id=request_id,
        )

@router.post("/save-external-video", response_model=BaseResponse)
async def save_external_video(
    req: SaveExternalVideoRequest,
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    """收藏外部视频（B站搜索结果）到学习资源库"""
    try:
        new_resource = Resource(
            user_id=req.user_id,
            resource_type="video",
            title=req.title,
            content=req.url,
            status="completed",
            in_library=True,
            extra_metadata={
                "source": "bilibili",
                "thumbnail": req.thumbnail,
                "author": req.author,
                "external_url": req.url,
            },
        )
        session.add(new_resource)
        await session.commit()
        await session.refresh(new_resource)
        return BaseResponse(
            code=HTTP_OK,
            message="已收藏到学习资源库",
            data={"id": new_resource.id, "title": new_resource.title},
            request_id=request_id,
        )
    except IntegrityError:
        await session.rollback()
        return BaseResponse(
            code=HTTP_OK,
            message="该视频已在资源库中",
            data=None,
            request_id=request_id,
        )
    except Exception as e:
        await session.rollback()
        logger.error(f"收藏外部视频失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"收藏失败: {e}",
            data=None,
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
    in_library: Optional[bool] = Query(None),
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
        else:
            from config.constants import RESOURCE_TYPE_DAILY_CHALLENGE, RESOURCE_TYPE_DAILY_EXTRA
            conditions.append(Resource.resource_type.notin_([RESOURCE_TYPE_DAILY_CHALLENGE, RESOURCE_TYPE_DAILY_EXTRA, "multimodal"]))
        if status:
            conditions.append(Resource.status == status)
        if in_library is not None:
            conditions.append(Resource.in_library == in_library)

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
            generation_failures: list[str] = []

            # 直接用用户原始输入，由 Agent 的 LLM 自行理解
            raw_topic = req.topic.strip()
            target_kp = raw_topic or DEFAULT_TOPIC
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
                    failure_code = "unknown"
                    last_error = ""
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
                                    failure_code = "kp_mismatch"
                                    last_error = f"知识点不匹配: 预期={target_kp}, 实际={item_kp}"
                                    logger.warning(f"[{failure_code}] 第 {idx+1} 题{last_error}，直接丢弃")
                                    break
                                return item
                            failure_code = "no_item"
                            last_error = "agent 未返回有效题目"
                            logger.warning(f"[{failure_code}] 第 {idx+1} 题未返回资源 (attempt {attempt+1})")
                        except asyncio.TimeoutError:
                            failure_code = "timeout"
                            last_error = "生成超时"
                            logger.warning(f"[{failure_code}] 第 {idx+1} 题超时 (attempt {attempt+1})")
                        except Exception as e:
                            failure_code = "agent_exception"
                            last_error = str(e) or "未知异常"
                            logger.warning(f"[{failure_code}] 第 {idx+1} 题异常 (attempt {attempt+1}): {e}")
                            if not _is_retryable_quiz_generation_error(e):
                                failure_code = "non_retryable"
                                logger.warning(f"第 {idx+1} 题命中不可重试错误，提前结束重试")
                                break
                    if last_error:
                        generation_failures.append(_build_quiz_failure_entry(idx + 1, failure_code, last_error))
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
                before_count = len(valid_items)
                for item in fill_results:
                    if item is None:
                        continue
                    meta = item.extra_metadata or {}
                    dedup_key = meta.get("question_hash") or item.content[:DEDUP_CONTENT_TRUNCATE_LENGTH]
                    if dedup_key not in seen_hashes:
                        seen_hashes.add(dedup_key)
                        valid_items.append(item)
                if len(valid_items) == before_count:
                    logger.warning(f"补生成第 {round_i+1} 轮没有新增有效题目，提前停止后续补生成")
                    break

            if generation_failures:
                logger.warning(f"练习题生成失败摘要: {_summarize_quiz_failures(generation_failures)}")

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
                failure_msg = generation_failures[0] if generation_failures else MSG_GENERATE_NO_DATA
                return BaseResponse(
                    code=HTTP_SERVER_ERROR,
                    message=failure_msg,
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
                in_library=False,
            )
            session.add(db_resource)

        else:
            # 单题模式 - 直接用用户原始输入，由各 Agent 的 LLM 自行理解
            raw_topic = req.topic.strip()
            single_kp = raw_topic or DEFAULT_TOPIC
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
                in_library=False,
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

@router.patch("/{resource_id}/add-to-library", response_model=BaseResponse)
async def add_to_library(
    resource_id: int,
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    """收藏/取消收藏资源（切换 in_library 状态）"""
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_RESOURCE_NOT_FOUND, data=None, request_id=request_id)
        if r.user_id != user_id:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="无权操作此资源", data=None, request_id=request_id)

        r.in_library = not r.in_library
        await session.commit()
        msg = "已收藏到资源库" if r.in_library else "已取消收藏"
        return BaseResponse(code=HTTP_OK, message=msg, data={"id": r.id, "in_library": r.in_library}, request_id=request_id)
    except Exception as e:
        logger.error(f"收藏操作失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)


@router.patch("/{resource_id}/note", response_model=BaseResponse)
async def save_note(
    resource_id: int,
    body: dict,
    user_id: int = Query(...),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id)
):
    """保存/更新资源的学习笔记"""
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r:
            return BaseResponse(code=HTTP_NOT_FOUND, message=MSG_RESOURCE_NOT_FOUND, data=None, request_id=request_id)
        if r.user_id != user_id:
            return BaseResponse(code=HTTP_BAD_REQUEST, message="无权操作此资源", data=None, request_id=request_id)

        r.note = body.get("note", "")
        await session.commit()
        return BaseResponse(code=HTTP_OK, message="笔记已保存", data={"id": r.id, "note": r.note}, request_id=request_id)
    except Exception as e:
        logger.error(f"保存笔记失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(code=HTTP_SERVER_ERROR, message=MSG_SERVER_ERROR, data=None, request_id=request_id)


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

        def merge_children(existing_children: list, new_children: list) -> list:
            merged = list(existing_children or [])
            index_by_key: dict[str, int] = {}

            for idx, child in enumerate(merged):
                if not isinstance(child, dict):
                    continue
                key = str(child.get("id") or child.get("topic") or idx)
                index_by_key[key] = idx

            for new_child in new_children or []:
                if not isinstance(new_child, dict):
                    merged.append(new_child)
                    continue

                key = str(new_child.get("id") or new_child.get("topic") or len(merged))
                existing_idx = index_by_key.get(key)
                if existing_idx is None:
                    index_by_key[key] = len(merged)
                    merged.append(new_child)
                    continue

                existing_child = merged[existing_idx]
                if not isinstance(existing_child, dict):
                    merged[existing_idx] = new_child
                    continue

                merged_child = {**existing_child, **new_child}
                merged_child["children"] = merge_children(
                    existing_child.get("children", []),
                    new_child.get("children", []),
                )
                merged[existing_idx] = merged_child

            return merged

        def find_and_merge(node: dict) -> bool:
            if node.get("id") == node_id:
                node["children"] = merge_children(node.get("children", []), children)
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


@router.post("/{resource_id}/render-video", response_model=BaseResponse)
async def render_video(
    resource_id: int,
    user_id: int = Query(..., description="用户ID"),
    session: AsyncSession = Depends(get_db),
    request_id: str = Depends(get_request_id),
):
    """将教学动画 HTML 渲染为 WebM/MP4 视频文件"""
    try:
        r: Optional[Resource] = await session.get(Resource, resource_id)
        if not r or r.user_id != user_id or not r.is_active:
            return BaseResponse(
                code=HTTP_NOT_FOUND,
                message=MSG_RESOURCE_NOT_FOUND,
                data=None,
                request_id=request_id,
            )
        if r.resource_type != "video":
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message="该资源不是视频类型",
                data=None,
                request_id=request_id,
            )
        if not r.content or len(r.content.strip()) < 50:
            return BaseResponse(
                code=HTTP_BAD_REQUEST,
                message="资源内容为空，无法渲染视频",
                data=None,
                request_id=request_id,
            )

        from utils.video_renderer import render_html_to_video, check_ffmpeg_available, convert_webm_to_mp4

        # 提取动画时长（从 extra_metadata）
        meta = r.extra_metadata or {}
        duration = meta.get("duration", 120)

        # 渲染 WebM
        output_name = f"animation_{resource_id}.webm"
        output_path = os.path.join(VIDEO_OUTPUT_DIR, output_name)

        webm_path = await render_html_to_video(
            html_content=r.content,
            output_path=output_path,
            duration_sec=duration,
        )

        result_data = {
            "video_url": f"/{webm_path}",
            "format": "webm",
            "file_size_kb": round(os.path.getsize(webm_path) / 1024, 1),
        }

        # 如果 FFmpeg 可用，同时生成 MP4
        if await check_ffmpeg_available():
            mp4_path = webm_path.replace(".webm", ".mp4")
            await convert_webm_to_mp4(webm_path, mp4_path)
            result_data["mp4_url"] = f"/{mp4_path}"
            result_data["mp4_file_size_kb"] = round(os.path.getsize(mp4_path) / 1024, 1)

        # 更新资源元数据
        meta["video_file_path"] = webm_path
        r.extra_metadata = meta
        await session.commit()

        return BaseResponse(
            code=HTTP_OK,
            message="视频渲染成功",
            data=result_data,
            request_id=request_id,
        )

    except asyncio.TimeoutError:
        return BaseResponse(
            code=HTTP_GATEWAY_TIMEOUT,
            message="视频渲染超时，请稍后重试",
            data=None,
            request_id=request_id,
        )
    except Exception as e:
        logger.error(f"视频渲染失败: {e}", exc_info=True, extra={"request_id": request_id})
        return BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=f"视频渲染失败: {e}",
            data=None,
            request_id=request_id,
        )
