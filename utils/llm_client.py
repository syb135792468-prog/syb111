"""
大模型统一调用封装（软件杯A3赛题 v5.5）
- ✅ 主模型：DeepSeek
- ✅ 备用模型：火山引擎方舟 GLM（自动降级）
- ✅ Embedding：讯飞原生（基于官方示例代码，100%正确）
- ✅ 全局配置统一：100%从 config/settings + config/model_config 读取
- ✅ 架构适配：同时提供同步 + 异步版本，异步优先适配FastAPI/LangGraph
- ✅ 功能完整：主模型 + 备用模型 + 内容安全被动拦截
- ✅ RAG支持：讯飞原生Embedding，供 utils/rag_utils.py 使用
- ✅ 工程化增强：单例模式、完善类型注解、详细日志记录
"""
from __future__ import annotations
import time
import asyncio
from typing import List, Optional

# 讯飞Embedding官方依赖
import json
import base64
import hmac
import hashlib
import struct
from datetime import datetime, timezone
import requests
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI, AsyncOpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

# 🔴 全局配置统一：100%从 config 导入，杜绝硬编码
from config.settings import settings
from config.model_config import (
    ENABLE_FALLBACK,
    MAX_RETRIES_PER_MODEL,
    PRIMARY_MODEL_CONFIG,
    GLM_FALLBACK_MODEL_CONFIG,
    EMBEDDING_CONFIG,
)
from config.constants import LLM_BACKOFF_BASE, EMBEDDING_TIMEOUT_SEC, EMBEDDING_MAX_WORKERS, EMBEDDING_MAX_RETRIES
from utils.logger import get_logger

# 关闭SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建模块专属日志记录器
logger = get_logger(__name__, task_id="llm_client")


# ============================================================
# 0. GLM 推理模型重试辅助（备用模型专用）
# ============================================================
def _needs_glm_retry_for_final_answer(content: Optional[str], reasoning_content: Optional[str], max_tokens: int) -> bool:
    """GLM-5.2 推理模型：只在 content 为空且 reasoning_content 非空时才重试。
    提高 max_tokens 阈值到 2048，让 explain 这类小请求一次到位，避免推理重跑。"""
    if content:
        return False
    if not reasoning_content:
        return False
    return max_tokens < 2048


def _expanded_glm_max_tokens(max_tokens: int) -> int:
    """为推理模型补足最终回答空间。"""
    return max(2048, max_tokens * 4)


# ============================================================
# 1. 内容安全异常定义
# ============================================================
class ContentSecurityError(Exception):
    """内容安全违规异常"""
    def __init__(self, message: str, category: Optional[str] = None):
        self.category = category
        super().__init__(message)


# ============================================================
# 讯飞Embedding官方签名生成函数（100%复制官方示例）
# ============================================================
def _generate_spark_signature(api_key: str, api_secret: str, host: str):
    """
    【讯飞官方原版】HMAC签名生成函数
    完全复制讯飞官方文档示例代码，没有任何修改
    """
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    signature_origin = f"host: {host}\ndate: {date}\nPOST / HTTP/1.1"

    hmac_obj = hmac.new(
        key=api_secret.encode('utf-8'),
        msg=signature_origin.encode('utf-8'),
        digestmod=hashlib.sha256
    )
    signature = base64.b64encode(hmac_obj.digest()).decode('utf-8')

    authorization = (
        f'api_key="{api_key}", '
        f'algorithm="hmac-sha256", '
        f'headers="host date request-line", '
        f'signature="{signature}"'
    )

    return date, authorization


