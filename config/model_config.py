"""
全局模型配置与赛题枚举管理（软件杯A3 v5.3）
- ✅ 分工明确：与 settings.py 分离（敏感/非敏感）
- ✅ 100%修复所有PyCharm报错/警告
- ✅ 100%统筹全局：统一管理画像维度、知识点、模型配置、路径
- ✅ 赛题显式化：明确标注大赛/编号/课程，方便评审
- ✅ 工程化增强：Pydantic模型、类型注解、配置自检
- ✅ 技术栈对齐：DeepSeek主模型、智谱GLM备用模型、讯飞Embedding（官方）
- ✅ 所有其他模块必须从此导入，杜绝硬编码

更新日志：
- v5.5 (2026-06-28): 主模型切回 DeepSeek，GLM 降为备用模型
- v5.4 (2026-06-27): 主模型切换为火山引擎方舟 GLM-5.2，DeepSeek 保留为备用
- v5.3 (2026-05-27): 主模型切换为小米MiMo-v2.5-pro，DeepSeek降为备用
- v5.2 (2026-05-09): 修复3个致命错误，主模型改用DeepSeek，修正Embedding地址和维度
- v5.2 (2026-04-18): 修复导入语法错误，新增缺失的PYTHON_KB_PATH配置
- v5.1 (2026-04-18): 修复所有PyCharm报错/警告，修正导入逻辑
- v5.0 (2026-04-18): 全局统筹最终版，结合旧版与新版所有优点
- v4.0 (2026-04-18): 新增赛题显式配置、全局统一画像维度/知识点
- v3.0 (2026-04-18): 适配讯飞Embedding，Pydantic结构化
- v2.2 (2026-04-18): 消除循环导入，强化类型提示
- v2.1 (2026-04-18): 适配星火Lite免费API
- v2.0 (2026-04-18): 废弃主动内容安全，改用被动拦截
- v1.0 (2026-04-01): 初始版本
"""
from pathlib import Path
from typing import Dict, List, Literal, Union, TypeAlias
from pydantic import BaseModel, Field

# 🔴 修复1：修正导入语法错误
from config.settings import settings

# ============================================================
# 1. 🔴 赛题显式配置（方便评审一眼看到）
# ============================================================
COMPETITION_INFO = {
    "name": "第十五届中国软件杯",
    "problem_id": "A3",
    "problem_name": "基于大模型的个性化资源生成与学习多智能体系统开发",
    "course_name": "Python程序设计",  # 明确指定课程
    # 课程展示信息（赛题对齐"高等教育"方向，前端课程概览页用）
    "course_intro": "面向高校 Python 编程课程的个性化智能学习平台，覆盖学-练-测-评-路径规划完整学习闭环。",
    "course_target": "帮助不同基础、不同学习风格的学生，通过多智能体协作生成定制化学习资源，实现因材施教。",
    "course_audience": "Python 编程初学者到中级学习者（高校 Python 课程在校生、自主学习者）",
    "course_modules": ["基础语法", "流程控制", "函数与模块", "数据结构", "面向对象", "异常与文件"],
}

# ============================================================
# 2. 🔴 全局统一的画像维度（与 models/profile.py 100%一致！）
# ============================================================
# 维度名称列表
PROFILE_DIMENSION_NAMES = [
    "gender",             # 性别
    "age",                # 年龄
    "knowledge_level",    # 整体基础水平
    "learning_goal",      # 核心学习目标
    "learning_style",     # 主导学习风格
    "duration_preference",# 单次学习时长偏好
    "weak_points",        # 薄弱知识点列表
    "mastered_points",    # 已掌握知识点列表
    "motivation_level"    # 当前学习动力
]
# 维度数量
PROFILE_DIMENSIONS = len(PROFILE_DIMENSION_NAMES)

# 维度可选值（与 models/profile.py 的 CheckConstraint 100%一致！）
PROFILE_DIMENSION_OPTIONS = {
    "gender": ["male", "female", "other"],
    "knowledge_level": ["beginner", "intermediate", "advanced"],
    "learning_goal": ["exam", "interest", "employment", "competition"],
    "learning_style": ["visual", "auditory", "kinesthetic", "mixed"],
    "duration_preference": ["short", "medium", "long"],
    "motivation_level": ["high", "medium", "low"],
}

