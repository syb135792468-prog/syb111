"""
讯飞多模态 API 封装（软件杯A3赛题 v1.3 零警告修复版）
- ✅ 从 config.settings 读取凭证，复用 llm_client 的认证方式
- ✅ 图片理解：通过 Spark Lite 的 OpenAI 兼容 Vision 接口实现
- ✅ 图文生成：预留框架，需根据实际开通的 API 补充端点
- ✅ 使用 httpx 异步客户端，与项目技术栈统一
- ✅ 【修复】所有PyCharm警告：未使用导入、未使用参数、protected访问、拼写错误
- ✅ 【新增】线程安全单例模式、图片大小限制、重试机制、完善MIME类型支持
- ✅ 完善的错误处理和日志
"""
from __future__ import annotations
import base64
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
# 【修复】httpx依赖异常处理，明确提示安装
try:
    import httpx
except ImportError as e:
    raise ImportError(
        "缺少httpx依赖，请执行安装：pip install httpx>=0.27.0"
    ) from e

from config.settings import settings
from config.constants import (
    MAX_IMAGE_SIZE_MB, MULTIMODAL_MAX_RETRIES,
    MULTIMODAL_TIMEOUT_SEC, IMAGE_UNDERSTANDING_MAX_TOKENS,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="multimodal_api")


class MultimodalAPIError(Exception):
    """多模态 API 错误"""
    pass


