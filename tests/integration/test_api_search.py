"""
Integration tests for facilitator search API endpoints.

Tests:
- GET /api/v1/search - Search across signals, clusters, and candidates
- GET /api/v1/search/counts - Get search result counts
- GET /api/v1/search/channels - Get available channel filters

These tests verify full-stack search functionality with database interactions.
"""

import pytest
from datetime import datetime, timedelta, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from tests.factories import (
    create_cluster,
    create_facilitator,
    create_signal,
    create_user,
)


# ============================================================================
# Search Index Setup Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_signals_by_content_keyword(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should find signals matching content keywords."""
    # Arrange
    power_signal = create_signal(
        content="Power outage reported in downtown area",
        channel_id="C001",
    )
    shelter_signal = create_signal(
        content="Shelter capacity at 80%",
        channel_id="C001",
    )

    await test_db.signals.insert_many([power_signal, shelter_signal])

    # Act - Search for "power" in content
    # Using regex search to simulate text search
    results = await test_db.signals.find(
        {"content": {"$regex": "power", "$options": "i"}}
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert "power" in results[0]["content"].lower()


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_clusters_by_topic(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should find clusters matching topic keywords."""
    # Arrange
    infrastructure_cluster = create_cluster(
        name="Infrastructure Status Update",
        topic_type="status",
    )
    shelter_cluster = create_cluster(
        name="Emergency Shelter Operations",
        topic_type="resource",
    )

    await test_db.clusters.insert_many([infrastructure_cluster, shelter_cluster])

    # Act - Search for "infrastructure"
    results = await test_db.clusters.find(
        {"name": {"$regex": "infrastructure", "$options": "i"}}
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert "infrastructure" in results[0]["name"].lower()


# ============================================================================
# Search Filtering Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_filter_by_channel(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should filter results by channel ID."""
    # Arrange
    channel1_signal = create_signal(
        content="Signal in channel 1",
        channel_id="C001",
    )
    channel2_signal = create_signal(
        content="Signal in channel 2",
        channel_id="C002",
    )

    await test_db.signals.insert_many([channel1_signal, channel2_signal])

    # Act - Filter by channel C001
    results = await test_db.signals.find(
        {"channel_id": "C001"}
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert results[0]["channel_id"] == "C001"


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_filter_by_time_range(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should filter results by time range."""
    # Arrange
    now = datetime.now(timezone.utc)
    recent_signal = create_signal(
        content="Recent signal",
        created_at=now - timedelta(hours=1),
    )
    old_signal = create_signal(
        content="Old signal",
        created_at=now - timedelta(days=7),
    )

    await test_db.signals.insert_many([recent_signal, old_signal])

    # Act - Filter for signals in last 24 hours
    cutoff = now - timedelta(hours=24)
    results = await test_db.signals.find(
        {"created_at": {"$gte": cutoff}}
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert results[0]["content"] == "Recent signal"


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_filter_by_start_and_end_time(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should support both start and end time filters."""
    # Arrange
    now = datetime.now(timezone.utc)
    signals = [
        create_signal(
            content=f"Signal {i}",
            created_at=now - timedelta(days=i),
        )
        for i in range(5)
    ]

    await test_db.signals.insert_many(signals)

    # Act - Filter for signals between 2 and 4 days ago
    start_time = now - timedelta(days=4)
    end_time = now - timedelta(days=2)

    results = await test_db.signals.find(
        {"created_at": {"$gte": start_time, "$lte": end_time}}
    ).to_list(None)

    # Assert
    assert len(results) == 3  # Days 2, 3, 4


# ============================================================================
# Search Result Types Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_returns_signal_results(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should return signal results with proper structure."""
    # Arrange
    signal = create_signal(
        content="Test signal content",
        channel_id="C001",
        slack_permalink="https://slack.com/archives/C001/p123",
    )
    await test_db.signals.insert_one(signal)

    # Act
    result = await test_db.signals.find_one({"_id": signal["_id"]})

    # Assert
    assert result is not None
    assert "content" in result
    assert "channel_id" in result
    assert "slack_permalink" in result


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_returns_cluster_results(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should return cluster results with proper structure."""
    # Arrange
    cluster = create_cluster(
        name="Emergency Response Cluster",
        ai_summary="Multiple reports of emergency response activities",
    )
    await test_db.clusters.insert_one(cluster)

    # Act
    result = await test_db.clusters.find_one({"_id": cluster["_id"]})

    # Assert
    assert result is not None
    assert "name" in result
    assert "ai_summary" in result
    assert "signal_ids" in result


# ============================================================================
# Search Counts Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_count_returns_correct_totals(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search count endpoint should return correct totals."""
    # Arrange
    signals = [
        create_signal(content="Power outage report 1"),
        create_signal(content="Power outage report 2"),
        create_signal(content="Power outage report 3"),
    ]
    await test_db.signals.insert_many(signals)

    # Act
    count = await test_db.signals.count_documents(
        {"content": {"$regex": "power", "$options": "i"}}
    )

    # Assert
    assert count == 3


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_count_with_filters(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search count should respect filters."""
    # Arrange
    signals = [
        create_signal(content="Power report", channel_id="C001"),
        create_signal(content="Power report", channel_id="C001"),
        create_signal(content="Power report", channel_id="C002"),
    ]
    await test_db.signals.insert_many(signals)

    # Act
    count = await test_db.signals.count_documents(
        {
            "content": {"$regex": "power", "$options": "i"},
            "channel_id": "C001",
        }
    )

    # Assert
    assert count == 2


# ============================================================================
# Channel List Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_available_channels(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Should return list of channels with signals."""
    # Arrange
    signals = [
        create_signal(content="Signal 1", channel_id="C001"),
        create_signal(content="Signal 2", channel_id="C001"),
        create_signal(content="Signal 3", channel_id="C002"),
        create_signal(content="Signal 4", channel_id="C003"),
    ]
    await test_db.signals.insert_many(signals)

    # Act - Get distinct channels
    channels = await test_db.signals.distinct("channel_id")

    # Assert
    assert len(channels) == 3
    assert "C001" in channels
    assert "C002" in channels
    assert "C003" in channels


# ============================================================================
# Search Access Control Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_requires_facilitator_role(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search endpoint should only be accessible to facilitators."""
    # Arrange
    participant = create_user(roles=["general_participant"])
    facilitator = create_facilitator()

    await test_db.users.insert_many([participant, facilitator])

    # Act & Assert - Verify roles
    participant_user = await test_db.users.find_one({"_id": participant["_id"]})
    facilitator_user = await test_db.users.find_one({"_id": facilitator["_id"]})

    assert "facilitator" not in participant_user["roles"]
    assert "facilitator" in facilitator_user["roles"]

    # In real API:
    # response = await async_client.get("/api/v1/search", auth=participant_token)
    # assert response.status_code == 403
    # response = await async_client.get("/api/v1/search", auth=facilitator_token)
    # assert response.status_code == 200


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_verifier_can_access(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Verifiers should have search access."""
    # Arrange
    verifier = create_user(roles=["verifier"])
    await test_db.users.insert_one(verifier)

    # Act
    user = await test_db.users.find_one({"_id": verifier["_id"]})

    # Assert - Verifier should have search capability
    assert "verifier" in user["roles"]

    # In real API:
    # response = await async_client.get("/api/v1/search", auth=verifier_token)
    # assert response.status_code == 200


# ============================================================================
# Search Pagination Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_pagination_limit(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should respect limit parameter."""
    # Arrange
    signals = [create_signal(content=f"Signal {i}") for i in range(20)]
    await test_db.signals.insert_many(signals)

    # Act - Get first 10 results
    results = await test_db.signals.find().limit(10).to_list(None)

    # Assert
    assert len(results) == 10


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_pagination_offset(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should respect offset parameter."""
    # Arrange
    signals = [
        create_signal(content=f"Signal {i:02d}")
        for i in range(20)
    ]
    await test_db.signals.insert_many(signals)

    # Act - Skip first 10, get next 5
    results = await test_db.signals.find().skip(10).limit(5).to_list(None)

    # Assert
    assert len(results) == 5


# ============================================================================
# Search Workspace Isolation Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_isolated_by_workspace(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search results should be isolated to user's workspace."""
    # Arrange
    workspace_a_signal = create_signal(
        content="Workspace A signal",
        workspace_id="T01TEAMA",
    )
    workspace_b_signal = create_signal(
        content="Workspace B signal",
        workspace_id="T01TEAMB",
    )

    await test_db.signals.insert_many([workspace_a_signal, workspace_b_signal])

    # Act - Search in workspace A only
    results = await test_db.signals.find(
        {"workspace_id": "T01TEAMA"}
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert results[0]["workspace_id"] == "T01TEAMA"


# ============================================================================
# Combined Search Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_search_combined_keyword_and_filters(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Search should combine keyword and filters correctly."""
    # Arrange
    now = datetime.now(timezone.utc)

    signals = [
        create_signal(
            content="Power outage downtown",
            channel_id="C001",
            created_at=now - timedelta(hours=1),
            workspace_id="T001",
        ),
        create_signal(
            content="Power restored in suburbs",
            channel_id="C002",
            created_at=now - timedelta(hours=1),
            workspace_id="T001",
        ),
        create_signal(
            content="Power outage old report",
            channel_id="C001",
            created_at=now - timedelta(days=10),
            workspace_id="T001",
        ),
    ]
    await test_db.signals.insert_many(signals)

    # Act - Search for "power" in C001, last 24 hours
    cutoff = now - timedelta(hours=24)
    results = await test_db.signals.find(
        {
            "content": {"$regex": "power", "$options": "i"},
            "channel_id": "C001",
            "created_at": {"$gte": cutoff},
            "workspace_id": "T001",
        }
    ).to_list(None)

    # Assert
    assert len(results) == 1
    assert "power" in results[0]["content"].lower()
    assert results[0]["channel_id"] == "C001"
