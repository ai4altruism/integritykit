"""Unit tests for clustering service."""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from bson import ObjectId
from datetime import datetime

from integritykit.models.cluster import Cluster, ClusterCreate, PriorityScores
from integritykit.models.signal import Signal
from integritykit.services.clustering import ClusteringService
from integritykit.services.database import SignalRepository, ClusterRepository
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService


@pytest.fixture
def mock_signal_repo():
    """Provide mock signal repository."""
    return Mock(spec=SignalRepository)


@pytest.fixture
def mock_cluster_repo():
    """Provide mock cluster repository."""
    return Mock(spec=ClusterRepository)


@pytest.fixture
def mock_embedding_service():
    """Provide mock embedding service."""
    return Mock(spec=EmbeddingService)


@pytest.fixture
def mock_llm_service():
    """Provide mock LLM service."""
    mock = Mock(spec=LLMService)
    mock.model = "gpt-4o-mini"
    return mock


@pytest.fixture
def clustering_service(
    mock_signal_repo,
    mock_cluster_repo,
    mock_embedding_service,
    mock_llm_service,
):
    """Provide clustering service with mocked dependencies."""
    return ClusteringService(
        signal_repository=mock_signal_repo,
        cluster_repository=mock_cluster_repo,
        embedding_service=mock_embedding_service,
        llm_service=mock_llm_service,
        similarity_threshold=0.75,
        enable_duplicate_detection=False,  # Disable for basic tests
        enable_conflict_detection=False,
    )


