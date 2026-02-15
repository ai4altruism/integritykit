"""
Shared pytest fixtures for Aid Arena Integrity Kit test suite.

This module provides fixtures for:
- MongoDB test client (async Motor with mongomock)
- ChromaDB test client (ephemeral in-memory)
- FastAPI test client with dependency overrides
- Async HTTP client for API testing
- Authenticated user mocks with configurable roles

All fixtures support async tests via pytest-asyncio.
"""

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ChromaDB imports
try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
except ImportError:
    chromadb = None  # type: ignore


# ============================================================================
# Event Loop Configuration
# ============================================================================


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create event loop for entire test session.

    Ensures all async tests share the same event loop to avoid
    "attached to a different loop" errors with Motor.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


# ============================================================================
# MongoDB Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def mongodb_client() -> AsyncGenerator[AsyncIOMotorClient, None]:
    """
    Provide async MongoDB test client using mongomock.

    Each test gets a fresh client instance. The database is automatically
    cleaned up after each test.

    Usage:
        async def test_signal_creation(mongodb_client):
            db = mongodb_client.test_db
            result = await db.signals.insert_one({"text": "Test signal"})
            assert result.inserted_id is not None
    """
    # Import mongomock here to make it an optional test dependency
    try:
        import mongomock_motor
    except ImportError:
        pytest.skip("mongomock-motor not installed")

    # Create mongomock client with Motor compatibility
    client = mongomock_motor.AsyncMongoMockClient()

    yield client

    # Cleanup: drop all databases
    for db_name in await client.list_database_names():
        if db_name not in ("admin", "local", "config"):
            await client.drop_database(db_name)


@pytest_asyncio.fixture
async def test_db(mongodb_client: AsyncIOMotorClient) -> AsyncIOMotorDatabase:
    """
    Provide test database instance.

    Returns:
        Motor database configured for testing

    Usage:
        async def test_with_db(test_db):
            result = await test_db.signals.find_one({"_id": signal_id})
            assert result is not None
    """
    return mongodb_client.integritykit_test


@pytest_asyncio.fixture
async def mongodb_collections(test_db: AsyncIOMotorDatabase) -> dict[str, Any]:
    """
    Provide dictionary of collection references with indexes.

    Creates all required collections with appropriate indexes for testing.

    Returns:
        Dictionary mapping collection names to collection objects
    """
    collections = {
        "signals": test_db.signals,
        "clusters": test_db.clusters,
        "cop_candidates": test_db.cop_candidates,
        "cop_updates": test_db.cop_updates,
        "audit_log": test_db.audit_log,
        "users": test_db.users,
    }

    # Create indexes for signals collection
    await collections["signals"].create_index(
        [("slack_channel_id", 1), ("slack_message_ts", 1)],
        unique=True,
    )
    await collections["signals"].create_index([("posted_at", -1)])
    await collections["signals"].create_index([("cluster_ids", 1)])

    # Create indexes for clusters collection
    await collections["clusters"].create_index(
        [("priority_score", -1), ("last_signal_at", -1)]
    )

    # Create indexes for cop_candidates collection
    await collections["cop_candidates"].create_index(
        [("readiness_state", 1), ("risk_tier", 1), ("updated_at", -1)]
    )

    # Create indexes for users collection
    await collections["users"].create_index(
        [("slack_user_id", 1), ("slack_team_id", 1)],
        unique=True,
    )

    return collections


# ============================================================================
# ChromaDB Fixtures
# ============================================================================


@pytest.fixture
def chromadb_client() -> Any:
    """
    Provide ephemeral ChromaDB client for vector embedding tests.

    Client uses in-memory storage and is automatically cleaned up after test.

    Returns:
        ChromaDB client configured for testing

    Usage:
        def test_embeddings(chromadb_client):
            collection = chromadb_client.create_collection("test_signals")
            collection.add(ids=["sig1"], embeddings=[[0.1, 0.2, 0.3]])
            assert collection.count() == 1
    """
    if chromadb is None:
        pytest.skip("chromadb not installed")

    # Create ephemeral in-memory client
    client = chromadb.Client(
        ChromaSettings(
            chroma_db_impl="duckdb",
            persist_directory=None,  # In-memory only
            anonymized_telemetry=False,
        )
    )

    return client


# ============================================================================
# FastAPI Application Fixtures
# ============================================================================


@pytest.fixture
def test_app() -> FastAPI:
    """
    Provide FastAPI application instance with test configuration.

    Dependencies are overridden to use test doubles (mocks/fakes).

    Returns:
        FastAPI app configured for testing

    Usage:
        def test_health_endpoint(test_app):
            client = TestClient(test_app)
            response = client.get("/health")
            assert response.status_code == 200
    """
    # Create minimal FastAPI app for testing
    # In real implementation, this would import the actual app
    # and override dependencies
    app = FastAPI(title="Integrity Kit Test App")

    # Add health check endpoint for basic tests
    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "healthy"}

    return app


