"""
utils/ark_vision_api.py - 火山方舟视觉理解模型（doubao-seed-2.1-turbo）多模态 API 封装
- ✅ 异步支持：使用 httpx.AsyncClient，不阻塞 FastAPI 事件循环
- ✅ 流式输出：支持 SSE 流式返回，逐 chunk 读取
- ✅ 系统提示词：支持完整 messages 列表
- ✅ 错误处理：自定义异常类，区分不同错误类型
- ✅ 线程安全单例：使用 threading.Lock
- ✅ 图片处理：正确的 MIME 类型 + 大小检查
- ✅ 配置管理：从 model_config 读取，无硬编码
- ✅ OpenAI 兼容：方舟视觉模型走标准端点 /api/v3，原生支持 image_url + base64 data URI
"""
from __future__ import annotations

import base64
import threading
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List, AsyncIterator

try:
    import httpx
except ImportError as e:
    raise ImportError("缺少 httpx 依赖，请执行：pip install httpx>=0.27.0") from e

from config.settings import settings
from config.model_config import ARK_VISION_CONFIG
from config.constants import (
    MULTIMODAL_OMNI_MAX_RETRIES,
    MULTIMODAL_OMNI_TIMEOUT_SEC,
    MULTIMODAL_OMNI_MAX_IMAGE_SIZE_MB,
    MAX_IMAGE_SIZE_MB,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="mimo_omni")


# ============================================================
# 自定义异常类
# ============================================================
class MimoAPIError(Exception):
    """MiMo API 基础异常"""
    pass


class MimoRateLimitError(MimoAPIError):
    """速率限制错误"""
    pass


class MimoAuthenticationError(MimoAPIError):
    """认证错误"""
    pass


class MimoModelNotFoundError(MimoAPIError):
    """模型不存在错误"""
    pass


class MimoImageError(MimoAPIError):
    """图片处理错误"""
    pass


