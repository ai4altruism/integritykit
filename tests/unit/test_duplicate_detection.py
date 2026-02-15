"""Unit tests for duplicate detection service."""

import pytest
from unittest.mock import AsyncMock, Mock
from bson import ObjectId

from integritykit.models.duplicate import DuplicateConfirmation, DuplicateMatch
from integritykit.models.signal import Signal
from integritykit.services.duplicate_detection import DuplicateDetectionService
from integritykit.services.database import SignalRepository
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService


@pytest.fixture
def mock_embedding_service():
    """Provide mock embedding service."""
    return Mock(spec=EmbeddingService)


@pytest.fixture
def mock_llm_service():
    """Provide mock LLM service."""
    mock = Mock(spec=LLMService)
    mock.model = "gpt-4o-mini"
    mock.temperature = 0.3
    mock.client = Mock()  # Add client attribute for LLM calls
    return mock


@pytest.fixture
def mock_signal_repo():
    """Provide mock signal repository."""
    return Mock(spec=SignalRepository)


@pytest.fixture
def duplicate_detection_service(
    mock_embedding_service,
    mock_llm_service,
    mock_signal_repo,
):
    """Provide duplicate detection service with mocked dependencies."""
    return DuplicateDetectionService(
        embedding_service=mock_embedding_service,
        llm_service=mock_llm_service,
        signal_repository=mock_signal_repo,
        similarity_threshold=0.85,
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
        content="Shelter Alpha is closing at 6pm",
    )


