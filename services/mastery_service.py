"""
services/mastery_service.py - 知识图谱掌握度服务

设计原则：
- 证据不可变：add_evidence 只追加，永不修改已有证据
- 掌握度可重算：mastery_score 由证据汇总得出，规则可调整
- 状态机自洽：4 态（locked/available/learning/mastered）由掌握度+前置依赖决定
- profile 投影：图谱是真相源，UserProfile.weak/mastered_points 是派生摘要

掌握度规则（用户对齐：不需要太严格）：
- 权重：quiz 50% + code 20% + path_node 30%（无 path_node 证据时退化为 quiz 70% + code 30%）
- quiz 维度：按 evidence.weight 加权计算正确率（避免次要知识点被当主知识点评分）
- 阈值：50 分即"已掌握"
- 证据门槛：2 次证据才可标 mastered
- 代码维度：3 次成功实践即满分（简化）
"""
from __future__ import annotations

from typing import Optional, Dict, List, Any, Sequence
from datetime import datetime, UTC

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models.knowledge_graph import (
    KnowledgeNode, KnowledgeEdge,
    UserKnowledgeMastery, KnowledgeMasteryEvidence,
    QuestionKnowledgeMap, UserMisconception,
)
from models.profile import UserProfile
from config.constants import (
    DIFFICULTY_EVIDENCE_WEIGHT,
    POSTERIOR_PRIOR, POSTERIOR_PRIOR_WEIGHT,
    UNCERTAINTY_DEFAULT, UNCERTAINTY_MIN_EVIDENCE,
    SIGNAL_TYPE_DIRECT, SIGNAL_TYPE_INFERRED,
    EVIDENCE_SOURCE_QUIZ, EVIDENCE_SOURCE_PATH, EVIDENCE_SOURCE_CODE,
    EVIDENCE_SOURCE_CHAT_JUDGE,
    HINT_PENALTY, COPY_PENALTY, WEAK_SIGNAL_THRESHOLD,
    MISCONCEPTION_SUSPECTED_CONFIDENCE,
    CHAT_JUDGE_WEIGHT_FACTOR, CHAT_JUDGE_LOW_CONFIDENCE_THRESHOLD,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="mastery_service")


# ==================== 常量 ====================

MASTERY_THRESHOLD: float = 50.0      # 50 分即掌握
EVIDENCE_THRESHOLD: int = 2          # 至少 2 次证据
CODE_FULL_COUNT: int = 3             # 3 次代码实践即满分
QUIZ_WEIGHT: float = 0.7
CODE_WEIGHT: float = 0.3

STATE_LOCKED = "locked"
STATE_AVAILABLE = "available"
STATE_LEARNING = "learning"
STATE_MASTERED = "mastered"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ==================== 核心 API ====================

