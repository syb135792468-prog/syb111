"""
utils/tts_api.py - 火山引擎语音合成（TTS）API 封装
- ✅ 异步支持：httpx.AsyncClient，不阻塞 FastAPI 事件循环
- ✅ 逐字时间戳：with_timestamp=true，返回 additions 数组供前端逐字高亮
- ✅ 错误处理：自定义异常类，区分鉴权/限流/服务端错误
- ✅ 线程安全单例：双重锁
- ✅ 指数退避重试：仅对 5xx 和网络错误重试，401/429 直接抛出

⚠️ 鉴权方式与方舟 LLM 不同：火山 TTS 用 `Authorization: Bearer;{token}`（分号），
   不是 OpenAI 的 `Bearer {token}`（空格）。app_id + access_token 在火山引擎控制台
   "语音技术 → 语音合成"产品线开通，与方舟 LLM 的 ark-API-Key 是两套独立凭证。
"""
from __future__ import annotations

import base64
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

try:
    import httpx
except ImportError as e:
    raise ImportError("缺少 httpx 依赖，请执行：pip install httpx>=0.27.0") from e

from config.model_config import TTS_CONFIG
from config.constants import (
    VIDEO_TTS_TIMEOUT_SEC,
    VIDEO_TTS_MAX_RETRIES,
    VIDEO_TTS_SAMPLE_RATE,
    VIDEO_TTS_AUDIO_ENCODING,
    VIDEO_TTS_MAX_TEXT_LENGTH,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="volcengine_tts")


# ============================================================
# 自定义异常类
# ============================================================
class TTSAPIError(Exception):
    """TTS API 基础异常"""
    pass


class TTSAuthenticationError(TTSAPIError):
    """鉴权失败（app_id/access_token 错误或未开通服务）"""
    pass


class TTSRateLimitError(TTSAPIError):
    """速率限制"""
    pass


class TTSServerError(TTSAPIError):
    """服务端错误（5xx）"""
    pass


class TTSContentError(TTSAPIError):
    """内容错误（文本过长、含违禁词等）"""
    pass


# ============================================================
# 返回结果
# ============================================================
@dataclass
class TTSSynthesizeResult:
    """单段 TTS 合成结果"""
    audio_b64: str                          # base64 编码的 mp3 音频
    duration_ms: int                        # 音频时长（毫秒）
    word_timestamps: List[Dict[str, Any]] = field(default_factory=list)
    # word_timestamps 每项格式：{text: str, start_ms: int, duration_ms: int}


