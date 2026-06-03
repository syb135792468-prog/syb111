"""
数据库连接与会话管理模块（v2.2 最终稳定版）
- 基于 SQLAlchemy 2.0 异步架构
- 支持 SQLite（开发）/ PostgreSQL（生产）无缝切换
- 修复事件监听警告、利用 models/__init__.py 统一导入模型
- 提供完整的类型注解与日志追踪
- 兼容 behavior_tracker 的 BehaviorLog 模型
"""
from __future__ import annotations
import asyncio
from typing import AsyncGenerator, Optional, Dict, Any
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
    AsyncEngine,
)
from sqlalchemy import event, text, inspect
from sqlalchemy.orm import DeclarativeBase

from config.settings import settings
from config.constants import SQLITE_CACHE_SIZE
from utils.logger import get_logger

logger = get_logger(__name__, task_id="db_core")


# -------------------- 1. 声明式基类 --------------------
class Base(DeclarativeBase):
    """SQLAlchemy 2.0 标准基类，所有 ORM 模型继承于此"""
    pass


# -------------------- 2. 数据库 URL 标准化 --------------------
def _normalize_db_url() -> str:
    """标准化数据库URL，处理相对路径"""
    url = settings.DATABASE_URL
    if url.startswith("sqlite+aiosqlite:///"):
        db_path_str = url.replace("sqlite+aiosqlite:///", "", 1)
        db_path = Path(db_path_str)
        if not db_path.is_absolute():
            db_path = settings.BASE_DIR / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        normalized = f"sqlite+aiosqlite:///{db_path.resolve()}"
        logger.info(f"📦 SQLite 数据库路径: {normalized}")
        return normalized
    else:
        masked = url.split("@")[-1] if "@" in url else url
        logger.info(f"🗄️  生产数据库连接: {masked}")
        return url


# -------------------- 3. 创建异步引擎 --------------------
NORMALIZED_DATABASE_URL = _normalize_db_url()

engine_kwargs: Dict[str, Any] = {
    "echo": settings.DEBUG,
    "future": True,
}

if "sqlite" in NORMALIZED_DATABASE_URL:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 10)
    engine_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 20)

engine: AsyncEngine = create_async_engine(NORMALIZED_DATABASE_URL, **engine_kwargs)


# -------------------- 4. SQLite 性能优化事件监听 --------------------
if "sqlite" in NORMALIZED_DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        """在每次 SQLite 连接建立时执行优化 PRAGMA"""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute(f"PRAGMA cache_size={SQLITE_CACHE_SIZE}")  # 64MB 缓存
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        logger.debug("✅ SQLite PRAGMA 优化已应用")


# -------------------- 5. 会话工厂 --------------------
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# -------------------- 6. FastAPI 依赖注入 --------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI 异步依赖项：获取数据库会话
    使用方式：
        @app.get("/items")
        async def read_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            logger.error("❌ 数据库事务异常，已回滚", exc_info=True)
            raise


# -------------------- 7. 数据库初始化工具（确保所有模型被注册）--------------------
_db_initialized: bool = False


async def _auto_migrate() -> None:
    """自动迁移：为已有表添加缺失的列"""
    try:
        async with engine.begin() as conn:
            inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))

            # chat_messages 表迁移
            chat_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("chat_messages")]
            )
            if "conversation_id" not in chat_columns:
                await conn.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL"
                ))
                logger.info("✅ 已添加 chat_messages.conversation_id 列")
            if "content_blocks_json" not in chat_columns:
                await conn.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN content_blocks_json TEXT"
                ))
                logger.info("✅ 已添加 chat_messages.content_blocks_json 列")

            # users 表迁移：AI 自适应字段
            user_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("users")]
            )
            if "ability_estimates" not in user_columns:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN ability_estimates TEXT DEFAULT '{}'"
                ))
                logger.info("✅ 已添加 users.ability_estimates 列")
            if "ability_standard_errors" not in user_columns:
                await conn.execute(text(
                    "ALTER TABLE users ADD COLUMN ability_standard_errors TEXT DEFAULT '{}'"
                ))
                logger.info("✅ 已添加 users.ability_standard_errors 列")

            # error_book 表迁移：间隔重复（艾宾浩斯）字段
            eb_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("error_book")]
            )
            if "next_review_at" not in eb_columns:
                await conn.execute(text(
                    "ALTER TABLE error_book ADD COLUMN next_review_at DATETIME"
                ))
                logger.info("✅ 已添加 error_book.next_review_at 列")
            if "review_interval_days" not in eb_columns:
                await conn.execute(text(
                    "ALTER TABLE error_book ADD COLUMN review_interval_days FLOAT NOT NULL DEFAULT 1.0"
                ))
                logger.info("✅ 已添加 error_book.review_interval_days 列")
            if "easiness_factor" not in eb_columns:
                await conn.execute(text(
                    "ALTER TABLE error_book ADD COLUMN easiness_factor FLOAT NOT NULL DEFAULT 2.5"
                ))
                logger.info("✅ 已添加 error_book.easiness_factor 列")
            if "repetition_count" not in eb_columns:
                await conn.execute(text(
                    "ALTER TABLE error_book ADD COLUMN repetition_count INTEGER NOT NULL DEFAULT 0"
                ))
                logger.info("✅ 已添加 error_book.repetition_count 列")

    except Exception as e:
        logger.warning(f"⚠️ 自动迁移跳过（可能表尚未创建）: {e}")

