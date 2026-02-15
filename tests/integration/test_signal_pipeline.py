"""Integration tests for end-to-end signal processing pipeline.

Tests the complete flow:
1. Signal creation and storage
2. Embedding generation
3. Cluster assignment
4. Duplicate/conflict detection
"""

import pytest
from bson import ObjectId

from integritykit.models.signal import Signal, SignalCreate, SourceQuality, AIFlags
from integritykit.models.cluster import Cluster
from integritykit.services.database import SignalRepository, ClusterRepository
from tests.factories import create_signal


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestSignalCreationAndStorage:
    """Test signal creation and storage in MongoDB."""

    @pytest.mark.asyncio
    async def test_create_signal_in_database(self, mongodb_collections):
        """Test creating signal stores in MongoDB."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Shelter Alpha is closing at 6pm due to power outage",
        )

        # Act
        signal = await signal_repo.create(signal_data)

        # Assert
        assert signal.id is not None
        assert signal.content == "Shelter Alpha is closing at 6pm due to power outage"
        assert signal.slack_channel_id == "C01TEST"
        assert isinstance(signal.source_quality, SourceQuality)
        assert isinstance(signal.ai_flags, AIFlags)
        assert signal.cluster_ids == []

    @pytest.mark.asyncio
    async def test_retrieve_signal_by_id(self, mongodb_collections):
        """Test retrieving signal by MongoDB ObjectId."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test signal",
        )
        created_signal = await signal_repo.create(signal_data)

        # Act
        retrieved_signal = await signal_repo.get_by_id(created_signal.id)

        # Assert
        assert retrieved_signal is not None
        assert retrieved_signal.id == created_signal.id
        assert retrieved_signal.content == "Test signal"

    @pytest.mark.asyncio
    async def test_retrieve_signal_by_slack_ts(self, mongodb_collections):
        """Test retrieving signal by Slack message timestamp."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test signal",
        )
        await signal_repo.create(signal_data)

        # Act
        retrieved_signal = await signal_repo.get_by_slack_ts(
            workspace_id="T01TEST",
            channel_id="C01TEST",
            message_ts="1234567890.123456",
        )

        # Assert
        assert retrieved_signal is not None
        assert retrieved_signal.content == "Test signal"

    @pytest.mark.asyncio
    async def test_duplicate_signal_prevents_creation(self, mongodb_collections):
        """Test duplicate signals (same Slack ts) are rejected by unique index."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="First signal",
        )
        await signal_repo.create(signal_data)

        # Act & Assert - attempt to create duplicate
        duplicate_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",  # Same timestamp
            slack_user_id="U01USER2",
            slack_permalink="https://test.slack.com",
            content="Duplicate signal",
        )

        # Should raise duplicate key error from MongoDB
        with pytest.raises(Exception):  # Will be DuplicateKeyError from pymongo
            await signal_repo.create(duplicate_data)


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestSignalClusterAssignment:
    """Test signal assignment to clusters."""

    @pytest.mark.asyncio
    async def test_add_signal_to_cluster(self, mongodb_collections):
        """Test adding signal to cluster updates both documents."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create signal
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test signal",
        )
        signal = await signal_repo.create(signal_data)

        # Create cluster
        cluster_dict = create_signal(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            summary="Test summary",
        )
        # Convert factory output to ClusterCreate-compatible format
        from integritykit.models.cluster import ClusterCreate

        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            summary="Test summary",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Act - add signal to cluster
        updated_cluster = await cluster_repo.add_signal(
            cluster_id=cluster.id,
            signal_id=signal.id,
        )
        updated_signal = await signal_repo.add_to_cluster(
            signal_id=signal.id,
            cluster_id=cluster.id,
        )

        # Assert
        assert signal.id in updated_cluster.signal_ids
        assert cluster.id in updated_signal.cluster_ids

    @pytest.mark.asyncio
    async def test_signal_in_multiple_clusters(self, mongodb_collections):
        """Test signal can belong to multiple clusters."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        # Create signal
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Signal about shelter and medical supplies",
        )
        signal = await signal_repo.create(signal_data)

        # Create two clusters
        from integritykit.models.cluster import ClusterCreate

        cluster1_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Shelter Resources",
        )
        cluster1 = await cluster_repo.create(cluster1_data)

        cluster2_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Medical Supplies",
        )
        cluster2 = await cluster_repo.create(cluster2_data)

        # Act - add signal to both clusters
        await cluster_repo.add_signal(cluster1.id, signal.id)
        await cluster_repo.add_signal(cluster2.id, signal.id)
        await signal_repo.add_to_cluster(signal.id, cluster1.id)
        updated_signal = await signal_repo.add_to_cluster(signal.id, cluster2.id)

        # Assert
        assert len(updated_signal.cluster_ids) == 2
        assert cluster1.id in updated_signal.cluster_ids
        assert cluster2.id in updated_signal.cluster_ids

    @pytest.mark.asyncio
    async def test_list_signals_by_cluster(self, mongodb_collections):
        """Test listing all signals in a cluster."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        cluster_repo = ClusterRepository(mongodb_collections["clusters"])

        from integritykit.models.cluster import ClusterCreate

        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Cluster",
        )
        cluster = await cluster_repo.create(cluster_data)

        # Create multiple signals and add to cluster
        signal_ids = []
        for i in range(3):
            signal_data = SignalCreate(
                slack_workspace_id="T01TEST",
                slack_channel_id="C01TEST",
                slack_message_ts=f"123456789{i}.123456",
                slack_user_id="U01TEST",
                slack_permalink=f"https://test.slack.com/{i}",
                content=f"Signal {i}",
            )
            signal = await signal_repo.create(signal_data)
            await cluster_repo.add_signal(cluster.id, signal.id)
            await signal_repo.add_to_cluster(signal.id, cluster.id)
            signal_ids.append(signal.id)

        # Act
        signals = await signal_repo.list_by_cluster(cluster.id)

        # Assert
        assert len(signals) == 3
        retrieved_ids = [s.id for s in signals]
        for signal_id in signal_ids:
            assert signal_id in retrieved_ids


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestSignalUpdates:
    """Test updating signal metadata."""

    @pytest.mark.asyncio
    async def test_update_signal_ai_flags(self, mongodb_collections):
        """Test updating signal AI flags for duplicate detection."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test signal",
        )
        signal = await signal_repo.create(signal_data)

        canonical_id = ObjectId()

        # Act - mark as duplicate
        updated_signal = await signal_repo.update(
            signal.id,
            {
                "ai_flags.is_duplicate": True,
                "ai_flags.duplicate_of": canonical_id,
            },
        )

        # Assert
        assert updated_signal is not None
        assert updated_signal.ai_flags.is_duplicate is True
        assert updated_signal.ai_flags.duplicate_of == canonical_id

    @pytest.mark.asyncio
    async def test_update_signal_embedding_id(self, mongodb_collections):
        """Test updating signal with embedding reference."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test signal",
        )
        signal = await signal_repo.create(signal_data)

        # Act
        embedding_id = str(signal.id)
        updated_signal = await signal_repo.update(
            signal.id,
            {"embedding_id": embedding_id},
        )

        # Assert
        assert updated_signal.embedding_id == embedding_id

    @pytest.mark.asyncio
    async def test_update_nonexistent_signal(self, mongodb_collections):
        """Test updating non-existent signal returns None."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])
        fake_id = ObjectId()

        # Act
        result = await signal_repo.update(
            fake_id,
            {"content": "Updated content"},
        )

        # Assert
        assert result is None


