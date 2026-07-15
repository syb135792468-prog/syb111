"""
scripts/smoke_test_mastery.py - 掌握度服务冒烟测试

验证：
1. 写入证据 -> 掌握度更新
2. 前置依赖未满足 -> locked
3. 前置满足 + 2 次答对 -> mastered
4. profile 投影 -> weak/mastered_points 同步
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import AsyncSessionLocal, init_db, engine
from models.user import User
from models.profile import UserProfile
from models.knowledge_graph import UserKnowledgeMastery
from services.mastery_service import (
    add_evidence,
    get_user_graph,
    get_node_detail,
    project_to_profile,
    STATE_LOCKED, STATE_AVAILABLE, STATE_LEARNING, STATE_MASTERED,
)
from utils.logger import get_logger

logger = get_logger(__name__, task_id="smoke_mastery")


async def setup_test_user(session: AsyncSession) -> int:
    """创建测试用户和画像"""
    user = User(username="smoke_test_user")
    user.password_hash = "test_hash_not_for_login"
    session.add(user)
    await session.flush()

    profile = UserProfile(user_id=user.id, knowledge_level="beginner")
    session.add(profile)
    await session.flush()
    return user.id


async def main() -> None:
    logger.info("=" * 60)
    logger.info("掌握度服务冒烟测试")
    logger.info("=" * 60)

    await init_db()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            user_id = await setup_test_user(session)

        # 测试 1：写入第一条证据（py_intro 节点，无前置）
        async with session.begin():
            await add_evidence(
                session, user_id, "py_intro",
                source_type="quiz_attempt", source_id=1,
                score=80.0, weight=1.0,
                detail={"question_type": "choice"},
            )

        async with session.begin():
            m = await get_user_node_local(session, user_id, "py_intro")
            logger.info(f"测试1 py_intro: score={m.mastery_score} state={m.state} evidence={m.evidence_count}")
            # 1 次答对 80 分：quiz_score=100（1/1），code_score=0
            # mastery = 100*0.7 + 0*0.3 = 70.0
            assert m.mastery_score == 70.0, f"预期 70.0，实际 {m.mastery_score}"
            assert m.state == STATE_LEARNING, f"1 次证据应 learning，实际 {m.state}"

        # 测试 2：写入第二条证据 -> 应升 mastered
        async with session.begin():
            await add_evidence(
                session, user_id, "py_intro",
                source_type="quiz_attempt", source_id=2,
                score=90.0, weight=1.0,
            )

        async with session.begin():
            m = await get_user_node_local(session, user_id, "py_intro")
            logger.info(f"测试2 py_intro: score={m.mastery_score} state={m.state}")
            assert m.state == STATE_MASTERED, f"2 次证据 score>=50 应 mastered，实际 {m.state}"
            assert m.quiz_correct_count == 2

        # 测试 3：py_print 依赖 py_intro，py_intro 已 mastered，py_print 应 available
        async with session.begin():
            m_print = await get_user_node_local(session, user_id, "py_print")
            logger.info(f"测试3 py_print（前置已满足）: state={m_print.state if m_print else '无记录'}")
            # 无证据的节点默认 available（前置满足时）
            # 注意：get_user_node 不会自动创建，需通过 add_evidence 或显式查询
            # 这里验证：直接查询应返回 None 或 available
            if m_print is None:
                logger.info("  py_print 尚无掌握记录（符合预期，未触发 add_evidence）")

        # 测试 4：py_arith 依赖 py_variable（未掌握），py_arith 写证据应被锁 locked
        async with session.begin():
            await add_evidence(
                session, user_id, "py_arith",
                source_type="quiz_attempt", source_id=3,
                score=100.0, weight=1.0,
            )

        async with session.begin():
            m_arith = await get_user_node_local(session, user_id, "py_arith")
            logger.info(f"测试4 py_arith（前置 py_variable 未掌握）: state={m_arith.state}")
            assert m_arith.state == STATE_LOCKED, f"前置未满足应 locked，实际 {m_arith.state}"

        # 测试 5：代码实践证据
        async with session.begin():
            await add_evidence(
                session, user_id, "py_variable",
                source_type="code_run", source_id=1,
                score=100.0, weight=1.0,
                detail={"status": "success"},
            )

        async with session.begin():
            m_var = await get_user_node_local(session, user_id, "py_variable")
            logger.info(f"测试5 py_variable（1次代码实践）: score={m_var.mastery_score} state={m_var.state}")
            assert m_var.code_practice_count == 1
            # 1 次代码实践：code_score = 1/3 * 100 = 33.3
            # quiz_score = 0
            # mastery = 0 * 0.7 + 33.3 * 0.3 = 10.0
            assert abs(m_var.mastery_score - 10.0) < 0.1, f"预期 10.0，实际 {m_var.mastery_score}"

        # 测试 6：profile 投影
        async with session.begin():
            await project_to_profile(session, user_id)

        async with session.begin():
            profile = (
                await session.execute(
                    select(UserProfile).where(UserProfile.user_id == user_id)
                )
            ).scalar_one()
            logger.info(f"测试6 profile: mastered={profile.mastered_points} weak={profile.weak_points}")
            assert "Python简介与环境" in profile.mastered_points, "py_intro 应在 mastered_points"

        # 测试 7：图谱查询
        async with session.begin():
            graph = await get_user_graph(session, user_id)
            logger.info(f"测试7 图谱: {graph['stats']}")
            assert graph["stats"]["total"] == 65
            assert graph["stats"]["mastered"] >= 1

        # 测试 8：节点详情
        async with session.begin():
            detail = await get_node_detail(session, user_id, "py_intro")
            logger.info(f"测试8 节点详情 py_intro: prerequisites={len(detail['prerequisites'])} evidences={len(detail['recent_evidences'])}")
            assert detail["node"]["code"] == "py_intro"
            assert detail["mastery"]["state"] == STATE_MASTERED

    # 清理测试用户
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = (
                await session.execute(
                    select(User).where(User.username == "smoke_test_user")
                )
            ).scalar_one_or_none()
            if user:
                await session.delete(user)

    logger.info("=" * 60)
    logger.info("✅ 所有冒烟测试通过")
    logger.info("=" * 60)

    await engine.dispose()


async def get_user_node_local(session: AsyncSession, user_id: int, node_code: str):
    """本地辅助：查 UserKnowledgeMastery"""
    from sqlalchemy import and_
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


if __name__ == "__main__":
    asyncio.run(main())
