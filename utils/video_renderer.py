"""
utils/video_renderer.py - HTML 教学动画 → 真视频渲染器
使用 Playwright 录制浏览器中的 GSAP 动画为 .webm 视频

优化：
- 支持语音保留选项（默认禁用，因为无头浏览器语音不稳定）
- 支持进度回调
- 优化超时配置
"""
from __future__ import annotations

import asyncio
import os
import re
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Callable

from config.constants import (
    VIDEO_RENDER_FPS,
    VIDEO_RENDER_WIDTH,
    VIDEO_RENDER_HEIGHT,
    VIDEO_RENDER_TIMEOUT_SEC,
    VIDEO_OUTPUT_DIR,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="video_renderer")

# 默认超时时间（优化为120秒，而非300秒）
DEFAULT_RENDER_TIMEOUT_SEC = 120

# 自动播放注入 JS：隐藏交互控件，触发 startAnimation()
_AUTOPLAY_JS = """
setTimeout(() => {
  // 隐藏开始界面
  var ss = document.getElementById('startScreen');
  if (ss) ss.style.display = 'none';
  // 显示播放界面
  var ps = document.getElementById('playerScreen');
  if (ps) ps.style.display = 'block';
  // 隐藏控制栏（视频不需要）
  var ctrl = document.getElementById('controls');
  if (ctrl) ctrl.style.display = 'none';
  // 触发动画
  if (typeof startAnimation === 'function') {
    startAnimation();
  }
}, 500);
"""

# 停止语音合成（无头浏览器下 speechSynthesis 可能不稳定）
_DISABLE_SPEECH_JS = """
window.speechSynthesis = { cancel: function(){}, speak: function(){}, pause: function(){}, resume: function(){} };
"""

# 保留语音的JS（用于有声音模式）
_KEEP_SPEECH_JS = """
// 语音保留模式：确保语音正常工作
if ('speechSynthesis' in window) {
  // 预热语音引擎
  var warmup = new SpeechSynthesisUtterance('');
  warmup.lang = 'zh-CN';
  window.speechSynthesis.speak(warmup);
  window.speechSynthesis.cancel();
}
"""


def _inject_autoplay(html_content: str, disable_speech: bool = True) -> str:
    """在 HTML 的 </body> 前注入自动播放脚本"""
    speech_js = _DISABLE_SPEECH_JS if disable_speech else _KEEP_SPEECH_JS
    script = f"<script>\n{speech_js}\n{_AUTOPLAY_JS}\n</script>"
    match = re.search(r"</body\s*>", html_content, re.IGNORECASE)
    if match:
        pos = match.start()
        return html_content[:pos] + "\n" + script + "\n" + html_content[pos:]
    return html_content + "\n" + script


def _extract_duration(html_content: str, default: int = 120) -> int:
    """从 HTML 中提取动画时长（秒）"""
    # 尝试从 meta 中提取
    m = re.search(r'"duration"\s*:\s*(\d+)', html_content)
    if m:
        return int(m.group(1))
    # 尝试从 data-duration 属性提取
    m = re.search(r'data-duration="(\d+)"', html_content)
    if m:
        return int(m.group(1))
    return default


