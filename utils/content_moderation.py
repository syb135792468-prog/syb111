"""
utils/content_moderation.py - 讯飞内容审核（audit.iflyaisol.com 文本审核 HTTP 接口）

赛题对齐：A3 要求内容安全过滤，主办方为科大讯飞，使用讯飞文本审核 API。
注意：讯飞 OpenAI 兼容主机 spark-api-open.xf-yun.com/v1 不提供 moderations 端点（404），
      内容审核走独立服务 audit.iflyaisol.com/audit/v2/auditText。
降级策略：API 不可用时放行+日志告警，保证业务可用性。
凭证复用：SPARK_API_KEY（APIKey:APISecret 组合，Bearer 鉴权）。
"""
from __future__ import annotations

import httpx
from typing import List, Optional, Tuple

from utils.logger import get_logger
from utils.llm_client import ContentSecurityError
from config.settings import settings

logger = get_logger(__name__, task_id="moderation")

# 讯飞 audit API 返回的 result 取值：block=明确违规 review=待人工 review pass=安全
# 命中 block 即拦截；review 仅打 warning 放行（无法实时人工复核，过度拦截影响体验）
_BLOCKED_RESULT = "block"

# 审核 API 不可用时的降级标志（避免每次请求都打错误日志）
_moderation_unavailable_logged = False


async def _call_moderation(text: str) -> Optional[dict]:
    """调讯飞文本审核 API，返回响应 JSON 或 None（不可用时降级放行）。"""
    global _moderation_unavailable_logged
    if not settings.SPARK_API_KEY:
        if not _moderation_unavailable_logged:
            logger.warning("内容审核跳过：SPARK_API_KEY 未配置，降级放行")
            _moderation_unavailable_logged = True
        return None
    try:
        async with httpx.AsyncClient(timeout=settings.CONTENT_MODERATION_TIMEOUT) as client:
            resp = await client.post(
                settings.MODERATION_BASE_URL,
                headers={
                    "Authorization": f"Bearer {settings.SPARK_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "content": text[:2000],
                    "isName": "false",
                    "type": "default",
                },
            )
            if resp.status_code != 200:
                if not _moderation_unavailable_logged:
                    logger.warning(f"内容审核 API 返回 {resp.status_code}，降级放行: {resp.text[:200]}")
                    _moderation_unavailable_logged = True
                return None
            payload = resp.json()
            # 讯飞 audit 业务码：code != 0 表示业务失败（鉴权/限流/参数等），按降级处理
            if payload.get("code") != 0:
                if not _moderation_unavailable_logged:
                    logger.warning(f"内容审核 API 业务失败 code={payload.get('code')} message={payload.get('message')}，降级放行")
                    _moderation_unavailable_logged = True
                return None
            _moderation_unavailable_logged = False
            return payload
    except Exception as e:
        if not _moderation_unavailable_logged:
            logger.warning(f"内容审核 API 不可用，降级放行: {e}")
            _moderation_unavailable_logged = True
        return None


def _is_blocked(result: Optional[dict]) -> Tuple[bool, Optional[str]]:
    """判断审核结果是否命中违规。返回 (is_blocked, category)。

    讯飞 audit 响应结构：
      {"code": 0, "data": {"result": "block|review|pass", "riskType": "politics|porn|..."}}
    """
    if not result:
        return False, None
    data = result.get("data") or {}
    audit_result = data.get("result")
    if audit_result == _BLOCKED_RESULT:
        return True, data.get("riskType")
    if audit_result == "review":
        # 边界内容：不拦截，但记 warning 便于后续抽样复盘
        logger.warning(f"内容审核 review 放行: riskType={data.get('riskType')}")
    return False, None


async def moderate_input(messages: List[dict]) -> None:
    """审核用户输入（messages 中 role=user 的内容）。命中则抛 ContentSecurityError。"""
    if not settings.CONTENT_MODERATION_ENABLED:
        return
    user_texts = [m.get("content", "") for m in messages if m.get("role") == "user" and m.get("content")]
    if not user_texts:
        return
    combined = "\n".join(user_texts)[:2000]
    result = await _call_moderation(combined)
    blocked, cat = _is_blocked(result)
    if blocked:
        logger.warning(f"输入审核命中: category={cat}, text_preview={combined[:80]}")
        raise ContentSecurityError("输入内容涉及敏感信息，已被系统拦截。", category=cat)


async def moderate_output(content: str) -> str:
    """审核 LLM 输出。命中则抛 ContentSecurityError，通过则原样返回。"""
    if not settings.CONTENT_MODERATION_ENABLED:
        return content
    if not content or len(content) < 10:
        return content
    result = await _call_moderation(content)
    blocked, cat = _is_blocked(result)
    if blocked:
        logger.warning(f"输出审核命中: category={cat}, text_preview={content[:80]}")
        raise ContentSecurityError("生成的内容涉及敏感信息，已被系统拦截。", category=cat)
    return content