async def add_evidence(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    source_type: str,
    score: float,
    source_id: Optional[int] = None,
    weight: float = 1.0,
    detail: Optional[Dict[str, Any]] = None,
    signal_type: str = SIGNAL_TYPE_DIRECT,
    source_weight: float = 1.0,
    difficulty: Optional[str] = None,
    weak_signal: bool = False,
) -> UserKnowledgeMastery:
    """
    写入一条不可变证据，重算掌握度，更新节点状态。

    Args:
        session: 异步会话
        user_id: 用户 ID
        node_code: 知识点 code
        source_type: quiz_attempt / path_node / code_run / review / manual / chat_judge
        score: 0-100
        source_id: 来源记录 ID（可空）
        weight: 该证据对节点的权重 0-1
        detail: 附加信息
        signal_type: direct=直接证据 / inferred=图谱推断（阶段4）
        source_weight: 证据质量权重 0-1（难度*提示*复制惩罚）
        difficulty: easy/medium/hard
        weak_signal: True 时证据仍写入留痕但不进 posterior 加总

    Returns:
        更新后的 UserKnowledgeMastery 记录
    """
    score = max(0.0, min(100.0, float(score)))
    weight = max(0.0, min(1.0, float(weight)))
    source_weight = max(0.0, min(1.0, float(source_weight)))

    # 0. 幂等预检：对有 source_id 的自动事件，若已存在同 (user,node,source_type,source_id) 证据则跳过
    #    （网络重试/重复提交不会重复累积；source_id 为 None 的 manual/review/chat_judge 不受约束）
    if source_id is not None:
        existing = (
            await session.execute(
                select(KnowledgeMasteryEvidence.id).where(
                    and_(
                        KnowledgeMasteryEvidence.user_id == user_id,
                        KnowledgeMasteryEvidence.node_code == node_code,
                        KnowledgeMasteryEvidence.source_type == source_type,
                        KnowledgeMasteryEvidence.source_id == source_id,
                    )
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.debug(
                f"证据已存在，跳过 user={user_id} node={node_code} "
                f"source={source_type} source_id={source_id}"
            )
            return await _get_or_create_mastery(session, user_id, node_code)

    # 1. 写入不可变证据（含新字段 signal_type/source_weight/difficulty/weak_signal）
    evidence = KnowledgeMasteryEvidence(
        user_id=user_id,
        node_code=node_code,
        source_type=source_type,
        source_id=source_id,
        score=score,
        weight=weight,
        detail=detail or {},
        signal_type=signal_type,
        source_weight=source_weight,
        difficulty=difficulty,
        weak_signal=1 if weak_signal else 0,
    )
    session.add(evidence)

    # 2. 取或创建用户节点掌握记录
    mastery = await _get_or_create_mastery(session, user_id, node_code)

    # 3. 累加统计字段（quiz 维度按正确性，code 维度按成功次数）
    #    weak_signal 证据也计数留痕，但 _update_posterior 会跳过它们
    if source_type == EVIDENCE_SOURCE_QUIZ:
        mastery.quiz_total_count += 1
        if score >= 60:  # 60 分以上算答对
            mastery.quiz_correct_count += 1
    elif source_type == EVIDENCE_SOURCE_CODE:
        if score >= 60:  # 代码运行成功
            mastery.code_practice_count += 1

    mastery.evidence_count += 1
    mastery.last_evidence_at = _now()

    # 4. 重算 posterior（跳过 weak_signal 证据）+ 同步派生字段 mastery_score
    latest_path_score = await _get_latest_path_score(session, user_id, node_code)
    await _update_posterior(session, mastery, latest_path_score)

    # 5. 更新状态（考虑前置依赖 + per-node 阈值）
    node_threshold = await _get_node_threshold(session, node_code)
    await _update_state(session, mastery, node_threshold)

    mastery.calculated_at = _now()
    await session.flush()

    logger.debug(
        f"证据写入 user={user_id} node={node_code} "
        f"source={source_type} score={score} weak={weak_signal} -> "
        f"posterior={mastery.posterior} mastery={mastery.mastery_score} state={mastery.state}"
    )
    return mastery


async def recalculate_all_mastery(
    session: AsyncSession,
    user_id: int,
) -> int:
    """
    从所有历史证据重算用户全部节点的掌握度。
    用于评分规则调整后或数据修复后。

    Returns: 重算的节点数
    """
    # 取用户所有节点
    mastery_rows = (
        await session.execute(
            select(UserKnowledgeMastery).where(UserKnowledgeMastery.user_id == user_id)
        )
    ).scalars().all()

    for mastery in mastery_rows:
        # 重置统计字段，从证据重新累加
        mastery.quiz_total_count = 0
        mastery.quiz_correct_count = 0
        mastery.code_practice_count = 0
        mastery.evidence_count = 0

        evidences = (
            await session.execute(
                select(KnowledgeMasteryEvidence)
                .where(
                    and_(
                        KnowledgeMasteryEvidence.user_id == user_id,
                        KnowledgeMasteryEvidence.node_code == mastery.node_code,
                    )
                )
                .order_by(KnowledgeMasteryEvidence.created_at)
            )
        ).scalars().all()

        for ev in evidences:
            mastery.evidence_count += 1
            if ev.source_type == "quiz_attempt":
                mastery.quiz_total_count += 1
                if ev.score >= 60:
                    mastery.quiz_correct_count += 1
            elif ev.source_type == "code_run":
                if ev.score >= 60:
                    mastery.code_practice_count += 1

        latest_path_score = await _get_latest_path_score(session, user_id, mastery.node_code)
        await _update_posterior(session, mastery, latest_path_score)
        node_threshold = await _get_node_threshold(session, mastery.node_code)
        await _update_state(session, mastery, node_threshold)
        mastery.calculated_at = _now()

    count = len(mastery_rows)
    logger.info(f"用户 {user_id} 重算完成，共 {count} 个节点")
    return count


# ==================== 查询 API ====================

async def get_user_node(
    session: AsyncSession,
    user_id: int,
    node_code: str,
) -> Optional[UserKnowledgeMastery]:
    return (
        await session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == user_id,
                    UserKnowledgeMastery.node_code == node_code,
                )
            )
        )
    ).scalar_one_or_none()


async def get_effective_state(
    session: AsyncSession,
    user_id: int,
    node_code: str,
) -> str:
    """轻量推断节点有效状态（含跨模块前置），不查错题/路径。

    有 mastery 记录 -> 直接返回 mastery.state。
    无 mastery 记录 -> 查全量 prerequisite（含跨模块），全部 mastered 才 available，否则 locked。

    用于 practice 接口前置校验，避免每次都跑完整 get_node_detail。
    """
    mastery = await get_user_node(session, user_id, node_code)
    if mastery:
        return mastery.state

    # 查全量 prerequisite（含跨模块）
    prereq_codes = (
        await session.execute(
            select(KnowledgeEdge.source_code).where(
                and_(
                    KnowledgeEdge.target_code == node_code,
                    KnowledgeEdge.edge_type == "prerequisite",
                )
            )
        )
    ).scalars().all()
    if not prereq_codes:
        return STATE_AVAILABLE

    prereq_mastery = (
        await session.execute(
            select(UserKnowledgeMastery.node_code, UserKnowledgeMastery.state).where(
                and_(
                    UserKnowledgeMastery.user_id == user_id,
                    UserKnowledgeMastery.node_code.in_(prereq_codes),
                )
            )
        )
    ).scalars().all()
    # Every prerequisite needs its own mastered record. Counting states in a set
    # collapses multiple "mastered" values and leaves multi-prerequisite nodes locked.
    prereq_states = {code: state for code, state in prereq_mastery}
    if all(prereq_states.get(code) == STATE_MASTERED for code in prereq_codes):
        return STATE_AVAILABLE
    return STATE_LOCKED


