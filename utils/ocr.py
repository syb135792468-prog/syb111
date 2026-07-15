"""
utils/ocr.py - EasyOCR 封装（图片文字识别）
- 懒加载单例，首次调用时初始化（约5-10秒加载模型）
- 同步/异步双版本
- 内存缓存避免重复识别
"""
from __future__ import annotations

import time
import asyncio
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

logger = get_logger(__name__, task_id="ocr")

# EasyOCR 单例
_ocr_engine = None

# OCR 结果缓存：url -> (text, timestamp)
_ocr_cache: dict[str, tuple[str, float]] = {}
_OCR_CACHE_TTL = 3600  # 1小时


def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        import easyocr
        _ocr_engine = easyocr.Reader(['ch_sim', 'en'], gpu=False)
        logger.info("✅ EasyOCR 引擎初始化完成（中英文）")
    return _ocr_engine


def extract_text_sync(image_path: str | Path) -> str:
    """同步提取图片中的文字，返回拼接后的文本"""
    try:
        engine = get_ocr_engine()
        result = engine.readtext(str(image_path), detail=0)
        if not result:
            return ""
        return "\n".join(result)
    except Exception as e:
        logger.warning(f"⚠️ OCR 识别失败: {e}")
        return ""


async def extract_text_from_image(image_path: str | Path) -> str:
    """异步提取图片文字（不阻塞事件循环）"""
    return await asyncio.to_thread(extract_text_sync, image_path)


def cache_ocr_result(url: str, text: str) -> None:
    """缓存 OCR 结果"""
    _ocr_cache[url] = (text, time.time())


def get_cached_ocr(url: str) -> Optional[str]:
    """获取缓存的 OCR 结果"""
    entry = _ocr_cache.get(url)
    if entry and time.time() - entry[1] < _OCR_CACHE_TTL:
        return entry[0]
    return None