# ============================================================
# API 封装
# ============================================================
class MimoOmniAPI:
    """
    小米 MiMo Omni 多模态 API 封装

    支持：
    - 图片+文本多模态请求
    - 流式/非流式响应
    - 系统提示词
    """

    _instance: Optional["MimoOmniAPI"] = None
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

        # 从配置读取，不硬编码
        self.api_key = settings.ARK_VISION_API_KEY
        self.base_url = ARK_VISION_CONFIG.base_url
        self.model_name = ARK_VISION_CONFIG.model_name
        self.timeout = MULTIMODAL_OMNI_TIMEOUT_SEC
        self.max_retries = MULTIMODAL_OMNI_MAX_RETRIES
        self.max_image_size_mb = MULTIMODAL_OMNI_MAX_IMAGE_SIZE_MB

        # 速率限制
        self._request_times: List[float] = []
        self._rate_limit_lock = threading.Lock()

        logger.info(f"✅ ArkVision API 初始化完成 | model={self.model_name} | base_url={self.base_url}")

    @property
    def _headers(self) -> Dict[str, str]:
        """标准 OpenAI 兼容请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # ============================================================
    # 图片处理
    # ============================================================
    @staticmethod
    def _get_mime_type(image_path: Path) -> str:
        """根据文件后缀获取正确的 MIME 类型"""
        ext = image_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
        }
        return mime_types.get(ext, "image/jpeg")

    def _encode_image(self, image_path: str | Path) -> str:
        """
        将图片编码为 base64 data URI

        Raises:
            MimoImageError: 文件过大或格式不支持
            FileNotFoundError: 文件不存在
        """
        image_path = Path(image_path)

        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        # 检查文件大小
        file_size_mb = image_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_image_size_mb:
            raise MimoImageError(
                f"图片文件过大: {file_size_mb:.1f}MB，最大支持 {self.max_image_size_mb}MB"
            )

        # 获取正确的 MIME 类型
        mime = self._get_mime_type(image_path)

        try:
            with open(image_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            raise MimoImageError(f"图片编码失败: {e}")

        return f"data:{mime};base64,{data}"

    # ============================================================
    # 速率限制
    # ============================================================
    def _check_rate_limit(self, max_per_min: int = 20):
        """简单的客户端速率限制"""
        with self._rate_limit_lock:
            now = time.monotonic()
            # 清理 1 分钟前的记录
            self._request_times = [t for t in self._request_times if now - t < 60]
            if len(self._request_times) >= max_per_min:
                wait_time = 60 - (now - self._request_times[0])
                raise MimoRateLimitError(
                    f"速率限制：每分钟最多 {max_per_min} 次请求，请等待 {wait_time:.0f} 秒"
                )
            self._request_times.append(now)

    # ============================================================
    # 错误处理
    # ============================================================
    def _handle_api_error(self, status_code: int, response_text: str) -> None:
        """解析 API 错误并抛出对应的自定义异常"""
        if status_code == 401:
            raise MimoAuthenticationError(f"API 认证失败，请检查 ARK_VISION_API_KEY")
        elif status_code == 404:
            raise MimoModelNotFoundError(f"模型不存在: {self.model_name}")
        elif status_code == 429:
            raise MimoRateLimitError(f"API 速率限制，请稍后重试")
        elif status_code >= 400:
            raise MimoAPIError(f"API 错误 ({status_code}): {response_text}")

    # ============================================================
    # 构建请求体
    # ============================================================
    def _build_payload(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """构建 OpenAI 兼容的请求体"""
        return {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
            "thinking": {"type": "disabled"},
        }

    def _build_messages(
        self,
        image_path: str | Path,
        prompt: str = "请识别并分析这张图片中的代码",
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """构建包含图片的消息列表"""
        image_url = self._encode_image(image_path)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        })

        return messages

    # ============================================================
    # 非流式调用
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
        非流式多模态调用

        Args:
            image_path: 图片文件路径
            prompt: 用户提示词（当 messages 为空时使用）
            system_prompt: 系统提示词
            messages: 完整的消息列表（优先级高于 image_path + prompt）
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            模型回复文本

        Raises:
            MimoAPIError: API 调用失败
            MimoImageError: 图片处理失败
        """
        self._check_rate_limit()

        # 构建消息
        if messages is None:
            messages = self._build_messages(image_path, prompt, system_prompt)

        payload = self._build_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
        )

        request_id = uuid.uuid4().hex[:8]
        logger.info(
            f"📤 ArkVision 请求 | id={request_id} | model={self.model_name} | "
            f"messages={len(messages)}条"
        )

        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )

                    if resp.status_code != 200:
                        self._handle_api_error(resp.status_code, resp.text)

                    result = resp.json()

                if "choices" in result and len(result["choices"]) > 0:
                    message = result["choices"][0]["message"]
                    content = message.get("content") or ""
                    if not content.strip():
                        reasoning_len = len(message.get("reasoning_content") or "")
                        raise MimoAPIError(
                            f"模型返回空 content（reasoning_content 长度={reasoning_len}）"
                        )
                    usage = result.get("usage", {})
                    logger.info(
                        f"✅ ArkVision 成功 | id={request_id} | "
                        f"tokens={usage.get('total_tokens', '?')} | "
                        f"长度={len(content)}字"
                    )
                    return content
                else:
                    raise MimoAPIError(f"API 返回异常: {result}")

            except (MimoRateLimitError, MimoAuthenticationError, MimoModelNotFoundError):
                raise  # 这些错误不重试
            except MimoAPIError as e:
                last_exception = e
                logger.warning(f"⚠️ 尝试 {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                last_exception = MimoAPIError(f"请求异常: {e}")
                logger.warning(f"⚠️ 尝试 {attempt + 1}/{self.max_retries}: {e}")
                if attempt < self.max_retries - 1:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)

        raise MimoAPIError(f"达到最大重试次数: {last_exception}")

    # ============================================================
    # 流式调用
    # ============================================================
    async def chat_completion_stream(
        self,
        image_path: str | Path,
        prompt: str = "请识别并分析这张图片中的代码",
        system_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """
        流式多模态调用，逐 chunk 返回文本

        Args:
            image_path: 图片文件路径
            prompt: 用户提示词（当 messages 为空时使用）
            system_prompt: 系统提示词
            messages: 完整的消息列表（优先级高于 image_path + prompt）
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Yields:
            每个 chunk 的文本片段

        Raises:
            MimoAPIError: API 调用失败
            MimoImageError: 图片处理失败
        """
        self._check_rate_limit()

        # 构建消息
        if messages is None:
            messages = self._build_messages(image_path, prompt, system_prompt)

        payload = self._build_payload(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        request_id = uuid.uuid4().hex[:8]
        logger.info(
            f"📤 ArkVision 流式请求 | id={request_id} | model={self.model_name}"
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers=self._headers,
                    json=payload,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        self._handle_api_error(resp.status_code, error_body.decode())

                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data: "):
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                import json
                                chunk = json.loads(data)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    yield content
                            except (json.JSONDecodeError, IndexError, KeyError):
                                continue

            logger.info(f"✅ ArkVision 流式完成 | id={request_id}")

        except MimoAPIError:
            raise
        except Exception as e:
            raise MimoAPIError(f"流式请求异常: {e}")

    # ============================================================
    # 健康检查
    # ============================================================
    async def health_check(self) -> bool:
        """检查 API 连通性"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers,
                )
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"⚠️ ArkVision 健康检查失败: {e}")
            return False


# ============================================================
# 模块级单例（线程安全）
# ============================================================
mimo_omni_api = MimoOmniAPI()


# ============================================================
# 便捷函数
# ============================================================
async def analyze_image(
    image_path: str | Path,
    prompt: str = "请识别并分析这张图片中的代码",
    system_prompt: Optional[str] = None,
) -> str:
    """便捷函数：非流式图片分析"""
    return await mimo_omni_api.chat_completion(
        image_path=image_path,
        prompt=prompt,
        system_prompt=system_prompt,
    )


async def analyze_image_stream(
    image_path: str | Path,
    prompt: str = "请识别并分析这张图片中的代码",
    system_prompt: Optional[str] = None,
) -> AsyncIterator[str]:
    """便捷函数：流式图片分析"""
    async for chunk in mimo_omni_api.chat_completion_stream(
        image_path=image_path,
        prompt=prompt,
        system_prompt=system_prompt,
    ):
        yield chunk
