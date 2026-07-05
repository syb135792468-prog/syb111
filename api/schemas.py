from __future__ import annotations
# noinspection PyTypeHints, PyUnresolvedReferences
# type: ignore



from typing import Generic, TypeVar, List, Optional, Dict, Any, Literal
from datetime import datetime, UTC

from pydantic import BaseModel, Field, field_validator, ConfigDict

# 全局唯一常量源，所有枚举都从这里导入
from config.model_config import (
    RESOURCE_TYPES,
    RESOURCE_STATUS,
    PROFILE_DIMENSION_OPTIONS,
    PYTHON_KNOWLEDGE_POINTS,
)
from config.constants import (
    HTTP_OK, RESOURCE_PROGRESS_COMPLETE,
    USERNAME_MAX_LENGTH, PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH,
    MESSAGE_MAX_LENGTH, TITLE_MAX_LENGTH, DIFFICULTY_MIN, DIFFICULTY_MAX,
)
from utils.agent_helpers import match_knowledge_point

# 泛型变量定义
T = TypeVar("T")

"""
api/schemas.py - 接口参数校验与响应格式（最终精炼版）
- ✅ 100%复用 config.model_config 中的常量，无重复定义
- ✅ 字段与 graph/state.py + models/profile.py 完全对齐
- ✅ 增加 Literal 类型安全，自动校验取值范围
- ✅ 完善 OpenAPI 文档描述，自动生成接口文档
- ✅ 保留所有核心功能，无冗余代码
- ✅ 统一响应格式和时间序列化
- ✅ 已修复所有与现有代码的不兼容问题
- ✅ 已添加缺失的 ResourceRequest 类
- ✅ 支持泛型 BaseResponse，类型安全
"""


# ============================================================
# 1. 通用基类（完全保留你的设计）
# ============================================================
class BaseSchema(BaseModel):
    """所有 Schema 的基类，禁止传入额外字段"""
    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=True,
        json_encoders={datetime: lambda v: v.replace(tzinfo=None).isoformat()}
    )


class BaseResponse(BaseSchema, Generic[T]):
    code: int = Field(HTTP_OK, description="业务状态码")
    message: str = Field("success", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")
    error_code: Optional[str] = Field(None, description="结构化错误码，便于前端识别失败类型")
    error_detail: Optional[str] = Field(None, description="错误详情，便于日志排查")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="服务器时间戳"
    )
    request_id: Optional[str] = Field(None, description="请求ID，用于排查问题")


# ============================================================
# 1.5 认证接口
# ============================================================
class RegisterRequest(BaseSchema):
    """用户注册"""
    username: str = Field(..., min_length=2, max_length=USERNAME_MAX_LENGTH, description="用户名")
    password: str = Field(..., min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH, description="密码")

    @field_validator("username")
    @classmethod
    def trim_username(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseSchema):
    """用户登录"""
    username: str = Field(..., min_length=1, max_length=USERNAME_MAX_LENGTH, description="用户名")
    password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH, description="密码")

    @field_validator("username")
    @classmethod
    def trim_username(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseSchema):
    """JWT Token 响应"""
    access_token: str = Field(..., description="JWT Token")
    token_type: str = Field("bearer", description="Token 类型")
    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")


class UserInfoResponse(BaseSchema):
    """当前用户信息"""
    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    created_at: Optional[datetime] = Field(None, description="注册时间")


# ============================================================
# 2. 聊天接口（核心）
# ============================================================
class ChatRequest(BaseSchema):
    """用户对话请求"""
    user_id: Optional[str] = Field(None, min_length=1, max_length=64, description="用户唯一标识（可选，优先使用token中的用户）")
    message: str = Field("", max_length=MESSAGE_MAX_LENGTH, description="用户输入内容")
    thread_id: Optional[str] = Field(None, description="工作流线程ID，用于多轮对话")
    conversation_id: Optional[int] = Field(None, description="对话ID，用于关联到指定对话")
    mode: Literal["fast", "deep"] = Field("fast", description="对话模式：fast=快速回答，deep=深度思考（多Agent协作）")
    images: Optional[List[str]] = Field(default=None, description="已上传图片的URL列表（通过 /api/images/upload 获取）")

    @field_validator("message")
    @classmethod
    def trim_message(cls, v: str) -> str:
        """自动去除首尾空白字符"""
        return v.strip()

    def model_post_init(self, __context) -> None:
        """校验：消息和图片至少有一个"""
        if not self.message and not self.images:
            raise ValueError("消息内容和图片不能同时为空")


