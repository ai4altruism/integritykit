"""Unit tests for Pydantic models (Signal, Cluster, etc.)."""

import pytest
from datetime import datetime, timezone
from bson import ObjectId

from integritykit.models.signal import (
    Signal,
    SignalCreate,
    SourceQuality,
    SourceQualityType,
    AIFlags,
    PyObjectId,
)
from integritykit.models.cluster import (
    Cluster,
    ClusterCreate,
    PriorityScores,
    ConflictRecord,
    ConflictSeverity,
    ConflictResolution,
    ConflictResolutionType,
)


@pytest.mark.unit
class TestPyObjectId:
    """Test PyObjectId custom type."""

    def test_validate_object_id(self):
        """Test validating ObjectId instance."""
        obj_id = ObjectId()
        result = PyObjectId.validate(obj_id)
        assert result == obj_id
        assert isinstance(result, ObjectId)

    def test_validate_string_object_id(self):
        """Test validating string ObjectId."""
        obj_id = ObjectId()
        result = PyObjectId.validate(str(obj_id))
        assert result == obj_id
        assert isinstance(result, ObjectId)

    def test_validate_invalid_string_raises_error(self):
        """Test validating invalid string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ObjectId"):
            PyObjectId.validate("invalid_id")

    def test_validate_invalid_type_raises_error(self):
        """Test validating invalid type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid ObjectId type"):
            PyObjectId.validate(12345)


@pytest.mark.unit
class TestSourceQuality:
    """Test SourceQuality model."""

    def test_default_values(self):
        """Test SourceQuality with default values."""
        sq = SourceQuality()
        assert sq.type == SourceQualityType.SECONDARY
        assert sq.confidence == 0.5
        assert sq.is_firsthand is False
        assert sq.has_external_link is False
        assert sq.external_links == []
        assert sq.author_credibility_score == 0.5

    def test_custom_values(self):
        """Test SourceQuality with custom values."""
        sq = SourceQuality(
            type=SourceQualityType.PRIMARY,
            confidence=0.9,
            is_firsthand=True,
            has_external_link=True,
            external_links=["https://example.com"],
            author_credibility_score=0.85,
        )
        assert sq.type == SourceQualityType.PRIMARY
        assert sq.confidence == 0.9
        assert sq.is_firsthand is True
        assert sq.has_external_link is True
        assert sq.external_links == ["https://example.com"]
        assert sq.author_credibility_score == 0.85

    def test_confidence_validation_minimum(self):
        """Test confidence score minimum validation."""
        with pytest.raises(ValueError):
            SourceQuality(confidence=-0.1)

    def test_confidence_validation_maximum(self):
        """Test confidence score maximum validation."""
        with pytest.raises(ValueError):
            SourceQuality(confidence=1.1)


@pytest.mark.unit
class TestAIFlags:
    """Test AIFlags model."""

    def test_default_values(self):
        """Test AIFlags with default values."""
        flags = AIFlags()
        assert flags.is_duplicate is False
        assert flags.duplicate_of is None
        assert flags.has_conflict is False
        assert flags.conflict_ids == []
        assert flags.quality_score == 0.5

    def test_duplicate_detection(self):
        """Test AIFlags with duplicate detection."""
        canonical_id = ObjectId()
        flags = AIFlags(
            is_duplicate=True,
            duplicate_of=canonical_id,
        )
        assert flags.is_duplicate is True
        assert flags.duplicate_of == canonical_id

    def test_conflict_detection(self):
        """Test AIFlags with conflict detection."""
        conflict_id = ObjectId()
        flags = AIFlags(
            has_conflict=True,
            conflict_ids=[conflict_id],
        )
        assert flags.has_conflict is True
        assert len(flags.conflict_ids) == 1
        assert flags.conflict_ids[0] == conflict_id


@pytest.mark.unit
class TestSignalCreate:
    """Test SignalCreate schema."""

    def test_valid_signal_create(self):
        """Test creating valid SignalCreate instance."""
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Test signal content",
        )
        assert signal_data.slack_workspace_id == "T01TEST"
        assert signal_data.slack_channel_id == "C01TEST"
        assert signal_data.slack_message_ts == "1234567890.123456"
        assert signal_data.content == "Test signal content"
        assert signal_data.attachments == []
        assert isinstance(signal_data.source_quality, SourceQuality)

    def test_signal_create_with_attachments(self):
        """Test SignalCreate with attachments."""
        signal_data = SignalCreate(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Test signal content",
            attachments=[{"type": "image", "url": "https://example.com/image.png"}],
        )
        assert len(signal_data.attachments) == 1
        assert signal_data.attachments[0]["type"] == "image"


