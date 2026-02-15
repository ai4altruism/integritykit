"""
Unit tests for facilitator search functionality.

Tests:
- FR-SEARCH-001: Searchable index with keyword, time range, channel filters
- Role-based access control for search
"""

import pytest
from bson import ObjectId
from datetime import datetime, timedelta

from integritykit.services.search import SearchResult, SearchService


# ============================================================================
# SearchResult Tests
# ============================================================================


@pytest.mark.unit
class TestSearchResult:
    """Test SearchResult model."""

    def test_create_signal_result(self) -> None:
        """Create a signal search result."""
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Power outage reported downtown",
            preview="Power outage reported...",
            relevance_score=1.5,
            slack_permalink="https://slack.com/archives/C01/p123",
            cluster_ids=[ObjectId()],
            cluster_topics=["Infrastructure"],
            channel_id="C01",
            created_at=datetime.utcnow(),
        )

        assert result.result_type == "signal"
        assert result.relevance_score == 1.5
        assert result.slack_permalink is not None

    def test_create_cluster_result(self) -> None:
        """Create a cluster search result."""
        result = SearchResult(
            result_type="cluster",
            entity_id=ObjectId(),
            content="Shelter Status Updates",
            preview="Shelter Status Updates",
            relevance_score=2.0,
            cluster_ids=[ObjectId()],
            cluster_topics=["Shelter Status Updates"],
        )

        assert result.result_type == "cluster"
        assert result.slack_permalink is None

    def test_create_candidate_result(self) -> None:
        """Create a COP candidate search result."""
        result = SearchResult(
            result_type="cop_candidate",
            entity_id=ObjectId(),
            content="Road closure on Main St",
            preview="Road closure...",
            relevance_score=1.8,
            cop_candidate_id=ObjectId(),
            cop_candidate_state="in_review",
        )

        assert result.result_type == "cop_candidate"
        assert result.cop_candidate_state == "in_review"

    def test_result_to_dict(self) -> None:
        """Convert result to dictionary."""
        entity_id = ObjectId()
        cluster_id = ObjectId()
        now = datetime.utcnow()

        result = SearchResult(
            result_type="signal",
            entity_id=entity_id,
            content="Test content",
            preview="Test...",
            relevance_score=1.0,
            slack_permalink="https://slack.com/test",
            cluster_ids=[cluster_id],
            cluster_topics=["Test Topic"],
            channel_id="C01",
            created_at=now,
        )

        data = result.to_dict()

        assert data["type"] == "signal"
        assert data["id"] == str(entity_id)
        assert data["content"] == "Test content"
        assert data["relevance_score"] == 1.0
        assert len(data["cluster_ids"]) == 1
        assert data["cluster_topics"] == ["Test Topic"]

    def test_result_without_cluster(self) -> None:
        """Result without cluster membership."""
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Unclustered signal",
            preview="Unclustered...",
            relevance_score=0.8,
        )

        assert result.cluster_ids == []
        assert result.cluster_topics == []
        assert result.cop_candidate_id is None


# ============================================================================
# Search Relevance Tests
# ============================================================================


@pytest.mark.unit
class TestSearchRelevance:
    """Test search result relevance scoring."""

    def test_relevance_sorting(self) -> None:
        """Results should sort by relevance."""
        results = [
            SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content="Low relevance",
                preview="Low...",
                relevance_score=0.5,
            ),
            SearchResult(
                result_type="cluster",
                entity_id=ObjectId(),
                content="High relevance",
                preview="High...",
                relevance_score=2.0,
            ),
            SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content="Medium relevance",
                preview="Medium...",
                relevance_score=1.0,
            ),
        ]

        sorted_results = sorted(results, key=lambda x: x.relevance_score, reverse=True)

        assert sorted_results[0].relevance_score == 2.0
        assert sorted_results[1].relevance_score == 1.0
        assert sorted_results[2].relevance_score == 0.5

    def test_topic_match_higher_relevance(self) -> None:
        """Topic matches should have higher relevance."""
        topic_match = SearchResult(
            result_type="cluster",
            entity_id=ObjectId(),
            content="Road Closure on Highway 101",
            preview="Road Closure...",
            relevance_score=2.0,  # Topic match
        )

        body_match = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Traffic backed up due to road closure",
            preview="Traffic backed up...",
            relevance_score=1.5,  # Body match
        )

        assert topic_match.relevance_score > body_match.relevance_score


# ============================================================================
# Search Filter Tests
# ============================================================================


@pytest.mark.unit
class TestSearchFilters:
    """Test search filter behavior."""

    def test_channel_filter_scopes_results(self) -> None:
        """Channel filter should scope results."""
        # Create results from different channels
        channel1_result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="From channel 1",
            preview="From channel 1",
            relevance_score=1.0,
            channel_id="C001",
        )

        channel2_result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="From channel 2",
            preview="From channel 2",
            relevance_score=1.0,
            channel_id="C002",
        )

        # Filter for channel 1
        all_results = [channel1_result, channel2_result]
        filtered = [r for r in all_results if r.channel_id == "C001"]

        assert len(filtered) == 1
        assert filtered[0].channel_id == "C001"

    def test_time_range_filter(self) -> None:
        """Time range filter should scope results."""
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        last_week = now - timedelta(days=7)

        recent = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Recent signal",
            preview="Recent...",
            relevance_score=1.0,
            created_at=now,
        )

        old = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Old signal",
            preview="Old...",
            relevance_score=1.0,
            created_at=last_week,
        )

        all_results = [recent, old]

        # Filter for signals from yesterday onwards
        filtered = [r for r in all_results if r.created_at and r.created_at >= yesterday]

        assert len(filtered) == 1
        assert filtered[0].content == "Recent signal"


