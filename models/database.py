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


async def _rebuild_sqlite_table(conn, table_name: str) -> None:
    """SQLite 重建表：用于修复外键/约束残留问题。"""
    temp_table = f"_{table_name}_old"

    idx_rows = await conn.execute(text(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=:table_name AND sql IS NOT NULL"
    ), {"table_name": table_name})
    for idx_row in idx_rows.fetchall():
        await conn.execute(text(f'DROP INDEX IF EXISTS "{idx_row[0]}"'))

    await conn.execute(text(f'ALTER TABLE "{table_name}" RENAME TO "{temp_table}"'))
    await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables[table_name]])

    old_cols = [c["name"] for c in await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_columns(temp_table)
    )]
    new_cols = [c["name"] for c in await conn.run_sync(
        lambda sync_conn: inspect(sync_conn).get_columns(table_name)
    )]
    common = [c for c in old_cols if c in new_cols]
    cols_str = ", ".join(f'"{col}"' for col in common)
    await conn.execute(text(
        f'INSERT INTO "{table_name}" ({cols_str}) SELECT {cols_str} FROM "{temp_table}"'
    ))
    await conn.execute(text(f'DROP TABLE "{temp_table}"'))
    logger.info(f"✅ 已重建 {table_name} 表")


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
            if "image_urls_json" not in chat_columns:
                await conn.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN image_urls_json TEXT"
                ))
                logger.info("✅ 已添加 chat_messages.image_urls_json 列")

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
            if "error_type" not in eb_columns:
                await conn.execute(text(
                    "ALTER TABLE error_book ADD COLUMN error_type VARCHAR(40)"
                ))
                logger.info("✅ 已添加 error_book.error_type 列（易错点偏好维度）")

            # user_profiles 表迁移：人口统计字段
            profile_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("user_profiles")]
            )
            if "gender" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN gender VARCHAR(10)"
                ))
                logger.info("✅ 已添加 user_profiles.gender 列")
            if "age" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN age INTEGER"
                ))
                logger.info("✅ 已添加 user_profiles.age 列")

            # user_profiles 表迁移：每日一题连续打卡字段
            if "current_streak" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN current_streak INTEGER NOT NULL DEFAULT 0"
                ))
                logger.info("✅ 已添加 user_profiles.current_streak 列")
            if "longest_streak" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN longest_streak INTEGER NOT NULL DEFAULT 0"
                ))
                logger.info("✅ 已添加 user_profiles.longest_streak 列")
            if "streak_status" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN streak_status VARCHAR(20) NOT NULL DEFAULT 'active'"
                ))
                logger.info("✅ 已添加 user_profiles.streak_status 列")
            if "recovery_progress" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN recovery_progress INTEGER NOT NULL DEFAULT 0"
                ))
                logger.info("✅ 已添加 user_profiles.recovery_progress 列")
            if "last_challenge_date" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN last_challenge_date VARCHAR(10)"
                ))
                logger.info("✅ 已添加 user_profiles.last_challenge_date 列")
            if "error_preferences" not in profile_columns:
                await conn.execute(text(
                    "ALTER TABLE user_profiles ADD COLUMN error_preferences JSON NOT NULL DEFAULT '[]'"
                ))
                logger.info("✅ 已添加 user_profiles.error_preferences 列（易错点偏好维度）")

            # resources 表迁移：in_library 字段
            resource_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("resources")]
            )
            if "in_library" not in resource_columns:
                await conn.execute(text(
                    "ALTER TABLE resources ADD COLUMN in_library BOOLEAN NOT NULL DEFAULT 1"
                ))
                logger.info("✅ 已添加 resources.in_library 列")

            # resources 表迁移：更新 CHECK 约束（添加 daily_challenge / daily_extra / multimodal）
            def _get_create_sql(sync_conn):
                result = sync_conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='resources'"
                ))
                row = result.fetchone()
                return row[0] if row else ""

            create_sql = await conn.run_sync(_get_create_sql)
            if "daily_challenge" not in create_sql or "multimodal" not in create_sql or "slides" not in create_sql:
                logger.info("🔧 检测到 resources 表缺少新资源类型，开始重建...")
                # 先删旧索引，避免重建时名称冲突
                idx_rows = await conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='resources' AND sql IS NOT NULL"
                ))
                for idx_row in idx_rows.fetchall():
                    await conn.execute(text(f'DROP INDEX IF EXISTS "{idx_row[0]}"'))
                # SQLite 无法 ALTER CHECK，需重建表
                await conn.execute(text("ALTER TABLE resources RENAME TO resources_old"))
                # 用 ORM metadata 创建新表（含更新后的 CHECK 约束 + 索引）
                await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables["resources"]])
                # 复制数据
                old_cols = [c["name"] for c in await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("resources_old")
                )]
                new_cols = [c["name"] for c in await conn.run_sync(
                    lambda sync_conn: inspect(sync_conn).get_columns("resources")
                )]
                common = [c for c in old_cols if c in new_cols]
                cols_str = ", ".join(common)
                await conn.execute(text(
                    f"INSERT INTO resources ({cols_str}) SELECT {cols_str} FROM resources_old"
                ))
                await conn.execute(text("DROP TABLE resources_old"))
                logger.info("✅ resources 表 CHECK 约束已更新（支持 daily_challenge / daily_extra / multimodal / slides）")

            # 修复残留外键：此前重建 resources 表后，部分子表仍引用 resources_old
            fk_broken_tables = []
            schema_rows = await conn.execute(text(
                "SELECT name, sql FROM sqlite_master WHERE type='table'"
            ))
            for row in schema_rows.fetchall():
                table_name = row[0]
                table_sql = row[1] or ""
                if "resources_old" in table_sql:
                    fk_broken_tables.append(table_name)

            # 同时收集所有引用 resources 表的子表（FK 可能指向旧表对象）
            fk_resource_dependents = []
            for table_name in Base.metadata.tables:
                if table_name == "resources":
                    continue
                table_def = Base.metadata.tables[table_name]
                for fk in table_def.foreign_keys:
                    if fk.column.table.name == "resources":
                        fk_resource_dependents.append(table_name)
                        break

            repairable_tables = list(set(
                [t for t in fk_broken_tables if t in Base.metadata.tables]
                + fk_resource_dependents
            ))
            if repairable_tables:
                logger.info(f"🔧 检测到外键仍引用 resources_old，开始修复: {repairable_tables}")
                await conn.execute(text("PRAGMA foreign_keys=OFF"))
                try:
                    for table_name in repairable_tables:
                        await _rebuild_sqlite_table(conn, table_name)
                finally:
                    await conn.execute(text("PRAGMA foreign_keys=ON"))
                logger.info("✅ 已修复所有引用 resources_old 的表")

            # chat_messages 表迁移：is_bookmarked 字段
            chat_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("chat_messages")]
            )
            if "is_bookmarked" not in chat_columns:
                await conn.execute(text(
                    "ALTER TABLE chat_messages ADD COLUMN is_bookmarked BOOLEAN NOT NULL DEFAULT 0"
                ))
                logger.info("✅ 已添加 chat_messages.is_bookmarked 列")

            # resources 表迁移：note 字段
            resource_columns = await conn.run_sync(
                lambda sync_conn: [col["name"] for col in inspector.get_columns("resources")]
            )
            if "note" not in resource_columns:
                await conn.execute(text(
                    "ALTER TABLE resources ADD COLUMN note TEXT"
                ))
                logger.info("✅ 已添加 resources.note 列")

            # explanations 表迁移：conversation_id/message_id 改为可空
            explanation_tables = await conn.run_sync(
                lambda sync_conn: [t for t in inspector.get_table_names() if t == "explanations"]
            )
            if explanation_tables:
                exp_cols = await conn.run_sync(
                    lambda sync_conn: inspector.get_columns("explanations")
                )
                # 检查 conversation_id 是否为 NOT NULL（旧表需要重建）
                conv_col = next((c for c in exp_cols if c["name"] == "conversation_id"), None)
                if conv_col and not conv_col.get("nullable", True):
                    logger.info("🔄 重建 explanations 表（conversation_id/message_id 改为可空）")
                    await conn.execute(text("ALTER TABLE explanations RENAME TO _explanations_old"))
                    await conn.execute(text("""
                        CREATE TABLE explanations (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
                            message_id INTEGER REFERENCES chat_messages(id) ON DELETE CASCADE,
                            selected_text TEXT NOT NULL,
                            explanation TEXT NOT NULL,
                            follow_ups JSON DEFAULT '[]',
                            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                            updated_at DATETIME
                        )
                    """))
                    await conn.execute(text("""
                        INSERT INTO explanations (id, user_id, conversation_id, message_id, selected_text, explanation, follow_ups, created_at, updated_at)
                        SELECT id, user_id, conversation_id, message_id, selected_text, explanation, follow_ups, created_at, updated_at
                        FROM _explanations_old
                    """))
                    await conn.execute(text("DROP TABLE _explanations_old"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_explanation_conversation ON explanations (conversation_id, created_at)"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_explanation_message ON explanations (message_id)"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_explanations_user_id ON explanations (user_id)"))
                    await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_explanations_conversation_id ON explanations (conversation_id)"))
                    logger.info("✅ explanations 表已重建（conversation_id/message_id 可空）")

            # knowledge_mastery_evidence 存量去重 + 部分唯一索引
            # 历史数据可能因重复提交导致同一 (user,node,source_type,source_id) 有多条证据，
            # 建唯一索引前需清理，保留最早一条（MIN(id)），其余备份后删除。
            kme_tables = await conn.run_sync(
                lambda sync_conn: inspector.get_table_names()
            )
            if "knowledge_mastery_evidence" in kme_tables:
                # 检查是否已有重复（避免无谓操作）
                dup_count = (
                    await conn.execute(text(
                        "SELECT COUNT(*) FROM knowledge_mastery_evidence "
                        "WHERE source_id IS NOT NULL "
                        "AND id NOT IN ("
                        "  SELECT MIN(id) FROM knowledge_mastery_evidence "
                        "  WHERE source_id IS NOT NULL "
                        "  GROUP BY user_id, node_code, source_type, source_id"
                        ")"
                    ))
                ).scalar_one()

                if dup_count and dup_count > 0:
                    # 1. 备份重复行到维护表
                    await conn.execute(text(
                        "CREATE TABLE IF NOT EXISTS knowledge_mastery_evidence_dedup_backup AS "
                        "SELECT * FROM knowledge_mastery_evidence WHERE 0"
                    ))
                    await conn.execute(text(
                        "INSERT INTO knowledge_mastery_evidence_dedup_backup "
                        "SELECT * FROM knowledge_mastery_evidence "
                        "WHERE source_id IS NOT NULL "
                        "AND id NOT IN ("
                        "  SELECT MIN(id) FROM knowledge_mastery_evidence "
                        "  WHERE source_id IS NOT NULL "
                        "  GROUP BY user_id, node_code, source_type, source_id"
                        ")"
                    ))
                    logger.info(f"✅ 已备份 {dup_count} 条重复证据到 knowledge_mastery_evidence_dedup_backup")

                    # 2. 删除重复行（保留最早一条）
                    await conn.execute(text(
                        "DELETE FROM knowledge_mastery_evidence "
                        "WHERE source_id IS NOT NULL "
                        "AND id NOT IN ("
                        "  SELECT MIN(id) FROM knowledge_mastery_evidence "
                        "  WHERE source_id IS NOT NULL "
                        "  GROUP BY user_id, node_code, source_type, source_id"
                        ")"
                    ))
                    logger.info(f"✅ 已删除 {dup_count} 条重复证据（保留每组最早一条）")

                # 3. 建部分唯一索引（幂等）
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_kme_user_node_source "
                    "ON knowledge_mastery_evidence (user_id, node_code, source_type, source_id) "
                    "WHERE source_id IS NOT NULL"
                ))
                logger.info("✅ 已确认 uq_kme_user_node_source 部分唯一索引存在")

            # ---- 精准画像重构：user_knowledge_mastery 加列 ----
            if "user_knowledge_mastery" in kme_tables:
                ukm_columns = await conn.run_sync(
                    lambda sync_conn: [c["name"] for c in inspector.get_columns("user_knowledge_mastery")]
                )
                ukm_col_names = set(ukm_columns)
                new_ukm_cols = [
                    ("posterior", "FLOAT NOT NULL DEFAULT 0.0"),
                    ("uncertainty", "FLOAT NOT NULL DEFAULT 0.9"),
                    ("last_verified", "DATETIME"),
                    ("review_risk", "FLOAT NOT NULL DEFAULT 0.0"),
                ]
                added_ukm = []
                for col_name, col_def in new_ukm_cols:
                    if col_name not in ukm_col_names:
                        await conn.execute(text(
                            f"ALTER TABLE user_knowledge_mastery ADD COLUMN {col_name} {col_def}"
                        ))
                        added_ukm.append(col_name)
                if added_ukm:
                    logger.info(f"✅ user_knowledge_mastery 已添加列: {added_ukm}")
                # 存量迁移：mastery_score/100 -> posterior（仅当 posterior=0 且 mastery_score>0）
                backfill_result = await conn.execute(text(
                    "UPDATE user_knowledge_mastery SET posterior = mastery_score / 100.0 "
                    "WHERE posterior = 0.0 AND mastery_score > 0"
                ))
                if backfill_result.rowcount and backfill_result.rowcount > 0:
                    logger.info(f"✅ 存量 posterior 回填: {backfill_result.rowcount} 行")

            # ---- 精准画像重构：knowledge_mastery_evidence 重建（扩 CHECK + 加列）----
            if "knowledge_mastery_evidence" in kme_tables:
                kme_columns = await conn.run_sync(
                    lambda sync_conn: [c["name"] for c in inspector.get_columns("knowledge_mastery_evidence")]
                )
                kme_col_names = set(kme_columns)

                def _get_kme_create_sql(sync_conn):
                    result = sync_conn.execute(text(
                        "SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_mastery_evidence'"
                    ))
                    row = result.fetchone()
                    return row[0] if row else ""

                kme_create_sql = await conn.run_sync(_get_kme_create_sql)
                needs_rebuild = ("chat_judge" not in kme_create_sql) or ("signal_type" not in kme_col_names)

                if needs_rebuild:
                    logger.info("🔧 knowledge_mastery_evidence 重建：扩 source_type CHECK + 加 signal_type/source_weight/difficulty/weak_signal 列...")
                    # 1. 删除旧索引（含部分唯一索引，避免重建时名称冲突）
                    kme_idx_rows = await conn.execute(text(
                        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='knowledge_mastery_evidence' AND sql IS NOT NULL"
                    ))
                    for idx_row in kme_idx_rows.fetchall():
                        await conn.execute(text(f'DROP INDEX IF EXISTS "{idx_row[0]}"'))
                    # 2. 重命名旧表
                    await conn.execute(text("ALTER TABLE knowledge_mastery_evidence RENAME TO knowledge_mastery_evidence_old"))
                    # 3. 用 ORM metadata 创建新表（含新 CHECK + 新列 + 索引）
                    await conn.run_sync(
                        Base.metadata.create_all,
                        tables=[Base.metadata.tables["knowledge_mastery_evidence"]]
                    )
                    # 4. 复制数据（旧表无新列，新列用默认值）
                    old_kme_cols = await conn.run_sync(
                        lambda sync_conn: [c["name"] for c in inspect(sync_conn).get_columns("knowledge_mastery_evidence_old")]
                    )
                    new_kme_cols = await conn.run_sync(
                        lambda sync_conn: [c["name"] for c in inspect(sync_conn).get_columns("knowledge_mastery_evidence")]
                    )
                    common_kme = [c for c in old_kme_cols if c in new_kme_cols]
                    kme_cols_str = ", ".join(common_kme)
                    await conn.execute(text(
                        f"INSERT INTO knowledge_mastery_evidence ({kme_cols_str}) SELECT {kme_cols_str} FROM knowledge_mastery_evidence_old"
                    ))
                    # 5. 删除旧表
                    await conn.execute(text("DROP TABLE knowledge_mastery_evidence_old"))
                    logger.info("✅ knowledge_mastery_evidence 重建完成（新列默认：signal_type='direct', source_weight=1.0, difficulty=NULL, weak_signal=0）")
                else:
                    logger.debug("knowledge_mastery_evidence schema 已是最新，跳过重建")

            # ---- 精准画像重构：user_misconceptions 建表（新表）----
            if "user_misconceptions" not in kme_tables:
                await conn.run_sync(
                    Base.metadata.create_all,
                    tables=[Base.metadata.tables["user_misconceptions"]]
                )
                logger.info("✅ user_misconceptions 表已创建")

            # ---- 辅导短视频：扩展 learning_path_node_resources.ck_lp_resource_type 约束 ----
            lp_res_tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
            if "learning_path_node_resources" in lp_res_tables:
                ck_row = await conn.execute(text(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND name='learning_path_node_resources'"
                ))
                create_sql = (ck_row.fetchone() or (None,))[0] or ""
                if "tutor_video" not in create_sql:
                    await _rebuild_sqlite_table(conn, "learning_path_node_resources")
                    logger.info("✅ learning_path_node_resources 约束已扩展 tutor_video")

    except Exception as e:
        logger.warning(f"⚠️ 自动迁移跳过（可能表尚未创建）: {e}")