# ============================================================
# 3. 🔴 全局统一的Python课程知识点列表（所有Agent共用！）
# ============================================================
PYTHON_KNOWLEDGE_POINTS = [
    # 基础模块
    "变量与数据类型",
    "运算符与表达式",
    "条件判断（if/elif/else）",
    "循环（for/while）",
    "函数定义与调用",
    "函数参数与返回值",
    "列表与元组",
    "字典与集合",
    "字符串操作",
    # 进阶模块
    "面向对象基础",
    "类与对象",
    "继承与多态",
    "异常处理",
    "文件操作",
    "模块与包",
]

# 编程关键字 → 标准知识点映射（match_knowledge_point 使用）
CODE_KEYWORD_ALIASES: Dict[str, str] = {
    "def": "函数定义与调用",
    "return": "函数定义与调用",
    "for": "循环（for/while）",
    "while": "循环（for/while）",
    "if": "条件判断（if/elif/else）",
    "elif": "条件判断（if/elif/else）",
    "else": "条件判断（if/elif/else）",
    "class": "类与对象",
    "try": "异常处理",
    "except": "异常处理",
    "import": "模块与包",
    "list": "列表与元组",
    "tuple": "列表与元组",
    "dict": "字典与集合",
    "set": "字典与集合",
    "str": "字符串操作",
    "int": "变量与数据类型",
    "float": "变量与数据类型",
    "bool": "变量与数据类型",
    "open": "文件操作",
    "read": "文件操作",
    "write": "文件操作",
}

# ============================================================
# 4. 🔴 全局统一的赛题枚举（禁止在其他文件硬编码！）
# ============================================================
# 严格对应赛题的5种核心资源类型
RESOURCE_TYPES: List[str] = [
    "doc",              # 讲解文档
    "quiz",             # 练习题
    "mindmap",          # 思维导图
    "code",             # 代码案例
    "video",            # 讲解视频
    "reading",          # 拓展阅读
    "daily_challenge",  # 每日一题
    "daily_extra",      # 每日一题额外挑战
    "multimodal",       # 多模态代码分析
    "slides",           # 教学幻灯片
]
# 🔴 修复警告4：用TypeAlias明确标注类型别名，解决类型专用化警告
ResourceTypeLiteral: TypeAlias = Literal["doc", "quiz", "mindmap", "code", "video", "reading", "daily_challenge", "daily_extra", "multimodal"]

# 资源生成状态枚举
RESOURCE_STATUS: List[str] = [
    "pending",    # 待生成
    "processing", # 生成中
    "completed",  # 已完成
    "failed"      # 生成失败
]
# 🔴 修复警告4：用TypeAlias明确标注类型别名
ResourceStatusLiteral: TypeAlias = Literal["pending", "processing", "completed", "failed"]

# 内容安全拦截错误码常量（供 llm_client.py 导入使用）
SECURITY_ERROR_CODES: List[str] = ["10013", "10014"]

# ============================================================
# 5. 核心模型配置（Pydantic结构化，100%适配已申请的API）
# ============================================================
class ModelConfig(BaseModel):
    """单个模型的配置"""
    provider: str = Field(..., description="模型提供商")
    model_name: str = Field(..., description="模型名称")
    base_url: str = Field(..., description="API基础URL")
    default_temperature: float = Field(0.7, ge=0.0, le=1.0, description="默认温度")
    default_max_tokens: int = Field(4096, gt=0, description="默认最大token数")
    default_top_p: float = Field(0.9, ge=0.0, le=1.0, description="默认top_p")
    timeout: int = Field(60, gt=0, description="请求超时时间（秒）")

# 主模型：DeepSeek（OpenAI 兼容端点）
# timeout=120：思维导图/video_html 等大任务 max_tokens 较高，需要充足时间
PRIMARY_MODEL_CONFIG = ModelConfig(
    provider="deepseek",
    model_name="deepseek-chat",
    base_url=settings.DEEPSEEK_BASE_URL,
    default_temperature=0.7,
    default_max_tokens=4096,
    default_top_p=0.9,
    timeout=120,
)

# 备用模型：火山引擎方舟 GLM（保留降级路径，主模型失败时使用）
# timeout=180：GLM-5.2 是推理模型，思维导图生成（max_tokens=8192 + JSON mode）60s 跑不完必超时
GLM_FALLBACK_MODEL_CONFIG = ModelConfig(
    provider="ark",
    model_name=settings.GLM_ENDPOINT_ID or settings.GLM_MODEL,
    base_url=settings.GLM_BASE_URL,
    default_temperature=0.7,
    default_max_tokens=4096,
    default_top_p=0.9,
    timeout=180,
)

