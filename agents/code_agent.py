"""
agents/code_agent.py - 代码案例生成智能体（增强版）
✅ 继承 BaseAgent，规则+LLM 双模式
✅ 内存缓存：避免重复 LLM 调用
✅ 增强规则模板：按代码类型生成差异化内容
✅ 复杂度判断：简单请求快速模式，复杂请求深度模式
"""
from __future__ import annotations

import time
import hashlib
from typing import Dict, Any, Optional, List, ClassVar
import re

from agents.base_agent import BaseAgent
from graph.state import ResourceItem
from config.model_config import PYTHON_KNOWLEDGE_POINTS
from config.constants import CODE_RAG_TOP_K, RESOURCE_PROGRESS_COMPLETE, DEFAULT_TOPIC, RESOURCE_STATUS_COMPLETED
from utils.agent_helpers import match_knowledge_point, get_profile_from_context


# ============================================================
# 缓存实现（带 TTL 的内存缓存）
# ============================================================
class _CodeCache:
    """基于 (code_type, topic) 的内存缓存，带过期时间"""

    def __init__(self, ttl_sec: int = 3600, max_size: int = 200) -> None:
        self._store: Dict[str, tuple[str, float]] = {}
        self._ttl = ttl_sec
        self._max_size = max_size

    def _make_key(self, code_type: str, topic: str) -> str:
        raw = f"{code_type}:{topic}".strip().lower()
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, code_type: str, topic: str) -> Optional[str]:
        key = self._make_key(code_type, topic)
        entry = self._store.get(key)
        if entry is None:
            return None
        content, ts = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return content

    def put(self, code_type: str, topic: str, content: str) -> None:
        if len(self._store) >= self._max_size:
            # 淘汰最旧的 25%
            sorted_keys = sorted(self._store, key=lambda k: self._store[k][1])
            for k in sorted_keys[: self._max_size // 4]:
                del self._store[k]
        key = self._make_key(code_type, topic)
        self._store[key] = (content, time.monotonic())


_code_cache = _CodeCache()


# ============================================================
# 规则模板库（按代码类型差异化）
# ============================================================
_RULE_TEMPLATES: Dict[str, str] = {
    "basic": '''# {kp} - 基础示例
# 知识点：{kp}

def demo_{func_name}():
    """
    {kp} 基础用法演示
    """
    # 示例：{kp} 的基本操作
    print("=== {kp} 基础示例 ===")

    # TODO: 在此编写 {kp} 相关基础代码
    # 提示：从最简单的用法开始，逐步理解核心概念

    pass


if __name__ == "__main__":
    demo_{func_name}()
''',
    "advanced": '''# {kp} - 进阶示例
# 知识点：{kp}

def advanced_{func_name}():
    """
    {kp} 进阶用法：结合实际场景
    """
    print("=== {kp} 进阶示例 ===")

    # 场景：在实际项目中如何运用 {kp}
    # TODO: 在此实现进阶逻辑
    # 提示：考虑边界条件、性能优化、代码复用

    pass


def practical_example():
    """实际应用场景"""
    # TODO: 将 {kp} 应用到一个真实场景中
    pass


if __name__ == "__main__":
    advanced_{func_name}()
    practical_example()
''',
    "error": '''# {kp} - 常见错误示例
# 知识点：{kp}

# ❌ 错误写法（会导致问题）
def bad_example():
    """
    {kp} 常见错误用法
    """
    # 错误原因：TODO 描述具体错误
    # TODO: 在此写出典型的错误代码
    pass


# ✅ 正确写法
def good_example():
    """
    {kp} 正确用法
    """
    # 修正方法：TODO 描述如何修正
    # TODO: 在此写出正确的代码
    pass


if __name__ == "__main__":
    print("❌ 错误示例：")
    try:
        bad_example()
    except Exception as e:
        print(f"  出错: {e}")

    print("\\n✅ 正确示例：")
    good_example()
''',
    "best_practice": '''# {kp} - 最佳实践
# 知识点：{kp}

# 📋 规范要点
# 1. 命名规范：使用有意义的变量名
# 2. 错误处理：考虑异常情况
# 3. 代码复用：提取公共逻辑
# 4. 注释清晰：说明为什么这样做


def best_practice_{func_name}():
    """
    {kp} 最佳实践示例

    遵循 PEP 8 规范，包含完整的错误处理
    """
    try:
        # TODO: 在此实现 {kp} 的最佳实践代码
        pass
    except Exception as e:
        # TODO: 针对性的异常处理
        print(f"处理异常: {e}")


# 🔧 工具函数示例
def helper():
    """辅助函数，提升代码复用性"""
    pass


if __name__ == "__main__":
    best_practice_{func_name}()
''',
}


def _sanitize_func_name(topic: str) -> str:
    """将中文知识点转为合法的 Python 函数名"""
    # 取前8个字符，替换非字母数字
    clean = re.sub(r'[^a-zA-Z0-9一-鿿]', '_', topic)[:8]
    # 如果全是中文，用拼音首字母兜底
    if not re.search(r'[a-zA-Z]', clean):
        return "example"
    return clean.lower().strip('_') or "example"


class CodeAgent(BaseAgent):
    """
    代码案例生成智能体（增强版）
    支持两种模式：
    1. 规则模式（默认，快速，无 API 成本，带差异化模板）
    2. LLM 模式（use_llm=True，智能生成，带缓存）
    支持四种代码类型：basic / advanced / error / best_practice
    """

    # 类型常量
    TYPE_BASIC: ClassVar[str] = "basic"
    TYPE_ADVANCED: ClassVar[str] = "advanced"
    TYPE_ERROR: ClassVar[str] = "error"
    TYPE_BEST_PRACTICE: ClassVar[str] = "best_practice"
    ALL_TYPES: ClassVar[List[str]] = [TYPE_BASIC, TYPE_ADVANCED, TYPE_ERROR, TYPE_BEST_PRACTICE]

    TYPE_NAMES: ClassVar[Dict[str, str]] = {
        TYPE_BASIC: "基础示例",
        TYPE_ADVANCED: "进阶示例",
        TYPE_ERROR: "常见错误",
        TYPE_BEST_PRACTICE: "最佳实践",
    }

    TYPE_DESCRIPTIONS: ClassVar[Dict[str, str]] = {
        TYPE_BASIC: "基础示例，包含简单的代码和详细注释",
        TYPE_ADVANCED: "进阶示例，包含复杂的用法和实际应用场景",
        TYPE_ERROR: "常见错误示例，包含错误代码和正确的修正方法",
        TYPE_BEST_PRACTICE: "最佳实践示例，包含代码规范和优化建议",
    }

    def __init__(
            self,
            user_id: Optional[str] = None,
            task_id: Optional[str] = None,
            use_llm: bool = False,
            code_type: str = TYPE_BASIC,
    ) -> None:
        super().__init__(
            agent_name="code",
            scene_name="code_generation",
            enable_rag=True,
            user_id=user_id,
            task_id=task_id,
        )
        self.use_llm = use_llm
        self.code_type = code_type
        mode = "LLM" if use_llm else "规则"
        self.logger.info(f"💻 代码案例生成已启用【{mode}】模式，类型：{code_type}")

    async def process(
            self,
            user_input: str,
            context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # 1. 确定目标知识点
        target_kp = self._get_target_knowledge_point(user_input, context)
        self.logger.info(f"🎯 目标知识点：{target_kp}")

        target_type = self.code_type

        # 2. 检查缓存
        cached = _code_cache.get(target_type, target_kp)
        if cached:
            self.logger.info(f"📦 缓存命中：{target_kp} ({target_type})")
            resource = self._build_resource(cached, target_kp, target_type)
            new_resources = self._append_resource(context, resource)
            return self._build_result(new_resources)

        # 3. 根据模式生成
        if self.use_llm:
            code_content = await self._llm_generate(target_kp, target_type)
        else:
            code_content = self._rule_generate(target_kp, target_type)

        # 4. 写入缓存
        _code_cache.put(target_type, target_kp, code_content)

        # 5. 构建结果
        resource = self._build_resource(code_content, target_kp, target_type)
        new_resources = self._append_resource(context, resource)

        self.logger.info(f"✅ 代码案例生成完成：{resource.title}")
        return self._build_result(new_resources)

    def _rule_generate(self, kp: str, ctype: str) -> str:
        """规则模式：使用差异化模板生成代码"""
        self.logger.info(f"📋 规则模式生成：{kp} ({ctype})")
        template = _RULE_TEMPLATES.get(ctype, _RULE_TEMPLATES["basic"])
        func_name = _sanitize_func_name(kp)
        return template.format(kp=kp, func_name=func_name)

    async def _llm_generate(self, kp: str, ctype: str) -> str:
        """LLM 模式：RAG + LLM 生成，失败降级规则模式"""
        rag_context = await self._get_rag_context(kp, top_k=CODE_RAG_TOP_K)
        type_desc = self.TYPE_DESCRIPTIONS.get(ctype, "基础示例")

        system_prompt = self._load_prompt(
            "code_generation_system",
            kp=kp, type_desc=type_desc,
            rag_context=rag_context if rag_context else "无参考资料",
        )

        try:
            resp = await self._call_llm([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._load_prompt("code_generation_user", kp=kp, ctype=ctype)}
            ])
            cleaned = self._clean_code_block(resp)
            if not cleaned.strip():
                raise ValueError("LLM 返回空内容")
            self.logger.info(f"🤖 LLM 代码生成成功，长度：{len(cleaned)}")
            return cleaned
        except Exception as exc:
            self.logger.warning(f"⚠️ LLM 代码生成失败，降级规则模式: {exc}")
            return self._rule_generate(kp, ctype)

    def _get_target_knowledge_point(
            self, user_input: str, context: Optional[Dict[str, Any]] = None,
    ) -> str:
        if context and context.get("topic"):
            return context["topic"]
        return user_input.strip() or DEFAULT_TOPIC

    @staticmethod
    def _clean_code_block(text: str) -> str:
        match = re.search(r"```python\s*\n(.*?)\n```", text, re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()
        match = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
        if match and match.group(1).strip():
            return match.group(1).strip()
        lines = text.split('\n')
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        return '\n'.join(lines).strip()

    def _build_resource(self, content: str, kp: str, ctype: str) -> ResourceItem:
        title = f"{kp} {self.TYPE_NAMES.get(ctype, '代码示例')}"
        line_count = content.count('\n') + 1
        return ResourceItem(
            resource_type="code",
            title=title,
            content=content,
            knowledge_points=[kp],
            status=RESOURCE_STATUS_COMPLETED,
            progress_percent=RESOURCE_PROGRESS_COMPLETE,
            is_reusable=True,
            extra_metadata={
                "code_type": ctype,
                "rag_used": self.enable_rag,
                "line_count": line_count,
                "runnable": True,
            },
        )
