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

    # --- 大模型凭证（主模型：DeepSeek，备用：智谱 GLM，SPARK_* 仅用于 Embedding 和内容安全）---
    SPARK_APP_ID: str = Field(default="", description="讯飞应用 ID（Embedding/内容安全用）")
    SPARK_API_KEY_RAW: str = Field(default="", description="讯飞 API Key（Embedding/内容安全用）")
    SPARK_API_SECRET: str = Field(default="", description="讯飞 API Secret（Embedding/内容安全用）")
    SPARK_BASE_URL: str = "https://spark-api-open.xf-yun.com/v1"
    SPARK_MODEL: str = "lite"
    DEEPSEEK_API_KEY: str = Field(default="", description="DeepSeek API Key（主模型）")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    GLM_API_KEY: str = Field(default="", description="火山引擎方舟 API Key（ark- 前缀，备用模型）")
    GLM_BASE_URL: str = Field(default="https://ark.cn-beijing.volces.com/api/coding/v3", env="GLM_BASE_URL")
    GLM_MODEL: str = Field(default="glm-5.2", env="GLM_MODEL", description="火山方舟模型名，适用于已开通的托管模型")
    GLM_ENDPOINT_ID: str = Field(default="", env="GLM_ENDPOINT_ID", description="火山方舟推理接入点 ID，配置后优先于 GLM_MODEL")
    # --- 火山引擎语音合成 TTS（视频配音用，与方舟 LLM 鉴权不同，需 app_id + access_token）---
    TTS_ENABLED: bool = Field(default=False, env="TTS_ENABLED", description="是否启用云端 TTS 配音，关闭则走 Web Speech 降级")
    TTS_APP_ID: str = Field(default="", env="TTS_APP_ID", description="火山引擎语音合成应用 ID")
    TTS_ACCESS_TOKEN: str = Field(default="", env="TTS_ACCESS_TOKEN", description="火山引擎语音合成 Access Token")
    TTS_DEFAULT_VOICE_ID: str = Field(default="zh_female_wanwanxiaohe_moon_bigtts", env="TTS_DEFAULT_VOICE_ID", description="默认音色 ID")
    # --- 科大讯飞超拟人合成 TTS（WebSocket，主用；火山TTS自动降级为备用）---
    TTS_XFYUN_APP_ID: str = Field(default="", env="TTS_XFYUN_APP_ID", description="讯飞应用 APPID")
    TTS_XFYUN_API_KEY: str = Field(default="", env="TTS_XFYUN_API_KEY", description="讯飞 API Key")
    TTS_XFYUN_API_SECRET: str = Field(default="", env="TTS_XFYUN_API_SECRET", description="讯飞 API Secret")
    TTS_XFYUN_API_PASSWORD: str = Field(default="", env="TTS_XFYUN_API_PASSWORD", description="讯飞超拟人合成 APIPassword（ak- 前缀，Bearer 鉴权用，与 APIKey/APISecret 不同）")
    TTS_XFYUN_WS_URL: str = Field(default="wss://cbm01.cn-huabei-1.xf-yun.com/v1/private/mcd9m97e6", env="TTS_XFYUN_WS_URL", description="讯飞超拟人合成 WebSocket 接口地址")
    TTS_XFYUN_VOICE_ID: str = Field(default="x6_lingyuyan_pro", env="TTS_XFYUN_VOICE_ID", description="讯飞默认音色（超拟人合成音色名形如 x6_lingyuyan_pro，非 legacy 小燕）")
    TTS_XFYUN_SERVICE_PARAM: str = Field(default="mcd9m97e6", env="TTS_XFYUN_SERVICE_PARAM", description="讯飞服务标识，URL path 的一部分")
    # --- 火山方舟视觉理解模型（多模态代码识别用，必须走标准端点 /api/v3，不是 /api/coding/v3）---
    ARK_VISION_API_KEY: str = Field(default="", description="火山方舟 API Key（ark- 前缀，视觉模型用）")
    ARK_VISION_BASE_URL: str = Field(default="https://ark.cn-beijing.volces.com/api/v3", env="ARK_VISION_BASE_URL")
    ARK_VISION_MODEL: str = Field(default="doubao-seed-2-1-turbo-260628", env="ARK_VISION_MODEL", description="方舟视觉理解模型名（注意是 2-1 不是 2.1，必须带日期后缀）")
    ARK_VISION_ENDPOINT_ID: str = Field(default="", env="ARK_VISION_ENDPOINT_ID", description="方舟推理接入点 ID（ep-xxx），配置后优先于 ARK_VISION_MODEL")
    # --- 讯飞图片理解 WebApi（多模态代码识别用，WebSocket 协议，签名鉴权）---
    XF_VISION_APP_ID: str = Field(default="", env="XF_VISION_APP_ID", description="讯飞应用 APPID（图片理解服务）")
    XF_VISION_API_KEY: str = Field(default="", env="XF_VISION_API_KEY", description="讯飞 APIKey（图片理解服务）")
    XF_VISION_API_SECRET: str = Field(default="", env="XF_VISION_API_SECRET", description="讯飞 APISecret（图片理解服务）")
    XF_VISION_DOMAIN: str = Field(default="imagev3", env="XF_VISION_DOMAIN", description="讯飞图片理解模型版本：general(基础版) / imagev3(高级版)")
    XF_VISION_HOST: str = Field(default="spark-api.cn-huabei-1.xf-yun.com", env="XF_VISION_HOST", description="讯飞图片理解 WebSocket 域名")
    XF_VISION_PATH: str = Field(default="/v2.1/image", env="XF_VISION_PATH", description="讯飞图片理解 WebSocket 路径")
    # --- 视觉模型 provider 选择（multimodal_code_agent 用）---
    VISION_PROVIDER: str = Field(default="xf", env="VISION_PROVIDER", description="视觉模型主 provider：xf(讯飞图片理解) / ark(火山方舟)。另一个自动作为降级 provider")
    DEEPSEEK_BASE_URL: str = Field(default="https://api.deepseek.com/v1", env="DEEPSEEK_BASE_URL")
    SEEDANCE_BASE_URL: str = Field(default="https://seedance.xf-yun.com/v1/generate", env="SEEDANCE_BASE_URL")
    MODERATION_BASE_URL: str = Field(default="https://audit.iflyaisol.com/audit/v2/auditText", env="MODERATION_BASE_URL")

    # --- 内容审核开关（赛题对齐：讯飞生态内容安全，复用 SPARK_API_KEY） ---
    CONTENT_MODERATION_ENABLED: bool = Field(default=True, env="CONTENT_MODERATION_ENABLED", description="内容审核开关，默认开启")
    CONTENT_MODERATION_TIMEOUT: int = Field(default=5, env="CONTENT_MODERATION_TIMEOUT", description="审核 API 超时秒数")

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
    DEMO_MODE: bool = Field(default=False, description="演示模式：跳过LLM冷却期，比赛演示时开启")
    CORS_ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="允许携带认证信息访问 API 的前端来源，以逗号分隔",
    )

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
        # 0. 生产环境安全检查：禁止使用默认 JWT 密钥
        if self.ENVIRONMENT == "production" and self.JWT_SECRET_KEY == "dev-secret-change-in-production":
            raise ValueError("生产环境必须配置JWT_SECRET_KEY环境变量，禁止使用默认值")

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