# 多模态视觉理解模型：火山方舟 doubao-seed-2.1-turbo（图片+文本 → 文本，用于多模态代码识别）
# 注意：必须走标准端点 /api/v3，不能用 coding 端点 /api/coding/v3（coding 端点只认 glm-5.2 这类）
ARK_VISION_CONFIG = ModelConfig(
    provider="ark_vision",
    model_name=settings.ARK_VISION_ENDPOINT_ID or settings.ARK_VISION_MODEL,
    base_url=settings.ARK_VISION_BASE_URL,
    default_temperature=0.1,  # 代码识别要稳，低温
    default_max_tokens=4096,  # 提到 4096，避免长代码截断（原 MiMo 是 2048 会截断）
    default_top_p=0.9,
    timeout=60,
)

# 多模态生成：讯飞 SeeDance（当前未启用，保留框架供后续加分项）
class SeeDanceConfig(BaseModel):
    """SeeDance视频生成配置"""
    provider: str = "seedance"
    api_url: str = settings.SEEDANCE_BASE_URL
    default_duration: int = 60
    default_resolution: str = "1080p"
    timeout: int = 300
    enabled: bool = False

SEEDANCE_CONFIG = SeeDanceConfig()

# 火山引擎语音合成 TTS（视频配音用，与方舟 LLM 鉴权不同，需 app_id + access_token）
class TTSConfig(BaseModel):
    """火山引擎语音合成配置"""
    provider: str = "volcengine_tts"
    api_endpoint: str = "https://openspeech.bytedance.com/api/v1/tts"
    app_id: str = settings.TTS_APP_ID
    access_token: str = settings.TTS_ACCESS_TOKEN
    default_voice_id: str = settings.TTS_DEFAULT_VOICE_ID
    timeout_sec: int = 30
    max_retries: int = 2
    max_concurrency: int = 4
    audio_encoding: str = "mp3"
    sample_rate: int = 24000
    enabled: bool = settings.TTS_ENABLED
    # 科大讯飞超拟人合成（主用，火山降级）
    xfyun_app_id: str = settings.TTS_XFYUN_APP_ID
    xfyun_api_key: str = settings.TTS_XFYUN_API_KEY
    xfyun_api_secret: str = settings.TTS_XFYUN_API_SECRET
    xfyun_api_password: str = settings.TTS_XFYUN_API_PASSWORD
    xfyun_ws_url: str = settings.TTS_XFYUN_WS_URL
    xfyun_voice_id: str = settings.TTS_XFYUN_VOICE_ID
    xfyun_service_param: str = settings.TTS_XFYUN_SERVICE_PARAM

TTS_CONFIG = TTSConfig()

# 🔴 修复致命错误2：修正讯飞Embedding的官方地址和维度
class EmbeddingConfig(BaseModel):
    """Embedding配置"""
    provider: str = "spark"
    model_name: str = "embedding-v1"  # 讯飞官方实际模型名
    base_url: str = settings.EMBEDDING_BASE_URL  # 讯飞Embedding官方独立域名
    dimension: int = 2560  # 讯飞官方Embedding维度
    timeout: int = 30
    max_text_length: int = 256

EMBEDDING_CONFIG = EmbeddingConfig()

# 内容安全配置（已废弃主动API，改用被动拦截）
CONTENT_SECURITY_CONFIG = {
    "provider": "spark",
    "api_url": settings.MODERATION_BASE_URL,
    "check_input": False,
    "check_output": False,
    "timeout": 10,
    "note": "被动拦截模式，错误码见 SECURITY_ERROR_CODES",
}

# ============================================================
# 6. 向量库与 RAG 防幻觉核心配置（Pydantic结构化）
# ============================================================
class VectorDBConfig(BaseModel):
    """向量库配置"""
    provider: str = "chromadb"
    collection_name: str = "python_basics_kb"
    persist_directory: Path = Field(..., description="向量库持久化目录")
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k: int = 3
    similarity_threshold: float = 0.7

# 向量库配置实例（基于 settings.BASE_DIR，避免相对路径问题）
VECTOR_DB_CONFIG = VectorDBConfig(
    persist_directory=settings.BASE_DIR / "data" / "vector_db"
)

# 🔴 修复2：新增缺失的PYTHON_KB_PATH配置（供scripts/build_kb.py使用）
PYTHON_KB_PATH: Path = settings.BASE_DIR / "data" / "knowledge_base" / "python_basics"

# ============================================================
# 7. 任务场景参数预设（Pydantic结构化，按赛题业务场景定制）
# ============================================================
class SceneConfig(BaseModel):
    """单个大模型调用场景的配置"""
    temperature: float = Field(..., ge=0.0, le=1.0, description="模型温度")
    max_tokens: int = Field(..., gt=0, description="最大生成token数")
    description: str = Field(..., description="场景描述")

