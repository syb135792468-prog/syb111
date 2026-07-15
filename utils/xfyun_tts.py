"""
utils/xfyun_tts.py - 科大讯飞超拟人合成 WebSocket TTS 客户端

接入讯飞超拟人合成私有服务（mcd9m97e6），主用于视频教学配音。
火山引擎 TTS 作为降级备用（由 utils/tts_api.py 门面统一调度）。

鉴权方式（与 spark-api WebSocket 的 HMAC 签名不同）：
  超拟人合成走 Kong API 网关，使用 Bearer Token 鉴权：
  Authorization: Bearer {APIPassword}
  APIPassword 在控制台"超拟人合成 -> APIPassword"中创建，ak- 前缀。

请求帧格式（实测通过）：
  {
    "header": {"app_id": ..., "uid": ..., "status": 2},
    "parameter": {"tts": {
      "vcn": "x6_lingyuyan_pro",
      "audio": {"encoding": "lame"}
    }},
    "payload": {"text": {
      "encoding": "utf8", "compress": "raw", "format": "plain", "status": 2,
      "text": base64(text)
    }}
  }
  关键点：
  - parameter 的键名固定为 "tts"（不是服务标识 mcd9m97e6）
  - 音色字段是 vcn，值形如 x6_lingyuyan_pro（不是 legacy xiaoyan）
  - 音频编码用 lame（不是 mp3）；不带 rate/bits/channels
  - header.status=2 表示最后一帧；payload.text.status=2 表示结束

响应帧格式：
  服务端通过多个 JSON 帧返回，每个帧的 payload.audio.audio 字段是 base64 编码的音频片段。
  header.status==2 表示最后一帧，此时音频合成完成。
  注意：音频数据在 JSON 帧里，不是独立的 bytes 帧。
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Optional, Dict, Any

try:
    import websockets
    from websockets.http11 import Headers
except ImportError as e:
    raise ImportError("缺少 websockets 依赖，请执行：pip install websockets>=12.0") from e

from config.model_config import TTS_CONFIG
from config.constants import (
    VIDEO_TTS_XFYUN_TIMEOUT_SEC,
    VIDEO_TTS_MAX_TEXT_LENGTH,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="xfyun_tts")


class XfyunTTSClient:
    """
    科大讯飞超拟人合成 WebSocket 客户端

    用法：
        client = XfyunTTSClient()
        result = await client.synthesize("你好世界", voice_id="x6_lingyuyan_pro")
        # result.audio_b64 -> base64 mp3
        # result.duration_ms -> 0（前端以 <audio>.duration 为准）
        # result.word_timestamps -> []（讯飞无逐字时间戳，前端降级纯文本字幕）
    """

    _instance: Optional["XfyunTTSClient"] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self.app_id = TTS_CONFIG.xfyun_app_id
        self.api_password = TTS_CONFIG.xfyun_api_password
        self.ws_url = TTS_CONFIG.xfyun_ws_url
        self.default_voice_id = TTS_CONFIG.xfyun_voice_id
        self.timeout = VIDEO_TTS_XFYUN_TIMEOUT_SEC

        if self.is_enabled():
            logger.info(
                f"✅ 讯飞超拟人 TTS 初始化 | voice={self.default_voice_id} | "
                f"ws={self.ws_url}"
            )
        else:
            logger.info("ℹ️ 讯飞超拟人 TTS 未启用（APIPassword 未配置）")

    def is_enabled(self) -> bool:
        return bool(self.app_id and self.api_password and self.ws_url)

    # ============================================================
    # 鉴权 headers（Bearer Token，Kong 网关）
    # ============================================================
    def _build_auth_headers(self) -> Headers:
        headers = Headers()
        headers["Authorization"] = f"Bearer {self.api_password}"
        return headers

    # ============================================================
    # 请求帧构建
    # ============================================================
    def _build_frame(self, text: str, voice_id: str) -> Dict[str, Any]:
        text_b64 = base64.b64encode(text.encode("utf-8")).decode("utf-8")
        return {
            "header": {
                "app_id": self.app_id,
                "uid": "video_agent",
                "status": 2,
            },
            "parameter": {
                "tts": {
                    "vcn": voice_id,
                    "audio": {
                        "encoding": "lame",
                    },
                }
            },
            "payload": {
                "text": {
                    "encoding": "utf8",
                    "compress": "raw",
                    "format": "plain",
                    "status": 2,
                    "text": text_b64,
                }
            },
        }

    # ============================================================
    # 核心合成方法
    # ============================================================
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
    ) -> "TTSSynthesizeResult":
        # 延迟导入避免循环依赖（tts_api <-> xfyun_tts）
        from utils.tts_api import TTSSynthesizeResult, TTSAPIError

        if not self.is_enabled():
            raise TTSAPIError("讯飞 TTS 未启用或 APIPassword 未配置")

        text = text.strip()
        if not text:
            raise TTSAPIError("待合成文本为空")
        if len(text) > VIDEO_TTS_MAX_TEXT_LENGTH:
            logger.warning(f"⚠️ 文本过长 {len(text)}>{VIDEO_TTS_MAX_TEXT_LENGTH}，已截断")
            text = text[:VIDEO_TTS_MAX_TEXT_LENGTH]

        voice = voice_id or self.default_voice_id
        headers = self._build_auth_headers()
        frame = self._build_frame(text, voice)

        logger.info(
            f"📤 讯飞 TTS 请求 | voice={voice} | text_len={len(text)}"
        )

        audio_buf = bytearray()
        frame_count = 0
        try:
            async with websockets.connect(
                self.ws_url,
                additional_headers=headers,
                open_timeout=self.timeout,
                close_timeout=self.timeout,
            ) as ws:
                await ws.send(json.dumps(frame, ensure_ascii=False))

                async for msg in ws:
                    if isinstance(msg, (bytes, bytearray)):
                        # 超拟人合成不会发 bytes 帧，但保险起见跳过
                        continue

                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"⚠️ 讯飞 TTS 无法解析的文本帧：{msg[:200]}")
                        continue

                    frame_count += 1
                    code = data.get("header", {}).get("code", -1)
                    if code != 0:
                        message = data.get("header", {}).get("message", "未知错误")
                        sid = data.get("header", {}).get("sid", "")
                        raise TTSAPIError(
                            f"讯飞 TTS 业务错误 code={code} | {message} | sid={sid}"
                        )

                    # 音频数据在 payload.audio.audio（base64 字符串）
                    audio_b64 = (
                        data.get("payload", {})
                        .get("audio", {})
                        .get("audio", "")
                    )
                    if audio_b64:
                        try:
                            audio_buf.extend(base64.b64decode(audio_b64))
                        except Exception as e:
                            logger.warning(f"⚠️ 讯飞 TTS 音频 base64 解码失败：{e}")

                    # header.status==2 表示合成结束
                    status = data.get("header", {}).get("status", 0)
                    if status == 2:
                        break

        except websockets.exceptions.InvalidStatus as e:
            status_code = getattr(e.response, "status_code", "?")
            body = getattr(e.response, "body", b"")
            body_text = body.decode("utf-8", errors="replace")[:300] if body else ""
            raise TTSAPIError(
                f"讯飞 TTS 鉴权/连接失败 HTTP {status_code}（检查 APIPassword）| body={body_text}"
            ) from e
        except websockets.exceptions.WebSocketException as e:
            raise TTSAPIError(f"讯飞 TTS WebSocket 异常：{e}") from e
        except asyncio.TimeoutError as e:
            raise TTSAPIError(f"讯飞 TTS 超时（{self.timeout}s）") from e

        if not audio_buf:
            raise TTSAPIError(f"讯飞 TTS 返回音频为空 | frames={frame_count}")

        audio_b64_final = base64.b64encode(bytes(audio_buf)).decode("utf-8")
        logger.info(
            f"✅ 讯飞 TTS 合成成功 | frames={frame_count} | "
            f"audio_len={len(audio_buf)}字节 | b64_len={len(audio_b64_final)}"
        )

        # duration_ms=0：前端以 <audio>.duration 为准，无需后端估算
        # word_timestamps=[]：讯飞超拟人合成无逐字时间戳，前端走纯文本字幕降级
        return TTSSynthesizeResult(
            audio_b64=audio_b64_final,
            duration_ms=0,
            word_timestamps=[],
        )

    async def health_check(self) -> bool:
        if not self.is_enabled():
            return False
        try:
            result = await self.synthesize("测试", voice_id=self.default_voice_id)
            return bool(result.audio_b64)
        except Exception as e:
            logger.warning(f"⚠️ 讯飞 TTS 健康检查失败：{e}")
            return False


# ============================================================
# 模块级单例
# ============================================================
xfyun_tts_client = XfyunTTSClient()


# ============================================================
# 自测入口
# ============================================================
if __name__ == "__main__":
    import sys
    from pathlib import Path

    if not xfyun_tts_client.is_enabled():
        print("[FAIL] 讯飞 TTS 凭证未配置，请检查 .env 中 TTS_XFYUN_API_PASSWORD")
        sys.exit(1)

    async def _test():
        text = "你好，这是讯飞超拟人合成的测试。"
        print(f"[TEST] 合成文本：{text}")
        result = await xfyun_tts_client.synthesize(text)
        audio_bytes = base64.b64decode(result.audio_b64)
        print(f"[OK] 合成成功 | 音频 {len(audio_bytes)} 字节 | duration_ms={result.duration_ms}")

        # 检查 mp3 魔数
        if audio_bytes[:3] == b"ID3" or (audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
            print(f"[OK] 音频格式合法（MP3 魔数匹配 {audio_bytes[:2].hex()}）")
        else:
            print(f"[WARN] 音频魔数异常：{audio_bytes[:4].hex()}（可能不是 MP3）")

        # 落盘试听
        out = "data/xfyun_tts_test.mp3"
        Path("data").mkdir(exist_ok=True)
        Path(out).write_bytes(audio_bytes)
        print(f"[SAVE] 已落盘：{out}（可用播放器试听）")

    asyncio.run(_test())