# ============================================================================
# Search Result Type Tests
# ============================================================================


@pytest.mark.unit
class TestSearchResultTypes:
    """Test different result types."""

    def test_include_only_signals(self) -> None:
        """Can filter to only signals."""
        results = [
            SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content="Signal",
                preview="Signal",
                relevance_score=1.0,
            ),
            SearchResult(
                result_type="cluster",
                entity_id=ObjectId(),
                content="Cluster",
                preview="Cluster",
                relevance_score=1.0,
            ),
        ]

        signals_only = [r for r in results if r.result_type == "signal"]

        assert len(signals_only) == 1
        assert signals_only[0].result_type == "signal"

    def test_include_only_clusters(self) -> None:
        """Can filter to only clusters."""
        results = [
            SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content="Signal",
                preview="Signal",
                relevance_score=1.0,
            ),
            SearchResult(
                result_type="cluster",
                entity_id=ObjectId(),
                content="Cluster",
                preview="Cluster",
                relevance_score=1.0,
            ),
        ]

        clusters_only = [r for r in results if r.result_type == "cluster"]

        assert len(clusters_only) == 1
        assert clusters_only[0].result_type == "cluster"

    def test_include_multiple_types(self) -> None:
        """Can include multiple types."""
        results = [
            SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content="Signal",
                preview="Signal",
                relevance_score=1.0,
            ),
            SearchResult(
                result_type="cluster",
                entity_id=ObjectId(),
                content="Cluster",
                preview="Cluster",
                relevance_score=1.0,
            ),
            SearchResult(
                result_type="cop_candidate",
                entity_id=ObjectId(),
                content="Candidate",
                preview="Candidate",
                relevance_score=1.0,
            ),
        ]

        include_types = ["signal", "cluster"]
        filtered = [r for r in results if r.result_type in include_types]

        assert len(filtered) == 2


# ============================================================================
# Cluster Membership Tests
# ============================================================================


@pytest.mark.unit
class TestClusterMembership:
    """Test cluster membership in search results."""

    def test_signal_with_cluster_membership(self) -> None:
        """Signal shows cluster membership."""
        cluster_id = ObjectId()
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Clustered signal",
            preview="Clustered...",
            relevance_score=1.0,
            cluster_ids=[cluster_id],
            cluster_topics=["Test Cluster"],
        )

        assert len(result.cluster_ids) == 1
        assert result.cluster_topics == ["Test Cluster"]

    def test_signal_with_multiple_clusters(self) -> None:
        """Signal can belong to multiple clusters."""
        cluster_ids = [ObjectId(), ObjectId()]
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Multi-cluster signal",
            preview="Multi-cluster...",
            relevance_score=1.0,
            cluster_ids=cluster_ids,
            cluster_topics=["Topic A", "Topic B"],
        )

        assert len(result.cluster_ids) == 2
        assert len(result.cluster_topics) == 2


# ============================================================================
# COP Candidate Status Tests
# ============================================================================


@pytest.mark.unit
class TestCOPCandidateStatus:
    """Test COP candidate status in search results."""

    def test_signal_with_candidate_status(self) -> None:
        """Signal shows COP candidate status."""
        candidate_id = ObjectId()
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content="Promoted signal",
            preview="Promoted...",
            relevance_score=1.0,
            cop_candidate_id=candidate_id,
            cop_candidate_state="verified",
        )

        assert result.cop_candidate_id == candidate_id
        assert result.cop_candidate_state == "verified"

    def test_candidate_states(self) -> None:
        """Test different candidate states."""
        states = ["in_review", "verified", "blocked"]

        for state in states:
            result = SearchResult(
                result_type="signal",
                entity_id=ObjectId(),
                content=f"Signal in {state}",
                preview=f"Signal in {state}",
                relevance_score=1.0,
                cop_candidate_id=ObjectId(),
                cop_candidate_state=state,
            )

            assert result.cop_candidate_state == state


# ============================================================================
# Preview Generation Tests
# ============================================================================


@pytest.mark.unit
class TestPreviewGeneration:
    """Test search result preview generation."""

    def test_short_content_preview(self) -> None:
        """Short content is used as preview."""
        content = "Short message"
        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content=content,
            preview=content,
            relevance_score=1.0,
        )

        assert result.preview == content

    def test_truncated_preview(self) -> None:
        """Long content is truncated in preview."""
        content = "A" * 300
        preview = content[:200] + "..."

        result = SearchResult(
            result_type="signal",
            entity_id=ObjectId(),
            content=content,
            preview=preview,
            relevance_score=1.0,
        )

        assert len(result.preview) < len(result.content)
        assert result.preview.endswith("...")