class SocraticChatRequest(BaseSchema):
    """苏格拉底导学模式请求"""
    message: str = Field("", max_length=MESSAGE_MAX_LENGTH, description="用户输入内容（hint/give_up/end 时可为空）")
    conversation_id: Optional[int] = Field(None, description="对话ID")
    thread_id: Optional[str] = Field(None, description="苏格拉底会话线程ID（后续轮次必传）")
    action: Literal["start", "answer", "hint", "give_up", "end", "confused"] = Field(
        "start",
        description="操作类型：start=开始新会话，answer=提交回答，hint=请求提示，give_up=直接给答案，end=结束学习，confused=没听懂"
    )
    images: Optional[List[str]] = Field(default=None, description="已上传图片的URL列表")

    @field_validator("message")
    @classmethod
    def trim_message(cls, v: str) -> str:
        return v.strip()


# ============================================================
# 2.5 对话会话接口
# ============================================================
class ConversationCreateRequest(BaseSchema):
    """创建对话请求"""
    title: Optional[str] = Field(None, max_length=TITLE_MAX_LENGTH, description="对话标题（可选，默认新对话）")


class ConversationResponse(BaseSchema):
    """对话会话响应"""
    id: int = Field(..., description="对话ID")
    title: str = Field(..., description="对话标题")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")
    message_count: int = Field(0, description="消息数量")
    last_message: Optional[str] = Field(None, description="最后一条消息预览")


class ChatMessage(BaseSchema):
    """单条聊天消息"""
    role: Literal["user", "assistant", "system"] = Field(..., description="消息角色")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[datetime] = Field(None, description="消息时间戳")


class ChatResponseData(BaseSchema):
    """聊天响应体"""
    reply: str = Field(..., description="AI助手最新回复")
    user_intent: Optional[str] = Field(None, description="识别出的用户意图")
    current_step: str = Field(..., description="工作流最终执行步骤")
    learning_path: List[Dict[str, Any]] = Field(default_factory=list, description="生成的学习路径")
    resources_generated: int = Field(0, description="本次生成的资源数量")


# ============================================================
# 3. 用户画像接口（严格7维，与profile_agent完全对齐）
# ============================================================
class ProfileData(BaseSchema):
    """用户学习画像数据"""
    gender: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["gender"])]] = Field(
        None, description="性别"
    )
    age: Optional[int] = Field(None, ge=3, le=120, description="年龄")
    knowledge_level: Literal[tuple(PROFILE_DIMENSION_OPTIONS["knowledge_level"])] = Field(
        "beginner", description="整体知识水平"
    )
    learning_goal: Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_goal"])] = Field(
        "interest", description="核心学习目标"
    )
    learning_style: Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_style"])] = Field(
        "mixed", description="主导学习风格"
    )
    duration_preference: Literal[tuple(PROFILE_DIMENSION_OPTIONS["duration_preference"])] = Field(
        "medium", description="单次学习时长偏好"
    )
    weak_points: List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        default_factory=list, description="薄弱知识点列表"
    )
    mastered_points: List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        default_factory=list, description="已掌握知识点列表"
    )
    motivation_level: Literal[tuple(PROFILE_DIMENSION_OPTIONS["motivation_level"])] = Field(
        "medium", description="当前学习动力"
    )
    current_topic: Optional[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        None, description="当前学习的知识点"
    )
    last_study_at: Optional[datetime] = Field(None, description="最后学习时间")

    @field_validator("weak_points", "mastered_points", mode="before")
    @classmethod
    def normalize_knowledge_points(cls, v: Any) -> List[str]:
        """将 LLM 返回的模糊知识点名称归一化为标准名称"""
        if not isinstance(v, list):
            return []
        normalized = []
        seen = set()
        for point in v:
            if not isinstance(point, str):
                continue
            std = match_knowledge_point(point)
            if std and std not in seen:
                normalized.append(std)
                seen.add(std)
        return normalized


class ProfileResponse(BaseSchema):
    """获取用户画像响应"""
    user_id: str = Field(..., description="用户ID")
    profile: ProfileData = Field(..., description="7维用户画像数据")
    updated_at: Optional[datetime] = Field(None, description="画像最后更新时间")