@pytest.fixture
def similar_signal():
    """Provide similar signal for testing."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id="T01TEST",
        slack_channel_id="C01TEST",
        slack_message_ts="1234567891.123456",
        slack_user_id="U01USER2",
        slack_permalink="https://test.slack.com/archives/C01TEST/p1234567891123456",
        content="Shelter A closing at 6:00pm today",
    )


@pytest.mark.unit
class TestFindDuplicateCandidates:
    """Test finding duplicate candidates via embedding similarity."""

    @pytest.mark.asyncio
    async def test_find_candidates_returns_similar_signals(
        self,
        duplicate_detection_service,
        mock_embedding_service,
        mock_signal_repo,
        sample_signal,
        similar_signal,
    ):
        """Test finding duplicate candidates returns similar signals."""
        cluster_id = ObjectId()

        # Setup mocks
        cluster_signals = [sample_signal, similar_signal]
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=cluster_signals)

        # Mock embedding service to return similarity
        mock_embedding_service.find_similar_in_cluster = AsyncMock(
            return_value=[(str(similar_signal.id), 0.92)]
        )
        mock_signal_repo.get_by_id = AsyncMock(return_value=similar_signal)

        # Execute
        candidates = await duplicate_detection_service.find_duplicate_candidates(
            signal=sample_signal,
            cluster_id=cluster_id,
            threshold=0.85,
        )

        # Verify
        assert len(candidates) == 1
        assert candidates[0][0].id == similar_signal.id
        assert candidates[0][1] == 0.92

    @pytest.mark.asyncio
    async def test_find_candidates_filters_by_threshold(
        self,
        duplicate_detection_service,
        mock_embedding_service,
        mock_signal_repo,
        sample_signal,
        similar_signal,
    ):
        """Test candidates below threshold are filtered out."""
        cluster_id = ObjectId()

        # Setup mocks
        cluster_signals = [sample_signal, similar_signal]
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=cluster_signals)

        # Mock embedding service with low similarity score - embedding service
        # filters by threshold internally, so it returns empty list
        mock_embedding_service.find_similar_in_cluster = AsyncMock(
            return_value=[]  # Empty - filtered by embedding service
        )

        # Execute
        candidates = await duplicate_detection_service.find_duplicate_candidates(
            signal=sample_signal,
            cluster_id=cluster_id,
            threshold=0.85,
        )

        # Verify - should be empty due to threshold
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_find_candidates_with_no_other_signals(
        self,
        duplicate_detection_service,
        mock_signal_repo,
        sample_signal,
    ):
        """Test finding candidates when signal is alone in cluster."""
        cluster_id = ObjectId()

        # Setup mock - only the signal itself in cluster
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal])

        # Execute
        candidates = await duplicate_detection_service.find_duplicate_candidates(
            signal=sample_signal,
            cluster_id=cluster_id,
        )

        # Verify
        assert len(candidates) == 0

    @pytest.mark.asyncio
    async def test_find_candidates_without_signal_id(
        self,
        duplicate_detection_service,
    ):
        """Test finding candidates for signal without ID returns empty."""
        signal_without_id = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test content",
        )

        candidates = await duplicate_detection_service.find_duplicate_candidates(
            signal=signal_without_id,
            cluster_id=ObjectId(),
        )

        assert len(candidates) == 0


@pytest.mark.unit
class TestConfirmDuplicateWithLLM:
    """Test LLM-powered duplicate confirmation."""

    @pytest.mark.asyncio
    async def test_confirm_duplicate_returns_confirmation(
        self,
        duplicate_detection_service,
        mock_llm_service,
        sample_signal,
        similar_signal,
    ):
        """Test LLM confirmation returns DuplicateConfirmation."""
        # Setup mock LLM response
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content='{"is_duplicate": true, "confidence": "high", "reasoning": "Same shelter and time", "shared_facts": ["Shelter Alpha", "6pm closure"]}'
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Execute
        confirmation = await duplicate_detection_service.confirm_duplicate_with_llm(
            signal1=sample_signal,
            signal2=similar_signal,
        )

        # Verify
        assert isinstance(confirmation, DuplicateConfirmation)
        assert confirmation.is_duplicate is True
        assert confirmation.confidence == "high"
        assert "Same shelter" in confirmation.reasoning
        assert len(confirmation.shared_facts) == 2

    @pytest.mark.asyncio
    async def test_confirm_duplicate_not_duplicate(
        self,
        duplicate_detection_service,
        mock_llm_service,
        sample_signal,
    ):
        """Test LLM confirmation when signals are not duplicates."""
        different_signal = Signal(
            id=ObjectId(),
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567892.123456",
            slack_user_id="U01USER3",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567892123456",
            content="Medical supplies needed at Hospital B",
        )

        # Setup mock LLM response
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content='{"is_duplicate": false, "confidence": "high", "reasoning": "Different topics - shelter vs medical supplies", "shared_facts": []}'
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Execute
        confirmation = await duplicate_detection_service.confirm_duplicate_with_llm(
            signal1=sample_signal,
            signal2=different_signal,
        )

        # Verify
        assert confirmation.is_duplicate is False
        assert confirmation.confidence == "high"


@pytest.mark.unit
class TestDetectDuplicatesForSignal:
    """Test end-to-end duplicate detection for a signal."""

    @pytest.mark.asyncio
    async def test_detect_duplicates_without_signal_id_raises_error(
        self,
        duplicate_detection_service,
    ):
        """Test detecting duplicates without signal ID raises ValueError."""
        signal_without_id = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com",
            content="Test content",
        )

        with pytest.raises(ValueError, match="must have an ID"):
            await duplicate_detection_service.detect_duplicates_for_signal(
                signal=signal_without_id,
                cluster_id=ObjectId(),
            )

    @pytest.mark.asyncio
    async def test_detect_duplicates_returns_confirmed_matches(
        self,
        duplicate_detection_service,
        mock_embedding_service,
        mock_llm_service,
        mock_signal_repo,
        sample_signal,
        similar_signal,
    ):
        """Test detecting duplicates returns confirmed matches."""
        cluster_id = ObjectId()

        # Setup mocks for candidate finding
        mock_signal_repo.list_by_cluster = AsyncMock(
            return_value=[sample_signal, similar_signal]
        )
        mock_embedding_service.find_similar_in_cluster = AsyncMock(
            return_value=[(str(similar_signal.id), 0.92)]
        )
        mock_signal_repo.get_by_id = AsyncMock(return_value=similar_signal)

        # Setup mock for LLM confirmation
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content='{"is_duplicate": true, "confidence": "high", "reasoning": "Same event", "shared_facts": ["Shelter Alpha"]}'
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Execute
        matches = await duplicate_detection_service.detect_duplicates_for_signal(
            signal=sample_signal,
            cluster_id=cluster_id,
        )

        # Verify
        assert len(matches) == 1
        assert isinstance(matches[0], DuplicateMatch)
        assert matches[0].signal_id == similar_signal.id
        assert matches[0].similarity_score == 0.92
        assert matches[0].confidence == "high"

    @pytest.mark.asyncio
    async def test_detect_duplicates_no_candidates(
        self,
        duplicate_detection_service,
        mock_signal_repo,
        sample_signal,
    ):
        """Test detecting duplicates when no candidates found."""
        cluster_id = ObjectId()

        # Setup mock - no similar signals
        mock_signal_repo.list_by_cluster = AsyncMock(return_value=[sample_signal])

        # Execute
        matches = await duplicate_detection_service.detect_duplicates_for_signal(
            signal=sample_signal,
            cluster_id=cluster_id,
        )

        # Verify
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_detect_duplicates_llm_rejects_candidate(
        self,
        duplicate_detection_service,
        mock_embedding_service,
        mock_llm_service,
        mock_signal_repo,
        sample_signal,
        similar_signal,
    ):
        """Test detecting duplicates when LLM rejects high similarity candidate."""
        cluster_id = ObjectId()

        # Setup mocks for candidate finding
        mock_signal_repo.list_by_cluster = AsyncMock(
            return_value=[sample_signal, similar_signal]
        )
        mock_embedding_service.find_similar_in_cluster = AsyncMock(
            return_value=[(str(similar_signal.id), 0.95)]  # High similarity
        )
        mock_signal_repo.get_by_id = AsyncMock(return_value=similar_signal)

        # Setup mock for LLM rejection
        mock_response = Mock()
        mock_response.choices = [
            Mock(
                message=Mock(
                    content='{"is_duplicate": false, "confidence": "medium", "reasoning": "Different times mentioned", "shared_facts": []}'
                )
            )
        ]
        mock_llm_service.client.chat.completions.create = AsyncMock(
            return_value=mock_response
        )

        # Execute
        matches = await duplicate_detection_service.detect_duplicates_for_signal(
            signal=sample_signal,
            cluster_id=cluster_id,
        )

        # Verify - LLM rejected, so no matches
        assert len(matches) == 0


@pytest.mark.unit
class TestMarkDuplicates:
    """Test marking signals as duplicates."""

    @pytest.mark.asyncio
    async def test_mark_duplicates_updates_signals(
        self,
        duplicate_detection_service,
        mock_signal_repo,
    ):
        """Test marking signals as duplicates updates database."""
        canonical_id = ObjectId()
        duplicate_ids = [ObjectId(), ObjectId()]

        mock_signal_repo.update = AsyncMock()

        # Execute
        await duplicate_detection_service.mark_duplicates(
            signal_ids=duplicate_ids,
            canonical_id=canonical_id,
        )

        # Verify all signals were updated
        assert mock_signal_repo.update.call_count == len(duplicate_ids)

        # Verify update calls include duplicate flags
        for call in mock_signal_repo.update.call_args_list:
            signal_id, updates = call[0]
            assert signal_id in duplicate_ids
            assert updates["ai_flags.is_duplicate"] is True
            assert updates["ai_flags.duplicate_of"] == canonical_id


@pytest.mark.unit
class TestAutoMarkDuplicates:
    """Test automatic duplicate marking based on confidence."""

    @pytest.mark.asyncio
    async def test_auto_mark_high_confidence_duplicates(
        self,
        duplicate_detection_service,
        mock_signal_repo,
        sample_signal,
    ):
        """Test auto-marking high confidence duplicates."""
        duplicate_matches = [
            DuplicateMatch(
                signal_id=ObjectId(),
                similarity_score=0.95,
                confidence="high",
                reasoning="Exact same event",
                shared_facts=["Shelter Alpha", "6pm"],
            ),
        ]

        mock_signal_repo.update = AsyncMock()

        # Execute
        await duplicate_detection_service.auto_mark_duplicates_for_signal(
            signal=sample_signal,
            duplicate_matches=duplicate_matches,
            confidence_threshold="high",
        )

        # Verify signal was marked
        assert mock_signal_repo.update.call_count == 1

    @pytest.mark.asyncio
    async def test_auto_mark_filters_by_confidence(
        self,
        duplicate_detection_service,
        mock_signal_repo,
        sample_signal,
    ):
        """Test auto-marking filters matches by confidence threshold."""
        duplicate_matches = [
            DuplicateMatch(
                signal_id=ObjectId(),
                similarity_score=0.87,
                confidence="medium",  # Below "high" threshold
                reasoning="Similar but not exact",
                shared_facts=["Shelter Alpha"],
            ),
        ]

        mock_signal_repo.update = AsyncMock()

        # Execute with "high" threshold
        await duplicate_detection_service.auto_mark_duplicates_for_signal(
            signal=sample_signal,
            duplicate_matches=duplicate_matches,
            confidence_threshold="high",
        )

        # Verify signal was NOT marked (below threshold)
        assert mock_signal_repo.update.call_count == 0

    @pytest.mark.asyncio
    async def test_auto_mark_with_medium_threshold(
        self,
        duplicate_detection_service,
        mock_signal_repo,
        sample_signal,
    ):
        """Test auto-marking with medium confidence threshold."""
        duplicate_matches = [
            DuplicateMatch(
                signal_id=ObjectId(),
                similarity_score=0.87,
                confidence="medium",
                reasoning="Similar event",
                shared_facts=["Shelter Alpha"],
            ),
        ]

        mock_signal_repo.update = AsyncMock()

        # Execute with "medium" threshold
        await duplicate_detection_service.auto_mark_duplicates_for_signal(
            signal=sample_signal,
            duplicate_matches=duplicate_matches,
            confidence_threshold="medium",
        )

        # Verify signal WAS marked (meets threshold)
        assert mock_signal_repo.update.call_count == 1