async def _recompute_after_dedup() -> None:
    """存量去重后，重算受影响用户的掌握度 + 重新投影画像。

    仅当 knowledge_mastery_evidence_dedup_backup 表存在且非空时触发。
    幂等：重算完成后清空 backup 标记（保留表结构作为审计痕迹）。
    """
    try:
        async with engine.connect() as conn:
            tables = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
            if "knowledge_mastery_evidence_dedup_backup" not in tables:
                return
            affected_users = (
                await conn.execute(text(
                    "SELECT DISTINCT user_id FROM knowledge_mastery_evidence_dedup_backup"
                ))
            ).all()
        if not affected_users:
            return

        # 延迟导入避免循环依赖
        from sqlalchemy.ext.asyncio import AsyncSessionLocal
        from services.mastery_service import recalculate_all_mastery, project_to_profile

        logger.info(f"🔄 重算 {len(affected_users)} 个受影响用户的掌握度...")
        for (uid,) in affected_users:
            try:
                async with AsyncSessionLocal() as s:
                    async with s.begin():
                        await recalculate_all_mastery(s, uid)
                        await project_to_profile(s, uid)
            except Exception as e:
                logger.warning(f"⚠️ 用户 {uid} 掌握度重算失败: {e}")

        # 清空 backup 表（保留结构作审计），避免下次启动重复重算
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM knowledge_mastery_evidence_dedup_backup"))
        logger.info("✅ 受影响用户掌握度重算完成，已清空 backup 表")
    except Exception as e:
        logger.warning(f"⚠️ 去重后重算跳过: {e}")

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

        # 5. 若刚清理过重复证据，重算受影响用户的掌握度 + 重新投影画像
        await _recompute_after_dedup()

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