async def get_user_graph(
    session: AsyncSession,
    user_id: int,
    module_filter: Optional[str] = None,
    state_filter: Optional[str] = None,
) -> Dict[str, Any]:
    """
    查询用户局部图谱快照。

    Returns:
        {
          "nodes": [{code, name, module, level, difficulty, mastery_score, state, ...}],
          "edges": [{source_code, target_code, edge_type}],
          "stats": {total, mastered, learning, available, locked}
        }
    """
    # 节点（模块内，用于展示）
    node_stmt = select(KnowledgeNode).where(KnowledgeNode.is_active == 1)
    if module_filter:
        node_stmt = node_stmt.where(KnowledgeNode.module == module_filter)
    node_stmt = node_stmt.order_by(KnowledgeNode.module, KnowledgeNode.level, KnowledgeNode.code)
    nodes = (await session.execute(node_stmt)).scalars().all()

    node_codes = [n.code for n in nodes]
    node_code_set = set(node_codes)

    # 跨模块前置：查所有 target 在模块内、source 在模块外的 prerequisite 边
    # 这些跨模块前置节点的 mastery 也要查到，否则会被当成 None 误判 locked
    extra_prereq_codes: set = set()
    if node_codes:
        cross_prereq_rows = (
            await session.execute(
                select(KnowledgeEdge.source_code, KnowledgeEdge.target_code).where(
                    and_(
                        KnowledgeEdge.edge_type == "prerequisite",
                        KnowledgeEdge.target_code.in_(node_codes),
                    )
                )
            )
        ).all()
        for src, tgt in cross_prereq_rows:
            if src not in node_code_set:
                extra_prereq_codes.add(src)

    # 全量 code 集合：模块内 + 跨模块前置（mastery 查询用全量，状态推断才正确）
    full_codes = node_code_set | extra_prereq_codes

    # 用户掌握状态（查全量，含跨模块前置节点）
    mastery_map: Dict[str, UserKnowledgeMastery] = {}
    if full_codes:
        mastery_rows = (
            await session.execute(
                select(UserKnowledgeMastery).where(
                    and_(
                        UserKnowledgeMastery.user_id == user_id,
                        UserKnowledgeMastery.node_code.in_(full_codes),
                    )
                )
            )
        ).scalars().all()
        mastery_map = {m.node_code: m for m in mastery_rows}

    # 前置边（用于状态推断，含跨模块）：target 在模块内的所有 prerequisite 边
    prereq_edges: List[KnowledgeEdge] = []
    if node_codes:
        prereq_edges = list((
            await session.execute(
                select(KnowledgeEdge).where(
                    and_(
                        KnowledgeEdge.edge_type == "prerequisite",
                        KnowledgeEdge.target_code.in_(node_codes),
                    )
                )
            )
        ).scalars().all())

    # 展示边（用于前端渲染，仅模块内全类型边，避免画跨模块长线）
    display_edges: List[KnowledgeEdge] = []
    if node_codes:
        display_edges = list((
            await session.execute(
                select(KnowledgeEdge).where(
                    and_(
                        KnowledgeEdge.source_code.in_(node_codes),
                        KnowledgeEdge.target_code.in_(node_codes),
                    )
                )
            )
        ).scalars().all())

    # 前置索引：target_code -> [source_code, ...]（仅 prerequisite 边，含跨模块）
    prereq_index: Dict[str, List[str]] = {}
    for e in prereq_edges:
        prereq_index.setdefault(e.target_code, []).append(e.source_code)

    def _infer_state_for_no_mastery(code: str) -> str:
        """无 mastery 记录的节点按前置是否全部 mastered 推断状态"""
        prereqs = prereq_index.get(code, [])
        if not prereqs:
            return STATE_AVAILABLE
        for pcode in prereqs:
            pm = mastery_map.get(pcode)
            if not pm or pm.state != STATE_MASTERED:
                return STATE_LOCKED
        return STATE_AVAILABLE

    # 组装节点列表
    node_list = []
    stats = {STATE_LOCKED: 0, STATE_AVAILABLE: 0, STATE_LEARNING: 0, STATE_MASTERED: 0}
    for n in nodes:
        m = mastery_map.get(n.code)
        if m:
            state = m.state
        else:
            state = _infer_state_for_no_mastery(n.code)
        # state_filter 在 Python 层做（避免 JOIN 复杂度）
        if state_filter and state != state_filter:
            continue
        stats[state] = stats.get(state, 0) + 1
        node_list.append({
            "code": n.code,
            "name": n.name,
            "module": n.module,
            "level": n.level,
            "difficulty": n.difficulty,
            "estimated_time": n.estimated_time,
            "description": n.description,
            "mastery_score": m.mastery_score if m else 0.0,
            "state": state,
            "evidence_count": m.evidence_count if m else 0,
            "quiz_correct_count": m.quiz_correct_count if m else 0,
            "quiz_total_count": m.quiz_total_count if m else 0,
            "code_practice_count": m.code_practice_count if m else 0,
            "last_evidence_at": m.last_evidence_at.isoformat() if m and m.last_evidence_at else None,
        })

    return {
        "nodes": node_list,
        "edges": [
            {"source_code": e.source_code, "target_code": e.target_code, "edge_type": e.edge_type}
            for e in display_edges
        ],
        "stats": {
            "total": len(node_list),
            "mastered": stats[STATE_MASTERED],
            "learning": stats[STATE_LEARNING],
            "available": stats[STATE_AVAILABLE],
            "locked": stats[STATE_LOCKED],
        },
    }


