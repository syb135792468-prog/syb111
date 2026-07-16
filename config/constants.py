"""
config/constants.py - 全局常量定义（魔法数字消除）
所有硬编码的魔法数字统一在此管理，其他模块通过导入使用。
"""

# ============================================================
# 1. HTTP 状态码
# ============================================================
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_INTERNAL_SERVER_ERROR = 500
HTTP_SERVER_ERROR = HTTP_INTERNAL_SERVER_ERROR  # 向后兼容别名
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
CHAT_HISTORY_LOAD_LIMIT = 20
CONVERSATION_TITLE_MAX_LENGTH = 20
DEFAULT_RAG_TOP_K = 3
DEFAULT_DISTANCE_THRESHOLD = 1.0
DEFAULT_RECURSION_LIMIT = 50
TYPING_CHUNK_SIZE = 2
TYPING_DELAY_MS = 5
SYNC_CHAT_TIMEOUT_SEC = 60

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
RESOURCE_GENERATE_TIMEOUT_SEC = 300
RESOURCE_PROGRESS_COMPLETE = 100

# ============================================================
# 5b. 练习题并行生成
# ============================================================
QUIZ_PARALLEL_CONCURRENCY = 5
QUIZ_DEDUP_MAX_ROUNDS = 3

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
EVAL_REPORT_MAX_WORDS = 300
EVAL_DEFAULT_DAYS = 30
EVAL_TEMPERATURE = 0.3
EVAL_MAX_TOKENS = 500
EVAL_QUIZ_MIN_COUNT = 2
EVAL_STUDY_HOURS_THRESHOLD = 3
EVAL_RESOURCE_VIEWS_THRESHOLD = 5

# 批量更新阈值（每天凌晨执行）
BATCH_MOTIVATION_STUDY_DAYS_HIGH = 5
BATCH_MOTIVATION_STUDY_DAYS_MEDIUM = 2
BATCH_MOTIVATION_COMPLETION_RATE_HIGH = 0.8
BATCH_MOTIVATION_COMPLETION_RATE_MEDIUM = 0.5
BATCH_WEAK_POINT_QUESTION_COUNT = 3
MILESTONE_COMPLETED_RESOURCES = 3

# ============================================================
# 9. 学习路径 Agent
# ============================================================
DEFAULT_START_KNOWLEDGE_POINT = "变量与数据类型"
DEFAULT_TOPIC = "Python基础"
DEFAULT_ESTIMATED_TIME_MIN = 10
EXTENDED_ESTIMATED_TIME_MIN = 15
MAX_LEARNING_PATH_STEPS = 8

# ============================================================
# 9b. 学习路径动态更新（软件杯A3赛题核心功能）
# ============================================================
LEARNING_PATH_STATUS_ACTIVE = "active"
LEARNING_PATH_STATUS_PAUSED = "paused"
LEARNING_PATH_STATUS_COMPLETED = "completed"
LEARNING_PATH_STATUS_ARCHIVED = "archived"

LP_NODE_STATUS_NOT_STARTED = "not_started"
LP_NODE_STATUS_IN_PROGRESS = "in_progress"
LP_NODE_STATUS_COMPLETED = "completed"
LP_NODE_STATUS_NEEDS_REVIEW = "needs_review"
LP_NODE_STATUS_SKIPPED = "skipped"

LP_RESOURCE_STATUS_PENDING = "pending"
LP_RESOURCE_STATUS_GENERATING = "generating"
LP_RESOURCE_STATUS_COMPLETED = "completed"
LP_RESOURCE_STATUS_FAILED = "failed"

LP_MASTERY_THRESHOLD = 0.7
LP_HIGH_ERROR_RATE_THRESHOLD = 0.3
LP_INACTIVE_DAYS_THRESHOLD = 3
LP_MAX_NODES_PER_PATH = 15
LP_DEFAULT_RESOURCE_TYPES = ["doc", "quiz", "mindmap"]

# ============================================================
# 10. 辅导 Agent
# ============================================================
TUTOR_HISTORY_WINDOW = 10
TUTOR_INPUT_TRUNCATE_LENGTH = 50

# ============================================================
# 11. 各 Agent RAG top_k
# ============================================================
QUIZ_RAG_TOP_K = 2
CODE_RAG_TOP_K = 2
MINDMAP_RAG_TOP_K = 5