# 所有场景的配置字典
SCENE_CONFIG: Dict[str, SceneConfig] = {
    "profile_building": SceneConfig(temperature=0.5, max_tokens=1024, description="对话式用户画像构建"),
    "intent_recognition": SceneConfig(temperature=0.1, max_tokens=256, description="用户学习意图精准识别"),
    "document_generation": SceneConfig(temperature=0.6, max_tokens=4096, description="课程讲解文档生成"),
    "quiz_generation": SceneConfig(temperature=0.4, max_tokens=4096, description="练习题生成"),
    "mindmap_generation": SceneConfig(temperature=0.3, max_tokens=8192, description="思维导图结构生成"),
    "mindmap_node_expand": SceneConfig(temperature=0.4, max_tokens=1024, description="思维导图节点按需展开"),
    "code_generation": SceneConfig(temperature=0.2, max_tokens=2048, description="Python代码案例生成"),
    "tutoring": SceneConfig(temperature=0.6, max_tokens=2048, description="智能答疑辅导"),
    "path_planning": SceneConfig(temperature=0.2, max_tokens=2048, description="个性化学习路径规划"),
    "evaluation": SceneConfig(temperature=0.3, max_tokens=2048, description="学习效果评估"),
    "unified_routing": SceneConfig(temperature=0.1, max_tokens=128, description="统一路由：意图+资源类型识别"),
    "video_html_generation": SceneConfig(temperature=0.7, max_tokens=16000, description="HTML教学动画生成"),
    "reading_generation": SceneConfig(temperature=0.6, max_tokens=4096, description="拓展阅读材料生成"),
    "slides_generation": SceneConfig(temperature=0.6, max_tokens=8192, description="教学幻灯片生成"),
    "aggregation": SceneConfig(temperature=0.4, max_tokens=8192, description="多Agent内容聚合整合"),
    "chat_judge": SceneConfig(temperature=0.1, max_tokens=512, description="对话判题：信号触发评估用户作答"),
}

# ============================================================
# 8. 模型降级与重试策略
# ============================================================
PRIMARY_MODEL = "deepseek"
FALLBACK_MODEL_ORDER = ["ark"]
ENABLE_FALLBACK = True
MAX_RETRIES_PER_MODEL = 1

# ============================================================
# 9. 个性化资源生成业务配置（赛题核心，100%合规）
# ============================================================
class ResourceConfig(BaseModel):
    """资源生成业务配置"""
    profile_dimensions: List[str] = Field(..., description="画像维度列表")
    resource_types: List[str] = Field(..., description="资源类型列表")
    cognitive_style_priority: Dict[str, List[str]] = Field(..., description="认知风格资源优先级")
    quiz_type_ratio: Dict[str, float] = Field(..., description="题库类型比例")
    default_quiz_count: int = 5
    max_items_per_type: int = 10

# 资源生成业务配置实例
RESOURCE_CONFIG = ResourceConfig(
    profile_dimensions=PROFILE_DIMENSION_NAMES,
    resource_types=RESOURCE_TYPES,
    cognitive_style_priority={
        "visual": ["mindmap", "video", "doc", "code", "quiz"],
        "auditory": ["video", "doc", "quiz", "code", "mindmap"],
        "kinesthetic": ["code", "quiz", "doc", "mindmap", "video"],
        "mixed": ["doc", "mindmap", "code", "quiz", "video"],
    },
    quiz_type_ratio={
        "choice": 0.4,
        "fill": 0.3,
        "coding": 0.3,
    },
)

# ============================================================
# 10. 进度追踪配置
# ============================================================
PROGRESS_CONFIG = {
    "status_pending": RESOURCE_STATUS[0],
    "status_generating": RESOURCE_STATUS[1],
    "status_completed": RESOURCE_STATUS[2],
    "status_failed": RESOURCE_STATUS[3],
    "update_interval": 1,
}

