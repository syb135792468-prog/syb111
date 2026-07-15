"""
agents/video_schema.py - 教学动画脚本 Pydantic Schema + 校验
三阶段流水线第一阶段的数据结构（Pydantic v2）
"""
from __future__ import annotations

from typing import List, Dict, Optional
import json

from pydantic import BaseModel, Field, field_validator, model_validator


# ============================================================
# 允许的动画类型
# ============================================================
VALID_CODE_ANIMATIONS = {
    "code_fade_up", "code_slide_left", "code_typewriter",
}
VALID_BUBBLE_ANIMATIONS = {
    "bubble_fade_up", "bubble_slide_right", "bubble_zoom_in",
}
# 兼容旧版单一动画字段
VALID_ANIMATION_TYPES = VALID_CODE_ANIMATIONS | VALID_BUBBLE_ANIMATIONS | {
    "slide_in_left", "slide_in_right", "slide_in_up", "slide_in_down",
    "scale_pop", "fade_in_up", "typewriter", "width_expand",
    "rotate_in", "blur_in", "bounce_in", "elastic_in",
}

# flowchart 风格专用动画（仅 chart_type 非 code_walkthrough 时允许）
VALID_FLOW_ANIMATIONS = {
    "flow_draw", "particle_flow",
}

# ============================================================
# 图表类型（chart_type）
# ============================================================
# code_walkthrough 是原有"代码逐行讲解"路径，必须保留以兼容旧缓存
VALID_CHART_TYPES = {
    "code_walkthrough",  # 代码逐行讲解（原默认路径）
    "flowchart",         # 步骤流程、决策分支、循环
    "concept",           # 概念关系、知识结构、层级
    "principle",         # 模型/算法/协议的动态工作过程
    "compare",            # 两种/多种方案并排对比
    "timeline",           # 事件发展、版本演进
    "system_overview",    # 简化的系统架构、模块关系
    "sequence",           # 消息交互、请求响应、调用链
}
DEFAULT_CHART_TYPE = "code_walkthrough"

# 节点允许的颜色（仅用现有 :root 色板，不引入新色）
VALID_NODE_COLORS = {
    "accent-purple", "accent-pink", "accent-cyan", "accent-yellow", "accent-blue",
}


# ============================================================
# Pydantic 数据模型
# ============================================================
class ScriptMeta(BaseModel):
    topic: str = Field(..., min_length=1, description="知识点主题")
    duration: int = Field(..., ge=10, le=600, description="总时长（秒）")
    style: str = Field(default="tutorial", description="动画风格")
    learning_goal: str = Field(default="", description="学习目标")
    chart_type: str = Field(default=DEFAULT_CHART_TYPE, description="图表类型")

    @field_validator("chart_type")
    @classmethod
    def check_chart_type(cls, v: str) -> str:
        # 非法值回退默认，不抛错（保降级）
        if not v or v not in VALID_CHART_TYPES:
            return DEFAULT_CHART_TYPE
        return v