# ============================================================
# 12. 视频 Agent
# ============================================================
VIDEO_MAX_TOKENS = 24000
VIDEO_MIN_HTML_LINES = 400
VIDEO_MAX_RETRIES = 1
VIDEO_DEFAULT_VOICE_RATE = 1.15
VIDEO_DEFAULT_VOICE_LANG = "zh-CN"
VIDEO_DEFAULT_STYLE = "tutorial"
VIDEO_DEFAULT_DURATION = 120
VIDEO_MIN_CODE_LINES = 0       # 最少代码行数（LLM命名不固定，跳过此检查）
VIDEO_MIN_SPEAK_CALLS = 5      # 最少讲解段数（speak() 调用次数）
VIDEO_GSAP_CDN_URL = "https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"

# ============================================================
# 12b. 视频渲染（HTML → WebM/MP4）
# ============================================================
VIDEO_RENDER_FPS = 15
VIDEO_RENDER_WIDTH = 1280
VIDEO_RENDER_HEIGHT = 720
VIDEO_RENDER_TIMEOUT_SEC = 300
VIDEO_OUTPUT_DIR = "static/videos"

# ============================================================
# 12c. 视频 TTS 配音（火山引擎语音合成）
# ============================================================
VIDEO_TTS_API_ENDPOINT = "https://openspeech.bytedance.com/api/v1/tts"
VIDEO_TTS_TIMEOUT_SEC = 30
VIDEO_TTS_MAX_RETRIES = 2
VIDEO_TTS_MAX_CONCURRENCY = 4
VIDEO_TTS_AUDIO_SUBDIR = "audio"
VIDEO_TTS_SAMPLE_RATE = 24000
VIDEO_TTS_AUDIO_ENCODING = "mp3"
VIDEO_TTS_MAX_TEXT_LENGTH = 500

# ============================================================
# 12d. 视频 TTS 配音（科大讯飞超拟人合成，WebSocket，主用）
# ============================================================
VIDEO_TTS_XFYUN_TIMEOUT_SEC = 30

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

# ============================================================
# 15. 练习题判分
# ============================================================
QUIZ_CORRECT_SCORE = 10
MAX_ANSWER_STORE_LENGTH = 2000

# ============================================================
# 16. 代码执行沙箱
# ============================================================
CODE_EXEC_DEFAULT_TIMEOUT = 5
CODE_EXEC_MIN_TIMEOUT = 1
CODE_EXEC_MAX_TIMEOUT = 15
CODE_EXEC_MAX_STDOUT_LENGTH = 10000
CODE_EXEC_MAX_STDERR_LENGTH = 5000
CODE_EXEC_MAX_CONCURRENT = 8          # 最大并发执行进程数
CODE_EXEC_MAX_MEMORY_MB = 256         # 子进程最大内存（MB）
CODE_EXEC_MAX_CPU_SEC = 10            # 子进程最大 CPU 时间（秒）
CODE_EXEC_RATE_LIMIT_PER_MIN = 10     # 每用户每分钟最大执行次数
CODE_EXEC_RATE_LIMIT_WINDOW_SEC = 60  # 限流窗口（秒）

# ============================================================
# 17. LLM 判分
# ============================================================
LLM_GRADING_TIMEOUT_SEC = 30

# ============================================================
# 18. Profile 生成
# ============================================================
PROFILE_GENERATE_TIMEOUT_SEC = 30
PROFILE_LLM_COOLDOWN_SEC = 10
PROFILE_LLM_CONFIDENCE_THRESHOLD = 0.8

# ============================================================
# 19. 自适应难度推荐
# ============================================================
DIFFICULTY_RECOMMEND_SAMPLE_SIZE = 10
DIFFICULTY_HARD_THRESHOLD = 0.8
DIFFICULTY_MEDIUM_THRESHOLD = 0.5

# ============================================================
# 20. 题目生成
# ============================================================
MAX_QUIZ_QUESTION_COUNT = 20
QUIZ_GEN_RETRY_COUNT = 3
DEDUP_CONTENT_TRUNCATE_LENGTH = 100
QUESTION_HASH_TRUNCATE_LENGTH = 12

# ============================================================
# 21. LLM 熔断器
# ============================================================
LLM_CIRCUIT_BREAKER_THRESHOLD = 3
LLM_CIRCUIT_BREAKER_COOLDOWN_SEC = 60

# ============================================================
# 22. 错题本
# ============================================================
ERROR_BOOK_DEFAULT_LIMIT = 50
ERROR_BOOK_MAX_LIMIT = 200

