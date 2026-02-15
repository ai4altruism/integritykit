"""Unit tests for conflict detection service."""

import pytest
from unittest.mock import AsyncMock, Mock
from bson import ObjectId
import json

from integritykit.models.cluster import (
    Cluster,
    ConflictRecord,
    ConflictSeverity,
    ConflictResolution,
    ConflictResolutionType,
)
from integritykit.models.signal import Signal
from integritykit.services.conflict_detection import ConflictDetectionService
from integritykit.services.database import SignalRepository, ClusterRepository
from integritykit.services.llm import LLMService


@pytest.fixture
def mock_llm_service():
    """Provide mock LLM service."""
    mock = Mock(spec=LLMService)
    mock.model = "gpt-4o-mini"
    mock.client = Mock()  # Add client attribute for LLM calls
    return mock


@pytest.fixture
def mock_signal_repo():
    """Provide mock signal repository."""
    return Mock(spec=SignalRepository)


@pytest.fixture
def mock_cluster_repo():
    """Provide mock cluster repository."""
    return Mock(spec=ClusterRepository)


@pytest.fixture
def conflict_detection_service(
    mock_llm_service,
    mock_signal_repo,
    mock_cluster_repo,
):
    """Provide conflict detection service with mocked dependencies."""
    return ConflictDetectionService(
        llm_service=mock_llm_service,
        signal_repository=mock_signal_repo,
        cluster_repository=mock_cluster_repo,
    )


@pytest.fixture
def sample_cluster():
    """Provide sample cluster for testing."""
    return Cluster(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        topic="Shelter Alpha Status",
        signal_ids=[ObjectId(), ObjectId()],
    )


@pytest.fixture
def sample_signal1():
    """Provide first sample signal."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        slack_channel_id="C01TEST",
        slack_message_ts="1234567890.123456",
        slack_user_id="U01USER1",
        slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
        content="Shelter Alpha is open and accepting families",
    )


@pytest.fixture
def sample_signal2():
    """Provide second sample signal (conflicting)."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        slack_channel_id="C01TEST",
        slack_message_ts="1234567891.123456",
        slack_user_id="U01USER2",
        slack_permalink="https://test.slack.com/archives/C01TEST/p1234567891123456",
        content="Shelter Alpha has closed due to power outage",
    )


@pytest.mark.unit
class TestAnalyzeSignalPair:
    """Test analyzing signal pairs for conflicts."""

    @pytest.mark.asyncio
    async def test_analyze_pair_detects_conflict(
        self,
        conflict_detection_service,
        mock_llm_service,
        mock_signal_repo,
        sample_cluster,
        sample_signal1,
        sample_signal2,
    ):
        """Test analyzing pair detects conflict."""
        # Setup mock LLM response indicating conflict
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "conflict_detected": True,
                        "severity": "high",
                        "explanation": "Shelter status contradicts - one says open, other says closed",
                        "conflicting_fields": [
                            {
                                "field": "shelter_status",
                                "signal_1_value": "open",
                                "signal_2_value": "closed",
                            }
                        ],
                    })
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_signal_repo.update = AsyncMock()

        # Execute
        conflict = await conflict_detection_service.analyze_signal_pair(
            signal1=sample_signal1,
            signal2=sample_signal2,
            cluster_topic=sample_cluster.topic,
        )

        # Verify conflict was detected
        assert conflict is not None
        assert isinstance(conflict, ConflictRecord)
        assert len(conflict.signal_ids) == 2
        assert sample_signal1.id in conflict.signal_ids
        assert sample_signal2.id in conflict.signal_ids
        assert conflict.severity == ConflictSeverity.HIGH
        assert conflict.field == "shelter_status"
        assert conflict.resolved is False

    @pytest.mark.asyncio
    async def test_analyze_pair_no_conflict(
        self,
        conflict_detection_service,
        mock_llm_service,
        sample_cluster,
        sample_signal1,
    ):
        """Test analyzing pair when no conflict exists."""
        similar_signal = Signal(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567892.123456",
            slack_user_id="U01USER3",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567892123456",
            content="Shelter Alpha continues to accept families",
        )

        # Setup mock LLM response indicating no conflict
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "conflict_detected": False,
                    })
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Execute
        conflict = await conflict_detection_service.analyze_signal_pair(
            signal1=sample_signal1,
            signal2=similar_signal,
            cluster_topic=sample_cluster.topic,
        )

        # Verify no conflict detected
        assert conflict is None

    @pytest.mark.asyncio
    async def test_analyze_pair_medium_severity(
        self,
        conflict_detection_service,
        mock_llm_service,
        mock_signal_repo,
        sample_cluster,
    ):
        """Test analyzing pair with medium severity conflict."""
        signal1 = Signal(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01USER1",
            slack_permalink="https://test.slack.com",
            content="100 families displaced",
        )

        signal2 = Signal(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567891.123456",
            slack_user_id="U01USER2",
            slack_permalink="https://test.slack.com",
            content="Around 120 families affected",
        )

        # Setup mock LLM response with medium severity
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "conflict_detected": True,
                        "severity": "medium",
                        "explanation": "Different counts - 100 vs 120 families",
                        "conflicting_fields": [
                            {
                                "field": "count",
                                "signal_1_value": "100",
                                "signal_2_value": "120",
                            }
                        ],
                    })
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_signal_repo.update = AsyncMock()

        # Execute
        conflict = await conflict_detection_service.analyze_signal_pair(
            signal1=signal1,
            signal2=signal2,
            cluster_topic="Displacement Count",
        )

        # Verify medium severity
        assert conflict is not None
        assert conflict.severity == ConflictSeverity.MEDIUM