class ProfileUpdateRequest(BaseSchema):
    """更新用户画像请求（所有字段可选）"""
    gender: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["gender"])]] = None
    age: Optional[int] = Field(None, ge=3, le=120)
    knowledge_level: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["knowledge_level"])]] = None
    learning_goal: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_goal"])]] = None
    learning_style: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_style"])]] = None
    duration_preference: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["duration_preference"])]] = None
    weak_points: Optional[List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]]] = None
    mastered_points: Optional[List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]]] = None
    motivation_level: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["motivation_level"])]] = None

    @field_validator("weak_points", "mastered_points", mode="before")
    @classmethod
    def normalize_knowledge_points(cls, v: Any) -> Any:
        if v is None:
            return v
        if not isinstance(v, list):
            return []
        normalized = []
        seen = set()
        for point in v:
            if not isinstance(point, str):
                continue
            std = match_knowledge_point(point)
            if std and std not in seen:
                normalized.append(std)
                seen.add(std)
        return normalized


# ============================================================
# 4. 学习资源接口（对齐ResourceItem）
# ============================================================
class ResourceMetadata(BaseModel):
    """资源扩展元数据（允许任意额外字段）"""
    model_config = ConfigDict(extra="allow")
    quiz_type: Optional[str] = Field(None, description="题型")
    answer: Optional[str] = Field(None, description="正确答案")
    explanation: Optional[str] = Field(None, description="答案解析")
    code_length: Optional[int] = Field(None, ge=0, description="代码行数")
    node_count: Optional[int] = Field(None, ge=0, description="思维导图节点数")
    output_format: Optional[str] = Field(None, description="输出格式")
    rag_used: Optional[bool] = Field(None, description="是否使用RAG增强")


class ResourceRequest(BaseSchema):
    """生成学习资源请求"""
    user_id: str = Field(..., min_length=1, max_length=64, description="用户ID")
    topic: str = Field(..., min_length=1, max_length=50000, description="知识点名称或SQL建表语句")
    resource_type: Literal[tuple(RESOURCE_TYPES)] = Field(..., description="资源类型")
    difficulty: Optional[int] = Field(None, ge=DIFFICULTY_MIN, le=DIFFICULTY_MAX, description="已废弃，请使用 config.difficulty")
    config: Optional[Dict[str, Any]] = Field(None, description="类型专属配置，quiz类型支持: questionTypes, questionCount, difficulty, includeExplanation, customPrompt")

    @field_validator("topic")
    @classmethod
    def trim_topic(cls, v: str) -> str:
        """自动去除知识点名称首尾空白字符"""
        return v.strip()


class ExpandNodeRequest(BaseSchema):
    """思维导图节点展开请求"""
    user_id: str = Field(..., min_length=1, max_length=64, description="用户ID")
    resource_id: int = Field(..., description="思维导图资源ID")
    node_id: str = Field(..., min_length=1, description="被点击的节点ID")
    node_topic: str = Field(..., min_length=1, max_length=128, description="节点主题")
    node_definition: str = Field("", description="节点详细解释")
    node_syntax: str = Field("", description="节点语法")
    node_examples: List[str] = Field(default_factory=list, description="节点示例列表")
    node_pitfalls: List[str] = Field(default_factory=list, description="节点常见陷阱")
    node_advice: str = Field("", description="节点学习建议")


class SaveExternalVideoRequest(BaseSchema):
    """收藏外部视频到资源库"""
    user_id: int = Field(..., description="用户ID")
    title: str = Field(..., min_length=1, max_length=200, description="视频标题")
    url: str = Field(..., min_length=1, max_length=500, description="视频链接")
    thumbnail: str = Field("", max_length=500, description="缩略图URL")
    author: str = Field("", max_length=100, description="作者")
    description: str = Field("", max_length=500, description="视频简介")


class ResourceResponse(BaseSchema):
    """学习资源响应"""
    id: Optional[int] = Field(None, description="资源ID")
    resource_type: Literal[tuple(RESOURCE_TYPES)] = Field(..., description="资源类型")
    title: str = Field(..., description="资源标题")
    content: Optional[str] = Field(None, description="资源内容")
    knowledge_points: List[str] = Field(
        default_factory=list, description="关联知识点"
    )
    status: Literal[tuple(RESOURCE_STATUS)] = Field("completed", description="生成状态")
    progress_percent: int = Field(RESOURCE_PROGRESS_COMPLETE, ge=0, le=100, description="生成进度百分比")
    in_library: bool = Field(False, description="是否已加入资源库")
    extra_metadata: Optional[ResourceMetadata] = Field(None, description="扩展元数据")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