# ============================================================
# 22b. 间隔重复（艾宾浩斯）
# ============================================================
SPACED_REP_DEFAULT_EF = 2.5
SPACED_REP_MIN_EF = 1.3
SPACED_REP_INITIAL_INTERVAL_DAYS = 1.0
SPACED_REP_MASTERED_THRESHOLD = 5

# ============================================================
# 23. 知识点匹配
# ============================================================
KP_PARTIAL_MATCH_MIN_LENGTH = 2
KP_KEYWORD_MIN_LENGTH = 2

# ============================================================
# 24. 难度/题型常量
# ============================================================
DIFFICULTY_EASY = "easy"
DIFFICULTY_MEDIUM = "medium"
DIFFICULTY_HARD = "hard"
QUIZ_TYPE_CHOICE = "choice"
QUIZ_TYPE_FILL = "fill"
QUIZ_TYPE_CODE = "code"

# ============================================================
# 25. 默认 Profile 兜底值
# ============================================================
DEFAULT_KNOWLEDGE_LEVEL = "beginner"
DEFAULT_LEARNING_GOAL = "Python 基础"
DEFAULT_LEARNING_STYLE = "hands-on"

# ============================================================
# 26. 通用状态/步骤
# ============================================================
RESOURCE_STATUS_COMPLETED = "completed"
DEFAULT_CURRENT_STEP = "start"
DEFAULT_INTENT = "ask_question"
DEFAULT_CONVERSATION_TITLE = "新对话"

# ============================================================
# 27. API Schema 限制
# ============================================================
USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 4
PASSWORD_MAX_LENGTH = 100
MESSAGE_MAX_LENGTH = 2000
TITLE_MAX_LENGTH = 200
DIFFICULTY_MIN = 1
DIFFICULTY_MAX = 5

# ============================================================
# 28. 截断长度
# ============================================================
LOG_TRUNCATE_LENGTH = 100
QUERY_TRUNCATE_LENGTH = 50
MSG_PREVIEW_TRUNCATE_LENGTH = 50
RESOURCE_ID_TRUNCATE_LENGTH = 6
CHAT_REPLY_TRUNCATE_LENGTH = 200
QUIZ_OUTPUT_TRUNCATE_LENGTH = 200
QUIZ_ERROR_TRUNCATE_LENGTH = 100
QUIZ_LLM_FEEDBACK_MAX_CHARS = 50

# ============================================================
# 29. 练习题判分阈值
# ============================================================
QUIZ_FILL_CORRECT_THRESHOLD = 0.8
QUIZ_PARTIAL_MATCH_MIN_RATIO = 0.5
QUIZ_PARTIAL_MATCH_MAX_RATIO = 2.0
QUIZ_PARTIAL_MATCH_SCORE = 0.5

# ============================================================
# 30. 系统参数
# ============================================================
SERVER_WAIT_TIMEOUT_SEC = 30.0
SOCKET_TIMEOUT = 1
RETRY_INTERVAL_SEC = 0.3
MAX_IMAGE_SIZE_MB = 10
MULTIMODAL_MAX_RETRIES = 3
MULTIMODAL_TIMEOUT_SEC = 60
IMAGE_UNDERSTANDING_MAX_TOKENS = 500
SECURITY_MAX_INPUT_LENGTH = 2000
PROGRESS_CLEANUP_MAX_AGE_SEC = 3600
EMBEDDING_MAX_RETRIES = 3
MINDMAP_TOPIC_MAX_LENGTH = 10
MINDMAP_DEFINITION_MIN_LENGTH = 15
MINDMAP_EXPAND_RAG_TOP_K = 2
MINDMAP_EXPAND_MAX_CHILDREN = 3
MINDMAP_EXPAND_TIMEOUT_SEC = 120
MINDMAP_SQL_DETECT_PATTERN = "CREATE TABLE"
MINDMAP_ER_RAG_TOP_K = 3
MINDMAP_ER_GENERATE_TIMEOUT_SEC = 120
PATH_FALLBACK_KP_COUNT = 5

# ============================================================
# 31. fast_build.py 知识库构建
# ============================================================
FAST_BUILD_CHUNK_SIZE = 800
FAST_BUILD_API_INTERVAL_SEC = 0.6

# ============================================================
# 32. RAG 相似度计算
# ============================================================
RAG_DISTANCE_PRECISION = 4
RAG_SIMILARITY_DIVISOR = 2

# ============================================================
# 33. SQLite 性能参数
# ============================================================
SQLITE_CACHE_SIZE = -64000

