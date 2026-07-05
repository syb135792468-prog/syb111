"""
utils/logger.py

统一日志工具（软件杯A3赛题专属优化版 v2.1 多进程安全版）
- ✅ 全局配置统一：100%从 config.settings 读取，通过实例访问属性
- ✅ 语法错误修复：修正导入语句，解决未解析引用问题
- ✅ 同时输出到控制台和日志文件（按天分割，方便演示复盘）
- ✅ 赛题专属：大模型调用专用 logger（追踪讯飞/DeepSeek切换、重试、降级）
- ✅ 赛题专属：资源生成专用 logger（追踪生成进度）
- ✅ 支持通过 LoggerAdapter 注入用户ID/任务ID上下文，追踪单个用户全流程
- ✅ 提供 get_logger(name) 函数，各模块通过名称获取专属 logger
- ✅ 🔴 新增：多进程安全，彻底解决Windows下"文件被占用"错误
"""

import logging
import sys
from concurrent_log_handler import ConcurrentRotatingFileHandler
from pathlib import Path
from typing import Optional, Union

# 🔴 修复1：正确的导入语句（只导入 settings 实例）
try:
    from config.settings import settings
    from config.constants import LOG_MAX_BYTES, LOG_BACKUP_COUNT
    # 从 settings 实例读取配置
    LOG_LEVEL = settings.LOG_LEVEL
    ENVIRONMENT = settings.ENVIRONMENT
    LOG_DIR = Path(settings.LOG_DIR) if hasattr(settings, 'LOG_DIR') else None
except ImportError:
    # 如果 settings 还没写好，使用默认值，确保本模块能独立运行
    LOG_LEVEL = "INFO"
    ENVIRONMENT = "development"
    LOG_DIR = Path(__file__).parent.parent / "logs"
    LOG_DIR.mkdir(exist_ok=True)
    LOG_MAX_BYTES = 10 * 1024 * 1024
    LOG_BACKUP_COUNT = 14

# 🔴 修复2：确保 LOG_DIR 存在
if LOG_DIR is None:
    LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


# ============================================================
# 日志格式定义（赛题专属优化）
# ============================================================

# 控制台格式：简洁，带颜色提示（开发时用）
CONSOLE_FORMAT = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# 文件格式：支持通过 extra 字段注入 user_id / task_id
FILE_FORMAT_STR = (
    "%(asctime)s | %(levelname)-8s | %(name)-20s | "
    "%(filename)s:%(lineno)d"
    "%(user_id)s%(task_id)s | %(message)s"
)

class ContextFormatter(logging.Formatter):
    """支持动态上下文的日志格式化器"""
    def format(self, record):
        # 添加 user_id 和 task_id 字段，如果不存在则设为空字符串
        record.user_id = f" | user:{record.user_id}" if hasattr(record, 'user_id') else ""
        record.task_id = f" | task:{record.task_id}" if hasattr(record, 'task_id') else ""
        return super().format(record)

FILE_FORMAT = ContextFormatter(
    fmt=FILE_FORMAT_STR,
    datefmt="%Y-%m-%d %H:%M:%S"
)


# ============================================================
# 配置根日志记录器
# ============================================================