# ============================================================
# 5. 流式事件接口（专门用于SSE）
# ============================================================
class StreamEvent(BaseSchema):
    """服务端推送的流式事件"""
    event: Literal["intent", "profile", "path", "resource", "tutor", "eval", "token", "end", "error",
                   "quiz", "code", "doc", "mindmap", "video", "evaluation", "slides",
                   "thinking", "clear",
                   "socratic_question", "socratic_hint", "socratic_feedback",
                   "socratic_answer", "socratic_summary", "socratic_end",
                   "socratic_explain", "socratic_demo", "socratic_practice", "socratic_relate",
                   "mastery_update", "learning_path", "path_node_resource",
                   "content_block_start", "content_block_data", "content_block_stop",
                   "code_recognition", "multimodal_analysis", "multimodal_exercises"] = Field(
        ..., description="事件类型"
    )
    data: Any = Field(..., description="事件数据")
    current_step: Optional[str] = Field(None, description="当前工作流步骤")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="事件时间戳"
    )


# ============================================================
# 5.5 Content Block 模型（统一内容块架构）
# ============================================================
class TextBlock(BaseModel):
    """文本块"""
    type: Literal["text"] = "text"
    text: str

class CodeBlock(BaseModel):
    """代码块"""
    type: Literal["code"] = "code"
    code: str
    language: str = "python"

class ThinkingBlock(BaseModel):
    """思考过程块"""
    type: Literal["thinking"] = "thinking"
    text: str

class CardBlock(BaseModel):
    """卡片资源块"""
    type: Literal["card"] = "card"
    card_type: str       # quiz|code|doc|mindmap|video
    card_id: int         # DB resource ID
    title: str
    data: Any = None     # 内联数据（测验题、代码等）

ContentBlock = TextBlock | CodeBlock | ThinkingBlock | CardBlock

class ContentBlockStartData(BaseModel):
    """content_block_start 事件数据"""
    block_type: str
    block_id: str
    card_type: Optional[str] = None
    card_id: Optional[int] = None
    title: Optional[str] = None

class ContentBlockDeltaData(BaseModel):
    """content_block_data 事件数据"""
    block_id: str
    delta: str

class ContentBlockStopData(BaseModel):
    """content_block_stop 事件数据"""
    block_id: str


# ============================================================
# 5b. 学习路径接口（软件杯A3赛题核心功能）
# ============================================================
class LearningPathNodeResourceData(BaseSchema):
    """路径节点关联资源"""
    id: Optional[int] = Field(None, description="资源关联ID")
    node_id: Optional[int] = Field(None, description="所属节点ID")
    resource_type: Literal[tuple(RESOURCE_TYPES)] = Field(..., description="资源类型")
    title: str = Field(..., description="资源标题")
    description: Optional[str] = Field(None, description="资源描述")
    content: Optional[str] = Field(None, description="资源内容")
    resource_id: Optional[int] = Field(None, description="关联的全局资源ID")
    duration: int = Field(0, ge=0, description="预计时长（分钟）")
    difficulty: float = Field(0.5, ge=0, le=1, description="资源难度")
    status: str = Field("pending", description="资源状态")
    is_cached: bool = Field(False, description="是否已缓存")


class LearningPathNodeData(BaseSchema):
    """路径节点数据"""
    id: Optional[int] = Field(None, description="节点ID")
    knowledge_point: str = Field(..., description="知识点名称")
    description: Optional[str] = Field(None, description="节点描述")
    order: int = Field(..., ge=1, description="节点顺序")
    prerequisites: List[str] = Field(default_factory=list, description="前置知识点")
    difficulty: float = Field(0.5, ge=0, le=1, description="知识点难度")
    estimated_time: int = Field(15, ge=1, description="预计学习时长（分钟）")
    mastery_threshold: float = Field(0.7, ge=0, le=1, description="掌握度阈值")
    mastery: float = Field(0.0, ge=0, le=1, description="当前掌握度")
    status: str = Field("not_started", description="节点状态")
    progress: float = Field(0.0, ge=0, le=100, description="学习进度")
    node_type: str = Field("new", description="节点类型：new/review")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    last_study_at: Optional[datetime] = Field(None, description="最后学习时间")
    resources: List[LearningPathNodeResourceData] = Field(
        default_factory=list, description="关联资源列表"
    )


class LearningPathData(BaseSchema):
    """学习路径完整数据"""
    id: Optional[int] = Field(None, description="路径ID")
    user_id: Optional[int] = Field(None, description="用户ID")
    title: str = Field(..., description="路径标题")
    description: Optional[str] = Field(None, description="路径描述")
    goal: Optional[str] = Field(None, description="学习目标")
    topic: str = Field("Python基础", description="路径主题")
    status: str = Field("active", description="路径状态")
    total_nodes: int = Field(0, description="总节点数")
    completed_nodes: int = Field(0, description="已完成节点数")
    total_estimated_time: int = Field(0, description="总预计时长（分钟）")
    progress_percent: float = Field(0.0, description="整体进度百分比")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    nodes: List[LearningPathNodeData] = Field(
        default_factory=list, description="路径节点列表"
    )