# ============================================================
# 34. 资源规划器参数
# ============================================================
RESOURCE_PLANNER_BEGINNER_MULTIPLIER = 1.5
RESOURCE_PLANNER_ADVANCED_MULTIPLIER = 0.8
RESOURCE_PLANNER_MIN_TIME_MINUTES = 5
RESOURCE_PLANNER_DEFAULT_RESOURCE_TIME = 20
RESOURCE_PLANNER_DEFAULT_STUDY_TIME_PER_DAY = 60
RESOURCE_PLANNER_MAX_RESOURCES_PER_PLAN = 20

# ============================================================
# 35. 预初始化与健康检查列表
# ============================================================
PREINIT_AGENT_TYPES = ["quiz", "code", "mindmap", "doc", "video", "slides"]
HEALTH_CHECK_SERVICES = ["chat", "profile", "resource", "database"]
DEV_RELOAD_DIRS = ["api", "models", "agents", "utils"]

# ============================================================
# 36. 实时学习状态阈值
# ============================================================
LEARNING_STATE_CONFUSED_THRESHOLD = 2
LEARNING_STATE_STRUGGLING_THRESHOLD = 3
LEARNING_STATE_MASTERING_THRESHOLD = 3
LEARNING_STATE_FAST_ANSWER_MS = 3000
LEARNING_STATE_HISTORY_WINDOW = 5
LEARNING_STATE_SESSION_EXPIRY_HOURS = 1

# ============================================================
# 37. LLM 置信度校准
# ============================================================
CONFIDENCE_SCALE = 0.8
CONFIDENCE_OFFSET = 0.1
CONFIDENCE_FALLBACK_THRESHOLD = 0.6

# ============================================================
# 38b. A/B 测试
# ============================================================
EXPERIMENT_TEACHING_MODE = "teaching_mode"
EXPERIMENT_DIFFICULTY = "difficulty_adaptation"
EXPERIMENT_REALTIME = "realtime_adaptation"
EXPERIMENT_STATUS_DRAFT = "draft"
EXPERIMENT_STATUS_ACTIVE = "active"
EXPERIMENT_STATUS_COMPLETED = "completed"
EXPERIMENT_MIN_SAMPLE_SIZE = 5
EXPERIMENT_SIGNIFICANCE_LEVEL = 0.05

# ============================================================
# 38. 🔴一级硬编码：业务逻辑关键词常量
# ============================================================
QUIZ_TYPE_MULTI = "multi"
RESOURCE_TYPE_QUIZ = "quiz"
RESOURCE_TYPE_MINDMAP = "mindmap"
RESOURCE_TYPE_DAILY_CHALLENGE = "daily_challenge"
RESOURCE_TYPE_DAILY_EXTRA = "daily_extra"
RESOURCE_TYPE_SLIDES = "slides"
RESOURCE_TYPE_TUTOR_VIDEO = "tutor_video"
DIFFICULTY_AUTO = "auto"
INTENT_GENERATE_RESOURCE = "generate_resource"
INTENT_START_LEARNING = "start_learning"
INTENT_ASK_QUESTION = "ask_question"
INTENT_TUTORING = "tutoring"
INTENT_DO_QUIZ = "do_quiz"
INTENT_VIEW_PATH = "view_path"
INTENT_EVALUATE = "evaluate"
KNOWLEDGE_LEVEL_BEGINNER = "beginner"
KNOWLEDGE_LEVEL_INTERMEDIATE = "intermediate"
KNOWLEDGE_LEVEL_ADVANCED = "advanced"
MOTIVATION_LEVEL_HIGH = "high"
MOTIVATION_LEVEL_MEDIUM = "medium"

# ============================================================
# 39. 多模态代码分析
# ============================================================
MULTIMODAL_OMNI_MAX_RETRIES = 3
MULTIMODAL_OMNI_TIMEOUT_SEC = 60
MULTIMODAL_OMNI_MAX_IMAGE_SIZE_MB = 10
MULTIMODAL_OMNI_RATE_LIMIT_PER_MIN = 20
MULTIMODAL_OMNI_CACHE_TTL_SEC = 3600
MULTIMODAL_ANALYSIS_MAX_TOKENS = 4096
MULTIMODAL_CODE_RECOGNITION_MAX_TOKENS = 2048

# ============================================================
# 40. 每日一题
# ============================================================
DAILY_CHALLENGE_QUESTION_TYPE = "code"
DAILY_CHALLENGE_STREAK_RECOVERY_COUNT = 3
DAILY_CHALLENGE_DATE_FORMAT = "%Y-%m-%d"

