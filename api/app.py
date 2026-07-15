from __future__ import annotations
from sqlalchemy import text
"""
api/app.py - FastAPI 应用入口（最终修复版）
- ✅ 修复所有导入和引用错误
- ✅ 启动时自动初始化数据库表 + 预初始化所有Agent
- ✅ 全局异常处理：所有异常返回统一 BaseResponse 格式
- ✅ 全局请求ID中间件：全链路日志自动追踪
- ✅ 慢请求日志：自动记录超过1秒的请求
- ✅ 增强健康检查：验证数据库连接状态
- ✅ 生产级 CORS 跨域配置
- ✅ 统一日志系统
- ✅ 零类型警告
"""

import sys
import os
import time
import uuid
import asyncio
import contextvars
from contextlib import asynccontextmanager
from typing import Callable

from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from api.schemas import BaseResponse
from api.routes import chat, profile, resource, progress, auth, conversation, quiz, error_book, code_execute, experiment, learning_path, images, task, multimodal, daily, graph, playground, course
from config.constants import (
    DEFAULT_PORT, SLOW_REQUEST_THRESHOLD_SEC, CORS_MAX_AGE,
    HTTP_OK, HTTP_BAD_REQUEST, HTTP_SERVER_ERROR, HTTP_SERVICE_UNAVAILABLE,
    PREINIT_AGENT_TYPES, HEALTH_CHECK_SERVICES, DEV_RELOAD_DIRS,
)
from config.messages import (
    MSG_SUCCESS, MSG_REQUEST_PARAM_ERROR, MSG_SERVER_INTERNAL_ERROR,
    MSG_SERVICE_UNAVAILABLE,
)
from config.settings import settings
from models.database import init_db, engine
from utils.logger import get_logger

# 全局日志器
logger = get_logger(__name__, task_id="app")

# 🔴 修复2：在app.py里自己定义request_id_var，不要从其他文件导入
request_id_var = contextvars.ContextVar("request_id", default="unknown")

# 从环境变量读取配置
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", DEFAULT_PORT))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
SLOW_REQUEST_THRESHOLD = float(os.getenv("SLOW_REQUEST_THRESHOLD", SLOW_REQUEST_THRESHOLD_SEC))


async def _daily_batch_update_loop():
    """每天凌晨3点执行批量画像更新"""
    from datetime import datetime
    while True:
        now = datetime.now()
        # 计算距离下一个凌晨3点的秒数
        target = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now >= target:
            from datetime import timedelta
            target += timedelta(days=1)
        wait_seconds = (target - now).total_seconds()
        logger.info(f"⏰ 下次批量更新: {target.strftime('%Y-%m-%d %H:%M')} (等待 {wait_seconds:.0f}s)")
        await asyncio.sleep(wait_seconds)
        try:
            from agents.profile_agent import ProfileAgent
            result = await ProfileAgent.batch_update_all_users()
            logger.info(f"✅ 每日批量画像更新完成: {result}")
        except Exception as e:
            logger.error(f"❌ 每日批量画像更新失败: {e}", exc_info=True)


# ============================================================
# 1. 应用生命周期管理
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 正在启动Python智能学习助手服务...")

    # 初始化数据库
    try:
        await init_db()
        logger.info("✅ 数据库表初始化成功")
    except Exception as e:
        logger.critical(f"❌ 数据库初始化失败: {str(e)}", exc_info=True)
        sys.exit(1)

    # 初始化预定义 A/B 测试实验
    try:
        from ai.experiment_config import ensure_experiments_exist
        from models.database import AsyncSessionLocal
        async with AsyncSessionLocal() as exp_db:
            await ensure_experiments_exist(exp_db)
        logger.info("✅ A/B 测试实验初始化成功")
    except Exception as e:
        logger.error(f"⚠️ 实验初始化失败（非致命）: {str(e)}", exc_info=True)

    # 预初始化所有Agent单例（解决冷启动）
    try:
        logger.info("🔄 预初始化所有AI Agent...")

        # 预初始化聊天工作流
        from api.routes.chat import get_workflow
        await get_workflow()

        # 预初始化用户画像Agent
        from api.routes.profile import get_profile_agent
        await get_profile_agent()

        # 预初始化资源生成Agent
        from api.routes.resource import get_agent
        for agent_type in PREINIT_AGENT_TYPES:
            await get_agent(agent_type)

        logger.info("✅ 所有AI Agent预初始化完成")
    except Exception as e:
        logger.error(f"⚠️ Agent预初始化失败: {str(e)}", exc_info=True)

    # 后台预加载 OCR 模型（不阻塞启动）
    async def _preload_ocr():
        try:
            from utils.ocr import get_ocr_engine
            await asyncio.to_thread(get_ocr_engine)
            logger.info("✅ EasyOCR 模型预加载完成")
        except Exception as e:
            logger.warning(f"⚠️ OCR 模型预加载失败（非致命）: {e}")
    _ocr_task = asyncio.create_task(_preload_ocr())

    # 启动每日批量更新定时任务
    _batch_task = asyncio.create_task(_daily_batch_update_loop())

    yield  # 应用运行期间

    # 取消定时任务
    _batch_task.cancel()
    _ocr_task.cancel()

    # 关闭时清理资源
    logger.info("🔌 正在关闭服务...")
    if engine:
        await engine.dispose()
    logger.info("✅ 服务已正常关闭")


# ============================================================
# 2. 创建 FastAPI 应用
# ============================================================
app = FastAPI(
    title="Python智能学习助手 API",
    description="第十五届软件杯A3赛题 - 基于大模型的Python智能学习助手后端接口",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    debug=DEBUG,
)


