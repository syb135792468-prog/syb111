import pytest
import sys
import types
from importlib import import_module
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

AGENTS_DIR = Path(__file__).resolve().parents[1] / "agents"
if "agents" not in sys.modules:
    agents_pkg = types.ModuleType("agents")
    agents_pkg.__path__ = [str(AGENTS_DIR)]
    sys.modules["agents"] = agents_pkg

content_agent_module = import_module("agents.content_agent")
ContentAgent = content_agent_module.ContentAgent
ContentType = content_agent_module.ContentType


@pytest.mark.asyncio
async def test_slides_prompt_supports_topic_and_rag_context_placeholders():
    agent = ContentAgent.__new__(ContentAgent)
    agent.content_type = ContentType.SLIDES
    agent.logger = MagicMock()
    agent._get_rag_context = AsyncMock(return_value="参考资料：函数可以封装可复用逻辑。")
    agent._call_llm = AsyncMock(return_value="# 函数\n\n---\n\n## 核心语法")

    result = await ContentAgent._llm_generate(agent, "函数")

    assert result == "# 函数\n\n---\n\n## 核心语法"
    agent._call_llm.assert_awaited_once()

    messages = agent._call_llm.await_args.args[0]
    assert "知识点：函数" in messages[1]["content"]
    assert "参考资料：函数可以封装可复用逻辑。" in messages[1]["content"]