class ScriptStep(BaseModel):
    step_id: int = Field(..., ge=1, description="步骤序号，从1开始")
    title: str = Field(..., min_length=2, max_length=30, description="步骤标题")
    narration: str = Field(..., min_length=20, description="旁白文案")
    code_snippet: str = Field(default="", min_length=0, description="代码片段（流程图风格可省）")
    highlight_lines: List[int] = Field(default_factory=list, description="高亮行号")
    animation_type: str = Field(default="code_fade_up", description="动画类型（兼容旧版）")
    code_animation: str = Field(default="code_fade_up", description="代码区动画")
    bubble_animation: str = Field(default="bubble_fade_up", description="讲解气泡动画")
    variable_panel: Dict[str, str] = Field(default_factory=dict, description="变量面板")
    # flowchart 风格字段（仅 chart_type 非 code_walkthrough 时使用）
    nodes: List[Dict] = Field(default_factory=list, description="流程图节点列表")
    edges: List[Dict] = Field(default_factory=list, description="流程图边列表")
    # TTS 音频字段（后端注入，LLM 不生成，parse_script 时不校验）
    audio_url: Optional[str] = Field(default=None, description="音频文件 URL（后续段落懒加载）")
    audio_base64: Optional[str] = Field(default=None, description="音频 base64（第一段内嵌）")
    word_timestamps: List[Dict] = Field(default_factory=list, description="逐字时间戳 [{text, start_ms, duration_ms}]")
    audio_duration_ms: Optional[int] = Field(default=None, description="音频实际时长（毫秒）")

    @field_validator("animation_type")
    @classmethod
    def check_animation_type(cls, v: str) -> str:
        if v and v not in VALID_ANIMATION_TYPES:
            return "code_fade_up"
        return v

    @field_validator("code_animation")
    @classmethod
    def check_code_animation(cls, v: str) -> str:
        # code_walkthrough 路径只允许原 3 种；流程图路径额外允许 flow_draw/particle_flow
        # 这里只做兜底：完全非法的值回退默认；具体宽放交给 AnimationScript.model_validator 处理
        if v and v not in (VALID_CODE_ANIMATIONS | VALID_FLOW_ANIMATIONS):
            return "code_fade_up"
        return v

    @field_validator("bubble_animation")
    @classmethod
    def check_bubble_animation(cls, v: str) -> str:
        if v and v not in VALID_BUBBLE_ANIMATIONS:
            return "bubble_fade_up"
        return v

    @field_validator("highlight_lines")
    @classmethod
    def check_highlight_lines(cls, v: List[int]) -> List[int]:
        return [i for i in v if i > 0]

    @field_validator("nodes")
    @classmethod
    def check_nodes(cls, v: List[Dict]) -> List[Dict]:
        cleaned = []
        for n in v:
            if not isinstance(n, dict):
                continue
            color = n.get("color", "accent-blue")
            if color not in VALID_NODE_COLORS:
                n["color"] = "accent-blue"
            cleaned.append(n)
        return cleaned


class ScriptSummary(BaseModel):
    key_points: List[str] = Field(default_factory=list, description="核心要点")
    ending_text: str = Field(default="", description="结束语")


class AnimationScript(BaseModel):
    meta: ScriptMeta
    steps: List[ScriptStep]
    summary: ScriptSummary

    @field_validator("steps")
    @classmethod
    def check_steps(cls, v: List[ScriptStep]) -> List[ScriptStep]:
        if len(v) < 3:
            raise ValueError(f"步骤数不足：{len(v)} < 3")
        # 校验 step_id 连续性
        for i, step in enumerate(v):
            if step.step_id != i + 1:
                step.step_id = i + 1  # 自动修正
        return v

    @model_validator(mode="after")
    def check_chart_type_consistency(self) -> "AnimationScript":
        """chart_type 与 step 内容交叉校验"""
        chart_type = self.meta.chart_type
        is_code_walkthrough = (chart_type == DEFAULT_CHART_TYPE)

        for i, step in enumerate(self.steps):
            prefix = f"steps[{i}]"
            if is_code_walkthrough:
                # 代码路径：code_snippet 必填，code_animation 不允许 flow_draw/particle_flow
                if not step.code_snippet.strip():
                    raise ValueError(f"{prefix}.code_snippet 在 code_walkthrough 路径下必填")
                if step.code_animation in VALID_FLOW_ANIMATIONS:
                    raise ValueError(
                        f"{prefix}.code_animation={step.code_animation} "
                        f"在 code_walkthrough 路径下不允许，仅允许 {VALID_CODE_ANIMATIONS}"
                    )
            else:
                # 流程图路径：nodes 必填，code_animation 允许 flow_draw/particle_flow
                if not step.nodes:
                    raise ValueError(
                        f"{prefix}.nodes 在 chart_type={chart_type} 路径下必填"
                    )
        return self

    def to_dict(self) -> dict:
        return self.model_dump()

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False, indent=2)


# ============================================================
# 校验结果
# ============================================================
class ValidationResult:
    def __init__(self, ok: bool, errors: List[str] = None, warnings: List[str] = None):
        self.ok = ok
        self.errors = errors or []
        self.warnings = warnings or []

    def __str__(self):
        parts = []
        if self.errors:
            parts.append(f"Errors: {'; '.join(self.errors)}")
        if self.warnings:
            parts.append(f"Warnings: {'; '.join(self.warnings)}")
        return " | ".join(parts) if parts else "OK"