async def get_node_detail(
    session: AsyncSession,
    user_id: int,
    node_code: str,
) -> Optional[Dict[str, Any]]:
    """节点详情：节点信息 + 用户掌握 + 前置节点状态 + 最近证据"""
    node = (
        await session.execute(
            select(KnowledgeNode).where(KnowledgeNode.code == node_code)
        )
    ).scalar_one_or_none()
    if not node:
        return None

    mastery = await get_user_node(session, user_id, node_code)

    # 前置节点
    prereq_codes = (
        await session.execute(
            select(KnowledgeEdge.source_code).where(
                and_(
                    KnowledgeEdge.target_code == node_code,
                    KnowledgeEdge.edge_type == "prerequisite",
                )
            )
        )
    ).scalars().all()

    prereq_states = []
    if prereq_codes:
        prereq_mastery = (
            await session.execute(
                select(UserKnowledgeMastery).where(
                    and_(
                        UserKnowledgeMastery.user_id == user_id,
                        UserKnowledgeMastery.node_code.in_(prereq_codes),
                    )
                )
            )
        ).scalars().all()
        prereq_map = {m.node_code: m for m in prereq_mastery}

        prereq_node_names = {
            n.code: n.name
            for n in (
                await session.execute(
                    select(KnowledgeNode).where(KnowledgeNode.code.in_(prereq_codes))
                )
            ).scalars().all()
        }

        for code in prereq_codes:
            m = prereq_map.get(code)
            # 前置节点的有效状态：有 mastery 用 mastery.state；无 mastery 时若该前置自己还有未满足的前置则也是 locked
            if m:
                p_state = m.state
            else:
                p_state = await get_effective_state(session, user_id, code)
            prereq_states.append({
                "code": code,
                "name": prereq_node_names.get(code, code),
                "state": p_state,
                "mastery_score": m.mastery_score if m else 0.0,
            })

    # 当前节点有效状态：有 mastery 用 mastery.state；无 mastery 看前置是否全部 mastered
    if mastery:
        effective_state = mastery.state
    else:
        prereqs_all_mastered = all(
            p["state"] == STATE_MASTERED for p in prereq_states
        ) if prereq_states else True
        effective_state = STATE_AVAILABLE if prereqs_all_mastered else STATE_LOCKED

    # 最近 10 条证据
    recent_evidences = (
        await session.execute(
            select(KnowledgeMasteryEvidence)
            .where(
                and_(
                    KnowledgeMasteryEvidence.user_id == user_id,
                    KnowledgeMasteryEvidence.node_code == node_code,
                )
            )
            .order_by(KnowledgeMasteryEvidence.created_at.desc())
            .limit(10)
        )
    ).scalars().all()

    # 错题数：按 node.name 和 aliases 匹配 ErrorBook.knowledge_point（排除已掌握的错题）
    from models.error_book import ErrorBook
    match_names = [node.name] + list(node.aliases or [])
    error_count = (
        await session.execute(
            select(func.count(ErrorBook.id)).where(
                and_(
                    ErrorBook.user_id == user_id,
                    ErrorBook.knowledge_point.in_(match_names),
                    ErrorBook.mastered == False,  # 仅未掌握的错题
                )
            )
        )
    ).scalar_one()

    # 关联学习路径：查 LearningPath+LearningPathNode 中 knowledge_point 匹配的
    from models.learning_path import LearningPath, LearningPathNode
    related_paths_rows = (
        await session.execute(
            select(
                LearningPath.id, LearningPath.title,
                LearningPathNode.id, LearningPathNode.status,
            )
            .join(LearningPathNode, LearningPathNode.learning_path_id == LearningPath.id)
            .where(
                and_(
                    LearningPath.user_id == user_id,
                    LearningPath.status == "active",
                    LearningPathNode.knowledge_point.in_(match_names),
                )
            )
            .order_by(LearningPath.id)
        )
    ).all()
    related_paths = [
        {
            "path_id": r[0],
            "path_title": r[1],
            "node_id": r[2],
            "node_status": r[3],
        }
        for r in related_paths_rows
    ]

    return {
        "node": node.to_dict(),
        "mastery": mastery.to_dict() if mastery else None,
        "effective_state": effective_state,
        "prerequisites": prereq_states,
        "recent_evidences": [e.to_dict() for e in recent_evidences],
        "threshold": node.mastery_threshold,
        "evidence_threshold": EVIDENCE_THRESHOLD,
        "error_count": int(error_count or 0),
        "related_paths": related_paths,
    }


# ==================== Profile 投影 ====================

async def project_to_profile(
    session: AsyncSession,
    user_id: int,
) -> None:
    """
    把图谱状态投影到 UserProfile.weak_points / mastered_points。
    保留 name-based 兼容字段，供旧路径生成和推荐使用。
    """
    profile = (
        await session.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
    ).scalar_one_or_none()
    if not profile:
        return

    # 取所有 mastered 和 learning（learning 中 score<阈值的算 weak）
    mastery_rows = (
        await session.execute(
            select(UserKnowledgeMastery, KnowledgeNode.name)
            .join(KnowledgeNode, UserKnowledgeMastery.node_code == KnowledgeNode.code)
            .where(UserKnowledgeMastery.user_id == user_id)
        )
    ).all()

    mastered_names: List[str] = []
    weak_names: List[str] = []
    for m, name in mastery_rows:
        if m.state == STATE_MASTERED:
            mastered_names.append(name)
        elif m.state == STATE_LEARNING and m.mastery_score < MASTERY_THRESHOLD:
            weak_names.append(name)

    # 增量合并：保留旧 name（避免图谱未覆盖的知识点被清空）
    existing_mastered = set(profile.mastered_points or [])
    existing_weak = set(profile.weak_points or [])

    # 图谱覆盖的 name 视为新真相，替换；图谱未覆盖的旧 name 保留
    mastered_set = existing_mastered | set(mastered_names)
    weak_set = (existing_weak - set(mastered_names)) | set(weak_names)

    profile.mastered_points = sorted(mastered_set)
    profile.weak_points = sorted(weak_set)
    profile.updated_at = _now()


# ==================== 内部辅助 ====================

async def _get_or_create_mastery(
    session: AsyncSession,
    user_id: int,
    node_code: str,
) -> UserKnowledgeMastery:
    mastery = (
        await session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == user_id,
                    UserKnowledgeMastery.node_code == node_code,
                )
            )
        )
    ).scalar_one_or_none()

    if not mastery:
        mastery = UserKnowledgeMastery(
            user_id=user_id,
            node_code=node_code,
            mastery_score=0.0,
            posterior=0.0,
            uncertainty=UNCERTAINTY_DEFAULT,
            review_risk=0.0,
            state=STATE_AVAILABLE,
            evidence_count=0,
            quiz_correct_count=0,
            quiz_total_count=0,
            code_practice_count=0,
            calculated_at=_now(),
        )
        session.add(mastery)
        await session.flush()
    return mastery


async def _update_posterior(
    session: AsyncSession,
    mastery: UserKnowledgeMastery,
    latest_path_score: Optional[float] = None,
) -> None:
    """
    根据证据重算 posterior（0-1 掌握概率），同步派生字段 mastery_score（0-100）。

    简化版（阶段5换对数几率贝叶斯更新）：
    - 跳过 weak_signal=1 的证据（单次代码异常不降 posterior）
    - effective_weight = weight * source_weight（难度/提示/复制惩罚体现在 source_weight）
    - 先验：POSTERIOR_PRIOR(0.4) * POSTERIOR_PRIOR_WEIGHT(2.0)
    - path_node 信号作为额外维度，0.7 posterior + 0.3 path_score
    - uncertainty 随证据数递减（阶段5换贝叶斯后验方差）
    - last_verified 仅在有非弱信号证据时更新
    """
    evidences = (
        await session.execute(
            select(
                KnowledgeMasteryEvidence.score,
                KnowledgeMasteryEvidence.weight,
                KnowledgeMasteryEvidence.source_weight,
                KnowledgeMasteryEvidence.weak_signal,
                KnowledgeMasteryEvidence.source_type,
            ).where(
                and_(
                    KnowledgeMasteryEvidence.user_id == mastery.user_id,
                    KnowledgeMasteryEvidence.node_code == mastery.node_code,
                )
            )
        )
    ).all()

    num = POSTERIOR_PRIOR * POSTERIOR_PRIOR_WEIGHT
    den = POSTERIOR_PRIOR_WEIGHT
    has_strong_signal = False
    for score, weight, source_weight, weak, stype in evidences:
        if weak:  # 弱信号不进 posterior 加总
            continue
        has_strong_signal = True
        ew = float(weight) * float(source_weight)
        num += (float(score) / 100.0) * ew
        den += ew

    posterior = max(0.0, min(1.0, num / den)) if den > 0 else POSTERIOR_PRIOR

    # path_node 信号作为额外维度（保持与旧逻辑一致的综合评估）
    if latest_path_score is not None:
        path_p = max(0.0, min(1.0, float(latest_path_score) / 100.0))
        posterior = posterior * 0.7 + path_p * 0.3

    mastery.posterior = round(posterior, 4)
    mastery.mastery_score = round(posterior * 100.0, 1)  # 派生字段，前端兼容

    # 不确定度：证据少则高，证据多则低（阶段5换贝叶斯后验方差）
    if mastery.evidence_count >= UNCERTAINTY_MIN_EVIDENCE:
        mastery.uncertainty = max(0.1, 0.9 - mastery.evidence_count * 0.1)
    else:
        mastery.uncertainty = UNCERTAINTY_DEFAULT

    # last_verified：仅在有非弱信号证据时更新
    if has_strong_signal:
        mastery.last_verified = _now()