class LearningPathGenerateRequest(BaseSchema):
    """生成学习路径请求"""
    topic: str = Field(
        "Python基础", min_length=1, max_length=200,
        description="学习主题/方向（如：Python基础、数据分析）"
    )
    goal: Optional[str] = Field(
        None, max_length=200, description="学习目标"
    )
    max_steps: Optional[int] = Field(
        None, ge=1, le=15, description="最大步数（默认8）"
    )
    mastered_points: Optional[List[str]] = Field(
        None, description="问卷：用户自认已掌握的知识点列表"
    )
    weak_points: Optional[List[str]] = Field(
        None, description="问卷：用户自认薄弱的知识点列表"
    )
    target_points: Optional[List[str]] = Field(
        None, description="问卷：该方向包含的知识点列表（用于过滤路径）"
    )


class LearningPathListResponse(BaseSchema):
    """学习路径列表响应"""
    paths: List[LearningPathData] = Field(default_factory=list, description="路径列表")
    total: int = Field(0, description="总数")


class LearningPathNodeCompleteRequest(BaseSchema):
    """标记节点完成请求"""
    mastery: Optional[float] = Field(
        None, ge=0, le=1, description="掌握度（可选，默认设为阈值）"
    )


class LearningPathQuizSubmitRequest(BaseSchema):
    """提交测验结果请求"""
    node_id: int = Field(..., description="路径节点ID")
    total_questions: int = Field(..., ge=1, description="总题数")
    correct_count: int = Field(..., ge=0, description="正确题数")
    details: Optional[List[Dict[str, Any]]] = Field(
        None, description="详细答题记录"
    )


# ============================================================
# 6. 错误响应
# ============================================================
class ErrorResponse(BaseSchema):
    """错误信息响应"""
    error: str = Field(..., description="错误类型")
    detail: Optional[str] = Field(None, description="错误详情")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="错误时间戳"
    )


# ============================================================
# 自检
# ============================================================
if __name__ == "__main__":
    # 验证所有Schema能否正常使用
    test_cases = [
        ("ChatRequest", ChatRequest(user_id="test_001", message="  我想学习Python循环  ")),
        ("ProfileData", ProfileData()),
        ("ResourceRequest", ResourceRequest(user_id="1", topic="Python循环", resource_type="quiz")),
        ("ResourceResponse", ResourceResponse(resource_type="quiz", title="Python循环练习题")),
        ("StreamEvent", StreamEvent(event="tutor", data={"reply": "Hello"})),
    ]

    for name, obj in test_cases:
        print(f"✅ {name} 校验通过")
        print(f"   JSON: {obj.model_dump_json(indent=2)[:100]}...\n")

    print("🎉 所有Schema自检通过！")


# ============================================================
# 7. 多模态代码分析接口
# ============================================================
class MultimodalAnalyzeRequest(BaseSchema):
    """多模态代码分析请求"""
    image_url: str = Field(..., description="已上传图片的URL（通过 /api/images/upload 获取）")
    prompt: Optional[str] = Field(None, max_length=1000, description="可选的自定义提示词")

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        if not v.startswith("/static/uploads/images/"):
            raise ValueError("图片URL格式不正确，应以 /static/uploads/images/ 开头")
        return v.strip()


class CodeProblem(BaseModel):
    """代码问题"""
    type: str = Field(..., description="问题类型：语法错误/逻辑错误/最佳实践")
    description: str = Field(..., description="问题描述")
    line: Optional[str] = Field(None, description="问题所在行")
    fix: str = Field(..., description="修复建议")


class Exercise(BaseModel):
    """练习题"""
    type: str = Field(..., description="题型：choice/fill/code")
    question: str = Field(..., description="题目内容")
    options: Optional[List[str]] = Field(None, description="选项列表（选择题）")
    answer: str = Field(..., description="正确答案")
    explanation: str = Field(..., description="解析")


class MultimodalAnalysisData(BaseModel):
    """多模态分析结果数据"""
    code_text: str = Field("", description="识别出的代码")
    explanation: str = Field("", description="代码解释")
    problems: List[CodeProblem] = Field(default_factory=list, description="问题诊断")
    exercises: List[Exercise] = Field(default_factory=list, description="练习题")
    knowledge_points: List[str] = Field(default_factory=list, description="涉及的知识点")
