"""
agents/content_agent.py - 统一内容生成智能体
合并原 doc_agent / reading_agent / slides_agent
通过 ContentType 枚举区分不同内容类型，复用同一套 RAG + LLM + 格式化执行链路
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Dict, Any, Optional, ClassVar

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.constants import DEFAULT_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED
from utils.agent_helpers import get_profile_from_context, build_profile_text


class ContentType(str, Enum):
    DOCUMENT = "document"
    READING = "reading"
    SLIDES = "slides"


# 各内容类型的配置映射
_CONTENT_CONFIG: Dict[ContentType, Dict[str, str]] = {
    ContentType.DOCUMENT: {
        "agent_name": "doc",
        "scene_name": "document_generation",
        "resource_type": "doc",
        "title_suffix": "学习文档",
        "system_prompt": "document_generation_system",
        "user_prompt": "document_generation_user",
        "fallback_prompt": "document_generation_fallback",
    },
    ContentType.READING: {
        "agent_name": "reading",
        "scene_name": "reading_generation",
        "resource_type": "reading",
        "title_suffix": "拓展阅读",
        "system_prompt": "reading_generation_system",
        "user_prompt": "reading_generation_user",
        "fallback_prompt": None,  # 使用内联模板
    },
    ContentType.SLIDES: {
        "agent_name": "slides",
        "scene_name": "slides_generation",
        "resource_type": "slides",
        "title_suffix": "教学幻灯片",
        "system_prompt": "slides_generation_system",
        "user_prompt": "slides_generation_user",
        "fallback_prompt": None,  # 使用内联模板
    },
}


class ContentAgent(BaseAgent):
    """统一内容生成智能体：LLM 生成结构化 Python 知识点学习内容"""

    def __init__(
        self,
        content_type: ContentType | str = ContentType.DOCUMENT,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> None:
        if isinstance(content_type, str):
            content_type = ContentType(content_type)
        self.content_type = content_type
        cfg = _CONTENT_CONFIG[content_type]

        super().__init__(
            agent_name=cfg["agent_name"],
            scene_name=cfg["scene_name"],
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )

    async def process(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"目标知识点：{target_kp}")

        profile = get_profile_from_context(context)
        content = await self._llm_generate(target_kp, profile)

        # slides 特有：格式校验与修复
        extra_metadata: Dict[str, Any] = {"rag_used": self.enable_rag}
        if self.content_type == ContentType.SLIDES:
            content = self._validate_and_fix_slides(content, target_kp)
            slide_count = len([s for s in re.split(r"\n\s*---\s*\n", content) if s.strip()])
            extra_metadata["slide_count"] = slide_count

        cfg = _CONTENT_CONFIG[self.content_type]
        resource = ResourceItem(
            resource_type=cfg["resource_type"],
            title=f"{target_kp} {cfg['title_suffix']}",
            content=content,
            knowledge_points=[target_kp],
            status=RESOURCE_STATUS_COMPLETED,
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata=extra_metadata,
        )

        new_resources = self._append_resource(context, resource)
        self.logger.info(f"内容生成完成：{resource.title}")
        return self._build_result(new_resources)

    async def _llm_generate(self, kp: str, profile: Optional[Dict[str, Any]] = None) -> str:
        cfg = _CONTENT_CONFIG[self.content_type]
        rag_context = await self._get_rag_context(kp, top_k=DEFAULT_RAG_TOP_K)
        profile_text = build_profile_text(
            profile, ["knowledge_level", "learning_style", "duration_preference", "weak_points"]
        )
        prompt_kwargs = {
            "kp": kp,
            "topic": kp,
            "rag_context": rag_context if rag_context else "无参考资料",
            "profile_text": profile_text,
        }

        system_prompt = self._load_prompt(cfg["system_prompt"], **prompt_kwargs)

        try:
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._load_prompt(cfg["user_prompt"], **prompt_kwargs)},
            ])
            if not resp.strip():
                raise ValueError("LLM返回空内容")
            return resp
        except Exception as e:
            self.logger.warning(f"LLM内容生成失败，使用兜底结构: {e}")
            return self._fallback_generate(kp, profile_text)

    def _fallback_generate(self, kp: str, profile_text: str = "（暂无画像信息）") -> str:
        cfg = _CONTENT_CONFIG[self.content_type]

        # 如果有 prompt 模板文件，使用它
        if cfg["fallback_prompt"]:
            return self._load_prompt(cfg["fallback_prompt"], kp=kp, profile_text=profile_text)

        # reading 兜底
        if self.content_type == ContentType.READING:
            return (
                f"# {kp} 拓展阅读\n\n"
                f"## 1. 实际应用场景\n"
                f"{kp}在日常开发中有着广泛的应用，掌握它能帮助你写出更优雅的代码。\n\n"
                f"## 2. 知识网络\n"
                f"- **前置知识**：Python基础语法\n"
                f"- **关联知识**：与{kp}相关的其他Python特性\n"
                f"- **进阶方向**：深入理解{kp}的底层原理\n\n"
                f"## 3. 推荐资源\n"
                f"- Python官方文档中关于{kp}的章节\n"
                f"- 《Python编程：从入门到实践》相关章节\n\n"
                f"## 4. 思考题\n"
                f"1. {kp}的核心设计思想是什么？\n"
                f"2. 在什么场景下应该优先使用{kp}？\n"
            )

        # slides 兜底
        if self.content_type == ContentType.SLIDES:
            return f"""# {kp}