# ============================================================
# API 封装
# ============================================================
class TTSClient:
    """
    火山引擎语音合成 API 封装

    用法：
        client = TTSClient()
        result = await client.synthesize("你好世界", voice_id="zh_female_wanwanxiaohe_moon_bigtts")
        # result.audio_b64 → base64 mp3
        # result.duration_ms → 音频时长
        # result.word_timestamps → 逐字时间戳
    """

    _instance: Optional["TTSClient"] = None
    _lock: threading.Lock = threading.Lock()

    # BigModel 音色对应 cluster=volcano_mega；普通双向流式音色用 volcano_tts
    # 用户开通后若冒烟失败可改 cluster
    DEFAULT_CLUSTER = "volcano_mega"

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.app_id = TTS_CONFIG.app_id
        self.access_token = TTS_CONFIG.access_token
        self.api_endpoint = TTS_CONFIG.api_endpoint
        self.default_voice_id = TTS_CONFIG.default_voice_id
        self.timeout = VIDEO_TTS_TIMEOUT_SEC
        self.max_retries = VIDEO_TTS_MAX_RETRIES
        self.sample_rate = VIDEO_TTS_SAMPLE_RATE
        self.audio_encoding = VIDEO_TTS_AUDIO_ENCODING
        self.max_text_length = VIDEO_TTS_MAX_TEXT_LENGTH

        if TTS_CONFIG.enabled and (not self.app_id or not self.access_token):
            logger.warning(
                "⚠️ TTS_ENABLED=true 但 TTS_APP_ID/TTS_ACCESS_TOKEN 未配置，"
                "将走 Web Speech 降级路径"
            )

        logger.info(
            f"✅ 火山引擎 TTS 初始化 | enabled={TTS_CONFIG.enabled} | "
            f"voice={self.default_voice_id}"
        )

        # 讯飞超拟人合成（主用），延迟导入避免循环依赖
        from utils.xfyun_tts import XfyunTTSClient
        self.xfyun = XfyunTTSClient()

    @property
    def _headers(self) -> Dict[str, str]:
        """火山 TTS 鉴权头：Bearer;{token}（分号，非空格）"""
        return {
            "Authorization": f"Bearer;{self.access_token}",
            "Content-Type": "application/json",
        }

    def is_enabled(self) -> bool:
        """是否可用（讯飞主 或 火山备 任一可用即可）"""
        return self.xfyun.is_enabled() or self._volcengine_enabled()

    def get_provider_name(self) -> str:
        """当前实际会使用的 provider 名（用于元数据/日志准确标记）"""
        if self.xfyun.is_enabled():
            return "xfyun_tts"
        if self._volcengine_enabled():
            return "volcengine_tts"
        return "browser_web_speech"

    def _volcengine_enabled(self) -> bool:
        """火山 TTS 是否可用（开关开 + 凭证齐全）"""
        return bool(
            TTS_CONFIG.enabled
            and self.app_id
            and self.access_token
        )

    # ============================================================
    # 请求体构建
    # ============================================================
    def _build_payload(
        self,
        text: str,
        voice_id: str,
        cluster: Optional[str] = None,
    ) -> Dict[str, Any]:
        """构建火山 TTS 请求体"""
        return {
            "app": {
                "appid": self.app_id,
                "token": self.access_token,
                "cluster": cluster or self.DEFAULT_CLUSTER,
            },
            "user": {"uid": "python_learning_helper"},
            "audio": {
                "voice_type": voice_id,
                "encoding": self.audio_encoding,
                "rate": self.sample_rate,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": text,
                "text_type": "plain",
                "operation": "query",            # 一次性合成（非流式）
                "with_timestamp": True,          # 返回逐字时间戳
            },
        }

    # ============================================================
    # 错误处理
    # ============================================================
    def _handle_api_error(self, status_code: int, response_text: str) -> None:
        """解析 API 错误并抛出对应异常"""
        if status_code == 401:
            raise TTSAuthenticationError(
                f"TTS 鉴权失败，请检查 TTS_APP_ID/TTS_ACCESS_TOKEN | resp={response_text[:200]}"
            )
        elif status_code == 429:
            raise TTSRateLimitError(f"TTS 速率限制，请稍后重试 | resp={response_text[:200]}")
        elif status_code >= 500:
            raise TTSServerError(f"TTS 服务端错误 ({status_code}) | resp={response_text[:200]}")
        elif status_code >= 400:
            raise TTSContentError(f"TTS 请求错误 ({status_code}) | resp={response_text[:200]}")

    def _handle_business_error(self, code: int, message: str) -> None:
        """解析业务码错误（HTTP 200 但 code != 3000）"""
        if code in (3001, 3002):
            raise TTSAuthenticationError(f"TTS 业务鉴权失败 code={code} | {message}")
        elif code == 3003:
            raise TTSRateLimitError(f"TTS 限流 code={code} | {message}")
        elif code in (3010, 3011, 3012):
            raise TTSContentError(f"TTS 内容错误 code={code} | {message}")
        else:
            raise TTSAPIError(f"TTS 业务错误 code={code} | {message}")

    # ============================================================
    # 核心合成方法（门面：讯飞主 + 火山降级）
    # ============================================================
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> TTSSynthesizeResult:
        """
        合成单段语音（门面：讯飞超拟人合成为主，火山引擎 TTS 降级）

        Args:
            text: 待合成文本（≤500 字，超出会被截断）
            voice_id: 音色 ID，为空则用默认音色
            cluster: 火山集群（仅降级路径使用），BigModel=volcano_mega

        Returns:
            TTSSynthesizeResult：含 audio_b64 / duration_ms / word_timestamps

        Raises:
            TTSAPIError: 讯飞+火山均不可用或均失败
        """
        # 主：讯飞超拟人合成（不传 voice_id，用讯飞默认音色，避免火山音色ID不兼容）
        if self.xfyun.is_enabled():
            try:
                return await self.xfyun.synthesize(text, None)
            except Exception as e:
                if self._volcengine_enabled():
                    logger.warning(f"⚠️ 讯飞 TTS 失败，降级火山：{e}")
                else:
                    raise

        # 备：火山引擎 TTS
        if self._volcengine_enabled():
            return await self._synthesize_volcengine(text, voice_id, cluster)

        raise TTSAPIError("TTS 全部不可用（讯飞+火山均未启用或均失败）")

    # ============================================================
    # 火山引擎 TTS（降级路径）
    # ============================================================
    async def _synthesize_volcengine(
        self,
        text: str,
        voice_id: Optional[str] = None,
        cluster: Optional[str] = None,
    ) -> TTSSynthesizeResult:
        """
        火山引擎 TTS 合成（降级路径）

        Args:
            text: 待合成文本（≤500 字，超出会被截断）
            voice_id: 音色 ID，为空则用默认音色
            cluster: 集群（BigModel=volcano_mega，普通=volcano_tts），为空用默认

        Raises:
            TTSAuthenticationError: 鉴权失败
            TTSRateLimitError: 限流
            TTSServerError: 服务端错误
            TTSContentError: 内容错误
            TTSAPIError: 其他错误
        """
        if not self.is_enabled():
            raise TTSAPIError("TTS 未启用或凭证未配置")

        text = text.strip()
        if not text:
            raise TTSContentError("待合成文本为空")
        if len(text) > self.max_text_length:
            logger.warning(f"⚠️ 文本过长 {len(text)}>{self.max_text_length}，已截断")
            text = text[:self.max_text_length]

        voice = voice_id or self.default_voice_id
        payload = self._build_payload(text, voice, cluster)
        request_id = payload["request"]["reqid"][:8]

        logger.info(
            f"📤 TTS 请求 | id={request_id} | voice={voice} | "
            f"text_len={len(text)}"
        )

        last_exception: Optional[TTSAPIError] = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.api_endpoint,
                        headers=self._headers,
                        json=payload,
                    )

                    if resp.status_code != 200:
                        self._handle_api_error(resp.status_code, resp.text)

                    result = resp.json()

                # 业务码校验：3000 = 成功
                code = result.get("code", 0)
                if code != 3000:
                    self._handle_business_error(code, result.get("message", ""))

                audio_b64 = result.get("data", "")
                if not audio_b64:
                    raise TTSAPIError(f"TTS 返回 data 为空 | resp={result}")

                # duration 字段：火山返回秒级浮点数，转毫秒
                duration_sec = result.get("duration", 0)
                duration_ms = int(duration_sec * 1000) if duration_sec else 0

                # 逐字时间戳：additions 数组
                word_timestamps = result.get("additions", []) or []

                logger.info(
                    f"✅ TTS 合成成功 | id={request_id} | "
                    f"duration={duration_ms}ms | words={len(word_timestamps)} | "
                    f"audio_b64_len={len(audio_b64)}"
                )

                return TTSSynthesizeResult(
                    audio_b64=audio_b64,
                    duration_ms=duration_ms,
                    word_timestamps=word_timestamps,
                )

            except (TTSAuthenticationError, TTSRateLimitError, TTSContentError):
                # 这三类错误不重试
                raise
            except TTSServerError as e:
                last_exception = e
                logger.warning(f"⚠️ TTS 服务端错误，尝试 {attempt + 1}/{self.max_retries + 1}: {e}")
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_exception = TTSServerError(f"TTS 网络错误: {e}")
                logger.warning(f"⚠️ TTS 网络错误，尝试 {attempt + 1}/{self.max_retries + 1}: {e}")
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
            except TTSAPIError as e:
                last_exception = e
                logger.warning(f"⚠️ TTS 调用失败，尝试 {attempt + 1}/{self.max_retries + 1}: {e}")
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_exception = TTSAPIError(f"TTS 未知异常: {e}")
                logger.warning(f"⚠️ TTS 未知异常，尝试 {attempt + 1}/{self.max_retries + 1}: {e}")
                if attempt < self.max_retries:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise TTSAPIError(f"TTS 达到最大重试次数: {last_exception}")

    # ============================================================
    # 健康检查
    # ============================================================
    async def health_check(self) -> bool:
        """简单连通性检查（讯飞主 + 火山备，任一通过即可）"""
        if not self.is_enabled():
            return False
        try:
            # 不传 voice_id，让各 provider 用自身默认音色
            result = await self.synthesize("测试")
            return bool(result.audio_b64)
        except Exception as e:
            logger.warning(f"⚠️ TTS 健康检查失败: {e}")
            return False


# ============================================================
# 模块级单例
# ============================================================
tts_client = TTSClient()


# ============================================================
# 便捷函数
# ============================================================
async def synthesize_speech(
    text: str,
    voice_id: Optional[str] = None,
) -> TTSSynthesizeResult:
    """便捷函数：合成单段语音"""
    return await tts_client.synthesize(text, voice_id=voice_id)


def is_tts_available() -> bool:
    """便捷函数：TTS 是否可用"""
    return tts_client.is_enabled()
