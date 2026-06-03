"""
内容块转换工具
- legacy_to_content_blocks: 旧格式 (content + {{card:ID}} markers) → content_blocks
- content_blocks_to_flat_text: content_blocks → 纯文本（用于搜索、摘要）
- content_blocks_to_legacy: content_blocks → 旧格式 (content, cards) 兼容
"""
from __future__ import annotations
import re
import json
from typing import List, Dict, Any, Optional


def content_blocks_to_flat_text(blocks: List[Dict[str, Any]]) -> str:
    """从 content_blocks 提取纯文本（用于搜索、摘要、content 字段存储）"""
    parts: List[str] = []
    for b in blocks:
        btype = b.get("type")
        if btype == "text":
            parts.append(b["text"])
        elif btype == "code":
            parts.append(f"```{b.get('language', 'python')}\n{b['code']}\n```")
        elif btype == "card":
            parts.append(f"[{b.get('card_type', 'card')}: {b.get('title', '')}]")
        elif btype == "thinking":
            pass  # thinking 不计入平坦文本
    return "\n\n".join(parts)


def content_blocks_to_legacy(blocks: List[Dict[str, Any]]) -> tuple[str, list]:
    """将 content_blocks 转为旧格式 (content, cards) 兼容旧前端"""
    content_parts: List[str] = []
    cards: List[Dict[str, Any]] = []
    for b in blocks:
        btype = b.get("type")
        if btype == "text":
            content_parts.append(b["text"])
        elif btype == "code":
            content_parts.append(f"```{b.get('language', 'python')}\n{b['code']}\n```")
        elif btype == "card":
            card_id = b["card_id"]
            content_parts.append(f"{{{{card:{card_id}}}}}")
            cards.append({
                "id": str(card_id),
                "type": b["card_type"],
                "title": b.get("title", ""),
                "data": b.get("data"),
            })
    return "\n\n".join(content_parts), cards


def legacy_to_content_blocks(content: str, cards: Optional[list] = None) -> List[Dict[str, Any]]:
    """将旧格式 (content + {{card:ID}} markers) 转为 content_blocks（读取旧数据时用）"""
    blocks: List[Dict[str, Any]] = []
    if not content and not cards:
        return blocks

    marker_re = re.compile(r'\{\{card:(\d+)\}\}')
    cards_map: Dict[str, Any] = {}
    for c in (cards or []):
        cid = c.get("id")
        if cid is not None:
            cards_map[str(cid)] = c
    last_idx = 0

    for match in marker_re.finditer(content):
        # marker 前的文本
        if match.start() > last_idx:
            text_part = content[last_idx:match.start()].strip()
            if text_part:
                blocks.append({"type": "text", "text": text_part})
        # card block
        card_id_str = match.group(1)
        card = cards_map.get(card_id_str)
        if card:
            blocks.append({
                "type": "card",
                "card_type": card.get("type", "unknown"),
                "card_id": int(card_id_str),
                "title": card.get("title", ""),
                "data": card.get("data"),
            })
        else:
            # card 数据不在列表中，仍然创建 block（data 为空）
            blocks.append({
                "type": "card",
                "card_type": "unknown",
                "card_id": int(card_id_str),
                "title": "",
                "data": None,
            })
        last_idx = match.end()

    # 剩余文本
    if last_idx < len(content):
        tail = content[last_idx:].strip()
        if tail:
            blocks.append({"type": "text", "text": tail})

    # 如果没有任何 marker，整个 content 作为一个 text block
    if not blocks and content:
        blocks.append({"type": "text", "text": content})

    return blocks


def parse_response_to_blocks(response: str, resource_map: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """将含 {{card:DB_ID}} 的 final_response 解析为 block 列表（用于流式输出）"""
    blocks: List[Dict[str, Any]] = []
    marker_re = re.compile(r'\{\{card:(\d+)\}\}')
    last_idx = 0

    for match in marker_re.finditer(response):
        if match.start() > last_idx:
            text = response[last_idx:match.start()].strip()
            if text:
                blocks.append({"type": "text", "text": text})
        card_id = int(match.group(1))
        res = resource_map.get(card_id, {})
        blocks.append({
            "type": "card",
            "card_id": card_id,
            "card_type": res.get("resource_type", "unknown"),
            "title": res.get("title", ""),
            "data": res.get("content"),
        })
        last_idx = match.end()

    if last_idx < len(response):
        tail = response[last_idx:].strip()
        if tail:
            blocks.append({"type": "text", "text": tail})

    return blocks


def build_resource_map(resource_list: List[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """从 resource_list 构建 id → resource 的映射"""
    result: Dict[int, Dict[str, Any]] = {}
    for r in resource_list:
        rid = r.get("id")
        if rid is not None:
            result[int(rid)] = r
    return result