### Python 编程核心知识点精讲

---

## 什么是 {kp}？

- **{kp}** 是 Python 中的重要概念
- 它帮助我们编写更高效、更优雅的代码
- 掌握它是进阶 Python 的必经之路

> 理解 {kp}，就像掌握了一把打开 Python 世界的钥匙

---

## 核心语法

- Python 中 {kp} 的基本写法如下
- 注意语法细节和缩进规范

```python
# {kp} 基础示例
# 请根据具体知识点补充代码
print("Hello, Python!")
```

---

## 实际应用

- {kp} 在日常开发中非常常见
- 以下是一个典型的使用场景

```python
# {kp} 实战示例
# 从简单的用法开始，逐步深入
result = "实践出真知"
print(result)
```

---

## 常见错误

- 初学者在 {kp} 上容易犯的错误
- 注意区分 **正确写法** 和 **错误写法**

```python
# 错误示例
# 常见的错误写法

# 正确示例
# 推荐的正确写法
```

---

## 总结

- **{kp}** 是 Python 编程的重要基础
- 核心要点：理解概念 → 掌握语法 → 动手实践
- 多写代码、多调试，才能真正掌握

### 下一步：尝试用 {kp} 解决一个小问题吧！
"""

        return f"# {kp}\n\n暂无内容，请稍后重试。"

    def _validate_and_fix_slides(self, content: str, kp: str) -> str:
        """校验并修复 LLM 输出的幻灯片格式（仅 slides 类型使用）"""
        # 1. 剥离代码块包裹
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.split("\n", 1)[-1] if "\n" in stripped else stripped
        if stripped.endswith("```"):
            stripped = stripped.rsplit("```", 1)[0]
        content = stripped.strip()

        # 2. 格式归一化：统一分隔符格式（单独一行的 ---）
        content = re.sub(r"\n\s*---\s*\n", "\n\n---\n\n", content)
        content = re.sub(r"\n{3,}", "\n\n", content)

        # 3. 分割并校验
        slides = [s.strip() for s in content.split("\n---\n") if s.strip()]

        # 4. 确保有封面页（第一个 slide 必须有 # 标题）
        if slides and not re.search(r"^#\s", slides[0], re.MULTILINE):
            slides.insert(0, f"# {kp}\n\nPython 教学幻灯片")

        # 5. 确保有总结页（最后一个 slide 必须有 总结/summary）
        if slides and not re.search(r"总结|summary|回顾|要点", slides[-1], re.IGNORECASE):
            slides.append(f"## 总结\n\n- {kp} 的核心要点回顾\n- 持续练习是掌握的关键")

        # 6. 重新拼接
        result = "\n\n---\n\n".join(slides)
        self.logger.debug(f"格式校验完成：{len(slides)} 页")
        return result

    def _get_target_knowledge_point(
        self, user_input: str, context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """优先使用统一路由提取的纯主题，兜底用用户输入"""
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC
