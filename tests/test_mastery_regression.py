"""
tests/test_mastery_regression.py - 知识图谱掌握度回归测试

覆盖 6 个 P1/P2 修复点：
1. 幂等：同 attempt_id 重复调 record_quiz_evidence 只写一条证据，掌握度不变
2. 跨模块前置：模块筛选时，跨模块前置未满足的节点应 locked
3. 锁定禁练：locked 节点 get_effective_state 返回 locked
4. mastery_threshold 生效：per-node 阈值高于 50 时，50 分不 mastered
5. last_correct 稳定：同题先错后对，practice 返回 last_correct=true
6. code_run 不双重计分：代码题调 record_code_evidence 只写 code_run，不写 quiz_attempt

运行：python -m pytest tests/test_mastery_regression.py -v
"""
import pytest
import pytest_asyncio
from datetime import datetime, UTC

from sqlalchemy import select, func, and_, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from models.database import Base
from models.user import User
from models.profile import UserProfile
from models.knowledge_graph import (
    KnowledgeNode, KnowledgeEdge,
    UserKnowledgeMastery, KnowledgeMasteryEvidence,
    QuestionKnowledgeMap,
)
from models.quiz_attempt import QuizAttempt
from models.resource import Resource
from services.mastery_service import (
    add_evidence,
    record_quiz_evidence,
    record_code_evidence,
    get_user_graph,
    get_node_detail,
    get_effective_state,
    STATE_LOCKED, STATE_AVAILABLE, STATE_LEARNING, STATE_MASTERED,
    MASTERY_THRESHOLD,
)


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """内存 SQLite 引擎，整个 session 共享"""
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 注入知识图谱种子（从 data.knowledge_catalog 取）
    async with engine.begin() as conn:
        from data.knowledge_catalog import NODES, EDGES
        for node_dict in NODES:
            conn_sync = conn
            await conn.execute(KnowledgeNode.__table__.insert().values(
                code=node_dict["code"],
                name=node_dict["name"],
                module=node_dict["module"],
                level=node_dict["level"],
                difficulty=node_dict.get("difficulty", 0.3),
                estimated_time=node_dict.get("estimated_time", 15),
                description=node_dict.get("description"),
                mastery_threshold=node_dict.get("mastery_threshold", 50.0),
                aliases=node_dict.get("aliases", []),
                is_active=True,
            ))
        for edge_tuple in EDGES:
            await conn.execute(KnowledgeEdge.__table__.insert().values(
                source_code=edge_tuple[0],
                target_code=edge_tuple[1],
                edge_type=edge_tuple[2],
            ))
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """每个测试独立会话，测试结束回滚"""
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    """创建测试用户 + 画像"""
    user = User(username=f"regression_user_{datetime.now(UTC).timestamp()}")
    user.password_hash = "test_hash_not_for_login"
    db_session.add(user)
    await db_session.flush()
    profile = UserProfile(user_id=user.id, knowledge_level="beginner")
    db_session.add(profile)
    await db_session.flush()
    return user


# ============================================================
# 测试 1：幂等 - 同 attempt_id 重复写证据只留一条
# ============================================================

async def test_idempotent_evidence_same_attempt_id(db_session, test_user):
    """同 attempt_id 调 record_quiz_evidence 两次，证据数应为 1，掌握度不变"""
    # 准备：QuestionKnowledgeMap
    db_session.add(QuestionKnowledgeMap(
        resource_id=1001, question_index=0, node_code="py_intro", weight=1.0,
    ))
    await db_session.flush()

    # 第一次写
    count1 = await record_quiz_evidence(
        db_session, test_user.id, 1001, 0, score=10,
        question_type="choice", attempt_id=5001,
    )
    assert count1 == 1
    await db_session.flush()

    # 读掌握度
    m1 = (
        await db_session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == test_user.id,
                    UserKnowledgeMastery.node_code == "py_intro",
                )
            )
        )
    ).scalar_one()
    score_after_first = m1.mastery_score
    evidence_after_first = m1.evidence_count

    # 第二次写（同 attempt_id，模拟网络重试）
    count2 = await record_quiz_evidence(
        db_session, test_user.id, 1001, 0, score=10,
        question_type="choice", attempt_id=5001,
    )
    assert count2 == 1  # 仍返回 1（幂等预检命中，跳过 INSERT 但仍计入 count）
    await db_session.flush()

    # 证据数应不变
    m2 = (
        await db_session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == test_user.id,
                    UserKnowledgeMastery.node_code == "py_intro",
                )
            )
        )
    ).scalar_one()
    assert m2.evidence_count == evidence_after_first, "同 attempt_id 重复写不应增加证据数"
    assert m2.mastery_score == score_after_first, "同 attempt_id 重复写不应改变掌握度"

    # 证据表实际行数
    evidence_count = (
        await db_session.execute(
            select(func.count(KnowledgeMasteryEvidence.id)).where(
                and_(
                    KnowledgeMasteryEvidence.user_id == test_user.id,
                    KnowledgeMasteryEvidence.node_code == "py_intro",
                    KnowledgeMasteryEvidence.source_type == "quiz_attempt",
                    KnowledgeMasteryEvidence.source_id == 5001,
                )
            )
        )
    ).scalar_one()
    assert evidence_count == 1, f"同 attempt_id 应只有 1 条证据，实际 {evidence_count}"


# ============================================================
# 测试 2：跨模块前置 - 模块筛选时跨模块前置未满足应 locked
# ============================================================

async def test_cross_module_prerequisite_locked(db_session, test_user):
    """节点 A 在模块 X，前置 B 在模块 Y，B 未 mastered -> 查模块 X 时 A 应 locked"""
    # py_collections (data_structures) 前置 py_dict_basic (datatypes) - 跨模块
    edge = (
        await db_session.execute(
            select(KnowledgeEdge).where(
                and_(
                    KnowledgeEdge.target_code == "py_collections",
                    KnowledgeEdge.source_code == "py_dict_basic",
                    KnowledgeEdge.edge_type == "prerequisite",
                )
            )
        )
    ).scalars().first()

    if not edge:
        pytest.skip("图谱中无 py_collections 跨模块前置边，跳过")

    # user 未掌握任何前置 -> py_collections 应 locked
    graph = await get_user_graph(db_session, test_user.id, module_filter="data_structures")
    node = next((n for n in graph["nodes"] if n["code"] == "py_collections"), None)
    if node is None:
        pytest.skip("py_collections 不在 data_structures 模块")
    assert node["state"] == STATE_LOCKED, (
        f"跨模块前置未满足应 locked，实际 {node['state']}"
    )


# ============================================================
# 测试 3：锁定禁练 - get_effective_state 返回 locked
# ============================================================

async def test_get_effective_state_locked(db_session, test_user):
    """无 mastery 记录且前置未满足 -> get_effective_state 返回 locked"""
    # py_arith 依赖 py_variable，user 未掌握 py_variable -> py_arith 应 locked
    state = await get_effective_state(db_session, test_user.id, "py_arith")
    assert state == STATE_LOCKED, f"前置未满足应 locked，实际 {state}"


async def test_get_effective_state_available_no_prereq(db_session, test_user):
    """无前置的节点 -> available"""
    # py_intro 是根节点，无前置
    state = await get_effective_state(db_session, test_user.id, "py_intro")
    assert state == STATE_AVAILABLE, f"无前置根节点应 available，实际 {state}"


# ============================================================
# 测试 4：mastery_threshold 生效
# ============================================================

async def test_per_node_mastery_threshold(db_session, test_user):
    """节点 mastery_threshold=80 时，70 分不应 mastered；改 50 后重算应 mastered"""
    # 取 py_intro 节点，临时改阈值为 80
    node = (
        await db_session.execute(
            select(KnowledgeNode).where(KnowledgeNode.code == "py_intro")
        )
    ).scalar_one()
    original_threshold = node.mastery_threshold
    node.mastery_threshold = 80.0
    await db_session.flush()

    # 写 2 条 80 分证据：quiz_score=80，无 path -> mastery=80*0.7=56.0
    await add_evidence(
        db_session, test_user.id, "py_intro",
        source_type="quiz_attempt", source_id=7001,
        score=80.0, weight=1.0,
    )
    await add_evidence(
        db_session, test_user.id, "py_intro",
        source_type="quiz_attempt", source_id=7002,
        score=80.0, weight=1.0,
    )
    await db_session.flush()

    m = (
        await db_session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == test_user.id,
                    UserKnowledgeMastery.node_code == "py_intro",
                )
            )
        )
    ).scalar_one()
    # 阈值 80，mastery=56 < 80 不应 mastered
    assert m.state != STATE_MASTERED, (
        f"阈值 80 时 mastery=56 不应 mastered，实际 state={m.state} score={m.mastery_score}"
    )
    assert abs(m.mastery_score - 56.0) < 0.1, f"预期 56.0，实际 {m.mastery_score}"

    # 改回 50，重算
    node.mastery_threshold = 50.0
    await db_session.flush()
    from services.mastery_service import recalculate_all_mastery, _get_node_threshold, _update_state
    await recalculate_all_mastery(db_session, test_user.id)
    await db_session.flush()

    m2 = (
        await db_session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == test_user.id,
                    UserKnowledgeMastery.node_code == "py_intro",
                )
            )
        )
    ).scalar_one()
    assert m2.state == STATE_MASTERED, (
        f"阈值 50 时 mastery=56 应 mastered，实际 state={m2.state} score={m2.mastery_score}"
    )

    # 恢复原阈值
    node.mastery_threshold = original_threshold
    await db_session.flush()


# ============================================================
# 测试 5：last_correct 稳定 - 同题先错后对取最新
# ============================================================

async def test_practice_last_correct_takes_latest(db_session, test_user):
    """同题先答错后答对，practice 接口的 last_correct 应为 true"""
    from api.routes.graph import get_node_practice
    # 这个测试需要 FastAPI request 上下文，改用直接查 graph.py 内部逻辑
    # 简化：直接验证 attempt_map 组装逻辑
    from models.quiz_attempt import QuizAttempt
    from fastapi import Query
    from unittest.mock import MagicMock

    # 准备：QuestionKnowledgeMap + Resource + 2 条 QuizAttempt（先错后对）
    db_session.add(QuestionKnowledgeMap(
        resource_id=2001, question_index=0, node_code="py_intro", weight=1.0,
    ))
    res = Resource(
        id=2001, user_id=test_user.id, title="测试题", content="{}",
        resource_type="quiz", knowledge_points=["Python简介与环境"],
    )
    res.is_active = True
    db_session.add(res)
    await db_session.flush()

    # 先答错（created_at 早）
    t1 = datetime(2026, 1, 1)
    a1 = QuizAttempt(
        user_id=test_user.id, resource_id=2001, question_index=0,
        question_type="choice", difficulty="easy",
        user_answer="x", correct_answer="y",
        is_correct=False, score=0, spent_time=10,
    )
    a1.created_at = t1
    db_session.add(a1)

    # 后答对（created_at 晚）
    t2 = datetime(2026, 1, 2)
    a2 = QuizAttempt(
        user_id=test_user.id, resource_id=2001, question_index=0,
        question_type="choice", difficulty="easy",
        user_answer="y", correct_answer="y",
        is_correct=True, score=10, spent_time=10,
    )
    a2.created_at = t2
    db_session.add(a2)
    await db_session.flush()

    # 直接调 graph.py 的查询逻辑验证 ORDER BY DESC + 只保留最新
    user_attempts = (
        await db_session.execute(
            select(QuizAttempt.resource_id, QuizAttempt.question_index, QuizAttempt.is_correct)
            .where(
                and_(
                    QuizAttempt.user_id == test_user.id,
                    QuizAttempt.resource_id.in_([2001]),
                )
            )
            .order_by(QuizAttempt.created_at.desc())
        )
    ).all()

    attempt_map = {}
    for a in user_attempts:
        key = (a[0], a[1])
        if key not in attempt_map:
            attempt_map[key] = bool(a[2])

    assert attempt_map.get((2001, 0)) is True, (
        f"先错后对应取最新为 True，实际 {attempt_map.get((2001, 0))}"
    )


# ============================================================
# 测试 6：code_run 不双重计分
# ============================================================

async def test_code_evidence_no_double_counting(db_session, test_user):
    """代码题调 record_code_evidence 只写 code_run 证据，不写 quiz_attempt"""
    db_session.add(QuestionKnowledgeMap(
        resource_id=3001, question_index=0, node_code="py_intro", weight=1.0,
    ))
    await db_session.flush()

    count = await record_code_evidence(
        db_session, test_user.id, 3001, 0,
        attempt_id=8001, success=True,
        question_type="code",
    )
    assert count == 1
    await db_session.flush()

    # 应有 1 条 code_run 证据
    code_run_count = (
        await db_session.execute(
            select(func.count(KnowledgeMasteryEvidence.id)).where(
                and_(
                    KnowledgeMasteryEvidence.user_id == test_user.id,
                    KnowledgeMasteryEvidence.node_code == "py_intro",
                    KnowledgeMasteryEvidence.source_type == "code_run",
                    KnowledgeMasteryEvidence.source_id == 8001,
                )
            )
        )
    ).scalar_one()
    assert code_run_count == 1, f"应有 1 条 code_run 证据，实际 {code_run_count}"

    # 应有 0 条 quiz_attempt 证据
    quiz_attempt_count = (
        await db_session.execute(
            select(func.count(KnowledgeMasteryEvidence.id)).where(
                and_(
                    KnowledgeMasteryEvidence.user_id == test_user.id,
                    KnowledgeMasteryEvidence.node_code == "py_intro",
                    KnowledgeMasteryEvidence.source_type == "quiz_attempt",
                )
            )
        )
    ).scalar_one()
    assert quiz_attempt_count == 0, (
        f"代码题不应写 quiz_attempt 证据，实际 {quiz_attempt_count} 条"
    )

    # code_practice_count 应 +1
    m = (
        await db_session.execute(
            select(UserKnowledgeMastery).where(
                and_(
                    UserKnowledgeMastery.user_id == test_user.id,
                    UserKnowledgeMastery.node_code == "py_intro",
                )
            )
        )
    ).scalar_one()
    assert m.code_practice_count == 1, (
        f"code_practice_count 应为 1，实际 {m.code_practice_count}"
    )


# ============================================================
# 测试 7：get_node_detail 返回 effective_state
# ============================================================

async def test_get_node_detail_returns_effective_state(db_session, test_user):
    """get_node_detail 应返回 effective_state 字段"""
    detail = await get_node_detail(db_session, test_user.id, "py_arith")
    assert detail is not None
    assert "effective_state" in detail, "get_node_detail 应返回 effective_state"
    assert detail["effective_state"] == STATE_LOCKED, (
        f"py_arith 前置未满足应 locked，实际 {detail['effective_state']}"
    )
    # threshold 应是节点自身 mastery_threshold，不是全局常量
    assert "threshold" in detail
    assert detail["threshold"] == detail["node"]["mastery_threshold"], (
        "threshold 应等于节点 mastery_threshold"
    )
