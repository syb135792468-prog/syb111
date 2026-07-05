"""
tests/test_learning_path.py - 学习路径功能测试（软件杯A3赛题）
覆盖三层：模型层、Agent层、API层
运行方式：python -m pytest tests/test_learning_path.py -v
"""
import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import AsyncClient, ASGITransport


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """创建测试数据库引擎（内存SQLite）"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from models.database import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """每个测试独立的数据库会话"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    """创建测试用户"""
    from models.user import User
    user = User(
        username="testuser",
        password_hash="hashed",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def test_path(db_session, test_user):
    """创建测试学习路径（含节点）"""
    from models.learning_path import LearningPath, LearningPathNode

    path = LearningPath(
        user_id=test_user.id,
        title="Python基础学习路径",
        topic="Python基础",
        status="active",
        total_nodes=3,
        completed_nodes=0,
        total_estimated_time=40,
    )
    db_session.add(path)
    await db_session.flush()

    nodes = []
    for i, (kp, prereqs, dtype) in enumerate([
        ("变量与数据类型", [], "new"),
        ("运算符与表达式", ["变量与数据类型"], "new"),
        ("条件判断（if/elif/else）", ["变量与数据类型", "运算符与表达式"], "new"),
    ], 1):
        node = LearningPathNode(
            learning_path_id=path.id,
            knowledge_point=kp,
            order=i,
            prerequisites=prereqs,
            difficulty=0.1 + i * 0.1,
            estimated_time=15,
            status="not_started",
            node_type=dtype,
        )
        db_session.add(node)
        nodes.append(node)

    await db_session.flush()
    return path, nodes


@pytest.fixture
def app():
    """创建测试用FastAPI应用"""
    from api.app import app
    return app


@pytest_asyncio.fixture
async def client(app):
    """创建测试HTTP客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    """注册+登录，返回认证headers"""
    await client.post("/api/auth/register", json={"username": "lptest", "password": "1234"})
    resp = await client.post("/api/auth/login", json={"username": "lptest", "password": "1234"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. 模型层测试
# ============================================================

class TestLearningPathModel:
    """LearningPath ORM 模型测试"""

    @pytest.mark.asyncio
    async def test_create_path(self, db_session, test_user):
        from models.learning_path import LearningPath
        path = LearningPath(
            user_id=test_user.id,
            title="测试路径",
            topic="Python基础",
        )
        db_session.add(path)
        await db_session.flush()
        assert path.id is not None
        assert path.status == "active"
        assert path.progress_percent == 0.0

    @pytest.mark.asyncio
    async def test_update_progress(self, db_session, test_path):
        path, nodes = test_path
        path.completed_nodes = 1
        path.total_nodes = 3
        path.update_progress()
        assert abs(path.progress_percent - 33.3) < 0.1

    @pytest.mark.asyncio
    async def test_to_dict(self, db_session, test_path):
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        from models.learning_path import LearningPath, LearningPathNode
        path, _ = test_path
        stmt = (
            select(LearningPath)
            .where(LearningPath.id == path.id)
            .options(
                selectinload(LearningPath.nodes).selectinload(LearningPathNode.resources)
            )
        )
        result = await db_session.execute(stmt)
        path = result.scalar_one()
        d = path.to_dict()
        assert "id" in d
        assert "nodes" in d
        assert isinstance(d["nodes"], list)
        assert len(d["nodes"]) == 3


class TestLearningPathNodeModel:
    """LearningPathNode ORM 模型测试"""

    @pytest.mark.asyncio
    async def test_mark_started(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        assert node.status == "not_started"
        node.mark_started()
        assert node.status == "in_progress"
        assert node.started_at is not None

    @pytest.mark.asyncio
    async def test_mark_completed(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        node.mark_completed()
        assert node.status == "completed"
        assert node.progress == 100.0
        assert node.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_mastery_threshold(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        node.update_mastery(0.8)
        assert node.mastery == 0.8
        assert node.status == "completed"  # 0.8 >= 0.7 threshold

    @pytest.mark.asyncio
    async def test_update_mastery_below_threshold(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        node.update_mastery(0.5)
        assert node.mastery == 0.5
        assert node.status != "completed"  # 0.5 < 0.7 threshold

    @pytest.mark.asyncio
    async def test_mastery_never_decreases(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        node.update_mastery(0.8)
        node.update_mastery(0.6)
        assert node.mastery == 0.8  # 取历史最高

    @pytest.mark.asyncio
    async def test_mark_needs_review(self, db_session, test_path):
        _, nodes = test_path
        node = nodes[0]
        node.mark_completed()
        node.mark_needs_review()
        assert node.status == "needs_review"

    @pytest.mark.asyncio
    async def test_to_dict_with_resources(self, db_session, test_path):
        _, nodes = test_path
        await db_session.refresh(nodes[0], ["resources"])
        d = nodes[0].to_dict()
        assert d["knowledge_point"] == "变量与数据类型"
        assert d["order"] == 1
        assert "resources" in d


# ============================================================
# 2. Agent层测试
# ============================================================

class TestPathAgent:
    """PathAgent 测试"""

    @pytest.mark.asyncio
    async def test_generate_path_basic(self):
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        result = await agent.process("Python基础", {
            "user_id": "test",
            "profile_data": {"weak_points": [], "mastered_points": []},
        })
        assert "learning_path" in result
        path = result["learning_path"]
        assert len(path) > 0
        assert len(path) <= 8
        # 每个步骤必须有核心字段
        for step in path:
            assert "knowledge_point" in step
            assert "order" in step
            assert "difficulty" in step

    @pytest.mark.asyncio
    async def test_generate_path_with_weak_points(self):
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        result = await agent.process("学习循环", {
            "user_id": "test",
            "profile_data": {
                "weak_points": ["循环（for/while）"],
                "mastered_points": ["变量与数据类型"],
            },
        })
        path = result["learning_path"]
        assert len(path) > 0
        # 已掌握的不应出现在路径中
        kps = [s["knowledge_point"] for s in path]
        assert "变量与数据类型" not in kps

    @pytest.mark.asyncio
    async def test_path_has_prerequisites(self):
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        result = await agent.process("Python基础", {
            "user_id": "test",
            "profile_data": {},
        })
        path = result["learning_path"]
        # 找到循环节点，应该有前置条件
        loop_node = next((s for s in path if "循环" in s["knowledge_point"]), None)
        if loop_node:
            assert len(loop_node["prerequisites"]) > 0

    @pytest.mark.asyncio
    async def test_path_has_difficulty(self):
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        result = await agent.process("Python基础", {
            "user_id": "test",
            "profile_data": {},
        })
        path = result["learning_path"]
        for step in path:
            assert "difficulty" in step
            assert 0 <= step["difficulty"] <= 1

    @pytest.mark.asyncio
    async def test_path_has_type(self):
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        result = await agent.process("Python基础", {
            "user_id": "test",
            "profile_data": {"mastered_points": ["变量与数据类型"]},
        })
        path = result["learning_path"]
        types = set(s["type"] for s in path)
        assert types.issubset({"new", "review"})


class TestMasteryCalculation:
    """掌握度计算测试（直接测试API层的辅助函数）"""

    def test_perfect_score(self):
        from api.routes.learning_path import _calculate_mastery
        m = _calculate_mastery(5, 5)
        assert m >= 0.9

    def test_good_score(self):
        from api.routes.learning_path import _calculate_mastery
        m = _calculate_mastery(4, 5)
        assert 0.7 <= m < 1.0

    def test_medium_score(self):
        from api.routes.learning_path import _calculate_mastery
        m = _calculate_mastery(3, 5)
        assert 0.5 <= m < 0.8

    def test_low_score(self):
        from api.routes.learning_path import _calculate_mastery
        m = _calculate_mastery(1, 5)
        assert m < 0.5

    def test_zero_questions(self):
        from api.routes.learning_path import _calculate_mastery
        m = _calculate_mastery(0, 0)
        assert m == 0.0


# ============================================================
# 3. API层测试（集成测试）
# ============================================================

class TestLearningPathAPI:
    """学习路径 API 端点测试"""

    @pytest.mark.asyncio
    async def test_health(self, client):
        resp = await client.get("/api/learning-path/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_list_paths_empty(self, client, auth_headers):
        resp = await client.get("/api/learning-path/", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] >= 0

    @pytest.mark.asyncio
    async def test_generate_path(self, client, auth_headers):
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础", "goal": "掌握基础"},
            headers=auth_headers,
            timeout=120,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] > 0
        assert len(data["nodes"]) > 0
        assert data["topic"] == "Python基础"
        assert data["status"] == "active"
        assert data["progress_percent"] == 0.0

    @pytest.mark.asyncio
    async def test_get_path_detail(self, client, auth_headers):
        # 先生成
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础"},
            headers=auth_headers,
            timeout=120,
        )
        path_id = resp.json()["data"]["id"]

        # 查询详情
        resp = await client.get(f"/api/learning-path/{path_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == path_id
        assert len(data["nodes"]) > 0

    @pytest.mark.asyncio
    async def test_get_path_not_found(self, client, auth_headers):
        resp = await client.get("/api/learning-path/99999", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 404

    @pytest.mark.asyncio
    async def test_complete_node(self, client, auth_headers):
        # 生成路径
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础"},
            headers=auth_headers,
            timeout=120,
        )
        nodes = resp.json()["data"]["nodes"]
        node_id = nodes[0]["id"]

        # 标记完成
        resp = await client.post(
            f"/api/learning-path/nodes/{node_id}/complete",
            json={"mastery": 0.85},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["progress_percent"] > 0
        assert data["completed_nodes"] >= 1

    @pytest.mark.asyncio
    async def test_submit_quiz(self, client, auth_headers):
        # 生成路径
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础"},
            headers=auth_headers,
            timeout=120,
        )
        nodes = resp.json()["data"]["nodes"]
        node_id = nodes[0]["id"]

        # 提交测验
        resp = await client.post(
            "/api/learning-path/quiz/submit",
            json={"node_id": node_id, "total_questions": 5, "correct_count": 4},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        qr = data["quiz_result"]
        assert qr["mastery"] > 0
        assert qr["correct_count"] == 4
        assert qr["total_questions"] == 5

    @pytest.mark.asyncio
    async def test_complete_node_updates_progress(self, client, auth_headers):
        # 生成路径
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础"},
            headers=auth_headers,
            timeout=120,
        )
        path_data = resp.json()["data"]
        nodes = path_data["nodes"]
        total = len(nodes)

        # 完成第一个节点
        resp = await client.post(
            f"/api/learning-path/nodes/{nodes[0]['id']}/complete",
            json={"mastery": 0.9},
            headers=auth_headers,
        )
        updated = resp.json()["data"]
        assert updated["completed_nodes"] == 1
        assert updated["progress_percent"] == pytest.approx(100 / total, rel=0.1)

    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client):
        resp = await client.get("/api/learning-path/")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_path(self, client, auth_headers):
        # 生成
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": "Python基础"},
            headers=auth_headers,
            timeout=120,
        )
        path_id = resp.json()["data"]["id"]

        # 删除
        resp = await client.delete(f"/api/learning-path/{path_id}", headers=auth_headers)
        assert resp.status_code == 200

        # 确认已删除
        resp = await client.get(f"/api/learning-path/{path_id}", headers=auth_headers)
        assert resp.json()["code"] == 404


# ============================================================
# 4. 边界条件测试
# ============================================================

class TestEdgeCases:
    """边界条件和异常场景测试"""

    @pytest.mark.asyncio
    async def test_generate_with_empty_topic(self, client, auth_headers):
        resp = await client.post(
            "/api/learning-path/generate",
            json={"topic": ""},
            headers=auth_headers,
        )
        # 应该被Pydantic校验拒绝
        assert resp.status_code == 422 or resp.json().get("code") != 200

    @pytest.mark.asyncio
    async def test_complete_nonexistent_node(self, client, auth_headers):
        resp = await client.post(
            "/api/learning-path/nodes/99999/complete",
            json={},
            headers=auth_headers,
        )
        assert resp.json()["code"] == 404

    @pytest.mark.asyncio
    async def test_quiz_with_zero_questions(self, client, auth_headers):
        resp = await client.post(
            "/api/learning-path/quiz/submit",
            json={"node_id": 1, "total_questions": 0, "correct_count": 0},
            headers=auth_headers,
        )
        # 应该被Pydantic校验拒绝（ge=1）
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_path_agent_fallback(self):
        """测试LLM失败时的降级处理"""
        from agents.path_agent import PathAgent
        agent = PathAgent(user_id="test")
        # 模拟LLM调用失败，触发fallback
        agent._call_llm = AsyncMock(side_effect=Exception("LLM unavailable"))
        result = await agent.process("Python基础", {
            "user_id": "test",
            "profile_data": {},
        })
        path = result["learning_path"]
        assert len(path) > 0  # 应该有降级路径


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