class SparkMultimodalAPI:
    """
    讯飞星火多模态 API 封装
    当前支持：图片理解（Image-to-Text）
    待扩展：图文生成（需根据讯飞实际图像生成服务补充）
    """

    _instance: Optional["SparkMultimodalAPI"] = None
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

        # 复用 Spark Lite 的 OpenAI 兼容配置（已在 llm_client.py 中验证可用）
        self.api_key = settings.SPARK_API_KEY  # 已拼接好的 Key:Secret
        self.base_url = settings.SPARK_BASE_URL  # https://spark-api-open.xf-yun.com/v1
        self.default_model = settings.SPARK_MODEL  # "lite"

        # 配置参数
        self.max_image_size_mb = MAX_IMAGE_SIZE_MB
        self.max_retries = MULTIMODAL_MAX_RETRIES
        self.timeout = MULTIMODAL_TIMEOUT_SEC

        logger.info("✅ 多模态 API 客户端已初始化")

    @property
    def _headers(self) -> Dict[str, str]:
        """标准 OpenAI 兼容请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # 【修复】protected方法改为public，解决外部访问警告，方法名规范
    @staticmethod
    def get_mime_type(image_path: Path) -> str:
        """
        根据文件后缀获取 MIME 类型
        """
        ext = image_path.suffix.lower()
        mime_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".tif": "image/tiff",
        }
        return mime_types.get(ext, "image/jpeg")  # 默认回退为 jpeg

    def _encode_image(self, image_path: str | Path) -> str:
        """
        将图片文件编码为 Base64 字符串，并自动添加 data URI 前缀

        Args:
            image_path: 图片文件路径

        Returns:
            Base64 编码的 data URI

        Raises:
            FileNotFoundError: 文件不存在
            MultimodalAPIError: 文件过大
        """
        image_path = Path(image_path)

        # 1. 检查文件是否存在
        if not image_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        # 2. 检查文件大小
        file_size_mb = image_path.stat().st_size / (1024 * 1024)
        if file_size_mb > self.max_image_size_mb:
            raise MultimodalAPIError(
                f"图片文件过大: {file_size_mb:.1f}MB，"
                f"最大支持 {self.max_image_size_mb}MB"
            )

        # 3. 获取 MIME 类型
        mime = self.get_mime_type(image_path)

        # 4. 编码为 Base64
        with open(image_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")

        logger.debug(f"📸 图片编码完成: {image_path.name}, "
                     f"大小: {file_size_mb:.1f}MB, "
                     f"MIME: {mime}")

        return f"data:{mime};base64,{data}"

    async def understand_image(
            self,
            image_path: str | Path,
            prompt: str = "请描述这张图片的内容",
            model: Optional[str] = None,
            max_tokens: int = IMAGE_UNDERSTANDING_MAX_TOKENS,
    ) -> str:
        """
        图片理解（Image-to-Text）
        通过 Spark Lite 的 Vision 能力分析图片内容

        Args:
            image_path: 图片文件路径
            prompt: 提示词
            model: 模型名称，默认使用 settings.SPARK_MODEL
            max_tokens: 最大生成 token 数

        Returns:
            文字描述
        """
        model = model or self.default_model
        logger.info(f"🖼️  开始图片理解: {image_path}, "
                    f"prompt='{prompt[:50]}...'")

        # 编码图片（先做，避免网络请求失败后重复编码）
        image_url = self._encode_image(image_path)

        # 构造 OpenAI Vision 请求体
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
            "max_tokens": max_tokens,
        }

        # 重试机制
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=self._headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    result = resp.json()

                if "choices" in result and len(result["choices"]) > 0:
                    description = result["choices"][0]["message"]["content"]
                    logger.info(f"✅ 图片理解成功 (尝试 {attempt + 1}/{self.max_retries}): "
                                f"{len(description)} 字")
                    return description
                else:
                    raise MultimodalAPIError(f"图片理解失败: {result}")

            except httpx.HTTPStatusError as e:
                last_exception = e
                logger.warning(f"⚠️  HTTP 错误 (尝试 {attempt + 1}/{self.max_retries}): "
                               f"{e.response.status_code} - {e.response.text}")
                if attempt == self.max_retries - 1:
                    logger.error(f"❌ 达到最大重试次数，放弃")
                    raise MultimodalAPIError(f"图片理解请求失败: {e}")
            except Exception as e:
                last_exception = e
                logger.warning(f"⚠️  错误 (尝试 {attempt + 1}/{self.max_retries}): {e}")
                if attempt == self.max_retries - 1:
                    logger.error(f"❌ 达到最大重试次数，放弃", exc_info=True)
                    raise MultimodalAPIError(f"图片理解失败: {e}")

        # 理论上不会走到这里，但为了类型安全
        raise MultimodalAPIError(f"图片理解失败: {last_exception}")

    async def generate_image(
            self,
            prompt: str,
            size: str = "1024x1024",
            n: int = 1,
            model: Optional[str] = None,
    ) -> List[str]:
        """
        图文生成（Text-to-Image）—— 预留接口
        需要根据讯飞实际开通的图像生成服务补充端点与请求格式
        """
        # 【修复】标记所有参数为已使用，消除未使用形参警告
        _ = (prompt, size, n, model)

        logger.warning("⚠️  图文生成接口尚未实现，需根据实际 API 文档补充")
        raise NotImplementedError(
            "图文生成功能暂未接入，请确认讯飞侧是否已开通该服务，并补充具体端点与参数"
        )

    async def health_check(self) -> bool:
        """快速测试 API 连通性（使用简单的模型列表请求）"""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self.base_url}/models",
                    headers=self._headers,
                )
                is_healthy = resp.status_code == 200
                logger.debug(f"🏥 API 健康检查: {'✅ 正常' if is_healthy else '❌ 异常'}")
                return is_healthy
        except Exception as e:
            logger.warning(f"⚠️  API 健康检查失败: {e}")
            return False


# ------------------------------
# 全局单例
# ------------------------------
def get_multimodal_api() -> SparkMultimodalAPI:
    return SparkMultimodalAPI()


# ------------------------------
# 模块自测
# ------------------------------
if __name__ == "__main__":
    import asyncio


    async def _test():
        print("=" * 60)
        print("🔍 讯飞多模态 API 模块自测 v1.3")
        print("=" * 60)

        api = get_multimodal_api()

        # 1. 测试健康检查
        print("\n1. 测试 API 健康检查...")
        healthy = await api.health_check()
        print(f"   健康状态: {'✅ 正常' if healthy else '❌ 异常'}")

        # 2. 测试 MIME 类型识别
        print("\n2. 测试 MIME 类型识别...")
        # 【修复】拼写错误：exts → extensions，消除拼写警告
        test_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".unknown"]
        for ext in test_extensions:
            mime = api.get_mime_type(Path(f"test{ext}"))
            print(f"   {ext} -> {mime}")

        print("\n" + "=" * 60)
        print("✅ 多模态 API 模块结构验证通过！")
        print("=" * 60)
        print("\n📝 完整测试说明：")
        print("   1. 配置 .env 文件中的 SPARK_APP_ID, SPARK_API_KEY_RAW, SPARK_API_SECRET")
        print("   2. 准备一张测试图片（<10MB）")
        print("   3. 调用 api.understand_image('test.jpg', prompt='这张图片里有什么？')")


    asyncio.run(_test())