@pytest.fixture
def test_client(test_app: FastAPI) -> TestClient:
    """
    Provide synchronous test client for FastAPI endpoints.

    Use for simple synchronous endpoint tests.

    Returns:
        FastAPI TestClient

    Usage:
        def test_endpoint(test_client):
            response = test_client.get("/api/backlog")
            assert response.status_code == 200
    """
    return TestClient(test_app)


@pytest_asyncio.fixture
async def async_client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide async HTTP client for FastAPI endpoint testing.

    Use for testing async endpoints and streaming responses.

    Returns:
        HTTPX AsyncClient

    Usage:
        async def test_async_endpoint(async_client):
            response = await async_client.get("/api/candidates")
            assert response.status_code == 200
    """
    from httpx import ASGITransport

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ============================================================================
# Authentication and User Fixtures
# ============================================================================


@pytest.fixture
def mock_user_id() -> ObjectId:
    """Provide consistent test user ObjectId."""
    return ObjectId("65d4f2c3e4b0a8c9d1234500")


@pytest.fixture
def authenticated_user(mock_user_id: ObjectId) -> dict[str, Any]:
    """
    Provide mock authenticated user with general_participant role.

    Returns:
        User document dictionary

    Usage:
        def test_with_auth(authenticated_user):
            assert "general_participant" in authenticated_user["roles"]
    """
    return {
        "_id": mock_user_id,
        "slack_user_id": "U01TESTUSER",
        "slack_team_id": "T01TESTTEAM",
        "slack_email": "test@example.com",
        "slack_display_name": "Test User",
        "slack_real_name": "Test User",
        "roles": ["general_participant"],
        "is_suspended": False,
        "created_at": "2026-02-15T00:00:00Z",
        "updated_at": "2026-02-15T00:00:00Z",
    }


@pytest.fixture
def facilitator_user(mock_user_id: ObjectId) -> dict[str, Any]:
    """
    Provide mock authenticated user with facilitator role.

    Returns:
        User document with facilitator permissions
    """
    return {
        "_id": mock_user_id,
        "slack_user_id": "U01FACILITATOR",
        "slack_team_id": "T01TESTTEAM",
        "slack_email": "facilitator@example.com",
        "slack_display_name": "Facilitator User",
        "slack_real_name": "Facilitator User",
        "roles": ["general_participant", "facilitator", "verifier"],
        "is_suspended": False,
        "created_at": "2026-02-15T00:00:00Z",
        "updated_at": "2026-02-15T00:00:00Z",
    }


@pytest.fixture
def admin_user() -> dict[str, Any]:
    """
    Provide mock authenticated user with workspace_admin role.

    Returns:
        User document with admin permissions
    """
    return {
        "_id": ObjectId("65d4f2c3e4b0a8c9d1234499"),
        "slack_user_id": "U01ADMIN",
        "slack_team_id": "T01TESTTEAM",
        "slack_email": "admin@example.com",
        "slack_display_name": "Admin User",
        "slack_real_name": "Admin User",
        "roles": ["general_participant", "facilitator", "verifier", "workspace_admin"],
        "is_suspended": False,
        "created_at": "2026-02-15T00:00:00Z",
        "updated_at": "2026-02-15T00:00:00Z",
    }


# ============================================================================
# Mock External Services
# ============================================================================


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """
    Provide mock OpenAI client for LLM prompt testing.

    Returns:
        Mock client that returns predictable responses

    Usage:
        def test_llm_call(mock_openai_client):
            mock_openai_client.chat.completions.create.return_value = {...}
            result = call_llm_function()
            assert result == expected
    """
    mock = MagicMock()

    # Configure default successful response
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='{"result": "success"}'))
    ]
    mock.chat.completions.create.return_value = mock_response

    return mock


@pytest.fixture
def mock_slack_client() -> MagicMock:
    """
    Provide mock Slack client for Slack API testing.

    Returns:
        Mock Slack SDK client

    Usage:
        def test_slack_message(mock_slack_client):
            mock_slack_client.chat_postMessage.return_value = {"ok": True}
            result = post_cop_update()
            assert result["ok"]
    """
    mock = MagicMock()

    # Configure default successful responses
    mock.chat_postMessage.return_value = {"ok": True, "ts": "1234567890.123456"}
    mock.conversations_history.return_value = {"ok": True, "messages": []}

    return mock


# ============================================================================
# Test Data Markers
# ============================================================================


def pytest_configure(config: Any) -> None:
    """
    Register custom pytest markers.

    Markers:
        - unit: Unit tests (isolated, fast)
        - integration: Integration tests (database, external services)
        - slow: Slow-running tests
        - requires_mongodb: Tests requiring MongoDB
        - requires_chromadb: Tests requiring ChromaDB
    """
    config.addinivalue_line("markers", "unit: Unit tests (isolated, fast)")
    config.addinivalue_line(
        "markers", "integration: Integration tests (database, external services)"
    )
    config.addinivalue_line("markers", "slow: Slow-running tests")
    config.addinivalue_line("markers", "requires_mongodb: Tests requiring MongoDB")
    config.addinivalue_line("markers", "requires_chromadb: Tests requiring ChromaDB")
