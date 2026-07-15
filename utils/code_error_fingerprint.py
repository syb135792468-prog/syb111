"""
utils/code_error_fingerprint.py - 代码错误指纹

单次异常只标 weak_signal，同类指纹累计达 WEAK_SIGNAL_THRESHOLD 才降 posterior。
指纹 = error_type + traceback 最后一帧的 basename:funcname（去行号，行号变化不改指纹）。
"""
from __future__ import annotations

import re
import hashlib
from typing import Tuple, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from utils.code_error_analyzer import code_error_analyzer


def build_fingerprint(stderr: str) -> Tuple[str, str]:
    """从 stderr 提取 (error_type, fingerprint_hash)。

    fingerprint = MD5(error_type|basename:funcname)[:12]
    去掉行号：同一函数同一错误类型视为同类，不同行号不改指纹。
    """
    if not stderr:
        return ("unknown", "")

    analysis = code_error_analyzer.analyze_error_output(stderr)
    error_type = analysis.get("error_type", "unknown")

    # 提取 traceback 最后一帧（File "path", line N, in funcname）
    frames = re.findall(r'File "([^"]+)", line \d+, in (\w+)', stderr)
    last_frame = ""
    if frames:
        filepath, funcname = frames[-1]
        # basename 去目录，保留 funcname，去掉行号
        last_frame = f"{filepath.split('/')[-1].split(chr(92))[-1]}:{funcname}"

    fp = hashlib.md5(f"{error_type}|{last_frame}".encode()).hexdigest()[:12]
    return (error_type, fp)


async def count_same_fingerprint(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    fingerprint: str,
) -> int:
    """查该用户该节点同指纹的 evidence 数（不含本次，用于判断是否达到阈值）。

    查 knowledge_mastery_evidence.detail->>'fingerprint' = fingerprint。
    """
    if not fingerprint:
        return 0
    result = await session.execute(
        text(
            "SELECT COUNT(*) FROM knowledge_mastery_evidence "
            "WHERE user_id = :uid AND node_code = :node "
            "AND json_extract(detail, '$.fingerprint') = :fp"
        ),
        {"uid": user_id, "node": node_code, "fp": fingerprint},
    )
    return int(result.scalar() or 0)
