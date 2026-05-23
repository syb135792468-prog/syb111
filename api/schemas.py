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
from config.constants import HTTP_OK, RESOURCE_PROGRESS_COMPLETE

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
    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    password: str = Field(..., min_length=4, max_length=100, description="密码")

    @field_validator("username")
    @classmethod
    def trim_username(cls, v: str) -> str:
        return v.strip().lower()


class LoginRequest(BaseSchema):
    """用户登录"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=100, description="密码")

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
    message: str = Field(..., min_length=1, max_length=2000, description="用户输入内容")
    thread_id: Optional[str] = Field(None, description="工作流线程ID，用于多轮对话")
    conversation_id: Optional[int] = Field(None, description="对话ID，用于关联到指定对话")

    @field_validator("message")
    @classmethod
    def trim_message(cls, v: str) -> str:
        """自动去除首尾空白字符"""
        return v.strip()


# ============================================================
# 2.5 对话会话接口
# ============================================================
class ConversationCreateRequest(BaseSchema):
    """创建对话请求"""
    title: Optional[str] = Field(None, max_length=200, description="对话标题（可选，默认新对话）")


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
    """用户7维学习画像数据"""
    knowledge_level: Literal[tuple(PROFILE_DIMENSION_OPTIONS["knowledge_level"])] = Field(
        "beginner", description="1. 整体知识水平"
    )
    learning_goal: Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_goal"])] = Field(
        "interest", description="2. 核心学习目标"
    )
    learning_style: Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_style"])] = Field(
        "mixed", description="3. 主导学习风格"
    )
    duration_preference: Literal[tuple(PROFILE_DIMENSION_OPTIONS["duration_preference"])] = Field(
        "medium", description="4. 单次学习时长偏好"
    )
    weak_points: List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        default_factory=list, description="5. 薄弱知识点列表"
    )
    mastered_points: List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        default_factory=list, description="6. 已掌握知识点列表"
    )
    motivation_level: Literal[tuple(PROFILE_DIMENSION_OPTIONS["motivation_level"])] = Field(
        "medium", description="7. 当前学习动力"
    )
    current_topic: Optional[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]] = Field(
        None, description="当前学习的知识点"
    )
    last_study_at: Optional[datetime] = Field(None, description="最后学习时间")


class ProfileResponse(BaseSchema):
    """获取用户画像响应"""
    user_id: str = Field(..., description="用户ID")
    profile: ProfileData = Field(..., description="7维用户画像数据")
    updated_at: Optional[datetime] = Field(None, description="画像最后更新时间")


class ProfileUpdateRequest(BaseSchema):
    """更新用户画像请求（所有字段可选）"""
    knowledge_level: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["knowledge_level"])]] = None
    learning_goal: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_goal"])]] = None
    learning_style: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["learning_style"])]] = None
    duration_preference: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["duration_preference"])]] = None
    weak_points: Optional[List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]]] = None
    mastered_points: Optional[List[Literal[tuple(PYTHON_KNOWLEDGE_POINTS)]]] = None
    motivation_level: Optional[Literal[tuple(PROFILE_DIMENSION_OPTIONS["motivation_level"])]] = None


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
    topic: str = Field(..., min_length=1, max_length=128, description="知识点名称")
    resource_type: Literal[tuple(RESOURCE_TYPES)] = Field(..., description="资源类型")
    difficulty: int = Field(2, ge=1, le=5, description="难度等级（1-5，默认2）")

    @field_validator("topic")
    @classmethod
    def trim_topic(cls, v: str) -> str:
        """自动去除知识点名称首尾空白字符"""
        return v.strip()


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
    extra_metadata: Optional[ResourceMetadata] = Field(None, description="扩展元数据")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


# ============================================================
# 5. 流式事件接口（专门用于SSE）
# ============================================================
class StreamEvent(BaseSchema):
    """服务端推送的流式事件"""
    event: Literal["intent", "profile", "path", "resource", "tutor", "eval", "token", "end", "error"] = Field(
        ..., description="事件类型"
    )
    data: Any = Field(..., description="事件数据")
    current_step: Optional[str] = Field(None, description="当前工作流步骤")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(tzinfo=None),
        description="事件时间戳"
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