@pytest.mark.unit
class TestSignal:
    """Test Signal model."""

    def test_signal_creation_with_defaults(self):
        """Test Signal creation with default values."""
        signal = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Test signal content",
        )
        assert signal.id is None
        assert signal.content == "Test signal content"
        assert signal.cluster_ids == []
        assert signal.embedding_id is None
        assert isinstance(signal.source_quality, SourceQuality)
        assert isinstance(signal.ai_flags, AIFlags)
        assert signal.redacted is False
        assert isinstance(signal.created_at, datetime)
        assert isinstance(signal.updated_at, datetime)

    def test_signal_with_cluster_assignment(self):
        """Test Signal with cluster assignment."""
        cluster_id = ObjectId()
        signal = Signal(
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Test signal content",
            cluster_ids=[cluster_id],
        )
        assert len(signal.cluster_ids) == 1
        assert signal.cluster_ids[0] == cluster_id

    def test_signal_serialization(self):
        """Test Signal serialization to dict."""
        signal_id = ObjectId()
        signal = Signal(
            id=signal_id,
            slack_workspace_id="T01TEST",
            slack_channel_id="C01TEST",
            slack_message_ts="1234567890.123456",
            slack_user_id="U01TEST",
            slack_permalink="https://test.slack.com/archives/C01TEST/p1234567890123456",
            content="Test signal content",
        )
        data = signal.model_dump(by_alias=True)
        # ObjectId is serialized to string by Pydantic
        assert data["_id"] == str(signal_id)
        assert data["content"] == "Test signal content"
        assert "source_quality" in data
        assert "ai_flags" in data


@pytest.mark.unit
class TestPriorityScores:
    """Test PriorityScores model."""

    def test_default_priority_scores(self):
        """Test PriorityScores with default values."""
        scores = PriorityScores()
        assert scores.urgency == 0.5
        assert scores.impact == 0.5
        assert scores.risk == 0.5
        assert scores.urgency_reasoning is None
        assert scores.impact_reasoning is None
        assert scores.risk_reasoning is None

    def test_composite_score_calculation(self):
        """Test composite priority score calculation."""
        scores = PriorityScores(
            urgency=60.0,
            impact=40.0,
            risk=20.0,
        )
        # Expected: (60 * 0.4) + (40 * 0.35) + (20 * 0.25) = 24 + 14 + 5 = 43
        assert scores.composite_score == pytest.approx(43.0)

    def test_high_urgency_weighted_composite(self):
        """Test composite score weights urgency higher."""
        scores = PriorityScores(
            urgency=100.0,
            impact=0.0,
            risk=0.0,
        )
        # Expected: (100 * 0.4) = 40
        assert scores.composite_score == pytest.approx(40.0)

    def test_priority_validation_minimum(self):
        """Test priority score minimum validation."""
        with pytest.raises(ValueError):
            PriorityScores(urgency=-0.1)

    def test_priority_validation_maximum(self):
        """Test priority score maximum validation."""
        with pytest.raises(ValueError):
            PriorityScores(urgency=100.1)


@pytest.mark.unit
class TestConflictRecord:
    """Test ConflictRecord model."""

    def test_conflict_record_creation(self):
        """Test creating ConflictRecord."""
        signal_id1 = ObjectId()
        signal_id2 = ObjectId()

        conflict = ConflictRecord(
            id="conflict-123",
            signal_ids=[signal_id1, signal_id2],
            field="location",
            severity=ConflictSeverity.HIGH,
            description="Location mismatch: Zone A vs Zone B",
            values={
                str(signal_id1): "Zone A",
                str(signal_id2): "Zone B",
            },
        )

        assert conflict.id == "conflict-123"
        assert len(conflict.signal_ids) == 2
        assert conflict.field == "location"
        assert conflict.severity == ConflictSeverity.HIGH
        assert conflict.resolved is False
        assert conflict.resolution is None

    def test_conflict_resolution(self):
        """Test ConflictRecord with resolution."""
        signal_id1 = ObjectId()
        signal_id2 = ObjectId()

        resolution = ConflictResolution(
            type=ConflictResolutionType.ONE_CORRECT,
            reasoning="Verified with official source - Zone A is correct",
            canonical_value="Zone A",
        )

        conflict = ConflictRecord(
            id="conflict-123",
            signal_ids=[signal_id1, signal_id2],
            field="location",
            severity=ConflictSeverity.HIGH,
            description="Location mismatch",
            resolved=True,
            resolution=resolution,
            resolved_by="U01FACILITATOR",
            resolved_at=datetime.utcnow(),
        )

        assert conflict.resolved is True
        assert conflict.resolution.type == ConflictResolutionType.ONE_CORRECT
        assert conflict.resolution.canonical_value == "Zone A"