# ============================================================
# 11. 辅助工具函数（保留旧版实用功能）
# ============================================================
def get_scene_params(
    scene: str,
    model: str = "primary",
    **kwargs
) -> Dict[str, Union[str, float, int]]:
    """
    根据任务场景获取模型调用参数，支持临时覆盖。

    Args:
        scene: 场景名称，见 SCENE_CONFIG 键名
        model: 'primary' 或 'fallback'
        **kwargs: 临时覆盖参数，如 temperature=0.8, max_tokens=8192

    Returns:
        包含 temperature, max_tokens 的字典，可直接解包传入 call_llm()
    """
    base_config = PRIMARY_MODEL_CONFIG if model == "primary" else GLM_FALLBACK_MODEL_CONFIG

    if scene in SCENE_CONFIG:
        params = {
            "temperature": SCENE_CONFIG[scene].temperature,
            "max_tokens": SCENE_CONFIG[scene].max_tokens,
        }
    else:
        params = {
            "temperature": base_config.default_temperature,
            "max_tokens": base_config.default_max_tokens,
        }

    # 临时覆盖（仅允许覆盖 temperature 和 max_tokens）
    allowed_overrides = {"temperature", "max_tokens"}
    for key in allowed_overrides:
        if key in kwargs:
            params[key] = kwargs[key]

    return params


def get_embedding_params() -> dict:
    """返回 Embedding 配置的字典，防止意外修改原配置"""
    return EMBEDDING_CONFIG.model_dump()

# ============================================================
# 12. 配置自检（真正检查，而非打印）
# ============================================================
if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()  # 加载 .env 文件

    print("=" * 60)
    print(f"📋 {COMPETITION_INFO['name']} {COMPETITION_INFO['problem_id']} 配置自检 v5.2")
    print(f"📚 课程名称：{COMPETITION_INFO['course_name']}")
    print("=" * 60)

    errors = []
    warnings = []

    # 1. 环境检查
    print(f"📍 当前运行环境: {'开发' if settings.DEBUG else '生产'}")

    # 2. 向量库持久化目录检查
    try:
        VECTOR_DB_CONFIG.persist_directory.mkdir(parents=True, exist_ok=True)
        print(f"💾 向量库目录: {VECTOR_DB_CONFIG.persist_directory.resolve()} (可创建/已存在)")
    except Exception as e:
        errors.append(f"无法创建向量库目录: {e}")

    # 3. 知识库目录检查
    try:
        PYTHON_KB_PATH.mkdir(parents=True, exist_ok=True)
        print(f"📚 知识库目录: {PYTHON_KB_PATH.resolve()} (可创建/已存在)")
    except Exception as e:
        errors.append(f"无法创建知识库目录: {e}")

    # 4. 模型名称基本校验
    print(f"🤖 主模型: {PRIMARY_MODEL_CONFIG.model_name} (DeepSeek)")
    print(f"📊 向量化模型: {EMBEDDING_CONFIG.model_name} (讯飞官方，维度 {EMBEDDING_CONFIG.dimension})")

    # 5. 赛题硬性合规检查
    profile_cnt = RESOURCE_CONFIG.profile_dimensions
    resource_cnt = RESOURCE_CONFIG.resource_types
    if len(profile_cnt) < 6:
        errors.append(f"画像维度不足：{len(profile_cnt)} < 6")
    if len(resource_cnt) < 5:
        errors.append(f"资源类型不足：{len(resource_cnt)} < 5")
    else:
        print(f"✅ 赛题合规：{len(profile_cnt)}维画像、{len(resource_cnt)}种资源")

    # 6. 关键环境变量提醒
    required_env_vars = ["GLM_API_KEY", "DEEPSEEK_API_KEY", "SPARK_APP_ID", "SPARK_API_KEY_RAW", "SPARK_API_SECRET"]
    missing_env = [v for v in required_env_vars if not getattr(settings, v, None)]
    if missing_env:
        warnings.append(f"缺少环境变量: {missing_env}，请检查 .env 文件")

    # 7. 功能开关汇总
    print("\n" + "-" * 40)
    print("🔧 功能开关状态:")
    print(f"  多模态视频生成: {'✅ 启用' if SEEDANCE_CONFIG.enabled else '❌ 禁用'}")
    print(f"  主动内容安全审核: ❌ 已废弃 (被动拦截模式)")
    print(f"  自动降级: {'✅ 启用' if ENABLE_FALLBACK else '❌ 禁用'}")
    print(f"  重试次数: {MAX_RETRIES_PER_MODEL}")

    # 8. 输出检查结果
    print("\n" + "=" * 60)
    if errors:
        print("❌ 配置自检发现错误，请修正后重试：")
        for err in errors:
            print(f"   - {err}")
        sys.exit(1)
    else:
        print("✅ 配置静态检查通过！")
        if warnings:
            print("⚠️  提示信息：")
            for warn in warnings:
                print(f"   - {warn}")
        print("💡 动态连通性测试请运行: python test_phase1.py")
    print("=" * 60)
