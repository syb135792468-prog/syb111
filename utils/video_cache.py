"""
utils/video_cache.py - 视频生成结果缓存
避免相同知识点重复生成，提升响应速度
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any

from config.constants import VIDEO_OUTPUT_DIR

# 缓存目录
_CACHE_DIR = Path(VIDEO_OUTPUT_DIR) / "cache"
_CACHE_INDEX_FILE = _CACHE_DIR / "index.json"
_CACHE_TTL_SECONDS = 24 * 3600  # 24小时有效期
_MAX_CACHE_ENTRIES = 100  # 最大缓存条目数

# 线程安全锁
_CACHE_LOCK = threading.Lock()

# 音频缓存子目录（TTS 生成的 mp3 按段落存放，文件名 {cache_key}_{idx}.mp3）
_AUDIO_CACHE_DIR = _CACHE_DIR / "audio"


def _delete_audio_files(cache_key: str) -> int:
    """删除某 cache_key 对应的所有音频文件，返回删除数"""
    if not _AUDIO_CACHE_DIR.exists():
        return 0
    count = 0
    for f in _AUDIO_CACHE_DIR.glob(f"{cache_key}_*.mp3"):
        try:
            f.unlink()
            count += 1
        except IOError:
            pass
    return count


def _ensure_audio_cache_dir() -> None:
    """确保音频缓存目录存在"""
    _AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 内存缓存索引（启动时加载）
_CACHE_INDEX: Optional[Dict[str, Dict[str, Any]]] = None


def _ensure_cache_dir() -> None:
    """确保缓存目录存在"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_cache_index() -> Dict[str, Dict[str, Any]]:
    """加载缓存索引"""
    global _CACHE_INDEX
    if _CACHE_INDEX is not None:
        return _CACHE_INDEX

    _ensure_cache_dir()
    try:
        if _CACHE_INDEX_FILE.exists():
            with open(_CACHE_INDEX_FILE, "r", encoding="utf-8") as f:
                _CACHE_INDEX = json.load(f)
        else:
            _CACHE_INDEX = {}
    except (json.JSONDecodeError, IOError):
        _CACHE_INDEX = {}

    return _CACHE_INDEX


def _save_cache_index() -> None:
    """保存缓存索引"""
    _ensure_cache_dir()
    with open(_CACHE_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(_CACHE_INDEX or {}, f, ensure_ascii=False, indent=2)


def _compute_cache_key(topic: str, video_config: Dict[str, Any]) -> str:
    """计算缓存键（基于topic和配置）"""
    config_str = json.dumps({
        "duration": video_config.get("duration"),
        "style": video_config.get("style"),
        "voice_rate": video_config.get("voice_rate"),
        "voice_id": video_config.get("voice_id"),
    }, sort_keys=True)
    combined = f"{topic}|{config_str}"
    return hashlib.md5(combined.encode("utf-8")).hexdigest()[:12]


def _cleanup_expired_cache() -> None:
    """清理过期缓存"""
    index = _load_cache_index()
    current_time = time.time()
    expired_keys = []

    for key, meta in index.items():
        created_at = meta.get("created_at", 0)
        if current_time - created_at > _CACHE_TTL_SECONDS:
            expired_keys.append(key)
            # 删除缓存文件
            cache_file = _CACHE_DIR / f"{key}.html"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except IOError:
                    pass
            _delete_audio_files(key)

    # 更新索引
    for key in expired_keys:
        index.pop(key, None)

    # 如果超过最大条目数，删除最旧的
    if len(index) > _MAX_CACHE_ENTRIES:
        sorted_items = sorted(index.items(), key=lambda x: x[1].get("created_at", 0))
        for key, _ in sorted_items[:len(index) - _MAX_CACHE_ENTRIES]:
            index.pop(key, None)
            cache_file = _CACHE_DIR / f"{key}.html"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except IOError:
                    pass
            _delete_audio_files(key)

    if expired_keys or len(index) > _MAX_CACHE_ENTRIES:
        _save_cache_index()


def get_cached_video(topic: str, video_config: Dict[str, Any]) -> Optional[str]:
    """
    获取缓存的视频HTML

    Args:
        topic: 知识点主题
        video_config: 视频配置

    Returns:
        缓存的HTML内容，如果不存在或过期则返回None
    """
    with _CACHE_LOCK:
        index = _load_cache_index()
        cache_key = _compute_cache_key(topic, video_config)

        if cache_key not in index:
            return None

        meta = index[cache_key]
        created_at = meta.get("created_at", 0)

        # 检查是否过期
        if time.time() - created_at > _CACHE_TTL_SECONDS:
            # 删除过期缓存
            cache_file = _CACHE_DIR / f"{cache_key}.html"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                except IOError:
                    pass
            _delete_audio_files(cache_key)
            index.pop(cache_key, None)
            _save_cache_index()
            return None

        # 读取缓存文件
        cache_file = _CACHE_DIR / f"{cache_key}.html"
        try:
            return cache_file.read_text(encoding="utf-8")
        except IOError:
            return None


def save_cached_video(topic: str, video_config: Dict[str, Any], html_content: str) -> None:
    """
    保存视频HTML到缓存

    Args:
        topic: 知识点主题
        video_config: 视频配置
        html_content: HTML内容
    """
    with _CACHE_LOCK:
        _cleanup_expired_cache()

        index = _load_cache_index()
        cache_key = _compute_cache_key(topic, video_config)

        # 保存缓存文件
        cache_file = _CACHE_DIR / f"{cache_key}.html"
        _ensure_cache_dir()
        cache_file.write_text(html_content, encoding="utf-8")

        # 更新索引
        index[cache_key] = {
            "topic": topic,
            "created_at": time.time(),
            "voice_id": video_config.get("voice_id"),
            "config": {
                "duration": video_config.get("duration"),
                "style": video_config.get("style"),
            }
        }
        _save_cache_index()


def get_cache_stats() -> Dict[str, Any]:
    """获取缓存统计信息"""
    with _CACHE_LOCK:
        index = _load_cache_index()
        total_entries = len(index)
        total_size = 0

        for key in index:
            cache_file = _CACHE_DIR / f"{key}.html"
            if cache_file.exists():
                total_size += cache_file.stat().st_size

        return {
            "total_entries": total_entries,
            "total_size_kb": round(total_size / 1024, 2),
            "max_entries": _MAX_CACHE_ENTRIES,
            "ttl_hours": _CACHE_TTL_SECONDS / 3600,
        }


def clear_cache() -> int:
    """清空所有缓存，返回删除的条目数"""
    with _CACHE_LOCK:
        index = _load_cache_index()
        deleted_count = 0

        for key in index:
            cache_file = _CACHE_DIR / f"{key}.html"
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    deleted_count += 1
                except IOError:
                    pass
            _delete_audio_files(key)

        _CACHE_INDEX = {}
        _save_cache_index()
        return deleted_count