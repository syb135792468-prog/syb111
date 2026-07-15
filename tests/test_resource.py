"""
tests/test_resource.py - 资源收藏功能验证
覆盖：模型层默认值 + API 层端点
运行方式：python -m pytest tests/test_resource.py -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ============================================================
# Fixtures（复用 test_learning_path.py 模式）
# ============================================================

@pytest_asyncio.fixture(scope="session")
async def db_engine():
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
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def test_user(db_session):
    from models.user import User
    user = User(username="restest", password_hash="hashed", is_active=True)
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def app():
    from api.app import app
    return app


@pytest_asyncio.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def auth_headers(client):
    await client.post("/api/auth/register", json={"username": "resapi", "password": "1234"})
    resp = await client.post("/api/auth/login", json={"username": "resapi", "password": "1234"})
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ============================================================
# 1. 模型层测试
# ============================================================

class TestResourceModel:

    @pytest.mark.asyncio
    async def test_default_not_in_library(self, db_session, test_user):
        """新建 Resource 不指定 in_library，默认为 False"""
        from models.resource import Resource
        r = Resource(
            user_id=test_user.id,
            resource_type="doc",
            title="默认不入库测试",
            content="test",
            status="completed",
        )
        db_session.add(r)
        await db_session.flush()
        assert r.in_library is False

    @pytest.mark.asyncio
    async def test_explicit_in_library_true(self, db_session, test_user):
        """显式设置 in_library=True 时正确保存"""
        from models.resource import Resource
        r = Resource(
            user_id=test_user.id,
            resource_type="quiz",
            title="显式入库测试",
            content="test",
            status="completed",
            in_library=True,
        )
        db_session.add(r)
        await db_session.flush()
        assert r.in_library is True

    @pytest.mark.asyncio
    async def test_to_dict_includes_in_library(self, db_session, test_user):
        """to_dict() 输出包含 in_library 字段"""
        from models.resource import Resource
        r = Resource(
            user_id=test_user.id,
            resource_type="code",
            title="字典输出测试",
            content="test",
            status="completed",
        )
        db_session.add(r)
        await db_session.flush()
        d = r.to_dict()
        assert "in_library" in d
        assert d["in_library"] is False


# ============================================================
# 2. API 层测试
# ============================================================

class TestResourceAPI:

    @pytest.mark.asyncio
    async def test_list_shows_all_by_default(self, client, auth_headers):
        """GET /resource/ 不传 in_library 时返回所有资源（含未收藏的）"""
        resp = await client.get("/api/resource/?user_id=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200

    @pytest.mark.asyncio
    async def test_add_to_library(self, client, auth_headers):
        """PATCH /resource/{id}/add-to-library 正确设置 in_library=True"""
        # 先通过 generate 端点创建一个资源（需要 mock agent）
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_item = MagicMock()
        mock_item.title = "收藏测试资源"
        mock_item.content = "test content"
        mock_item.knowledge_points = ["PY001"]
        mock_item.extra_metadata = {"quiz_type": "choice"}

        mock_result = {"resource_list": [mock_item]}

        with patch("api.routes.resource.get_agent") as mock_get_agent:
            mock_agent = AsyncMock()
            mock_agent.process = AsyncMock(return_value=mock_result)
            mock_agent.use_llm = True
            mock_agent._llm_disabled_until = None
            mock_get_agent.return_value = mock_agent

            gen_resp = await client.post("/api/resource/generate", json={
                "user_id": "1",
                "topic": "收藏测试",
                "resource_type": "doc",
            }, headers=auth_headers)

        assert gen_resp.status_code == 200
        gen_data = gen_resp.json()
        assert gen_data["code"] == 200
        resource_id = gen_data["data"]["id"]
        assert gen_data["data"]["in_library"] is False

        # 收藏
        save_resp = await client.patch(
            f"/api/resource/{resource_id}/add-to-library?user_id=1",
            headers=auth_headers,
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["code"] == 200
        assert save_resp.json()["data"]["in_library"] is True

    @pytest.mark.asyncio
    async def test_list_filter_in_library(self, client, auth_headers):
        """传 in_library=true 时只返回已收藏资源"""
        resp = await client.get(
            "/api/resource/?user_id=1&in_library=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        # 所有返回的资源都应该是 in_library=True
        for r in data["data"]["resources"]:
            assert r["in_library"] is True

    @pytest.mark.asyncio
    async def test_generate_resource_not_in_library(self, client, auth_headers):
        """POST /generate 生成的资源 in_library=False"""
        from unittest.mock import AsyncMock, patch, MagicMock

        mock_item = MagicMock()
        mock_item.title = "不入库测试"
        mock_item.content = "content"
        mock_item.knowledge_points = []
        mock_item.extra_metadata = {}

        with patch("api.routes.resource.get_agent") as mock_get_agent:
            mock_agent = AsyncMock()
            mock_agent.process = AsyncMock(return_value={"resource_list": [mock_item]})
            mock_agent.use_llm = True
            mock_agent._llm_disabled_until = None
            mock_get_agent.return_value = mock_agent

            resp = await client.post("/api/resource/generate", json={
                "user_id": "1",
                "topic": "不入库测试",
                "resource_type": "doc",
            }, headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 200
        assert data["data"]["in_library"] is False

    def test_merge_children_into_tree_preserves_existing_children(self):
        """重复合并节点时保留已有子节点并追加新节点"""
        import json
        from api.routes.resource import _merge_children_into_tree

        original = {
            "nodeData": {
                "id": "root",
                "topic": "Root",
                "children": [
                    {
                        "id": "target",
                        "topic": "Target",
                        "children": [
                            {"id": "existing", "topic": "Existing", "children": []}
                        ],
                    }
                ],
            }
        }

        merged = _merge_children_into_tree(
            json.dumps(original, ensure_ascii=False),
            "target",
            [{"id": "new", "topic": "New", "children": []}],
        )
        merged_data = json.loads(merged)
        target_children = merged_data["nodeData"]["children"][0]["children"]

        assert [child["id"] for child in target_children] == ["existing", "new"]


# ============================================================
# 3. 消息收藏 API 测试
# ============================================================

class TestChatBookmarkModel:

    @pytest.mark.asyncio
    async def test_message_default_not_bookmarked(self, db_session, test_user):
        """新建 ChatMessage 默认 is_bookmarked=False"""
        from models.chat_message import ChatMessage
        msg = ChatMessage(
            user_id=test_user.id,
            role="assistant",
            content="测试回复",
        )
        db_session.add(msg)
        await db_session.flush()
        assert msg.is_bookmarked is False

    @pytest.mark.asyncio
    async def test_message_toggle_bookmark(self, db_session, test_user):
        """ChatMessage 可以切换 is_bookmarked"""
        from models.chat_message import ChatMessage
        msg = ChatMessage(
            user_id=test_user.id,
            role="assistant",
            content="测试回复",
            is_bookmarked=True,
        )
        db_session.add(msg)
        await db_session.flush()
        assert msg.is_bookmarked is True
        msg.is_bookmarked = False
        await db_session.flush()
        assert msg.is_bookmarked is False