async def _get_node_threshold(session: AsyncSession, node_code: str) -> float:
    """取节点 per-node 掌握度阈值，查不到则回退全局常量 MASTERY_THRESHOLD。"""
    row = (
        await session.execute(
            select(KnowledgeNode.mastery_threshold).where(KnowledgeNode.code == node_code)
        )
    ).scalar_one_or_none()
    if row is None:
        return MASTERY_THRESHOLD
    try:
        return float(row)
    except (TypeError, ValueError):
        return MASTERY_THRESHOLD


async def _update_state(
    session: AsyncSession,
    mastery: UserKnowledgeMastery,
    node_threshold: Optional[float] = None,
) -> None:
    """根据掌握度分数和前置依赖更新节点状态。

    Args:
        node_threshold: 该节点的掌握度阈值。None 时按节点 mastery_threshold 字段查询（默认 50.0）。
    """
    old_state = mastery.state

    if node_threshold is None:
        node_threshold = await _get_node_threshold(session, mastery.node_code)

    # 1. 检查前置是否全部 mastered（无前置则视为满足）
    prereq_codes = (
        await session.execute(
            select(KnowledgeEdge.source_code).where(
                and_(
                    KnowledgeEdge.target_code == mastery.node_code,
                    KnowledgeEdge.edge_type == "prerequisite",
                )
            )
        )
    ).scalars().all()

    if prereq_codes:
        prereq_mastery = (
            await session.execute(
                select(UserKnowledgeMastery).where(
                    and_(
                        UserKnowledgeMastery.user_id == mastery.user_id,
                        UserKnowledgeMastery.node_code.in_(prereq_codes),
                    )
                )
            )
        ).scalars().all()

        prereq_map = {m.node_code: m for m in prereq_mastery}
        all_prereq_mastered = all(
            prereq_map.get(code) and prereq_map[code].state == STATE_MASTERED
            for code in prereq_codes
        )
        if not all_prereq_mastered:
            mastery.state = STATE_LOCKED
            return

    # 2. 前置满足，按掌握度判定（用节点自身阈值；node_threshold 仍 0-100 语义，posterior*100 对齐）
    if mastery.evidence_count >= EVIDENCE_THRESHOLD and mastery.posterior * 100.0 >= node_threshold:
        mastery.state = STATE_MASTERED
    elif mastery.evidence_count >= 1:
        mastery.state = STATE_LEARNING
    else:
        mastery.state = STATE_AVAILABLE

    # 3. 节点变为 mastered 时，联动刷新下游节点（下游可能因前置刚满足而从 locked 解锁）
    #    （无记录的下游节点由 get_user_graph 在查询时按前置推断，无需创建空记录）
    if mastery.state == STATE_MASTERED and old_state != STATE_MASTERED:
        await _refresh_downstream_states(session, mastery.user_id, mastery.node_code)


async def _refresh_downstream_states(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    depth: int = 0,
) -> None:
    """节点解锁后，刷新直接下游节点的状态（可能从 locked 变为 available/learning/mastered）。

    递归刷新：当下游节点也解锁时，继续刷新它的下游。深度限制避免极端环。
    只刷新已有 mastery 记录的下游节点，避免为未接触的节点创建空记录。
    """
    if depth > 10:  # 保险深度限制
        return

    downstream_codes = (
        await session.execute(
            select(KnowledgeEdge.target_code).where(
                and_(
                    KnowledgeEdge.source_code == node_code,
                    KnowledgeEdge.edge_type == "prerequisite",
                )
            )
        )
    ).scalars().all()

    if not downstream_codes:
        return

    # 只取已有 mastery 记录的下游
    downstream_mastery = (
        await session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == user_id,
                    UserKnowledgeMastery.node_code.in_(downstream_codes),
                )
            )
        )
    ).scalars().all()

    for dm in downstream_mastery:
        dm_old_state = dm.state
        await _update_state(session, dm)  # 递归调用，会自动继续刷新下游
        if dm_old_state == STATE_LOCKED and dm.state != STATE_LOCKED:
            await _refresh_downstream_states(session, user_id, dm.node_code, depth + 1)