# ============================================================
# 3. 全局中间件
# ============================================================
@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable):
    """全局请求ID中间件"""
    # 从请求头获取或生成新的request_id
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # 设置到全局上下文变量
    token = request_id_var.set(request_id)

    start_time = time.time()

    try:
        response = await call_next(request)
        # 将request_id添加到响应头
        response.headers["X-Request-ID"] = request_id

        # 记录慢请求
        duration = time.time() - start_time
        if duration > SLOW_REQUEST_THRESHOLD:
            logger.warning(
                f"🐢 慢请求: {request.method} {request.url.path} | 耗时: {duration:.2f}s",
                extra={"request_id": request_id}
            )

        return response
    finally:
        request_id_var.reset(token)


# CORS 跨域中间件
cors_allowed_origins = [
    origin.strip().rstrip("/")
    for origin in settings.CORS_ALLOWED_ORIGINS.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=CORS_MAX_AGE,
)


# ============================================================
# 4. 全局异常处理
# ============================================================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.warning(
        f"HTTP异常: {exc.status_code} - {exc.detail}",
        extra={"request_id": request_id_var.get()}
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=BaseResponse(
            code=exc.status_code,
            message=str(exc.detail),
            data=None,
            request_id=request_id_var.get()
        ).model_dump(mode="json")
    )


@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    logger.warning(
        f"参数校验失败: {str(exc)}",
        extra={"request_id": request_id_var.get()}
    )
    return JSONResponse(
        status_code=HTTP_BAD_REQUEST,
        content=BaseResponse(
            code=HTTP_BAD_REQUEST,
            message=MSG_REQUEST_PARAM_ERROR,
            data={"errors": exc.errors()},
            request_id=request_id_var.get()
        ).model_dump(mode="json")
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(
        f"未捕获异常: {str(exc)}",
        exc_info=True,
        extra={"request_id": request_id_var.get()}
    )
    return JSONResponse(
        status_code=HTTP_SERVER_ERROR,
        content=BaseResponse(
            code=HTTP_SERVER_ERROR,
            message=MSG_SERVER_INTERNAL_ERROR,
            data={"detail": str(exc)} if DEBUG else None,
            request_id=request_id_var.get()
        ).model_dump(mode="json")
    )


# ============================================================
# 5. 注册所有路由
# ============================================================
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(profile.router, prefix="/api")
app.include_router(resource.router, prefix="/api")
app.include_router(progress.router, prefix="/api")
app.include_router(conversation.router, prefix="/api")
app.include_router(quiz.router, prefix="/api")
app.include_router(error_book.router, prefix="/api")
app.include_router(code_execute.router, prefix="/api")
app.include_router(experiment.router, prefix="/api")
app.include_router(learning_path.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(task.router, prefix="/api")
app.include_router(multimodal.router, prefix="/api")
app.include_router(daily.router, prefix="/api")
app.include_router(graph.router, prefix="/api")
app.include_router(playground.router, prefix="/api")
app.include_router(course.router, prefix="/api")


# ============================================================
# 6. 全局通用接口
# ============================================================
@app.get("/api/health", response_model=BaseResponse, description="全局服务健康检查")
async def global_health():
    try:
        # 🔴 修复5：正确的数据库连接测试写法
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        return BaseResponse(
            code=HTTP_OK,
            message=MSG_SUCCESS,
            data={
                "status": "ok",
                "services": HEALTH_CHECK_SERVICES,
            },
            request_id=request_id_var.get()  # 🔴 修复6：补全request_id参数
        )
    except Exception as e:
        logger.error(f"❌ 健康检查失败: {str(e)}", exc_info=True)
        return BaseResponse(
            code=HTTP_SERVICE_UNAVAILABLE,
            message=MSG_SERVICE_UNAVAILABLE,
            data={"error": str(e)},
            request_id=request_id_var.get()
        )


# ============================================================
# 7. 前端静态文件托管（SPA 路由支持）
# ============================================================
_frontend_dir = Path(__file__).parent.parent / "frontend"
_frontend_dist = _frontend_dir / "dist"
# 优先使用构建产物目录(dist)，否则使用源码目录
_static_dir = _frontend_dist if _frontend_dist.is_dir() else _frontend_dir

if _static_dir.is_dir():
    _index_html = _static_dir / "index.html"

    # 挂载静态资源目录（JS/CSS/图片等实际文件）
    app.mount("/assets", StaticFiles(directory=str(_static_dir / "assets")), name="static-assets")

    # 挂载用户上传的图片目录
    _uploads_dir = Path(__file__).parent.parent / "static" / "uploads"
    _uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploaded-images")

    # 挂载渲染视频目录
    _videos_dir = Path(__file__).parent.parent / "static" / "videos"
    _videos_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static/videos", StaticFiles(directory=str(_videos_dir)), name="rendered-videos")

    # SPA catch-all：所有非 API、非静态文件的请求都返回 index.html
    from fastapi.responses import FileResponse

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        """SPA 路由回退：客户端路由全部返回 index.html"""
        # API 路径不拦截，交给 API 路由处理
        if full_path.startswith("api/") or full_path.startswith("api"):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=404, content={"detail": "API not found"})
        # 尝试返回实际存在的静态文件（favicon.svg 等）
        file_path = _static_dir / full_path
        if full_path and file_path.is_file():
            return FileResponse(str(file_path))
        # 其他所有路径返回 index.html，由前端路由处理
        return FileResponse(str(_index_html))

    logger.info(f"✅ 前端静态文件已托管（SPA 模式）: {_static_dir}")
else:
    logger.warning(f"⚠️ 前端目录不存在: {_static_dir}")


# ============================================================
# 8. 开发环境运行入口
# ============================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        reload_dirs=DEV_RELOAD_DIRS,
        log_level="info",
        access_log=True,
        workers=1
    )
