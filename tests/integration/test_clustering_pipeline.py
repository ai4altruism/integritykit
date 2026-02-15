"""Integration tests for clustering pipeline.

Tests the complete clustering flow:
1. New cluster creation
2. Adding signals to clusters
3. Priority score updates
4. Backlog ordering
"""

import pytest
from bson import ObjectId

from integritykit.models.cluster import ClusterCreate, PriorityScores
from integritykit.models.signal import SignalCreate
from integritykit.services.database import SignalRepository, ClusterRepository


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterCreationAndStorage:
    """Test cluster creation and storage in MongoDB."""

    @pytest.mark.asyncio
    async def test_create_cluster_in_database(self, mongodb_collections):
        """Test creating cluster stores in MongoDB."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        signal_id = ObjectId()

        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            signal_ids=[signal_id],
            topic="Shelter Alpha Closure",
            incident_type="infrastructure",
            summary="Shelter Alpha closing due to power outage",
        )

        # Act
        cluster = await cluster_repo.create(cluster_data)

        # Assert
        assert cluster.id is not None
        assert cluster.topic == "Shelter Alpha Closure"
        assert cluster.incident_type == "infrastructure"
        assert signal_id in cluster.signal_ids
        assert cluster.signal_count == 1
        assert isinstance(cluster.priority_scores, PriorityScores)

    @pytest.mark.asyncio
    async def test_retrieve_cluster_by_id(self, mongodb_collections):
        """Test retrieving cluster by MongoDB ObjectId."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
            summary="Test summary",
        )
        created_cluster = await cluster_repo.create(cluster_data)

        # Act
        retrieved_cluster = await cluster_repo.get_by_id(created_cluster.id)

        # Assert
        assert retrieved_cluster is not None
        assert retrieved_cluster.id == created_cluster.id
        assert retrieved_cluster.topic == "Test Cluster"

    @pytest.mark.asyncio
    async def test_cluster_with_default_priority_scores(self, mongodb_collections):
        """Test cluster created with default priority scores."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )

        # Act
        cluster = await cluster_repo.create(cluster_data)

        # Assert
        assert cluster.priority_scores.urgency == 0.5
        assert cluster.priority_scores.impact == 0.5
        assert cluster.priority_scores.risk == 0.5


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterSignalManagement:
    """Test adding and managing signals in clusters."""

    @pytest.mark.asyncio
    async def test_add_signal_to_cluster(self, mongodb_collections):
        """Test adding signal to cluster updates signal list."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        signal_id = ObjectId()

        # Act
        updated_cluster = await cluster_repo.add_signal(
            cluster_id=cluster.id,
            signal_id=signal_id,
        )

        # Assert
        assert signal_id in updated_cluster.signal_ids
        assert updated_cluster.signal_count == 1

    @pytest.mark.asyncio
    async def test_add_multiple_signals_to_cluster(self, mongodb_collections):
        """Test adding multiple signals to cluster."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        signal_ids = [ObjectId() for _ in range(5)]

        # Act
        for signal_id in signal_ids:
            cluster = await cluster_repo.add_signal(cluster.id, signal_id)

        # Assert
        assert cluster.signal_count == 5
        for signal_id in signal_ids:
            assert signal_id in cluster.signal_ids

    @pytest.mark.asyncio
    async def test_add_duplicate_signal_to_cluster(self, mongodb_collections):
        """Test adding same signal twice doesn't duplicate (using $addToSet)."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        signal_id = ObjectId()

        # Act - add same signal twice
        await cluster_repo.add_signal(cluster.id, signal_id)
        updated_cluster = await cluster_repo.add_signal(cluster.id, signal_id)

        # Assert - should only appear once (MongoDB $addToSet behavior)
        assert updated_cluster.signal_count == 1
        assert updated_cluster.signal_ids.count(signal_id) == 1


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterPriorityScores:
    """Test cluster priority score management."""

    @pytest.mark.asyncio
    async def test_update_priority_scores(self, mongodb_collections):
        """Test updating cluster priority scores."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="High Priority Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act
        new_scores = PriorityScores(
            urgency=85.0,
            urgency_reasoning="Time-sensitive shelter closure",
            impact=70.0,
            impact_reasoning="Affects 150+ families",
            risk=65.0,
            risk_reasoning="Safety risk if not addressed",
        )
        updated_cluster = await cluster_repo.update_priority_scores(
            cluster.id,
            new_scores.model_dump(),
        )

        # Assert
        assert updated_cluster.priority_scores.urgency == 85.0
        assert updated_cluster.priority_scores.impact == 70.0
        assert updated_cluster.priority_scores.risk == 65.0
        assert updated_cluster.priority_scores.urgency_reasoning == "Time-sensitive shelter closure"

    @pytest.mark.asyncio
    async def test_priority_composite_score(self, mongodb_collections):
        """Test composite priority score calculation."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act
        new_scores = PriorityScores(
            urgency=100.0,
            impact=50.0,
            risk=0.0,
        )
        updated_cluster = await cluster_repo.update_priority_scores(
            cluster.id,
            new_scores.model_dump(),
        )

        # Assert - composite score: (100 * 0.4) + (50 * 0.35) + (0 * 0.25) = 57.5
        assert updated_cluster.priority_scores.composite_score == pytest.approx(57.5)


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterBacklogOrdering:
    """Test cluster backlog ordering by priority."""

    @pytest.mark.asyncio
    async def test_list_unpromoted_clusters(self, mongodb_collections):
        """Test listing unpromoted clusters for backlog."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create promoted cluster (should not appear)
        promoted_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Promoted Cluster",
        )
        promoted = await cluster_repo.create(promoted_data)
        await cluster_repo.update(promoted.id, {"promoted_to_candidate": True})

        # Create unpromoted clusters with different priorities
        low_priority_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Low Priority",
        )
        low_priority = await cluster_repo.create(low_priority_data)
        await cluster_repo.update_priority_scores(
            low_priority.id,
            PriorityScores(urgency=20.0, impact=20.0, risk=20.0).model_dump(),
        )

        high_priority_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="High Priority",
        )
        high_priority = await cluster_repo.create(high_priority_data)
        await cluster_repo.update_priority_scores(
            high_priority.id,
            PriorityScores(urgency=90.0, impact=80.0, risk=70.0).model_dump(),
        )

        # Act
        backlog_clusters = await cluster_repo.list_unpromoted_clusters(
            workspace_id="T01TEST",
            limit=10,
        )

        # Assert
        assert len(backlog_clusters) == 2  # Promoted cluster excluded
        # High priority should be first
        assert backlog_clusters[0].topic == "High Priority"
        assert backlog_clusters[1].topic == "Low Priority"

    @pytest.mark.asyncio
    async def test_backlog_pagination(self, mongodb_collections):
        """Test backlog pagination."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create multiple clusters
        for i in range(10):
            cluster_data = ClusterCreate(
                slack_workspace_id="T01TEST",
                topic=f"Cluster {i}",
            )
            cluster = await cluster_repo.create(cluster_data)
            await cluster_repo.update_priority_scores(
                cluster.id,
                PriorityScores(urgency=float(i), impact=float(i), risk=float(i)).model_dump(),
            )

        # Act
        page1 = await cluster_repo.list_unpromoted_clusters("T01TEST", limit=5, offset=0)
        page2 = await cluster_repo.list_unpromoted_clusters("T01TEST", limit=5, offset=5)

        # Assert
        assert len(page1) == 5
        assert len(page2) == 5
        # No overlap
        page1_ids = {c.id for c in page1}
        page2_ids = {c.id for c in page2}
        assert len(page1_ids & page2_ids) == 0

    @pytest.mark.asyncio
    async def test_backlog_workspace_filtering(self, mongodb_collections):
        """Test backlog filters by workspace."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create clusters in different workspaces
        workspace1_data = ClusterCreate(
            slack_workspace_id="T01WORKSPACE1",
            topic="Workspace 1 Cluster",
        )
        await cluster_repo.create(workspace1_data)

        workspace2_data = ClusterCreate(
            slack_workspace_id="T01WORKSPACE2",
            topic="Workspace 2 Cluster",
        )
        await cluster_repo.create(workspace2_data)

        # Act
        workspace1_clusters = await cluster_repo.list_unpromoted_clusters("T01WORKSPACE1")

        # Assert
        assert len(workspace1_clusters) == 1
        assert workspace1_clusters[0].slack_workspace_id == "T01WORKSPACE1"


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterUpdates:
    """Test updating cluster metadata."""

    @pytest.mark.asyncio
    async def test_update_cluster_summary(self, mongodb_collections):
        """Test updating cluster summary."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
            summary="Initial summary",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act
        updated_cluster = await cluster_repo.update(
            cluster.id,
            {"summary": "Updated summary with new information"},
        )

        # Assert
        assert updated_cluster.summary == "Updated summary with new information"

    @pytest.mark.asyncio
    async def test_update_cluster_conflicts(self, mongodb_collections):
        """Test updating cluster with conflict information."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act
        from integritykit.models.cluster import ConflictRecord, ConflictSeverity

        conflict = ConflictRecord(
            id="conflict-1",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.HIGH,
            description="Location mismatch",
        )

        updated_cluster = await cluster_repo.update(
            cluster.id,
            {"conflicts": [conflict.model_dump()]},
        )

        # Assert
        assert len(updated_cluster.conflicts) == 1
        assert updated_cluster.conflicts[0].severity == ConflictSeverity.HIGH
        assert updated_cluster.has_conflicts is True

    @pytest.mark.asyncio
    async def test_update_cluster_promotion(self, mongodb_collections):
        """Test marking cluster as promoted to COP candidate."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Ready for Promotion",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act
        cop_candidate_id = ObjectId()
        updated_cluster = await cluster_repo.update(
            cluster.id,
            {
                "promoted_to_candidate": True,
                "cop_candidate_id": cop_candidate_id,
            },
        )

        # Assert
        assert updated_cluster.promoted_to_candidate is True
        assert updated_cluster.cop_candidate_id == cop_candidate_id

    @pytest.mark.asyncio
    async def test_update_nonexistent_cluster(self, mongodb_collections):
        """Test updating non-existent cluster returns None."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])
        fake_id = ObjectId()

        # Act
        result = await cluster_repo.update(
            fake_id,
            {"summary": "Updated summary"},
        )

        # Assert
        assert result is None


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestClusterQuerying:
    """Test querying clusters by various criteria."""

    @pytest.mark.asyncio
    async def test_list_clusters_by_workspace(self, mongodb_collections):
        """Test listing clusters by workspace."""
        # Arrange
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create clusters in workspace
        for i in range(3):
            cluster_data = ClusterCreate(
                slack_workspace_id="T01WORKSPACE",
                topic=f"Cluster {i}",
            )
            await cluster_repo.create(cluster_data)

        # Create cluster in different workspace
        other_data = ClusterCreate(
            slack_workspace_id="T01OTHER",
            topic="Other Cluster",
        )
        await cluster_repo.create(other_data)

        # Act
        workspace_clusters = await cluster_repo.list_by_workspace("T01WORKSPACE")

        # Assert
        assert len(workspace_clusters) == 3
        for cluster in workspace_clusters:
            assert cluster.slack_workspace_id == "T01WORKSPACE"