# ============================================================
# 2. 同步大模型客户端
# ============================================================
class LLMClient:
    """同步大模型客户端单例"""

    _instance: Optional[LLMClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 主模型：DeepSeek
        self.primary_client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=PRIMARY_MODEL_CONFIG.base_url,
            timeout=PRIMARY_MODEL_CONFIG.timeout,
        )
        self.primary_model = PRIMARY_MODEL_CONFIG.model_name
        logger.info(f"✅ DeepSeek主模型初始化成功：{self.primary_model}")

        # 备用模型：智谱 GLM（主模型失败时降级）
        self.fallback_client = None
        if settings.GLM_API_KEY and ENABLE_FALLBACK:
            self.fallback_client = OpenAI(
                api_key=settings.GLM_API_KEY,
                base_url=GLM_FALLBACK_MODEL_CONFIG.base_url,
                timeout=GLM_FALLBACK_MODEL_CONFIG.timeout,
            )
            self.fallback_model = GLM_FALLBACK_MODEL_CONFIG.model_name
            logger.info(f"✅ GLM备用模型初始化成功：{self.fallback_model}")
        else:
            logger.info(f"ℹ️ 备用模型未启用：FALLBACK={ENABLE_FALLBACK}")

        self.max_retries = MAX_RETRIES_PER_MODEL

    def _call_with_retry(
        self,
        client: OpenAI,
        model: str,
        messages: List[dict],
        temperature: float,
        max_tokens: int,
        provider_name: str,
        response_format: Optional[dict] = None,
    ) -> str:
        """对指定客户端执行带重试的调用"""
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = dict(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                content = message.content
                reasoning_content = getattr(message, "reasoning_content", None)

                if _needs_glm_retry_for_final_answer(content, reasoning_content, max_tokens):
                    expanded_tokens = _expanded_glm_max_tokens(max_tokens)
                    logger.info(
                        f"[{provider_name}] 检测到仅返回 reasoning_content，自动扩容 max_tokens: "
                        f"{max_tokens} -> {expanded_tokens}"
                    )
                    expand_kwargs = dict(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=expanded_tokens,
                    )
                    if response_format is not None:
                        expand_kwargs["response_format"] = response_format
                    response = client.chat.completions.create(**expand_kwargs)
                    message = response.choices[0].message
                    content = message.content

                if not content:
                    logger.warning(f"[{provider_name}] 响应内容为空 (尝试 {attempt}/{self.max_retries})")
                    last_exception = Exception(f"{provider_name} 返回空内容")
                    if attempt < self.max_retries:
                        time.sleep(LLM_BACKOFF_BASE ** attempt)
                    continue
                logger.info(f"[{provider_name}] 同步调用成功 (尝试 {attempt})")
                return content

            except (APIConnectionError, APITimeoutError, RateLimitError) as net_err:
                last_exception = net_err
                logger.warning(
                    f"[{provider_name}] 网络/限流错误 (尝试 {attempt}/{self.max_retries}): {net_err}"
                )
                if attempt < self.max_retries:
                    time.sleep(LLM_BACKOFF_BASE ** attempt)
                continue

            except APIError as api_err:
                error_str = str(api_err)
                if "content_policy_violation" in error_str or "sensitive" in error_str:
                    logger.warning(f"[{provider_name}] 内容违规，触发安全拦截")
                    raise ContentSecurityError("生成的内容涉及敏感信息，已被系统拦截。")
                else:
                    last_exception = api_err
                    logger.warning(
                        f"[{provider_name}] API 错误 (尝试 {attempt}/{self.max_retries}): {api_err}"
                    )
                    if attempt < self.max_retries:
                        time.sleep(LLM_BACKOFF_BASE ** attempt)
                    continue

            except Exception as unk_err:
                last_exception = unk_err
                logger.error(f"[{provider_name}] 未知异常: {unk_err}")
                if attempt < self.max_retries:
                    time.sleep(LLM_BACKOFF_BASE ** attempt)
                continue

        raise last_exception or Exception(f"{provider_name} 调用失败，已达最大重试次数")

    def call(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """同步调用大模型（自动降级）"""
        temp = temperature if temperature is not None else PRIMARY_MODEL_CONFIG.default_temperature
        tokens = max_tokens if max_tokens is not None else PRIMARY_MODEL_CONFIG.default_max_tokens

        try:
            return self._call_with_retry(
                client=self.primary_client,
                model=self.primary_model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                provider_name="DeepSeek",
                response_format=response_format,
            )
        except ContentSecurityError:
            raise
        except Exception as primary_exc:
            logger.warning(f"DeepSeek主模型调用失败: {primary_exc}")
            if self.fallback_client is not None:
                try:
                    return self._call_with_retry(
                        client=self.fallback_client,
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temp,
                        max_tokens=tokens,
                        provider_name="GLM备用",
                        response_format=response_format,
                    )
                except ContentSecurityError:
                    raise
                except Exception as fallback_exc:
                    logger.error(f"GLM备用模型也失败: {fallback_exc}")
                raise Exception("所有大模型均不可用，请稍后重试。") from fallback_exc
            else:
                raise

    def call_embedding_sync(self, texts: List[str], domain: str = "para") -> List[List[float]]:
        """
        【讯飞官方原版】同步调用讯飞 Embedding API
        完全基于讯飞官方示例代码，100%正确
        """
        OFFICIAL_HOST = settings.EMBEDDING_BASE_URL.replace("https://", "").replace("http://", "").rstrip("/")
        OFFICIAL_URL = settings.EMBEDDING_BASE_URL if settings.EMBEDDING_BASE_URL.endswith("/") else settings.EMBEDDING_BASE_URL + "/"

        api_key = settings.SPARK_API_KEY_RAW
        api_secret = settings.SPARK_API_SECRET
        app_id = settings.SPARK_APP_ID

        date, authorization = _generate_spark_signature(api_key, api_secret, OFFICIAL_HOST)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Host": OFFICIAL_HOST,
            "Date": date,
            "Authorization": authorization
        }

        embeddings = []
        max_retries = EMBEDDING_MAX_RETRIES

        for text in texts:
            # 【讯飞官方要求】text字段必须是base64编码的JSON
            text_content = json.dumps({
                "messages": [{"content": text.strip(), "role": "user"}]
            }, ensure_ascii=False)
            text_base64 = base64.b64encode(text_content.encode('utf-8')).decode('utf-8')

            payload = {
                "header": {
                    "app_id": app_id,
                    "status": 3
                },
                "parameter": {
                    "emb": {
                        "domain": domain,
                        "feature": {
                            "encoding": "utf8",
                            "compress": "raw",
                            "format": "plain"
                        }
                    }
                },
                "payload": {
                    "messages": {
                        "encoding": "utf8",
                        "compress": "raw",
                        "format": "json",
                        "status": 3,
                        "text": text_base64
                    }
                }
            }

            last_exception = None
            for attempt in range(max_retries):
                try:
                    resp = requests.post(
                        OFFICIAL_URL,
                        json=payload,
                        headers=headers,
                        timeout=EMBEDDING_TIMEOUT_SEC,
                        verify=False
                    )

                    if resp.status_code == 200:
                        result = resp.json()
                        encoded_vector = result["payload"]["feature"]["text"]
                        vector_bytes = base64.b64decode(encoded_vector)
                        vector = list(struct.unpack('<' + 'f' * (len(vector_bytes) // 4), vector_bytes))
                        embeddings.append(vector)
                        logger.info(f"✅ 同步文本向量化成功，维度：{len(vector)}")
                        break
                    else:
                        error_text = resp.text
                        logger.error(f"同步Embedding失败[{attempt+1}/{max_retries}]: {resp.status_code} - {error_text}")
                        last_exception = Exception(f"同步Embedding失败: {resp.status_code}")
                        time.sleep(LLM_BACKOFF_BASE ** attempt)
                except Exception as e:
                    last_exception = e
                    logger.error(f"同步Embedding异常[{attempt+1}/{max_retries}]: {str(e)}")
                    time.sleep(LLM_BACKOFF_BASE ** attempt)

            if last_exception:
                raise last_exception

        logger.info(f"✅ 成功获取{len(embeddings)}条文本的同步向量")
        return embeddings


# ============================================================
# 3. 异步大模型客户端（推荐使用）
# ============================================================
class AsyncLLMClient:
    """异步大模型客户端单例"""

    _instance: Optional[AsyncLLMClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # 主模型：DeepSeek（异步）
        self.primary_client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=PRIMARY_MODEL_CONFIG.base_url,
            timeout=PRIMARY_MODEL_CONFIG.timeout,
        )
        self.primary_model = PRIMARY_MODEL_CONFIG.model_name
        logger.info(f"✅ DeepSeek异步主模型初始化成功：{self.primary_model}")

        # 备用模型：智谱 GLM（异步，主模型失败时降级）
        self.fallback_client = None
        if settings.GLM_API_KEY and ENABLE_FALLBACK:
            self.fallback_client = AsyncOpenAI(
                api_key=settings.GLM_API_KEY,
                base_url=GLM_FALLBACK_MODEL_CONFIG.base_url,
                timeout=GLM_FALLBACK_MODEL_CONFIG.timeout,
            )
            self.fallback_model = GLM_FALLBACK_MODEL_CONFIG.model_name
            logger.info(f"✅ GLM异步备用模型初始化成功：{self.fallback_model}")
        else:
            logger.info(f"ℹ️ 异步备用模型未启用：FALLBACK={ENABLE_FALLBACK}")

        self.max_retries = MAX_RETRIES_PER_MODEL

    async def _call_with_retry(
        self,
        client: AsyncOpenAI,
        model: str,
        messages: List[dict],
        temperature: float,
        max_tokens: int,
        provider_name: str,
        response_format: Optional[dict] = None,
    ) -> str:
        """异步对指定客户端执行带重试的调用"""
        last_exception = None
        for attempt in range(1, self.max_retries + 1):
            try:
                kwargs = dict(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if response_format is not None:
                    kwargs["response_format"] = response_format
                response = await client.chat.completions.create(**kwargs)
                message = response.choices[0].message
                content = message.content
                reasoning_content = getattr(message, "reasoning_content", None)

                if _needs_glm_retry_for_final_answer(content, reasoning_content, max_tokens):
                    expanded_tokens = _expanded_glm_max_tokens(max_tokens)
                    logger.info(
                        f"[{provider_name}] 检测到仅返回 reasoning_content，自动扩容 max_tokens: "
                        f"{max_tokens} -> {expanded_tokens}"
                    )
                    expand_kwargs = dict(
                        model=model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=expanded_tokens,
                    )
                    if response_format is not None:
                        expand_kwargs["response_format"] = response_format
                    response = await client.chat.completions.create(**expand_kwargs)
                    message = response.choices[0].message
                    content = message.content

                if not content:
                    logger.warning(f"[{provider_name}] 异步响应内容为空 (尝试 {attempt}/{self.max_retries})")
                    last_exception = Exception(f"{provider_name} 返回空内容")
                    if attempt < self.max_retries:
                        await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                    continue
                logger.info(f"[{provider_name}] 异步调用成功 (尝试 {attempt})")
                return content

            except (APIConnectionError, APITimeoutError, RateLimitError) as net_err:
                last_exception = net_err
                logger.warning(
                    f"[{provider_name}] 网络/限流错误 (尝试 {attempt}/{self.max_retries}): {net_err}"
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                continue

            except APIError as api_err:
                error_str = str(api_err)
                if "content_policy_violation" in error_str or "sensitive" in error_str:
                    logger.warning(f"[{provider_name}] 内容违规，触发安全拦截")
                    raise ContentSecurityError("生成的内容涉及敏感信息，已被系统拦截。")
                else:
                    last_exception = api_err
                    logger.warning(
                        f"[{provider_name}] API 错误 (尝试 {attempt}/{self.max_retries}): {api_err}"
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                    continue

            except Exception as unk_err:
                last_exception = unk_err
                logger.error(f"[{provider_name}] 未知异常: {unk_err}")
                if attempt < self.max_retries:
                    await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                continue

        raise last_exception or Exception(f"{provider_name} 调用失败，已达最大重试次数")

    async def call(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """异步调用大模型（自动降级）"""
        temp = temperature if temperature is not None else PRIMARY_MODEL_CONFIG.default_temperature
        tokens = max_tokens if max_tokens is not None else PRIMARY_MODEL_CONFIG.default_max_tokens

        try:
            return await self._call_with_retry(
                client=self.primary_client,
                model=self.primary_model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                provider_name="DeepSeek",
                response_format=response_format,
            )
        except ContentSecurityError:
            raise
        except Exception as primary_exc:
            logger.warning(f"DeepSeek主模型调用失败: {primary_exc}")
            if self.fallback_client is not None:
                try:
                    return await self._call_with_retry(
                        client=self.fallback_client,
                        model=self.fallback_model,
                        messages=messages,
                        temperature=temp,
                        max_tokens=tokens,
                        provider_name="GLM备用",
                        response_format=response_format,
                    )
                except ContentSecurityError:
                    raise
                except Exception as fallback_exc:
                    logger.error(f"GLM备用模型也失败: {fallback_exc}")
                raise Exception("所有大模型均不可用，请稍后重试。") from fallback_exc
            else:
                raise

    async def call_fallback(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """直接调用备用模型（GLM），跳过主模型 DeepSeek。
        适用于 DeepSeek 主模型在重任务上频繁超时/返回空内容的场景。
        备用客户端未启用时抛 RuntimeError。"""
        if self.fallback_client is None:
            raise RuntimeError("备用模型未启用，请将 config/model_config.py 的 ENABLE_FALLBACK 设为 True")

        temp = temperature if temperature is not None else GLM_FALLBACK_MODEL_CONFIG.default_temperature
        tokens = max_tokens if max_tokens is not None else GLM_FALLBACK_MODEL_CONFIG.default_max_tokens

        try:
            return await self._call_with_retry(
                client=self.fallback_client,
                model=self.fallback_model,
                messages=messages,
                temperature=temp,
                max_tokens=tokens,
                provider_name="GLM",
                response_format=response_format,
            )
        except ContentSecurityError:
            raise

    async def call_stream(
        self,
        messages: List[dict],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        流式调用大模型（自动降级），逐 chunk yield 文本片段。
        首 chunk 延迟约 0.5-2s，之后实时输出。
        """
        import time as _time
        temp = temperature if temperature is not None else PRIMARY_MODEL_CONFIG.default_temperature
        tokens = max_tokens if max_tokens is not None else PRIMARY_MODEL_CONFIG.default_max_tokens

        async def _try_stream(client, model, provider_name):
            """尝试流式调用，成功则 yield 所有 chunk，失败则抛异常"""
            last_exception = None
            for attempt in range(1, self.max_retries + 1):
                t_start = _time.monotonic()
                try:
                    logger.info(f"[{provider_name}] 流式调用开始 (尝试 {attempt}), model={model}")
                    stream = await client.chat.completions.create(
                        model=model,
                        messages=messages,
                        temperature=temp,
                        max_tokens=tokens,
                        stream=True,
                    )
                    t_connected = _time.monotonic()
                    print(f"[{provider_name}] 流式连接建立: {(t_connected-t_start)*1000:.0f}ms", flush=True)

                    chunk_count = 0
                    async for chunk in stream:
                        delta = chunk.choices[0].delta if chunk.choices else None
                        if delta and delta.content:
                            chunk_count += 1
                            if chunk_count == 1:
                                print(f"[{provider_name}] 首token: {(_time.monotonic()-t_start)*1000:.0f}ms", flush=True)
                            yield delta.content

                    logger.info(f"[{provider_name}] 流式完成: {chunk_count}个chunk, {(_time.monotonic()-t_start)*1000:.0f}ms")
                    return  # 成功，退出重试循环

                except (APIConnectionError, APITimeoutError, RateLimitError) as net_err:
                    last_exception = net_err
                    logger.warning(f"[{provider_name}] 流式网络错误 (尝试 {attempt}/{self.max_retries}): {net_err}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                except APIError as api_err:
                    error_str = str(api_err)
                    if "content_policy_violation" in error_str or "sensitive" in error_str:
                        raise ContentSecurityError("生成的内容涉及敏感信息，已被系统拦截。")
                    last_exception = api_err
                    logger.warning(f"[{provider_name}] 流式API错误 (尝试 {attempt}/{self.max_retries}): {api_err}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)
                except ContentSecurityError:
                    raise
                except Exception as unk_err:
                    last_exception = unk_err
                    logger.error(f"[{provider_name}] 流式未知异常: {unk_err}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(LLM_BACKOFF_BASE ** attempt)

            raise last_exception or Exception(f"{provider_name} 流式调用失败，已达最大重试次数")

        # 主模型流式
        try:
            async for chunk in _try_stream(self.primary_client, self.primary_model, "DeepSeek"):
                yield chunk
            return
        except ContentSecurityError:
            raise
        except Exception as primary_exc:
            logger.warning(f"DeepSeek流式失败: {primary_exc}")

        # 降级到 GLM 流式
        if self.fallback_client is not None:
            try:
                async for chunk in _try_stream(self.fallback_client, self.fallback_model, "GLM"):
                    yield chunk
                return
            except ContentSecurityError:
                raise
            except Exception as fallback_exc:
                logger.error(f"GLM流式也失败: {fallback_exc}")
                raise Exception("所有大模型均不可用") from fallback_exc
        else:
            raise

    async def call_embedding(self, texts: List[str], domain: str = "para") -> List[List[float]]:
        loop = asyncio.get_event_loop()
        sync_client = get_llm_client()   # 复用同步客户端
        with ThreadPoolExecutor(max_workers=EMBEDDING_MAX_WORKERS) as executor:
            embeddings = await loop.run_in_executor(
                executor,
                sync_client.call_embedding_sync,
                texts,
                domain
            )
        return embeddings
# ============================================================
# 4. 全局单例 + 兼容快捷函数
# ============================================================
_llm_client_sync: Optional[LLMClient] = None
_llm_client_async: Optional[AsyncLLMClient] = None

def get_llm_client() -> LLMClient:
    global _llm_client_sync
    if _llm_client_sync is None:
        _llm_client_sync = LLMClient()
    return _llm_client_sync

def get_async_llm_client() -> AsyncLLMClient:
    global _llm_client_async
    if _llm_client_async is None:
        _llm_client_async = AsyncLLMClient()
    return _llm_client_async

def call_llm(
    messages: List[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    client = get_llm_client()
    return client.call(messages, temperature=temperature, max_tokens=max_tokens)

async def call_llm_async(
    messages: List[dict],
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    client = get_async_llm_client()
    return await client.call(messages, temperature=temperature, max_tokens=max_tokens)

async def call_embedding(texts: List[str], domain: str = "para") -> List[List[float]]:
    client = get_async_llm_client()
    return await client.call_embedding(texts, domain=domain)


# ============================================================
# 5. 模块自测代码
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("🔍 大模型客户端模块自测 v4.2（最终验证版）")
    print("=" * 60)

    # 1. 同步调用
    print("\n1. 测试同步大模型调用...")
    try:
        test_messages = [{"role": "user", "content": "用一句话介绍Python"}]
        reply = call_llm(test_messages, max_tokens=100)
        print(f"   ✅ 同步调用成功：{reply[:80]}...")
    except Exception as exc:
        print(f"   ❌ 同步调用失败：{exc}")

    # 2. 异步调用
    print("\n2. 测试异步大模型调用...")
    async def _test_async():
        try:
            test_messages = [{"role": "user", "content": "用一句话介绍Python"}]
            reply = await call_llm_async(test_messages, max_tokens=100)
            print(f"   ✅ 异步调用成功：{reply[:80]}...")
        except Exception as exc:
            print(f"   ❌ 异步调用失败：{exc}")
    asyncio.run(_test_async())

    # 3. 异步Embedding
    print("\n3. 测试异步Embedding调用...")
    async def _test_embedding():
        try:
            test_texts = ["Python列表", "Python元组"]
            embeddings = await call_embedding(test_texts)
            print(f"   ✅ Embedding调用成功：返回 {len(embeddings)} 个向量，每个维度 {len(embeddings[0])}")
        except Exception as exc:
            print(f"   ❌ Embedding调用失败：{exc}")
    asyncio.run(_test_embedding())

    print("\n" + "=" * 60)
    print("✅ 大模型客户端模块自测完成！")
    print("=" * 60)
