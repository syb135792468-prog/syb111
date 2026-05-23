# config/settings.py
from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, computed_field

from config.constants import (
    TYPING_CHUNK_SIZE as _DEFAULT_TYPING_CHUNK_SIZE,
    TYPING_DELAY_MS as _DEFAULT_TYPING_DELAY_MS,
    SYNC_CHAT_TIMEOUT_SEC as _DEFAULT_SYNC_CHAT_TIMEOUT,
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",  # 关键：绝对路径
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # --- 大模型凭证（主模型已切换为 DeepSeek，SPARK_* 仅用于 Embedding 和内容安全）---
    SPARK_APP_ID: str = Field(default="", description="讯飞应用 ID（Embedding/内容安全用）")
    SPARK_API_KEY_RAW: str = Field(default="", description="讯飞 API Key（Embedding/内容安全用）")
    SPARK_API_SECRET: str = Field(default="", description="讯飞 API Secret（Embedding/内容安全用）")
    SPARK_BASE_URL: str = "https://spark-api-open.xf-yun.com/v1"
    SPARK_MODEL: str = "lite"
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API Key（主模型）")

    # --- 内容安全凭证 ---
    SECURITY_APP_ID: str = Field(default="", description="内容安全应用 ID")
    SECURITY_API_KEY_RAW: str = Field(default="", description="内容安全 API Key")
    SECURITY_API_SECRET: str = Field(default="", description="内容安全 API Secret")
    SECURITY_BASE_URL: str = "https://spark-api-open.xf-yun.com/v1"

    # --- Embedding 服务专用凭证（新增）---
    EMBEDDING_API_KEY: str = Field(default="", env="EMBEDDING_API_KEY")
    EMBEDDING_BASE_URL: str = Field(default="https://emb-cn-huabei-1.xf-yun.com", env="EMBEDDING_BASE_URL")

    # --- 项目路径 ---
    BASE_DIR: Path = Path(__file__).parent.parent
    LOG_DIR: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "logs")
    VECTOR_DB_PATH: Path = Field(default_factory=lambda: Path(__file__).parent.parent / "data" / "vector_db")

    # --- JWT 认证配置 ---
    JWT_SECRET_KEY: str = Field(default="dev-secret-change-in-production", env="JWT_SECRET_KEY")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24小时

    # --- 运行环境 ---
    ENVIRONMENT: str = Field(default="development")
    LOG_LEVEL: str = Field(default="INFO")
    DEBUG: bool = Field(default=True)

    # --- 数据库配置 ---
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data/app.db")
    DB_POOL_SIZE: int = Field(default=10)
    DB_MAX_OVERFLOW: int = Field(default=20)

    # --- 计算属性（兼容旧代码）---
    @computed_field(return_type=str)
    @property
    def SPARK_API_KEY(self) -> str:
        """拼接讯飞星火 API Key 和 Secret，符合兼容层要求"""
        return f"{self.SPARK_API_KEY_RAW}:{self.SPARK_API_SECRET}"

    @computed_field(return_type=str)
    @property
    def SECURITY_API_KEY(self) -> str:
        """拼接内容安全 API Key 和 Secret"""
        return f"{self.SECURITY_API_KEY_RAW}:{self.SECURITY_API_SECRET}"

    # --- Embedding 凭证拆分（新增）---
    @computed_field(return_type=str)
    @property
    def EMBEDDING_API_KEY_RAW(self) -> str:
        """从 EMBEDDING_API_KEY 中解析 API Key 部分（冒号前）"""
        if ":" in self.EMBEDDING_API_KEY:
            return self.EMBEDDING_API_KEY.split(":")[0]
        return self.EMBEDDING_API_KEY

    @computed_field(return_type=str)
    @property
    def EMBEDDING_API_SECRET(self) -> str:
        """从 EMBEDDING_API_KEY 中解析 APISecret 部分（冒号后）"""
        if ":" in self.EMBEDDING_API_KEY:
            return self.EMBEDDING_API_KEY.split(":")[1]
        return ""

    def model_post_init(self, __context) -> None:
        """
        Pydantic 推荐的初始化后钩子
        用于创建必需目录等副作用操作
        """
        # 1. 创建核心目录
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)
        self.VECTOR_DB_PATH.mkdir(parents=True, exist_ok=True)

        # 2. 如果使用 SQLite，确保数据库文件父目录存在
        if self.DATABASE_URL.startswith("sqlite"):
            self._ensure_sqlite_db_dir()

    def _ensure_sqlite_db_dir(self) -> None:
        """内部方法：确保 SQLite 数据库文件的父目录存在"""
        parsed_url = urlparse(self.DATABASE_URL)
        # 提取路径并处理前导斜杠（Windows 兼容）
        db_path_str = parsed_url.path.lstrip("/")
        db_path = Path(db_path_str)

        # 相对路径基于项目根目录解析
        if not db_path.is_absolute():
            db_path = self.BASE_DIR / db_path

        # 创建父目录
        db_path.parent.mkdir(parents=True, exist_ok=True)
    # 聊天接口配置（默认值与 constants.py 保持一致）
    TYPING_CHUNK_SIZE: int = Field(default=_DEFAULT_TYPING_CHUNK_SIZE)
    TYPING_DELAY_MS: int = Field(default=_DEFAULT_TYPING_DELAY_MS)
    SYNC_CHAT_TIMEOUT: int = Field(default=_DEFAULT_SYNC_CHAT_TIMEOUT)

# 全局单例
settings = Settings()