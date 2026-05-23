"""
config/constants.py - 全局常量定义（魔法数字消除）
所有硬编码的魔法数字统一在此管理，其他模块通过导入使用。
"""

# ============================================================
# 1. HTTP 状态码
# ============================================================
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500
HTTP_SERVICE_UNAVAILABLE = 503
HTTP_GATEWAY_TIMEOUT = 504

# ============================================================
# 2. 服务器/API 默认值
# ============================================================
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8000
SLOW_REQUEST_THRESHOLD_SEC = 1.0
CORS_MAX_AGE = 86400

# ============================================================
# 3. 聊天/RAG 常量
# ============================================================
DEFAULT_RAG_TOP_K = 3
DEFAULT_DISTANCE_THRESHOLD = 1.0
DEFAULT_RECURSION_LIMIT = 50
TYPING_CHUNK_SIZE = 2
TYPING_DELAY_MS = 20
SYNC_CHAT_TIMEOUT_SEC = 30

# ============================================================
# 4. LLM 默认值
# ============================================================
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 4096
LLM_MAX_RETRIES = 3
LLM_BACKOFF_BASE = 2
EMBEDDING_TIMEOUT_SEC = 30
EMBEDDING_MAX_WORKERS = 5
EMBEDDING_MAX_TEXT_LENGTH = 256

# ============================================================
# 5. 资源/API 限制
# ============================================================
DEFAULT_RESOURCE_LIMIT = 20
MAX_RESOURCE_LIMIT = 100
RESOURCE_GENERATE_TIMEOUT_SEC = 60
RESOURCE_PROGRESS_COMPLETE = 100

# ============================================================
# 6. 行为追踪器
# ============================================================
DEFAULT_BEHAVIOR_DAYS = 7
DEFAULT_BEHAVIOR_LIMIT = 100
STATS_AGGREGATION_DAYS = 30
STATS_AGGREGATION_LIMIT = 2000
SECONDS_PER_HOUR = 3600.0

# ============================================================
# 7. 日志配置
# ============================================================
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 14

# ============================================================
# 8. 评估 Agent 阈值
# ============================================================
EVAL_DEFAULT_DAYS = 30
EVAL_TEMPERATURE = 0.3
EVAL_MAX_TOKENS = 500
EVAL_QUIZ_MIN_COUNT = 2
EVAL_STUDY_HOURS_THRESHOLD = 3
EVAL_RESOURCE_VIEWS_THRESHOLD = 5

# ============================================================
# 9. 学习路径 Agent
# ============================================================
DEFAULT_ESTIMATED_TIME_MIN = 10
EXTENDED_ESTIMATED_TIME_MIN = 15
MAX_LEARNING_PATH_STEPS = 8

# ============================================================
# 10. 辅导 Agent
# ============================================================
TUTOR_HISTORY_WINDOW = 4
TUTOR_INPUT_TRUNCATE_LENGTH = 50

# ============================================================
# 11. 各 Agent RAG top_k
# ============================================================
QUIZ_RAG_TOP_K = 2
CODE_RAG_TOP_K = 2
MINDMAP_RAG_TOP_K = 3

# ============================================================
# 12. 视频 Agent
# ============================================================
VIDEO_MAX_TOKENS = 3000

# ============================================================
# 13. Base Agent 回退默认值
# ============================================================
BASE_AGENT_FALLBACK_TEMPERATURE = 0.7
BASE_AGENT_FALLBACK_MAX_TOKENS = 4096
BASE_AGENT_DEFAULT_TOP_K = 3
BASE_AGENT_DISTANCE_THRESHOLD = 1.0

# ============================================================
# 14. RAG 查询倍数（n_results = top_k * multiplier）
# ============================================================
RAG_QUERY_MULTIPLIER = 2
