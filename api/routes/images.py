"""
api/routes/images.py - 图片上传接口
- 接收图片文件，保存到本地，运行 OCR
- 返回图片 URL + OCR 识别文本
- OCR 失败时仍返回图片 URL（降级处理）
"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException

from api.routes.auth import get_current_user
from api.schemas import BaseResponse
from models.user import User
from utils.logger import get_logger

logger = get_logger(__name__, task_id="images")

router = APIRouter(prefix="/images", tags=["图片上传"])

# 允许的 MIME 类型
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
# 最大文件大小 10MB
MAX_FILE_SIZE = 10 * 1024 * 1024

# 上传目录
UPLOAD_DIR = Path(__file__).parent.parent.parent / "static" / "uploads" / "images"


@router.post("/upload", response_model=BaseResponse)
async def upload_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> BaseResponse:
    """上传图片并进行 OCR 识别"""
    # 校验 MIME 类型
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {file.content_type}，支持 PNG/JPG/GIF/WebP")

    # 读取文件内容
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小超过 10MB 限制")

    # 生成文件路径：static/uploads/images/YYYYMMDD/uuid.ext
    today = datetime.now().strftime("%Y%m%d")
    ext = Path(file.filename or "image.png").suffix or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    day_dir = UPLOAD_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)
    file_path = day_dir / filename

    # 保存文件
    file_path.write_bytes(content)
    url = f"/static/uploads/images/{today}/{filename}"
    logger.info(f"✅ 图片已保存: {url} ({len(content)} bytes)")

    # OCR 识别（失败时降级，不阻塞上传）
    ocr_text = ""
    try:
        import asyncio
        from utils.ocr import extract_text_sync, cache_ocr_result
        ocr_text = await asyncio.to_thread(extract_text_sync, str(file_path))
        if ocr_text.strip():
            cache_ocr_result(url, ocr_text)
            logger.info(f"✅ OCR 识别完成: {len(ocr_text)} 字符")
        else:
            logger.info("ℹ️ OCR 未识别到文字")
    except Exception as e:
        logger.warning(f"⚠️ OCR 识别失败（不影响上传）: {e}")

    return BaseResponse(data={
        "url": url,
        "ocr_text": ocr_text,
        "filename": file.filename or "image.png",
    })
