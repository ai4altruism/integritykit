# Aid Arena Integrity Kit - Test Suite

Comprehensive pytest infrastructure for testing the Integrity Kit application.

## Overview

The test suite includes:
- **64 tests** covering unit and integration test patterns
- Async MongoDB testing with mongomock
- Test data factories for all MongoDB collections
- Shared fixtures for authentication, database, and HTTP clients
- Example tests demonstrating best practices

## Project Structure

```
tests/
├── conftest.py              # Shared fixtures and pytest configuration
├── factories.py             # Test data factory functions
├── unit/                    # Fast, isolated unit tests
│   ├── test_readiness.py   # Readiness computation logic
│   └── test_rbac.py        # Role-based access control
├── integration/             # Integration tests with database
│   ├── test_api_auth.py    # Authentication and RBAC endpoints
│   └── test_api_backlog.py # Backlog API endpoints
└── README.md               # This file
```

## Running Tests

### Install Dependencies

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # or .venv/Scripts/activate on Windows

# Install package with dev dependencies
pip install -e ".[dev]"

# Install MongoDB mock for testing
pip install mongomock-motor
```

### Run All Tests

```bash
pytest
```

### Run Specific Test Files

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# Specific test file
pytest tests/unit/test_rbac.py

# Specific test
pytest tests/unit/test_rbac.py::TestRoleAssignment::test_facilitator_has_multiple_roles
```

### Run by Marker

```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests only
pytest -m integration

# MongoDB-dependent tests
pytest -m requires_mongodb

# ChromaDB-dependent tests
pytest -m requires_chromadb
```

### Coverage Reports

```bash
# Run with coverage
pytest --cov=integritykit --cov-report=html

# Open HTML report
open htmlcov/index.html
```

## Using Test Fixtures

### MongoDB Fixtures

```python
@pytest.mark.asyncio
async def test_with_database(test_db: AsyncIOMotorDatabase):
    """Test using MongoDB test database."""
    # Insert document
    result = await test_db.signals.insert_one({"text": "Test"})

    # Query document
    signal = await test_db.signals.find_one({"_id": result.inserted_id})
    assert signal is not None
```

### Collection Fixtures

```python
@pytest.mark.asyncio
async def test_with_collections(mongodb_collections):
    """Test using collection dictionary with indexes."""
    signals = mongodb_collections["signals"]

    # Collections come with indexes pre-created
    await signals.insert_one(create_signal())
    count = await signals.count_documents({})
    assert count == 1
```

### Authentication Fixtures

```python
def test_with_authenticated_user(authenticated_user):
    """Test with general participant user."""
    assert "general_participant" in authenticated_user["roles"]

def test_with_facilitator(facilitator_user):
    """Test with facilitator user."""
    assert "facilitator" in facilitator_user["roles"]
    assert "verifier" in facilitator_user["roles"]

def test_with_admin(admin_user):
    """Test with workspace admin user."""
    assert "workspace_admin" in admin_user["roles"]
```

### HTTP Client Fixtures

```python
@pytest.mark.asyncio
async def test_api_endpoint(async_client: AsyncClient):
    """Test FastAPI endpoint with async client."""
    response = await async_client.get("/api/health")
    assert response.status_code == 200
```

### Mock External Services

```python
def test_with_openai_mock(mock_openai_client):
    """Test LLM integration with mock."""
    mock_openai_client.chat.completions.create.return_value = {
        "choices": [{"message": {"content": "test"}}]
    }

    # Call function that uses OpenAI
    result = call_llm_function()
    assert result is not None

def test_with_slack_mock(mock_slack_client):
    """Test Slack integration with mock."""
    mock_slack_client.chat_postMessage.return_value = {"ok": True}

    # Call function that posts to Slack
    result = post_message()
    assert result["ok"]
```

## Using Test Factories

### Signal Factory

```python
from tests.factories import create_signal

def test_signal_creation():
    # Create with defaults
    signal = create_signal()

    # Override specific fields
    signal = create_signal(
        text="Shelter Alpha closing",
        slack_channel_id="C01CRISIS",
        ai_flags={"quality_score": 0.95}
    )

    # Create with reactions
    signal = create_signal_with_reaction(
        reaction_name="heavy_check_mark",
        reaction_count=5
    )
```

### Cluster Factory

```python
from tests.factories import create_cluster, create_cluster_with_signals

def test_cluster_creation():
    # Create cluster with auto-generated signals
    cluster = create_cluster_with_signals(signal_count=5)
    assert len(cluster["signal_ids"]) == 5

    # Create cluster with specific properties
    cluster = create_cluster(
        topic_type="incident",
        priority_score=0.9,
        has_conflicts=True
    )
```