@pytest.mark.unit
class TestDetectConflictsForNewSignal:
    """Test detecting conflicts when new signal added to cluster."""

    @pytest.mark.asyncio
    async def test_detect_conflicts_for_new_signal(
        self,
        conflict_detection_service,
        mock_llm_service,
        mock_signal_repo,
        sample_cluster,
        sample_signal1,
        sample_signal2,
    ):
        """Test detecting conflicts for new signal against existing signals."""
        # Setup mocks
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal1])

        # Mock LLM to detect conflict
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "conflict_detected": True,
                        "severity": "high",
                        "explanation": "Status conflict",
                        "conflicting_fields": [
                            {
                                "field": "status",
                                "signal_1_value": "open",
                                "signal_2_value": "closed",
                            }
                        ],
                    })
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_signal_repo.update = AsyncMock()

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_for_new_signal(
            signal=sample_signal2,
            cluster=sample_cluster,
        )

        # Verify
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    @pytest.mark.asyncio
    async def test_detect_conflicts_no_existing_signals(
        self,
        conflict_detection_service,
        mock_signal_repo,
        sample_cluster,
        sample_signal1,
    ):
        """Test detecting conflicts when no existing signals in cluster."""
        # Setup mock - empty cluster
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=[])

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_for_new_signal(
            signal=sample_signal1,
            cluster=sample_cluster,
        )

        # Verify - no conflicts possible
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_detect_conflicts_multiple_existing_signals(
        self,
        conflict_detection_service,
        mock_llm_service,
        mock_signal_repo,
        sample_cluster,
        sample_signal2,
    ):
        """Test detecting conflicts with multiple existing signals."""
        # Create multiple existing signals
        existing_signals = [
            Signal(
                id=ObjectId(),
                slack_workspace_id="T01TEST",
                slack_channel_id="C01TEST",
                slack_message_ts=f"123456789{i}.123456",
                slack_user_id=f"U01USER{i}",
                slack_permalink="https://test.slack.com",
                content=f"Signal {i}",
            )
            for i in range(3)
        ]

        mock_signal_repo.list_by_cluster = AsyncMock(return_value=existing_signals)

        # Mock LLM to detect conflict with one signal
        call_count = 0

        async def mock_llm_response(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            conflict_detected = call_count == 2  # Conflict with second signal only

            mock_response = Mock()
            mock_response.choices = [
                Mock(
                    message=Mock(
                        content=json.dumps({
                            "conflict_detected": conflict_detected,
                            "severity": "medium" if conflict_detected else "none",
                            "explanation": "Conflict" if conflict_detected else "No conflict",
                            "conflicting_fields": [
                                {
                                    "field": "status",
                                    "signal_1_value": "value1",
                                    "signal_2_value": "value2",
                                }
                            ] if conflict_detected else [],
                        })
                    )
                )
            ]
            return mock_response

        mock_llm_service.client.chat.completions.create = AsyncMock(
            side_effect=mock_llm_response
        )
        mock_signal_repo.update = AsyncMock()

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_for_new_signal(
            signal=sample_signal2,
            cluster=sample_cluster,
        )

        # Verify - should have checked all 3 signals and found 1 conflict
        assert mock_llm_service.client.chat.completions.create.call_count == 3
        assert len(conflicts) == 1


@pytest.mark.unit
class TestDetectConflictsInCluster:
    """Test detecting conflicts across all signals in cluster."""

    @pytest.mark.asyncio
    async def test_detect_conflicts_in_small_cluster(
        self,
        conflict_detection_service,
        mock_llm_service,
        mock_signal_repo,
        mock_cluster_repo,
        sample_cluster,
        sample_signal1,
        sample_signal2,
    ):
        """Test detecting conflicts in cluster with few signals (pairwise)."""
        # Setup mocks
        mock_cluster_repo.get_by_id = AsyncMock(return_value=sample_cluster)
        mock_signal_repo.list_by_cluster = AsyncMock(
            return_value=[sample_signal1, sample_signal2]
        )

        # Mock LLM to detect conflict
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content=json.dumps({
                        "conflict_detected": True,
                        "severity": "high",
                        "explanation": "Status conflict",
                        "conflicting_fields": [
                            {
                                "field": "status",
                                "signal_1_value": "open",
                                "signal_2_value": "closed",
                            }
                        ],
                    })
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )
        mock_signal_repo.update = AsyncMock()

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_in_cluster(
            cluster_id=sample_cluster.id
        )

        # Verify
        assert len(conflicts) == 1
        assert conflicts[0].severity == ConflictSeverity.HIGH

    @pytest.mark.asyncio
    async def test_detect_conflicts_single_signal_cluster(
        self,
        conflict_detection_service,
        mock_cluster_repo,
        mock_signal_repo,
        sample_cluster,
        sample_signal1,
    ):
        """Test detecting conflicts in cluster with single signal."""
        # Setup mocks
        mock_cluster_repo.get_by_id = AsyncMock(return_value=sample_cluster)
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal1])

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_in_cluster(
            cluster_id=sample_cluster.id
        )

        # Verify - no conflicts possible with single signal
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_detect_conflicts_nonexistent_cluster(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test detecting conflicts in non-existent cluster."""
        # Setup mock - cluster not found
        mock_cluster_repo.get_by_id = AsyncMock(return_value=None)

        # Execute
        conflicts = await conflict_detection_service.detect_conflicts_in_cluster(
            cluster_id=ObjectId()
        )

        # Verify
        assert len(conflicts) == 0


@pytest.mark.unit
class TestResolveConflict:
    """Test resolving detected conflicts."""

    @pytest.mark.asyncio
    async def test_resolve_conflict_success(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test successfully resolving a conflict."""
        conflict = ConflictRecord(
            id="conflict-123",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.HIGH,
            description="Location mismatch",
            resolved=False,
        )

        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[conflict],
        )

        mock_cluster_repo.get_by_id = AsyncMock(return_value=cluster)
        mock_cluster_repo.update = AsyncMock()

        resolution = ConflictResolution(
            type=ConflictResolutionType.ONE_CORRECT,
            reasoning="Verified with official source",
            canonical_value="Zone A",
        )

        # Execute
        success = await conflict_detection_service.resolve_conflict(
            cluster_id=cluster.id,
            conflict_id="conflict-123",
            resolution=resolution,
            resolved_by="U01FACILITATOR",
        )

        # Verify
        assert success is True
        mock_cluster_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_conflict(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test resolving non-existent conflict."""
        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[],
        )

        mock_cluster_repo.get_by_id = AsyncMock(return_value=cluster)

        resolution = ConflictResolution(
            type=ConflictResolutionType.ONE_CORRECT,
            reasoning="Test",
            canonical_value="Test",
        )

        # Execute
        success = await conflict_detection_service.resolve_conflict(
            cluster_id=cluster.id,
            conflict_id="nonexistent",
            resolution=resolution,
            resolved_by="U01USER",
        )

        # Verify
        assert success is False

    @pytest.mark.asyncio
    async def test_resolve_conflict_in_nonexistent_cluster(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test resolving conflict in non-existent cluster."""
        mock_cluster_repo.get_by_id = AsyncMock(return_value=None)

        resolution = ConflictResolution(
            type=ConflictResolutionType.ONE_CORRECT,
            reasoning="Test",
            canonical_value="Test",
        )

        # Execute
        success = await conflict_detection_service.resolve_conflict(
            cluster_id=ObjectId(),
            conflict_id="conflict-123",
            resolution=resolution,
            resolved_by="U01USER",
        )

        # Verify
        assert success is False


@pytest.mark.unit
class TestGetUnresolvedConflicts:
    """Test retrieving unresolved conflicts."""

    @pytest.mark.asyncio
    async def test_get_unresolved_conflicts(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test getting unresolved conflicts from cluster."""
        resolved_conflict = ConflictRecord(
            id="conflict-1",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.MEDIUM,
            description="Resolved conflict",
            resolved=True,
        )

        unresolved_conflict = ConflictRecord(
            id="conflict-2",
            signal_ids=[ObjectId(), ObjectId()],
            field="time",
            severity=ConflictSeverity.HIGH,
            description="Unresolved conflict",
            resolved=False,
        )

        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[resolved_conflict, unresolved_conflict],
        )

        mock_cluster_repo.get_by_id = AsyncMock(return_value=cluster)

        # Execute
        unresolved = await conflict_detection_service.get_unresolved_conflicts(
            cluster_id=cluster.id
        )

        # Verify
        assert len(unresolved) == 1
        assert unresolved[0].id == "conflict-2"
        assert unresolved[0].resolved is False

    @pytest.mark.asyncio
    async def test_get_unresolved_conflicts_all_resolved(
        self,
        conflict_detection_service,
        mock_cluster_repo,
    ):
        """Test getting unresolved conflicts when all are resolved."""
        resolved_conflict = ConflictRecord(
            id="conflict-1",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.MEDIUM,
            description="Resolved conflict",
            resolved=True,
        )

        cluster = Cluster(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[resolved_conflict],
        )

        mock_cluster_repo.get_by_id = AsyncMock(return_value=cluster)

        # Execute
        unresolved = await conflict_detection_service.get_unresolved_conflicts(
            cluster_id=cluster.id
        )

        # Verify
        assert len(unresolved) == 0
