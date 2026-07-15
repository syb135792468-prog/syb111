"""
utils/xfyun_vision_api.py - 讯飞图片理解 WebApi 封装
- 协议：WebSocket（wss://spark-api.cn-huabei-1.xf-yun.com/v2.1/image）
- 鉴权：HMAC-SHA256 签名（host + date + request-line），authorization base64
- 接口与 utils/ark_vision_api.py 对齐：chat_completion(image_path, prompt, system_prompt, ...)
- 注意：讯飞图片理解不支持 system role，system_prompt 会被拼到 user prompt 前面
- domain=imagev3（高级版，动态 token），首项必须是图片
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote

try:
    import websockets
except ImportError as e:
    raise ImportError("缺少 websockets 依赖，请执行：pip install websockets>=12.0") from e

from config.settings import settings
from config.constants import (
    MULTIMODAL_OMNI_MAX_RETRIES,
    MULTIMODAL_OMNI_TIMEOUT_SEC,
    MULTIMODAL_OMNI_MAX_IMAGE_SIZE_MB,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="xf_vision")


# ============================================================
# 自定义异常类
# ============================================================
class XfVisionError(Exception):
    """讯飞图片理解 API 基础异常"""
    pass


class XfVisionAuthError(XfVisionError):
    """鉴权错误"""
    pass


class XfVisionSchemaError(XfVisionError):
    """请求 schema 错误"""
    pass


class XfVisionImageError(XfVisionError):
    """图片处理错误"""
    pass


# ============================================================
# API 封装
# ============================================================
class XfVisionAPI:
    """
    讯飞图片理解 WebApi 封装

    支持：
    - 图片+文本多模态请求（WebSocket）
    - 自动签名鉴权
    - 同步等待完整响应（讯飞 v2.1 image 是单轮问答，非流式语义）
    - 线程安全单例
    """

    _instance: Optional["XfVisionAPI"] = None
    _lock: threading.Lock = threading.Lock()

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

        self.app_id = settings.XF_VISION_APP_ID
        self.api_key = settings.XF_VISION_API_KEY
        self.api_secret = settings.XF_VISION_API_SECRET
        self.domain = settings.XF_VISION_DOMAIN or "imagev3"
        self.host = settings.XF_VISION_HOST
        self.path = settings.XF_VISION_PATH
        self.timeout = MULTIMODAL_OMNI_TIMEOUT_SEC
        self.max_retries = MULTIMODAL_OMNI_MAX_RETRIES
        self.max_image_size_mb = MULTIMODAL_OMNI_MAX_IMAGE_SIZE_MB

        self._request_times: List[float] = []
        self._rate_limit_lock = threading.Lock()

        logger.info(
            f"✅ XfVision API 初始化完成 | app_id={self.app_id} | "
            f"domain={self.domain} | host={self.host}"
        )

    # ============================================================
    # 图片处理
    # ============================================================
    @staticmethod
    def _get_mime_type(image_path: Path) -> str:
        ext = image_path.suffix.lower()
        return {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png"}.get(ext, "image/jpeg")

    def _encode_image(self, image_path: str | Path) -> str:
        """返回纯 base64 字符串（讯飞 v2.1 image 不用 data URI）"""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        file_size_mb = image_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_image_size_mb:
            raise XfVisionImageError(
                f"图片文件过大: {file_size_mb:.1f}MB，最大支持 {self.max_image_size_mb}MB"
            )

        # 讯飞图片理解只支持 jpg/jpeg/png
        ext = image_path.suffix.lower()
        if ext not in (".jpg", ".jpeg", ".png"):
            raise XfVisionImageError(
                f"讯飞图片理解仅支持 jpg/jpeg/png，当前: {ext}"
            )

        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            raise XfVisionImageError(f"图片编码失败: {e}")

    # ============================================================
    # 签名鉴权
    # ============================================================
    def _build_auth_url(self) -> str:
        """生成带签名的 WebSocket URL"""
        date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {self.host}\ndate: {date}\nGET {self.path} HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode(),
            signature_origin.encode(),
            hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode()
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode()).decode()
        return (
            f"wss://{self.host}{self.path}"
            f"?authorization={authorization}&date={quote(date)}&host={self.host}"
        )

    # ============================================================
    # 速率限制
    # ============================================================
    def _check_rate_limit(self, max_per_min: int = 20):
        with self._rate_limit_lock:
            now = time.monotonic()
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= max_per_min:
                wait_time = 60 - (now - self._request_times[0])
                raise XfVisionError(
                    f"速率限制：每分钟最多 {max_per_min} 次请求，请等待 {wait_time:.0f} 秒"
                )
            self._request_times.append(now)

    # ============================================================
    # 构建请求 payload
    # ============================================================
    def _build_payload(
        self,
        image_b64: str,
        prompt: str,
        system_prompt: Optional[str],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        # 讯飞 v2.1 image 不支持 system role，拼到 user prompt 前面
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        # 官方要求：首项必须是图片
        text_items = [
            {"role": "user", "content": image_b64, "content_type": "image"},
            {"role": "user", "content": full_prompt, "content_type": "text"},
        ]
        return {
            "header": {"app_id": self.app_id},
            "parameter": {
                "chat": {
                    "domain": self.domain,
                    "temperature": temperature,
                    "top_k": 4,
                    "max_tokens": max_tokens,
                }
            },
            "payload": {"message": {"text": text_items}},
        }

    # ============================================================
    # 非流式调用（WebSocket 单轮问答，聚合所有帧后返回完整文本）
    # ============================================================
    async def chat_completion(
        self,
        image_path: str | Path,
        prompt: str = "请识别并分析这张图片中的代码",
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        非流式多模态调用（讯飞 v2.1 image 单轮问答）

        Args:
            image_path: 图片文件路径
            prompt: 用户提示词（messages 为空时使用）
            system_prompt: 系统提示词（拼到 user prompt 前，讯飞不支持 system role）
            messages: 完整消息列表（优先级高于 image_path + prompt，本项目暂不使用）
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            模型回复文本
        """
        if not self.app_id or not self.api_key or not self.api_secret:
            raise XfVisionAuthError(
                "讯飞视觉 API 凭证未配置，请检查 XF_VISION_APP_ID/API_KEY/API_SECRET"
            )

        self._check_rate_limit()

        image_b64 = self._encode_image(image_path)
        payload = self._build_payload(image_b64, prompt, system_prompt, temperature, max_tokens)

        import asyncio

        img_name = Path(image_path).name if isinstance(image_path, (str, Path)) else "image"
        request_id = f"{int(time.time()*1000)}_{hash(img_name) & 0xffff:x}"
        logger.info(
            f"📤 XfVision 请求 | id={request_id} | domain={self.domain} | "
            f"图片={img_name}"
        )

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                url = self._build_auth_url()
                result_text = ""

                async with websockets.connect(
                    url,
                    max_size=20 * 1024 * 1024,
                    open_timeout=self.timeout,
                    additional_headers={"Origin": f"https://{self.host}"},
                ) as ws:
                    await ws.send(__import__("json").dumps(payload, ensure_ascii=False))

                    for _ in range(60):
                        msg = await asyncio.wait_for(ws.recv(), timeout=self.timeout)
                        import json
                        data = json.loads(msg)
                        code = data.get("header", {}).get("code", -1)
                        if code != 0:
                            err_msg = data.get("header", {}).get("message", "")
                            raise XfVisionSchemaError(f"讯飞返回错误 code={code}: {err_msg}")

                        status = data.get("header", {}).get("status", 0)
                        texts = data.get("payload", {}).get("choices", {}).get("text", [])
                        for t in texts:
                            result_text += t.get("content", "")

                        if status == 2:
                            usage = data.get("payload", {}).get("usage", {}).get("text", {})
                            logger.info(
                                f"✅ XfVision 成功 | id={request_id} | "
                                f"tokens={usage.get('total_tokens', '?')} | "
                                f"长度={len(result_text)}字"
                            )
                            return result_text

                    raise XfVisionError("超过最大帧数，未收到完成信号")

            except (XfVisionAuthError, XfVisionSchemaError, XfVisionImageError):
                raise  # 这些错误不重试
            except XfVisionError as e:
                last_exception = e
                logger.warning(f"⚠️ 尝试 {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_exception = XfVisionError(f"请求异常: {e}")
                logger.warning(f"⚠️ 尝试 {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        raise XfVisionError(f"达到最大重试次数: {last_exception}")

    # ============================================================
    # 健康检查
    # ============================================================
    async def health_check(self) -> bool:
        """检查凭证是否配置完整（不发起真实请求）"""
        return bool(self.app_id and self.api_key and self.api_secret)


# ============================================================
# 模块级单例
# ============================================================
xf_vision_api = XfVisionAPI()