### COP Candidate Factory

```python
from tests.factories import (
    create_cop_candidate,
    create_verified_candidate,
    create_blocked_candidate
)

def test_candidate_states():
    # Verified candidate
    candidate = create_verified_candidate()
    assert candidate["readiness_state"] == "verified"
    assert len(candidate["verifications"]) > 0

    # Blocked candidate
    candidate = create_blocked_candidate()
    assert candidate["readiness_state"] == "blocked"
    assert len(candidate["blocking_issues"]) > 0

    # Custom candidate
    candidate = create_cop_candidate(
        readiness_state="in_review",
        risk_tier="high_stakes",
        fields={
            "what": "Custom situation",
            "where": "Test location",
        }
    )
```

### User Factory

```python
from tests.factories import create_user, create_facilitator, create_admin

def test_user_roles():
    # Basic user
    user = create_user()
    assert "general_participant" in user["roles"]

    # Facilitator
    facilitator = create_facilitator()
    assert "facilitator" in facilitator["roles"]

    # Admin
    admin = create_admin()
    assert "workspace_admin" in admin["roles"]
```

### Audit Log Factory

```python
from tests.factories import create_audit_entry

def test_audit_logging():
    entry = create_audit_entry(
        action_type="cop_update.publish",
        actor_id=facilitator_id,
        target_entity_type="cop_update",
        justification="Regular scheduled update"
    )

    assert entry["action_type"] == "cop_update.publish"
```

## Writing New Tests

### Unit Test Template

```python
"""
Unit tests for [module/feature name].

Tests [brief description of what's being tested].
These are pure unit tests with no external dependencies.
"""

import pytest
from tests.factories import create_relevant_factory


@pytest.mark.unit
class TestFeatureName:
    """Test [feature] logic."""

    def test_specific_behavior(self):
        """Test that [expected behavior] when [scenario]."""
        # Arrange
        data = create_relevant_factory()

        # Act
        result = function_under_test(data)

        # Assert
        assert result == expected_value
```

### Integration Test Template

```python
"""
Integration tests for [API endpoint/feature].

Tests [description of integration].
These tests use real database connections.
"""

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from tests.factories import create_relevant_factory


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_endpoint_behavior(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
):
    """Test that [endpoint/feature] [expected behavior]."""
    # Arrange - Set up database state
    document = create_relevant_factory()
    await test_db.collection.insert_one(document)

    # Act - Make request or call function
    # response = await async_client.get("/api/endpoint")

    # Assert - Verify results
    retrieved = await test_db.collection.find_one({"_id": document["_id"]})
    assert retrieved is not None
```

## Test Markers

Available pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Integration tests with dependencies
- `@pytest.mark.requires_mongodb` - Tests requiring MongoDB
- `@pytest.mark.requires_chromadb` - Tests requiring ChromaDB
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.asyncio` - Async tests (auto-detected)

## Test Data Best Practices

1. **Use factories for all test data** - Don't create dictionaries manually
2. **Override only what matters** - Use factory defaults, override specifics
3. **Keep tests independent** - Each test should set up its own data
4. **Clean up automatically** - Fixtures handle cleanup between tests
5. **Use realistic data** - Factory defaults mirror production data
6. **Test edge cases** - Create data representing boundary conditions

## Coverage Goals

- **Unit tests**: 80%+ coverage of business logic
- **Integration tests**: Cover all API endpoints and database operations
- **Fast execution**: Unit tests < 0.1s, integration tests < 1s
- **Isolated tests**: No shared mutable state between tests

## Troubleshooting

### ImportError: No module named 'mongomock_motor'

```bash
pip install mongomock-motor
```

### Tests hang on async operations

Ensure you're using `@pytest.mark.asyncio` and `pytest-asyncio` is installed:

```bash
pip install pytest-asyncio
```

### Unique constraint violations in tests

Mongomock doesn't enforce unique constraints like real MongoDB. Tests expecting
DuplicateKeyError will behave differently with mongomock vs real MongoDB.

### Fixture not found errors

Ensure fixtures are defined in `conftest.py` or imported from the correct module.

## Next Steps

1. **Add API implementation** - Wire up FastAPI endpoints to use these tests
2. **Add service layer tests** - Test business logic in service modules
3. **Add LLM integration tests** - Test prompt evaluation with mock responses
4. **Add E2E tests** - Full workflow tests from signal ingestion to COP publish
5. **Set up CI/CD** - Run tests automatically on PR and merge

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [mongomock-motor](https://github.com/michaelkryukov/mongomock_motor)
- [HTTPX testing](https://www.python-httpx.org/advanced/#testing)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