async def init_db(force: bool = False) -> None:
    """
    创建所有已定义的表（基于 Base.metadata）
    通过显式导入 BehaviorLog 来避免循环依赖，同时保证模型被发现

    Args:
        force: 是否强制重新初始化（开发时用）
    """
    global _db_initialized

    if _db_initialized and not force:
        logger.debug("数据库已初始化，跳过")
        return

    logger.info("🔧 正在初始化数据库表结构...")
    try:
        # 1. 导入 models 包，自动加载 User, UserProfile, Resource
        import models  # noqa: F401
        logger.debug("✅ 已加载 models 包")

        # 2. 显式导入 BehaviorLog，确保被 SQLAlchemy 发现（避开循环导入）
        try:
            from utils.behavior_tracker import BehaviorLog  # noqa: F401
            logger.debug("✅ 已加载 behavior_tracker.BehaviorLog")
        except ImportError as e:
            logger.warning(f"⚠️  未找到 BehaviorLog 模型，跳过: {e}")

        # 3. 创建表
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # 4. 自动迁移：检查并添加缺失的列
        await _auto_migrate()

        _db_initialized = True
        logger.info("✅ 数据库表结构初始化成功")

    except ImportError as e:
        logger.error(f"❌ 模型导入失败，请检查 models/__init__.py 是否正确导出: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}", exc_info=True)
        raise


async def is_db_initialized() -> bool:
    """检查数据库是否已初始化（表是否已创建）"""
    try:
        async with engine.connect() as conn:
            inspector = await conn.run_sync(lambda sync_conn: inspect(sync_conn))
            tables = await conn.run_sync(lambda sync_conn: inspector.get_table_names())
            # 检查核心表是否存在
            required_tables = {"users", "user_profiles", "resources", "learning_progress", "behavior_logs"}
            return required_tables.issubset(set(tables))
    except Exception:
        return False


async def reset_db() -> None:
    """重置数据库（开发时快速重置，删除所有表重新创建）"""
    logger.warning("⚠️  正在重置数据库...")
    try:
        async with engine.begin() as conn:
            # 删除所有表
            await conn.run_sync(Base.metadata.drop_all)
            # 重新创建
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ 数据库已重置")
    except Exception as e:
        logger.error(f"❌ 数据库重置失败: {e}", exc_info=True)
        raise


# -------------------- 8. 资源清理 --------------------
async def dispose_db() -> None:
    """关闭数据库连接池（应用关闭时调用）"""
    logger.info("🔌 关闭数据库连接池...")
    await engine.dispose()
    logger.info("✅ 数据库连接池已关闭")


# -------------------- 9. 模块自测 --------------------
if __name__ == "__main__":
    async def _test_db():
        print("=" * 60)
        print("🔍 数据库模块自测 v2.2")
        print("=" * 60)
        try:
            # 1. 连接测试
            print("\n1. 测试数据库连接...")
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                assert result.scalar() == 1
                print("   ✅ 连接测试通过")

            # 2. 初始化测试
            print("\n2. 测试表结构初始化...")
            await init_db()
            print("   ✅ 表结构初始化测试通过")

            # 3. 检查状态
            print("\n3. 检查初始化状态...")
            status = await is_db_initialized()
            print(f"   ✅ 初始化状态: {status}")

            # 4. 清理
            await dispose_db()
            print("\n🎉 所有自测通过！")

        except Exception as e:
            print(f"\n❌ 自测失败: {e}")
            raise

    asyncio.run(_test_db())