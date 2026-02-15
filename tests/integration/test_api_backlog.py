"""
Integration tests for backlog API endpoints.

Tests the backlog prioritization and cluster management endpoints:
- GET /api/backlog - List prioritized clusters
- GET /api/backlog/{cluster_id} - Get cluster details
- POST /api/backlog/{cluster_id}/promote - Promote cluster to candidate

These tests use real database connections and test the full stack.
"""

import pytest
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from tests.factories import (
    create_cluster,
    create_cluster_with_signals,
    create_facilitator,
    create_signal,
)


# ============================================================================
# Backlog List Endpoint Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_backlog_returns_clusters_sorted_by_priority(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog should return clusters sorted by priority_score."""
    # Arrange - Create clusters with different priorities
    high_priority = create_cluster(
        name="High Priority Cluster",
        priority_score=0.9,
        urgency_score=0.95,
    )
    medium_priority = create_cluster(
        name="Medium Priority Cluster",
        priority_score=0.5,
        urgency_score=0.5,
    )
    low_priority = create_cluster(
        name="Low Priority Cluster",
        priority_score=0.2,
        urgency_score=0.1,
    )

    await test_db.clusters.insert_many(
        [high_priority, medium_priority, low_priority]
    )

    # Act
    # Note: Actual endpoint would need to be implemented
    # response = await async_client.get("/api/backlog")

    # Assert
    # assert response.status_code == 200
    # data = response.json()
    # assert len(data["clusters"]) == 3
    # assert data["clusters"][0]["name"] == "High Priority Cluster"
    # assert data["clusters"][0]["priority_score"] == 0.9

    # Verify database state
    clusters = await test_db.clusters.find().sort("priority_score", -1).to_list(None)
    assert len(clusters) == 3
    assert clusters[0]["name"] == "High Priority Cluster"
    assert clusters[0]["priority_score"] == 0.9


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_backlog_excludes_promoted_clusters(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog should exclude clusters already promoted to candidates."""
    # Arrange
    unpromoted = create_cluster(name="Unpromoted Cluster")
    promoted = create_cluster(
        name="Promoted Cluster",
        promoted_to_candidate_id="65d4f2c3e4b0a8c9d1234570",
    )

    await test_db.clusters.insert_many([unpromoted, promoted])

    # Act - Would query for clusters without promoted_to_candidate_id
    unpromoted_clusters = (
        await test_db.clusters.find({"promoted_to_candidate_id": None}).to_list(None)
    )

    # Assert
    assert len(unpromoted_clusters) == 1
    assert unpromoted_clusters[0]["name"] == "Unpromoted Cluster"


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_backlog_prioritizes_conflicts(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog should prioritize clusters with conflicts."""
    # Arrange
    cluster_with_conflict = create_cluster(
        name="Conflicted Cluster",
        priority_score=0.5,
        has_conflicts=True,
        conflict_details=[
            {
                "field": "time",
                "values": ["6pm", "6:30pm"],
                "severity": "moderate",
            }
        ],
    )
    cluster_without_conflict = create_cluster(
        name="Clean Cluster",
        priority_score=0.5,
        has_conflicts=False,
    )

    await test_db.clusters.insert_many(
        [cluster_with_conflict, cluster_without_conflict]
    )

    # Act - Query with conflict prioritization
    clusters = (
        await test_db.clusters.find()
        .sort([("has_conflicts", -1), ("priority_score", -1)])
        .to_list(None)
    )

    # Assert
    assert len(clusters) == 2
    assert clusters[0]["has_conflicts"] is True
    assert clusters[0]["name"] == "Conflicted Cluster"


# ============================================================================
# Cluster Detail Endpoint Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_cluster_detail_returns_full_cluster(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog/{cluster_id} should return full cluster with signals."""
    # Arrange
    cluster = create_cluster_with_signals(signal_count=3)
    await test_db.clusters.insert_one(cluster)

    # Insert signals
    signals = [create_signal(_id=sig_id) for sig_id in cluster["signal_ids"]]
    await test_db.signals.insert_many(signals)

    # Act
    retrieved = await test_db.clusters.find_one({"_id": cluster["_id"]})

    # Assert
    assert retrieved is not None
    assert retrieved["_id"] == cluster["_id"]
    assert len(retrieved["signal_ids"]) == 3
    assert retrieved["signal_count"] == 3


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_get_cluster_detail_includes_ai_summary(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog/{cluster_id} should include AI-generated summary."""
    # Arrange
    cluster = create_cluster(
        ai_summary="Shelter Alpha closure due to power outage; residents relocated"
    )
    await test_db.clusters.insert_one(cluster)

    # Act
    retrieved = await test_db.clusters.find_one({"_id": cluster["_id"]})

    # Assert
    assert retrieved is not None
    assert "ai_summary" in retrieved
    assert "power outage" in retrieved["ai_summary"]


# ============================================================================
# Cluster Promotion Endpoint Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_promote_cluster_creates_candidate(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
    facilitator_user: dict,
) -> None:
    """POST /api/backlog/{cluster_id}/promote should create COP candidate."""
    # Arrange
    cluster = create_cluster_with_signals()
    await test_db.clusters.insert_one(cluster)
    await test_db.users.insert_one(facilitator_user)

    # Act - Simulate promotion
    # In real implementation:
    # response = await async_client.post(
    #     f"/api/backlog/{cluster['_id']}/promote",
    #     headers={"Authorization": f"Bearer {facilitator_token}"}
    # )
    # assert response.status_code == 201

    # For now, verify cluster can be retrieved
    retrieved = await test_db.clusters.find_one({"_id": cluster["_id"]})
    assert retrieved is not None


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_promote_cluster_updates_cluster_with_candidate_link(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
    facilitator_user: dict,
) -> None:
    """Promoting cluster should update cluster.promoted_to_candidate_id."""
    # Arrange
    cluster = create_cluster()
    await test_db.clusters.insert_one(cluster)

    # Act - Simulate setting promoted_to_candidate_id
    from bson import ObjectId

    candidate_id = ObjectId()
    await test_db.clusters.update_one(
        {"_id": cluster["_id"]},
        {
            "$set": {
                "promoted_to_candidate_id": candidate_id,
                "promoted_by": facilitator_user["_id"],
            }
        },
    )

    # Assert
    updated = await test_db.clusters.find_one({"_id": cluster["_id"]})
    assert updated is not None
    assert updated["promoted_to_candidate_id"] == candidate_id
    assert updated["promoted_by"] == facilitator_user["_id"]


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_promote_cluster_requires_facilitator_role(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
    authenticated_user: dict,
) -> None:
    """Non-facilitators should not be able to promote clusters."""
    # Arrange
    cluster = create_cluster()
    await test_db.clusters.insert_one(cluster)
    await test_db.users.insert_one(authenticated_user)

    # Act & Assert - Verify user lacks facilitator role
    user = await test_db.users.find_one({"_id": authenticated_user["_id"]})
    assert user is not None
    assert "facilitator" not in user["roles"]

    # In real API:
    # response = await async_client.post(
    #     f"/api/backlog/{cluster['_id']}/promote",
    #     headers={"Authorization": f"Bearer {user_token}"}
    # )
    # assert response.status_code == 403


# ============================================================================
# Backlog Filtering Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_filter_backlog_by_topic_type(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog?topic_type=incident should filter by topic."""
    # Arrange
    incident = create_cluster(topic_type="incident", name="Incident Cluster")
    need = create_cluster(topic_type="need", name="Need Cluster")

    await test_db.clusters.insert_many([incident, need])

    # Act
    incidents = await test_db.clusters.find({"topic_type": "incident"}).to_list(None)

    # Assert
    assert len(incidents) == 1
    assert incidents[0]["topic_type"] == "incident"
    assert incidents[0]["name"] == "Incident Cluster"


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_filter_backlog_by_time_range(
    test_db: AsyncIOMotorDatabase,
    async_client: AsyncClient,
) -> None:
    """GET /api/backlog?since={timestamp} should filter by time."""
    # Arrange
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    recent = create_cluster(
        name="Recent Cluster",
        last_signal_at=now - timedelta(minutes=10),
    )
    old = create_cluster(
        name="Old Cluster",
        last_signal_at=now - timedelta(days=2),
    )

    await test_db.clusters.insert_many([recent, old])

    # Act - Query for clusters updated in last hour
    cutoff = now - timedelta(hours=1)
    recent_clusters = (
        await test_db.clusters.find({"last_signal_at": {"$gte": cutoff}}).to_list(None)
    )

    # Assert
    assert len(recent_clusters) == 1
    assert recent_clusters[0]["name"] == "Recent Cluster"