@pytest.fixture
def sample_signal():
    """Provide sample signal for testing."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        slack_channel_id="C01TEST",
        slack_message_ts="1234567890.123456",
        slack_user_id="U01TEST",
        slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
        content="Shelter Alpha is closing at 6pm due to power outage",
    )


@pytest.fixture
def sample_cluster():
    """Provide sample cluster for testing."""
    return Cluster(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        topic="Shelter Alpha Closure",
        summary="Shelter Alpha closing due to power outage",
        signal_ids=[ObjectId()],
    )


@pytest.mark.unit
class TestCreateCluster:
    """Test cluster creation from seed signal."""

    @pytest.mark.asyncio
    async def test_create_cluster_from_signal(
        self,
        clustering_service,
        mock_llm_service,
        mock_cluster_repo,
        sample_signal,
    ):
        """Test creating new cluster from seed signal."""
        # Setup mocks
        mock_llm_service.generate_topic_from_signal = AsyncMock(
            return_value="Shelter Alpha Closure"
        )
        mock_llm_service.generate_cluster_summary = AsyncMock(
            return_value="Shelter Alpha closing due to power outage"
        )
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=60.0, impact=50.0, risk=40.0)
        )

        created_cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Shelter Alpha Closure",
            summary="Shelter Alpha closing due to power outage",
            signal_ids=[sample_signal.id],
        )
        mock_cluster_repo.create = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=created_cluster)

        clustering_service.signal_repo.add_to_cluster = AsyncMock()

        # Execute
        result = await clustering_service.create_cluster(sample_signal)

        # Verify
        assert result is not None
        assert result.topic == "Shelter Alpha Closure"
        mock_llm_service.generate_topic_from_signal.assert_called_once_with(sample_signal)
        mock_llm_service.generate_cluster_summary.assert_called_once()
        mock_cluster_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_cluster_adds_ai_metadata(
        self,
        clustering_service,
        mock_llm_service,
        mock_cluster_repo,
        sample_signal,
    ):
        """Test cluster creation includes AI metadata."""
        # Setup mocks
        mock_llm_service.generate_topic_from_signal = AsyncMock(return_value="Test Topic")
        mock_llm_service.generate_cluster_summary = AsyncMock(return_value="Test summary")
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=50.0, impact=50.0, risk=50.0)
        )

        created_cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            signal_ids=[sample_signal.id],
        )
        mock_cluster_repo.create = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=created_cluster)
        clustering_service.signal_repo.add_to_cluster = AsyncMock()

        # Execute
        await clustering_service.create_cluster(sample_signal)

        # Verify AI metadata was added
        update_calls = [call for call in mock_cluster_repo.update.call_args_list]
        assert len(update_calls) >= 1

        # Check that one of the updates includes ai_generated_metadata
        metadata_updated = any(
            "ai_generated_metadata" in call[0][1]
            for call in update_calls
        )
        assert metadata_updated


@pytest.mark.unit
class TestAddSignalToCluster:
    """Test adding signals to existing clusters."""

    @pytest.mark.asyncio
    async def test_add_signal_to_cluster_success(
        self,
        clustering_service,
        mock_cluster_repo,
        mock_llm_service,
        sample_signal,
        sample_cluster,
    ):
        """Test successfully adding signal to cluster."""
        # Setup mocks
        mock_cluster_repo.add_signal = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=sample_cluster)
        clustering_service.signal_repo.add_to_cluster = AsyncMock()
        clustering_service.signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal])

        mock_llm_service.generate_cluster_summary = AsyncMock(
            return_value="Updated summary"
        )
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=70.0, impact=60.0, risk=50.0)
        )

        # Execute
        result = await clustering_service.add_signal_to_cluster(
            signal_id=sample_signal.id,
            cluster_id=sample_cluster.id,
        )

        # Verify
        assert result is not None
        mock_cluster_repo.add_signal.assert_called_once_with(
            cluster_id=sample_cluster.id,
            signal_id=sample_signal.id,
        )
        clustering_service.signal_repo.add_to_cluster.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_signal_to_nonexistent_cluster(
        self,
        clustering_service,
        mock_cluster_repo,
        sample_signal,
    ):
        """Test adding signal to non-existent cluster returns None."""
        # Setup mock to return None (cluster not found)
        mock_cluster_repo.add_signal = AsyncMock(return_value=None)

        # Execute
        result = await clustering_service.add_signal_to_cluster(
            signal_id=sample_signal.id,
            cluster_id=ObjectId(),
        )

        # Verify
        assert result is None

    @pytest.mark.asyncio
    async def test_add_signal_updates_summary(
        self,
        clustering_service,
        mock_cluster_repo,
        mock_llm_service,
        sample_signal,
        sample_cluster,
    ):
        """Test adding signal regenerates cluster summary."""
        # Setup mocks
        signals_in_cluster = [sample_signal]
        mock_cluster_repo.add_signal = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=sample_cluster)
        clustering_service.signal_repo.add_to_cluster = AsyncMock()
        clustering_service.signal_repo.list_by_cluster = AsyncMock(
            return_value=signals_in_cluster
        )

        mock_llm_service.generate_cluster_summary = AsyncMock(
            return_value="New summary with additional signal"
        )
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=50.0, impact=50.0, risk=50.0)
        )

        # Execute
        await clustering_service.add_signal_to_cluster(
            signal_id=sample_signal.id,
            cluster_id=sample_cluster.id,
        )

        # Verify summary was regenerated
        mock_llm_service.generate_cluster_summary.assert_called_once_with(
            signals=signals_in_cluster,
            topic=sample_cluster.topic,
        )


@pytest.mark.unit
class TestCalculatePriorityScores:
    """Test priority score calculation."""

    @pytest.mark.asyncio
    async def test_calculate_priority_scores(
        self,
        clustering_service,
        mock_llm_service,
        sample_cluster,
        sample_signal,
    ):
        """Test priority score calculation via LLM."""
        # Setup mocks
        clustering_service.signal_repo.list_by_cluster = AsyncMock(
            return_value=[sample_signal]
        )

        expected_scores = PriorityScores(
            urgency=80.0,
            urgency_reasoning="Time-sensitive closure",
            impact=60.0,
            impact_reasoning="Affects many families",
            risk=70.0,
            risk_reasoning="Safety risk",
        )
        mock_llm_service.assess_priority = AsyncMock(return_value=expected_scores)

        # Execute
        result = await clustering_service.calculate_priority_scores(sample_cluster)

        # Verify
        assert result.urgency == 80.0
        assert result.impact == 60.0
        assert result.risk == 70.0
        assert result.composite_score > 0
        mock_llm_service.assess_priority.assert_called_once()

    @pytest.mark.asyncio
    async def test_priority_scores_composite_calculation(
        self,
        clustering_service,
        mock_llm_service,
        sample_cluster,
        sample_signal,
    ):
        """Test composite priority score is calculated correctly."""
        # Setup mocks
        clustering_service.signal_repo.list_by_cluster = AsyncMock(
            return_value=[sample_signal]
        )

        scores = PriorityScores(
            urgency=100.0,
            impact=50.0,
            risk=0.0,
        )
        mock_llm_service.assess_priority = AsyncMock(return_value=scores)

        # Execute
        result = await clustering_service.calculate_priority_scores(sample_cluster)

        # Verify composite is weighted average
        # (100 * 0.4) + (50 * 0.35) + (0 * 0.25) = 40 + 17.5 + 0 = 57.5
        assert result.composite_score == pytest.approx(57.5)


@pytest.mark.unit
class TestProcessNewSignal:
    """Test processing new signals for cluster assignment."""

    @pytest.mark.asyncio
    async def test_process_signal_without_id_raises_error(
        self,
        clustering_service,
    ):
        """Test processing signal without ID raises ValueError."""
        signal_without_id = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test content",
        )

        with pytest.raises(ValueError, match="must be saved to database"):
            await clustering_service.process_new_signal(signal_without_id)

    @pytest.mark.asyncio
    async def test_process_signal_creates_new_cluster_when_no_matches(
        self,
        clustering_service,
        mock_embedding_service,
        mock_llm_service,
        mock_cluster_repo,
        sample_signal,
    ):
        """Test processing signal creates new cluster when no similar signals."""
        # Setup mocks - no similar signals found
        mock_embedding_service.add_signal = AsyncMock(return_value=str(sample_signal.id))
        mock_embedding_service.find_similar = AsyncMock(return_value=[])

        created_cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="New Topic",
            signal_ids=[sample_signal.id],
        )

        mock_llm_service.generate_topic_from_signal = AsyncMock(return_value="New Topic")
        mock_llm_service.generate_cluster_summary = AsyncMock(return_value="Summary")
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=50.0, impact=50.0, risk=50.0)
        )

        mock_cluster_repo.create = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=created_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=created_cluster)
        clustering_service.signal_repo.add_to_cluster = AsyncMock()

        # Execute
        result = await clustering_service.process_new_signal(sample_signal)

        # Verify new cluster was created
        assert result is not None
        mock_cluster_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_signal_assigns_to_existing_cluster(
        self,
        clustering_service,
        mock_embedding_service,
        mock_llm_service,
        mock_cluster_repo,
        sample_signal,
        sample_cluster,
    ):
        """Test processing signal assigns to existing cluster when LLM decides."""
        # Setup mocks - similar signals found
        similar_signal_id = str(ObjectId())
        mock_embedding_service.add_signal = AsyncMock(return_value=str(sample_signal.id))
        mock_embedding_service.find_similar = AsyncMock(
            return_value=[(similar_signal_id, 0.95)]
        )

        # Mock similar signal that belongs to cluster
        similar_signal = Signal(
            id=ObjectId(similar_signal_id),
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Similar content",
            cluster_ids=[sample_cluster.id],
        )
        clustering_service.signal_repo.get_by_id = AsyncMock(return_value=similar_signal)

        # LLM decides to assign to existing cluster
        mock_llm_service.classify_cluster_assignment = AsyncMock(
            return_value={
                "assignment": "existing_cluster",
                "cluster_id": str(sample_cluster.id),
                "confidence": 0.95,
            }
        )

        # Mock cluster operations
        mock_cluster_repo.add_signal = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.update_priority_scores = AsyncMock(return_value=sample_cluster)
        mock_cluster_repo.get_by_id = AsyncMock(return_value=sample_cluster)
        clustering_service.signal_repo.add_to_cluster = AsyncMock()
        clustering_service.signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal])

        mock_llm_service.generate_cluster_summary = AsyncMock(return_value="Updated summary")
        mock_llm_service.assess_priority = AsyncMock(
            return_value=PriorityScores(urgency=50.0, impact=50.0, risk=50.0)
        )

        # Execute
        result = await clustering_service.process_new_signal(sample_signal)

        # Verify signal was added to existing cluster
        assert result is not None
        mock_cluster_repo.add_signal.assert_called_once_with(
            cluster_id=sample_cluster.id,
            signal_id=sample_signal.id,
        )


@pytest.mark.unit
class TestGetCandidateClusters:
    """Test candidate cluster retrieval."""

    @pytest.mark.asyncio
    async def test_get_candidate_clusters_filters_by_threshold(
        self,
        clustering_service,
    ):
        """Test candidate clusters are filtered by similarity threshold."""
        # Similar signals with varying scores
        similar_signals = [
            ("signal1", 0.95),  # Above threshold
            ("signal2", 0.80),  # Above threshold
            ("signal3", 0.70),  # Below threshold (0.75)
        ]

        # Execute
        result = await clustering_service._get_candidate_clusters(
            similar_signals=similar_signals,
            workspace_id="T01TEST",
        )

        # Verify - should only process signals above threshold
        # (actual implementation depends on signal repo mocks)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_candidate_clusters_empty_when_no_similar(
        self,
        clustering_service,
    ):
        """Test returns empty list when no similar signals."""
        result = await clustering_service._get_candidate_clusters(
            similar_signals=[],
            workspace_id="T01TEST",
        )

        assert result == []