@pytest.mark.integration
@pytest.mark.requires_mongodb
class TestSignalQuerying:
    """Test querying signals by various criteria."""

    @pytest.mark.asyncio
    async def test_list_signals_by_channel(self, mongodb_collections):
        """Test listing signals by Slack channel."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])

        # Create signals in different channels
        for i in range(3):
            signal_data = SignalCreate(
                slack_workspace_id="T01TEST",
                slack_channel_id="C01CHANNEL1",
                slack_message_ts=f"123456789{i}.123456",
                slack_user_id="U01TEST",
                slack_permalink=f"https://test.slack.com/{i}",
                content=f"Signal {i} in channel 1",
            )
            await signal_repo.create(signal_data)

        # Create signal in different channel
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01CHANNEL2",
            slack_message_ts="1234567899.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/other",
            content="Signal in channel 2",
        )
        await signal_repo.create(signal_data)

        # Act
        channel1_signals = await signal_repo.list_by_channel("C01CHANNEL1")

        # Assert
        assert len(channel1_signals) == 3
        for signal in channel1_signals:
            assert signal.slack_channel_id == "C01CHANNEL1"

    @pytest.mark.asyncio
    async def test_list_signals_with_pagination(self, mongodb_collections):
        """Test listing signals with pagination."""
        # Arrange
        signal_repo = SignalRepository(mongodb_collections["signals"])

        # Create multiple signals
        for i in range(10):
            signal_data = SignalCreate(
                slack_workspace_id="T01TEST",
                slack_channel_id="C01TEST",
                slack_message_ts=f"123456789{i}.123456",
                slack_user_id="U01TEST",
                slack_permalink=f"https://test.slack.com/{i}",
                content=f"Signal {i}",
            )
            await signal_repo.create(signal_data)

        # Act - get first page
        page1 = await signal_repo.list_by_channel("C01TEST", limit=5, offset=0)
        page2 = await signal_repo.list_by_channel("C01TEST", limit=5, offset=5)

        # Assert
        assert len(page1) == 5
        assert len(page2) == 5
        # Ensure no overlap
        page1_ids = {s.id for s in page1}
        page2_ids = {s.id for s in page2}
        assert len(page1_ids & page2_ids) == 0  # No intersection