# ============================================================
# 41. 错因类型与易错点偏好（赛题"易错点偏好"画像维度）
# ============================================================
ERROR_TYPE_SYNTAX = "syntax_error"
ERROR_TYPE_TYPE_CONFUSION = "type_confusion"
ERROR_TYPE_SCOPE_CONFUSION = "scope_confusion"
ERROR_TYPE_BOUNDARY = "boundary_error"
ERROR_TYPE_CONCEPT = "concept_misunderstanding"
ERROR_TYPE_API_MISUSE = "api_misuse"
ERROR_TYPE_LOGIC = "logic_error"
ERROR_TYPE_OTHER = "other"
ALL_ERROR_TYPES = [
    ERROR_TYPE_SYNTAX,
    ERROR_TYPE_TYPE_CONFUSION,
    ERROR_TYPE_SCOPE_CONFUSION,
    ERROR_TYPE_BOUNDARY,
    ERROR_TYPE_CONCEPT,
    ERROR_TYPE_API_MISUSE,
    ERROR_TYPE_LOGIC,
    ERROR_TYPE_OTHER,
]
ERROR_PREFERENCES_TOP_N = 3
ERROR_PREFERENCES_MIN_SAMPLES = 3


# ============================================================
# 42. 学习画像证据权重（精准画像重构）
# ============================================================
# 难度权重（从 api/routes/quiz.py 收口到常量）
# 注意：source_weight 列有 CHECK 0-1 约束，所有值必须 <= 1.0
# 相对顺序 hard(1.0) = medium(1.0) > easy(0.8)。中等题是基准证据，
# 难题不会额外抬高单次作答的分数，避免一次偶然正确造成虚高。
DIFFICULTY_WEIGHT_EASY = 0.8
DIFFICULTY_WEIGHT_MEDIUM = 1.0
DIFFICULTY_WEIGHT_HARD = 1.0
DIFFICULTY_WEIGHT_DEFAULT = DIFFICULTY_WEIGHT_MEDIUM  # difficulty 缺失/未知时用中性权重
DIFFICULTY_EVIDENCE_WEIGHT = {
    "easy": DIFFICULTY_WEIGHT_EASY,
    "medium": DIFFICULTY_WEIGHT_MEDIUM,
    "hard": DIFFICULTY_WEIGHT_HARD,
}

# 证据质量惩罚
HINT_PENALTY = 0.6        # 看提示后答对
COPY_PENALTY = 0.4        # 复制运行成功
WEAK_SIGNAL_THRESHOLD = 2  # 同类弱信号累计次数，达到才降 posterior

# posterior 先验与初始值
POSTERIOR_PRIOR = 0.4          # 先验掌握概率（对应旧 prior_score=40/100）
POSTERIOR_PRIOR_WEIGHT = 2.0
UNCERTAINTY_DEFAULT = 0.9      # 新节点不确定度
UNCERTAINTY_MIN_EVIDENCE = 2   # 证据数 >= 此值才降不确定度

# 证据来源类型枚举（与 knowledge_mastery_evidence CHECK 对齐）
EVIDENCE_SOURCE_QUIZ = "quiz_attempt"
EVIDENCE_SOURCE_PATH = "path_node"
EVIDENCE_SOURCE_CODE = "code_run"
EVIDENCE_SOURCE_REVIEW = "review"
EVIDENCE_SOURCE_MANUAL = "manual"
EVIDENCE_SOURCE_CHAT_JUDGE = "chat_judge"
ALL_EVIDENCE_SOURCES = [
    EVIDENCE_SOURCE_QUIZ, EVIDENCE_SOURCE_PATH, EVIDENCE_SOURCE_CODE,
    EVIDENCE_SOURCE_REVIEW, EVIDENCE_SOURCE_MANUAL, EVIDENCE_SOURCE_CHAT_JUDGE,
]

# 证据信号类型
SIGNAL_TYPE_DIRECT = "direct"
SIGNAL_TYPE_INFERRED = "inferred"  # 阶段4图谱传播用

# 误解置信度
MISCONCEPTION_SUSPECTED_CONFIDENCE = 0.5  # 单次即标"疑似"

# 对话判题权重（弱于 quiz 直答）
CHAT_JUDGE_WEIGHT_FACTOR = 0.7
CHAT_JUDGE_LOW_CONFIDENCE_THRESHOLD = 0.5  # 低于此值走 weak_signal