def setup_root_logger():
    """配置根日志记录器，添加控制台和文件处理器"""
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))

    # 避免重复添加处理器
    if root_logger.handlers:
        return

    # 1. 控制台处理器（Windows GBK 兼容：UTF-8 输出 + 降级替换）
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    # 用 TextIOWrapper 包装 stdout，确保 emoji 等非 GBK 字符不会导致 [Errno 22]
    import io
    safe_stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True
    ) if hasattr(sys.stdout, 'buffer') else sys.stdout
    console_handler = logging.StreamHandler(safe_stdout)
    console_handler.setLevel(logging.DEBUG if ENVIRONMENT == "development" else logging.INFO)
    console_handler.setFormatter(CONSOLE_FORMAT)
    root_logger.addHandler(console_handler)


    # 2. 文件处理器（多进程安全 + 按大小分割）
    try:
        log_file = LOG_DIR / "app.log"
        file_handler = ConcurrentRotatingFileHandler(
            filename=str(log_file),
            maxBytes=LOG_MAX_BYTES,  # 每个日志文件10MB
            backupCount=LOG_BACKUP_COUNT,  # 保留14个备份文件
            encoding="utf-8",
            use_gzip=False,
            lock_file_directory=str(LOG_DIR)
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(FILE_FORMAT)
        root_logger.addHandler(file_handler)
    except Exception as e:
        root_logger.warning(f"无法创建文件日志处理器: {e}")
# ============================================================
# 对外接口
# ============================================================

def get_logger(
    name: str,
    user_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> Union[logging.Logger, logging.LoggerAdapter]:
    """
    获取指定名称的 logger 实例，可选注入用户/任务上下文。

    用法:
        from utils.logger import get_logger
        logger = get_logger(__name__, user_id="123", task_id="gen_doc_001")
        logger.info("开始生成文档")
    """
    if not logging.getLogger().handlers:
        setup_root_logger()

    logger = logging.getLogger(name)
    if user_id or task_id:
        # 使用 LoggerAdapter 注入额外字段
        extra = {}
        if user_id:
            extra['user_id'] = user_id
        if task_id:
            extra['task_id'] = task_id
        return logging.LoggerAdapter(logger, extra)
    return logger


# ============================================================
# 【软件杯A3赛题专属】专用 Logger
# ============================================================

def get_llm_logger(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> Union[logging.Logger, logging.LoggerAdapter]:
    """大模型调用专用 logger"""
    return get_logger("LLM_CALL", user_id=user_id, task_id=task_id)


def get_resource_logger(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> Union[logging.Logger, logging.LoggerAdapter]:
    """资源生成专用 logger"""
    return get_logger("RESOURCE_GEN", user_id=user_id, task_id=task_id)


def get_rag_logger(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> Union[logging.Logger, logging.LoggerAdapter]:
    """RAG 检索专用 logger"""
    return get_logger("RAG_RETRIEVE", user_id=user_id, task_id=task_id)


# ============================================================
# 可选：便捷日志记录函数（用于特殊事件）
# ============================================================

def log_llm_switch(
    from_model: str,
    to_model: str,
    reason: str,
    user_id: Optional[str] = None
) -> None:
    """记录模型降级/切换事件"""
    llm_logger = get_llm_logger(user_id=user_id)
    llm_logger.warning(f"[模型切换] {from_model} -> {to_model}，原因: {reason}")


def log_resource_progress(
    resource_type: str,
    progress: int,
    user_id: Optional[str] = None,
    task_id: Optional[str] = None
) -> None:
    """记录资源生成进度"""
    res_logger = get_resource_logger(user_id=user_id, task_id=task_id)
    res_logger.info(f"[{resource_type}] 生成进度: {progress}%")


# ============================================================
# 快捷全局函数
# ============================================================

def info(msg: str, *args, **kwargs):
    get_logger("global").info(msg, *args, **kwargs)

def debug(msg: str, *args, **kwargs):
    get_logger("global").debug(msg, *args, **kwargs)

def warning(msg: str, *args, **kwargs):
    get_logger("global").warning(msg, *args, **kwargs)

def error(msg: str, *args, **kwargs):
    get_logger("global").error(msg, *args, **kwargs)

def exception(msg: str, *args, **kwargs):
    get_logger("global").exception(msg, *args, **kwargs)


# ============================================================
# 自测
# ============================================================
if __name__ == "__main__":
    print("===== 测试日志模块（软件杯A3专属改进版 v2.1 多进程安全版） =====")

    # 1. 通用测试
    test_logger = get_logger("test")
    test_logger.info("普通日志")

    # 2. 带上下文测试
    ctx_logger = get_logger("test_ctx", user_id="user_001", task_id="task_abc")
    ctx_logger.info("这条日志包含用户和任务ID")

    # 3. 赛题专属测试
    llm_test_logger = get_llm_logger(user_id="user_001")
    llm_test_logger.info("[讯飞星火] 调用成功")
    log_llm_switch("讯飞星火", "DeepSeek", "超时降级", user_id="user_001")

    res_test_logger = get_resource_logger(user_id="user_001", task_id="doc_gen_001")
    log_resource_progress("文档生成", 30, user_id="user_001", task_id="doc_gen_001")
    log_resource_progress("文档生成", 100, user_id="user_001", task_id="doc_gen_001")

    rag_test_logger = get_rag_logger()
    rag_test_logger.debug("RAG 检索测试")

    print(f"\n✅ 测试完成，日志文件: {LOG_DIR / 'app.log'}")