@pytest.mark.unit
class TestClusterCreate:
    """Test ClusterCreate schema."""

    def test_valid_cluster_create(self):
        """Test creating valid ClusterCreate instance."""
        signal_id = ObjectId()
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            signal_ids=[signal_id],
            topic="Shelter Alpha Closure",
            incident_type="infrastructure",
            summary="Shelter Alpha closing due to power outage",
        )

        assert cluster_data.slack_workspace_id == "T01TEST"
        assert len(cluster_data.signal_ids) == 1
        assert cluster_data.topic == "Shelter Alpha Closure"
        assert cluster_data.summary == "Shelter Alpha closing due to power outage"

    def test_cluster_create_minimal(self):
        """Test ClusterCreate with minimal fields."""
        cluster_data = ClusterCreate(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
        )
        assert cluster_data.signal_ids == []
        assert cluster_data.summary == ""


@pytest.mark.unit
class TestCluster:
    """Test Cluster model."""

    def test_cluster_creation_with_defaults(self):
        """Test Cluster creation with default values."""
        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Shelter Alpha Closure",
        )

        assert cluster.id is None
        assert cluster.topic == "Shelter Alpha Closure"
        assert cluster.signal_ids == []
        assert cluster.summary == ""
        assert isinstance(cluster.priority_scores, PriorityScores)
        assert cluster.conflicts == []
        assert cluster.promoted_to_candidate is False
        assert cluster.cop_candidate_id is None
        assert isinstance(cluster.created_at, datetime)
        assert isinstance(cluster.updated_at, datetime)

    def test_cluster_signal_count_property(self):
        """Test Cluster signal_count property."""
        signal_ids = [ObjectId() for _ in range(5)]
        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            signal_ids=signal_ids,
        )
        assert cluster.signal_count == 5

    def test_cluster_has_conflicts_property(self):
        """Test Cluster has_conflicts property."""
        conflict = ConflictRecord(
            id="conflict-1",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.MEDIUM,
            description="Test conflict",
        )

        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[conflict],
        )
        assert cluster.has_conflicts is True

    def test_cluster_no_conflicts_property(self):
        """Test Cluster has_conflicts when no conflicts."""
        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
        )
        assert cluster.has_conflicts is False

    def test_cluster_has_unresolved_conflicts_property(self):
        """Test Cluster has_unresolved_conflicts property."""
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
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[resolved_conflict, unresolved_conflict],
        )
        assert cluster.has_unresolved_conflicts is True

    def test_cluster_all_conflicts_resolved_property(self):
        """Test Cluster has_unresolved_conflicts when all resolved."""
        resolved_conflict = ConflictRecord(
            id="conflict-1",
            signal_ids=[ObjectId(), ObjectId()],
            field="location",
            severity=ConflictSeverity.MEDIUM,
            description="Resolved conflict",
            resolved=True,
        )

        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            conflicts=[resolved_conflict],
        )
        assert cluster.has_unresolved_conflicts is False

    def test_cluster_with_priority_scores(self):
        """Test Cluster with custom priority scores."""
        priority_scores = PriorityScores(
            urgency=80.0,
            urgency_reasoning="Time-sensitive shelter closure",
            impact=60.0,
            impact_reasoning="Affects 100+ displaced families",
            risk=70.0,
            risk_reasoning="Safety risk if not addressed",
        )

        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Shelter Alpha Closure",
            priority_scores=priority_scores,
        )

        assert cluster.priority_scores.urgency == 80.0
        assert cluster.priority_scores.impact == 60.0
        assert cluster.priority_scores.risk == 70.0
        assert cluster.priority_scores.composite_score > 0

    def test_cluster_promoted_to_candidate(self):
        """Test Cluster promoted to COP candidate."""
        candidate_id = ObjectId()
        cluster = Cluster(
            slack_workspace_id="T01TEST",
            topic="Test Topic",
            promoted_to_candidate=True,
            cop_candidate_id=candidate_id,
        )

        assert cluster.promoted_to_candidate is True
        assert cluster.cop_candidate_id == candidate_id