# ============================================================
# 校验函数（单一入口，只构建一次 AnimationScript）
# ============================================================
def _check_content(script: AnimationScript, topic: str = "") -> tuple[List[str], List[str]]:
    """内容密度校验，返回 (errors, warnings)。Pydantic 格式校验由调用方负责。"""
    errors = []
    warnings = []

    chart_type = script.meta.chart_type
    is_code_walkthrough = (chart_type == DEFAULT_CHART_TYPE)

    # 流程图路径：收集全局节点 id 用于 edges 校验
    all_node_ids = set()
    if not is_code_walkthrough:
        for step in script.steps:
            for n in step.nodes:
                nid = n.get("id")
                if nid:
                    all_node_ids.add(nid)
        if len(all_node_ids) < 3:
            warnings.append(
                f"chart_type={chart_type} 但全局 unique nodes 不足 3 个（{len(all_node_ids)}）"
            )

    for i, step in enumerate(script.steps):
        prefix = f"steps[{i}]"

        if len(step.narration) < 20:
            errors.append(f"{prefix}.narration 过短（{len(step.narration)}字 < 20）")

        if is_code_walkthrough:
            # 代码路径原校验
            if not step.code_snippet.strip():
                errors.append(f"{prefix}.code_snippet 为空")

            total_lines = len(step.code_snippet.split("\n"))
            for hl in step.highlight_lines:
                if hl > total_lines:
                    warnings.append(f"{prefix}.highlight_lines: 行号{hl}超出代码总行数{total_lines}")

            # edges 校验（流程图路径）
            for j, edge in enumerate(step.edges):
                f, t = edge.get("from"), edge.get("to")
                if f and f not in all_node_ids:
                    errors.append(f"{prefix}.edges[{j}].from={f} 不在全局 nodes 中")
                if t and t not in all_node_ids:
                    errors.append(f"{prefix}.edges[{j}].to={t} 不在全局 nodes 中")
        else:
            # 流程图路径校验
            if not step.nodes:
                errors.append(f"{prefix}.nodes 为空（chart_type={chart_type}）")

            for j, edge in enumerate(step.edges):
                f, t = edge.get("from"), edge.get("to")
                if f and f not in all_node_ids:
                    errors.append(f"{prefix}.edges[{j}].from={f} 不在全局 nodes 中")
                if t and t not in all_node_ids:
                    errors.append(f"{prefix}.edges[{j}].to={t} 不在全局 nodes 中")

    # 代码行数递进校验只在 code_walkthrough 路径
    if is_code_walkthrough:
        code_lengths = [len(s.code_snippet.split("\n")) for s in script.steps]
        for i in range(1, len(code_lengths)):
            if code_lengths[i] < code_lengths[i - 1] - 2:
                warnings.append(f"steps[{i}].code_snippet 行数少于上一步")

    if topic:
        topic_chars = set(topic.replace(" ", "").lower())
        all_text_parts = []
        for s in script.steps:
            all_text_parts.append(s.title)
            all_text_parts.append(s.narration)
            if s.code_snippet:
                all_text_parts.append(s.code_snippet)
            for n in s.nodes:
                if isinstance(n, dict):
                    all_text_parts.append(str(n.get("label", "")))
        all_text = " ".join(all_text_parts).lower()
        if topic_chars:
            match_count = sum(1 for c in topic_chars if c in all_text)
            match_ratio = match_count / len(topic_chars)
            if match_ratio < 0.3:
                warnings.append(f"内容与主题 '{topic}' 相关性较低（匹配率 {match_ratio:.0%}）")

    if len(script.summary.key_points) < 2:
        warnings.append("summary.key_points 不足 2 条")

    return errors, warnings


def parse_script(raw_json: str, topic: str = "") -> tuple[Optional[AnimationScript], ValidationResult]:
    """解析并校验 JSON 字符串，返回 (脚本对象, 校验结果)。只构建一次 AnimationScript。"""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return None, ValidationResult(False, [f"JSON 解析失败: {e}"])

    try:
        script = AnimationScript(**data)
    except Exception as e:
        err_msg = str(e)
        if "Field required" in err_msg:
            msg = f"缺少必填字段: {err_msg.split('Field required')[0].strip()}"
        elif "Input should be" in err_msg:
            msg = f"字段类型错误: {err_msg[:200]}"
        else:
            msg = f"格式校验失败: {err_msg[:200]}"
        return None, ValidationResult(False, [msg])

    errors, warnings = _check_content(script, topic)
    if errors:
        return None, ValidationResult(False, errors, warnings)

    return script, ValidationResult(True, warnings=warnings)