async def _get_latest_path_score(
    session: AsyncSession,
    user_id: int,
    node_code: str,
) -> Optional[float]:
    """取最近一条 path_node 证据的分数，作为综合掌握度信号"""
    row = (
        await session.execute(
            select(KnowledgeMasteryEvidence.score)
            .where(
                and_(
                    KnowledgeMasteryEvidence.user_id == user_id,
                    KnowledgeMasteryEvidence.node_code == node_code,
                    KnowledgeMasteryEvidence.source_type == "path_node",
                )
            )
            .order_by(KnowledgeMasteryEvidence.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return float(row) if row is not None else None


# ==================== 高层回写接口 ====================

async def _get_question_node_map(
    session: AsyncSession,
    resource_id: int,
    question_index: int,
) -> List[tuple]:
    """查题目到知识点的映射（一题对多节点），返回 [(node_code, weight), ...]。"""
    return list((
        await session.execute(
            select(QuestionKnowledgeMap.node_code, QuestionKnowledgeMap.weight)
            .where(
                and_(
                    QuestionKnowledgeMap.resource_id == resource_id,
                    QuestionKnowledgeMap.question_index == question_index,
                )
            )
        )
    ).all())


async def record_quiz_evidence(
    session: AsyncSession,
    user_id: int,
    resource_id: int,
    question_index: int,
    score: int,
    question_type: Optional[str] = None,
    difficulty: Optional[str] = None,
    attempt_id: Optional[int] = None,
) -> int:
    """
    测验提交后回写图谱证据。

    根据 question_knowledge_map 把一题的得分写到对应的一个或多个知识点节点。
    每个节点写一条证据，分数 = score * 10（score 0-10 转 0-100），
    权重 = question_knowledge_map.weight（一题对多节点时按权重分摊）。

    source_id 使用 attempt_id（非 resource_id），配合部分唯一索引实现幂等：
    同一 attempt 重试只留一条，不同 attempt 各留一条（重答自然衰减）。

    Returns: 实际写入证据的节点数
    """
    # 查 question_knowledge_map
    map_rows = await _get_question_node_map(session, resource_id, question_index)

    if not map_rows:
        return 0

    # score 0-10 -> 0-100
    score_100 = max(0.0, min(100.0, float(score) * 10.0))

    detail = {
        "question_type": question_type,
        "difficulty": difficulty,
        "resource_id": resource_id,
        "question_index": question_index,
        "attempt_id": attempt_id,
        "raw_score": score,
    }

    count = 0
    diff_weight = DIFFICULTY_EVIDENCE_WEIGHT.get(difficulty or "", 1.0)
    for node_code, weight in map_rows:
        await add_evidence(
            session, user_id, node_code,
            source_type=EVIDENCE_SOURCE_QUIZ,
            score=score_100,
            source_id=attempt_id,
            weight=float(weight),
            detail=detail,
            signal_type=SIGNAL_TYPE_DIRECT,
            source_weight=diff_weight,
            difficulty=difficulty,
            weak_signal=False,
        )
        count += 1

    # 投影到 profile
    await project_to_profile(session, user_id)
    return count


async def record_code_evidence(
    session: AsyncSession,
    user_id: int,
    resource_id: int,
    question_index: int,
    attempt_id: Optional[int],
    success: bool,
    question_type: Optional[str] = None,
    difficulty: Optional[str] = None,
) -> int:
    """
    测验内代码题运行后回写 code_run 证据。

    仅测验代码题使用（playground 无知识点上下文，不写）。
    复用 question_knowledge_map 的多对多映射和权重。
    source_id 使用 attempt_id（与 quiz_attempt 同去重策略），同一 attempt 重试不重复写。

    注意：代码题不应同时调 record_quiz_evidence，否则同 attempt_id 会产生 quiz_attempt
    和 code_run 两条证据导致双重计分。

    Returns: 实际写入证据的节点数
    """
    map_rows = await _get_question_node_map(session, resource_id, question_index)
    if not map_rows:
        return 0

    score_100 = 100.0 if success else 0.0
    detail = {
        "question_type": question_type,
        "difficulty": difficulty,
        "resource_id": resource_id,
        "question_index": question_index,
        "attempt_id": attempt_id,
        "success": success,
    }

    count = 0
    diff_weight = DIFFICULTY_EVIDENCE_WEIGHT.get(difficulty or "", 1.0)
    for node_code, weight in map_rows:
        await add_evidence(
            session, user_id, node_code,
            source_type=EVIDENCE_SOURCE_CODE,
            score=score_100,
            source_id=attempt_id,
            weight=float(weight),
            detail=detail,
            signal_type=SIGNAL_TYPE_DIRECT,
            source_weight=diff_weight,
            difficulty=difficulty,
            weak_signal=False,
        )
        count += 1

    await project_to_profile(session, user_id)
    return count


async def _resolve_node_by_name(
    session: AsyncSession,
    knowledge_point_name: str,
) -> Optional[KnowledgeNode]:
    """按 name 精确匹配，再按 aliases 匹配，返回 KnowledgeNode 或 None。"""
    if not knowledge_point_name:
        return None
    node = (
        await session.execute(
            select(KnowledgeNode).where(KnowledgeNode.name == knowledge_point_name)
        )
    ).scalar_one_or_none()
    if not node:
        all_nodes = (
            await session.execute(select(KnowledgeNode))
        ).scalars().all()
        for n in all_nodes:
            if knowledge_point_name in (n.aliases or []):
                node = n
                break
    return node


async def record_path_node_evidence(
    session: AsyncSession,
    user_id: int,
    knowledge_point_name: str,
    mastery: float,
    node_id: Optional[int] = None,
) -> Optional[str]:
    """
    学习路径节点完成时回写图谱证据。

    通过 knowledge_point_name 匹配图谱节点（先精确匹配 name，再匹配 aliases）。
    mastery 是 0-1 的浮点，转成 0-100 分数。

    Returns: 匹配到的 node_code，未匹配返回 None
    """
    node = await _resolve_node_by_name(session, knowledge_point_name)
    if not node:
        logger.debug(f"路径节点知识点 '{knowledge_point_name}' 未在图谱中找到匹配")
        return None

    # mastery 0-1 -> 0-100
    score_100 = max(0.0, min(100.0, float(mastery) * 100.0))

    await add_evidence(
        session, user_id, node.code,
        source_type=EVIDENCE_SOURCE_PATH,
        score=score_100,
        source_id=node_id,
        weight=1.0,
        detail={"knowledge_point_name": knowledge_point_name, "path_node_id": node_id},
        signal_type=SIGNAL_TYPE_DIRECT,
        source_weight=1.0,
        difficulty=None,
        weak_signal=False,
    )
    await project_to_profile(session, user_id)
    return node.code


# ==================== Playground 代码证据（阶段2） ====================

async def record_playground_code_evidence(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    success: bool,
    stderr: str = "",
) -> None:
    """
    playground 代码运行回写（source_id=None，不去重）。

    - 成功：写 direct 证据，score=100，source_weight=COPY_PENALTY（复制运行权重低）
    - 失败：build_fingerprint，查同类计数
        * 首次（same_count < WEAK_SIGNAL_THRESHOLD-1）：weak_signal=True，不降 posterior
        * 同类第 >=WEAK_SIGNAL_THRESHOLD 次：weak_signal=False，降 posterior
    """
    from utils.code_error_fingerprint import build_fingerprint, count_same_fingerprint

    if success:
        await add_evidence(
            session, user_id, node_code,
            source_type=EVIDENCE_SOURCE_CODE, score=100.0, source_id=None,
            weight=1.0, source_weight=COPY_PENALTY,
            difficulty=None, weak_signal=False,
            detail={"source": "playground", "success": True},
        )
        return

    error_type, fp = build_fingerprint(stderr)
    same_count = await count_same_fingerprint(session, user_id, node_code, fp)
    is_weak = same_count < (WEAK_SIGNAL_THRESHOLD - 1)
    await add_evidence(
        session, user_id, node_code,
        source_type=EVIDENCE_SOURCE_CODE, score=0.0, source_id=None,
        weight=1.0, source_weight=1.0,
        difficulty=None, weak_signal=is_weak,
        detail={
            "source": "playground", "success": False,
            "error_type": error_type, "fingerprint": fp,
            "same_count": same_count,
        },
    )
    await project_to_profile(session, user_id)


# ==================== 对话判题证据 + 误解记录（阶段3） ====================

async def record_chat_judge_evidence(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    judge_result: Dict[str, Any],
    signal_type_str: str,
) -> None:
    """
    对话判题证据：source_type='chat_judge'，source_id=None（不去重，允许多次）。

    score: correct=100, partial=60, wrong=0
    source_weight: confidence * CHAT_JUDGE_WEIGHT_FACTOR（对话判题弱于 quiz 直答）
    weak_signal: confidence < CHAT_JUDGE_LOW_CONFIDENCE_THRESHOLD 时不降 posterior
    """
    score_map = {"correct": 100.0, "partial": 60.0, "wrong": 0.0}
    result = judge_result.get("result")
    score = score_map.get(result, 50.0)
    conf = float(judge_result.get("confidence", 0.5))
    await add_evidence(
        session, user_id, node_code,
        source_type=EVIDENCE_SOURCE_CHAT_JUDGE, score=score, source_id=None,
        weight=1.0, source_weight=conf * CHAT_JUDGE_WEIGHT_FACTOR,
        difficulty=None, weak_signal=(conf < CHAT_JUDGE_LOW_CONFIDENCE_THRESHOLD),
        detail={
            "evidence_type": judge_result.get("evidence_type"),
            "result": result,
            "confidence": conf,
            "signal": signal_type_str,
        },
    )
    await project_to_profile(session, user_id)


async def record_misconception(
    session: AsyncSession,
    user_id: int,
    node_code: str,
    text: str,
    confidence: float = MISCONCEPTION_SUSPECTED_CONFIDENCE,
) -> None:
    """
    单次即标"疑似"误解，resolved=False，不影响 posterior。
    误解与掌握状态共存，仅记录不降概率。
    """
    session.add(UserMisconception(
        user_id=user_id,
        node_code=node_code,
        misconception_text=(text or "")[:500],
        confidence=confidence,
        resolved=False,
    ))