async def render_html_to_video(
    html_content: str,
    output_path: Optional[str] = None,
    duration_sec: Optional[int] = None,
    fps: int = VIDEO_RENDER_FPS,
    width: int = VIDEO_RENDER_WIDTH,
    height: int = VIDEO_RENDER_HEIGHT,
    timeout_sec: int = DEFAULT_RENDER_TIMEOUT_SEC,
    disable_speech: bool = True,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> str:
    """
    将 HTML 教学动画录制为 .webm 视频文件

    Args:
        html_content: 完整的 HTML 字符串
        output_path: 输出文件路径（默认自动命名）
        duration_sec: 录制时长（秒），默认从 HTML 提取
        fps: 帧率
        width: 视频宽度
        height: 视频高度
        timeout_sec: 超时时间（默认120秒，优化后）
        disable_speech: 是否禁用语音（默认True，无头浏览器语音不稳定）
        progress_callback: 进度回调函数，参数为进度百分比(0-100)

    Returns:
        输出文件的绝对路径

    Raises:
        RuntimeError: 录制失败时
        asyncio.TimeoutError: 超时时
    """
    from playwright.async_api import async_playwright

    # 确保输出目录存在
    os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

    if output_path is None:
        output_path = os.path.join(VIDEO_OUTPUT_DIR, f"animation_{uuid.uuid4().hex[:8]}.webm")

    output_path = os.path.abspath(output_path)

    if duration_sec is None:
        duration_sec = _extract_duration(html_content)

    # 录制时长 = 动画时长 + 2s 缓冲
    record_ms = (duration_sec + 2) * 1000
    # 超时保护（使用优化后的默认值）
    max_timeout_ms = min(timeout_sec, DEFAULT_RENDER_TIMEOUT_SEC) * 1000
    record_ms = min(record_ms, max_timeout_ms)

    # 注入自动播放（根据语音设置选择）
    modified_html = _inject_autoplay(html_content, disable_speech=disable_speech)

    # 写入临时文件
    tmp_dir = tempfile.mkdtemp(prefix="video_render_")
    tmp_html = os.path.join(tmp_dir, "animation.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(modified_html)

    tmp_video_dir = os.path.join(tmp_dir, "videos")
    os.makedirs(tmp_video_dir, exist_ok=True)

    logger.info(f"开始录制视频: {duration_sec}s, {width}x{height}@{fps}fps → {output_path}")
    logger.info(f"语音模式: {'禁用' if disable_speech else '保留'}")

    # 进度报告
    if progress_callback:
        progress_callback(0.0)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": width, "height": height},
                record_video_dir=tmp_video_dir,
                record_video_size={"width": width, "height": height},
            )
            page = await context.new_page()

            # 加载 HTML（使用 file:// 协议）
            file_url = Path(tmp_html).as_uri()
            await page.goto(file_url, wait_until="domcontentloaded", timeout=30000)

            if progress_callback:
                progress_callback(10.0)

            # 等待 GSAP 加载
            try:
                await page.wait_for_function("typeof gsap !== 'undefined'", timeout=10000)
            except Exception:
                logger.warning("GSAP 未检测到，继续录制")

            if progress_callback:
                progress_callback(20.0)

            # 分段等待，报告进度
            total_wait_ms = record_ms
            wait_interval_ms = 1000  # 每秒报告一次进度
            elapsed_ms = 0
            while elapsed_ms < total_wait_ms:
                wait_time = min(wait_interval_ms, total_wait_ms - elapsed_ms)
                await page.wait_for_timeout(wait_time)
                elapsed_ms += wait_time
                if progress_callback:
                    progress = 20.0 + (elapsed_ms / total_wait_ms) * 70.0
                    progress_callback(progress)

            # 获取视频路径
            video = page.video
            if video:
                await video.path()

            await context.close()
            await browser.close()

        if progress_callback:
            progress_callback(95.0)

        # 找到生成的 .webm 文件
        video_files = sorted(
            Path(tmp_video_dir).glob("*.webm"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if not video_files:
            raise RuntimeError("Playwright 未生成视频文件")

        src_video = str(video_files[0])

        # 移动到目标路径
        import shutil
        shutil.move(src_video, output_path)
        logger.info(f"视频录制完成: {output_path} ({os.path.getsize(output_path) / 1024:.1f} KB)")

        if progress_callback:
            progress_callback(100.0)

        return output_path

    except asyncio.TimeoutError:
        logger.error(f"视频录制超时: {timeout_sec}秒")
        raise RuntimeError(f"视频录制超时（{timeout_sec}秒），请检查动画时长配置")
    except Exception as e:
        logger.error(f"视频录制失败: {type(e).__name__}: {e}", exc_info=True)
        raise
    finally:
        # 清理临时文件
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def check_ffmpeg_available() -> bool:
    """检查 FFmpeg 是否可用"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return proc.returncode == 0
    except FileNotFoundError:
        return False


async def convert_webm_to_mp4(webm_path: str, mp4_path: Optional[str] = None) -> str:
    """
    将 .webm 转换为 .mp4（需要 FFmpeg）

    Args:
        webm_path: 输入 .webm 文件路径
        mp4_path: 输出 .mp4 文件路径（默认同名替换扩展名）

    Returns:
        输出 .mp4 文件路径

    Raises:
        RuntimeError: FFmpeg 不可用时
    """
    if not await check_ffmpeg_available():
        raise RuntimeError("FFmpeg 未安装，无法转换为 MP4。请安装 FFmpeg 并加入 PATH。")

    if mp4_path is None:
        mp4_path = webm_path.rsplit(".", 1)[0] + ".mp4"

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", webm_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        mp4_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg 转换失败: {stderr.decode()[:500]}")

    logger.info(f"MP4 转换完成: {mp4_path} ({os.path.getsize(mp4_path) / 1024:.1f} KB)")
    return mp4_path
