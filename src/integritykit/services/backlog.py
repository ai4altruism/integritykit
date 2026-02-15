"""Private COP backlog service for facilitators.

Implements:
- FR-BACKLOG-001: Private backlog with prioritized clusters
- FR-BACKLOG-002: Support for promote to COP candidate
- NFR-PRIVACY-001: Private facilitator views
"""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.cluster import Cluster, PriorityScores
from integritykit.models.signal import Signal
from integritykit.services.database import (
    ClusterRepository,
    SignalRepository,
    get_collection,
)


class BacklogItem:
    """Enriched backlog item with cluster and signal details."""

    def __init__(
        self,
        cluster: Cluster,
        signals: list[Signal],
        signal_count: int,
    ):
        """Initialize backlog item.

        Args:
            cluster: The cluster data
            signals: Sample signals from the cluster
            signal_count: Total number of signals in cluster
        """
        self.cluster = cluster
        self.signals = signals
        self.signal_count = signal_count

    @property
    def id(self) -> ObjectId:
        """Get cluster ID."""
        return self.cluster.id

    @property
    def topic(self) -> str:
        """Get cluster topic."""
        return self.cluster.topic

    @property
    def summary(self) -> str:
        """Get cluster summary."""
        return self.cluster.summary

    @property
    def incident_type(self) -> Optional[str]:
        """Get incident type."""
        return self.cluster.incident_type

    @property
    def priority_scores(self) -> PriorityScores:
        """Get priority scores."""
        return self.cluster.priority_scores

    @property
    def composite_score(self) -> float:
        """Get composite priority score."""
        return self.cluster.priority_scores.composite_score

    @property
    def has_conflicts(self) -> bool:
        """Check if cluster has conflicts."""
        return self.cluster.has_conflicts

    @property
    def has_unresolved_conflicts(self) -> bool:
        """Check if cluster has unresolved conflicts."""
        return self.cluster.has_unresolved_conflicts

    @property
    def conflict_count(self) -> int:
        """Get number of conflicts."""
        return len(self.cluster.conflicts)

    @property
    def unresolved_conflict_count(self) -> int:
        """Get number of unresolved conflicts."""
        return sum(1 for c in self.cluster.conflicts if not c.resolved)

    @property
    def created_at(self) -> datetime:
        """Get creation timestamp."""
        return self.cluster.created_at

    @property
    def updated_at(self) -> datetime:
        """Get last update timestamp."""
        return self.cluster.updated_at

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for API response.

        Returns:
            Dictionary representation
        """
        return {
            "id": str(self.cluster.id),
            "topic": self.topic,
            "summary": self.summary,
            "incident_type": self.incident_type,
            "signal_count": self.signal_count,
            "priority_scores": {
                "urgency": self.priority_scores.urgency,
                "urgency_reasoning": self.priority_scores.urgency_reasoning,
                "impact": self.priority_scores.impact,
                "impact_reasoning": self.priority_scores.impact_reasoning,
                "risk": self.priority_scores.risk,
                "risk_reasoning": self.priority_scores.risk_reasoning,
                "composite_score": self.composite_score,
            },
            "has_conflicts": self.has_conflicts,
            "conflict_count": self.conflict_count,
            "unresolved_conflict_count": self.unresolved_conflict_count,
            "sample_signals": [
                {
                    "id": str(s.id),
                    "content": s.content[:200] + "..." if len(s.content) > 200 else s.content,
                    "slack_permalink": s.slack_permalink,
                    "created_at": s.created_at.isoformat(),
                }
                for s in self.signals[:3]  # Limit to 3 sample signals
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class BacklogService:
    """Service for managing the facilitator backlog (FR-BACKLOG-001).

    The backlog contains unpromoted clusters ordered by priority.
    Access is restricted to facilitators and verifiers.
    """

    def __init__(
        self,
        cluster_repo: Optional[ClusterRepository] = None,
        signal_repo: Optional[SignalRepository] = None,
    ):
        """Initialize backlog service.

        Args:
            cluster_repo: Cluster repository (optional)
            signal_repo: Signal repository (optional)
        """
        self.cluster_repo = cluster_repo or ClusterRepository()
        self.signal_repo = signal_repo or SignalRepository()

    async def get_backlog(
        self,
        workspace_id: str,
        limit: int = 50,
        offset: int = 0,
        include_signals: bool = True,
        sort_by: str = "priority",
    ) -> list[BacklogItem]:
        """Get prioritized backlog items for a workspace.

        Args:
            workspace_id: Slack workspace ID
            limit: Maximum items to return
            offset: Number of items to skip
            include_signals: Whether to include sample signals
            sort_by: Sort field (priority, urgency, impact, risk, updated)

        Returns:
            List of BacklogItem instances
        """
        clusters = await self.cluster_repo.list_unpromoted_clusters(
            workspace_id=workspace_id,
            limit=limit,
            offset=offset,
        )

        backlog_items = []
        for cluster in clusters:
            signals = []
            if include_signals and cluster.signal_ids:
                # Fetch a few sample signals for preview
                signals = await self._get_sample_signals(cluster.signal_ids[:5])

            item = BacklogItem(
                cluster=cluster,
                signals=signals,
                signal_count=len(cluster.signal_ids),
            )
            backlog_items.append(item)

        # Apply secondary sorting if needed
        if sort_by == "urgency":
            backlog_items.sort(key=lambda x: x.priority_scores.urgency, reverse=True)
        elif sort_by == "impact":
            backlog_items.sort(key=lambda x: x.priority_scores.impact, reverse=True)
        elif sort_by == "risk":
            backlog_items.sort(key=lambda x: x.priority_scores.risk, reverse=True)
        elif sort_by == "updated":
            backlog_items.sort(key=lambda x: x.updated_at, reverse=True)
        # Default "priority" sorting is already done by the repository

        return backlog_items

    async def get_backlog_item(
        self,
        workspace_id: str,
        cluster_id: ObjectId,
        include_all_signals: bool = False,
    ) -> Optional[BacklogItem]:
        """Get a single backlog item by cluster ID.

        Args:
            workspace_id: Slack workspace ID
            cluster_id: Cluster ObjectId
            include_all_signals: Whether to include all signals (vs sample)

        Returns:
            BacklogItem or None if not found
        """
        cluster = await self.cluster_repo.get_by_id(cluster_id)

        if not cluster:
            return None

        # Verify workspace matches
        if cluster.slack_workspace_id != workspace_id:
            return None

        # Don't return promoted clusters as backlog items
        if cluster.promoted_to_candidate:
            return None

        signals = []
        if cluster.signal_ids:
            if include_all_signals:
                signals = await self._get_all_signals(cluster.signal_ids)
            else:
                signals = await self._get_sample_signals(cluster.signal_ids[:5])

        return BacklogItem(
            cluster=cluster,
            signals=signals,
            signal_count=len(cluster.signal_ids),
        )

    async def count_backlog_items(self, workspace_id: str) -> int:
        """Count total backlog items for a workspace.

        Args:
            workspace_id: Slack workspace ID

        Returns:
            Count of unpromoted clusters
        """
        collection = self.cluster_repo.collection
        return await collection.count_documents(
            {
                "slack_workspace_id": workspace_id,
                "promoted_to_candidate": False,
            }
        )

    async def get_backlog_stats(self, workspace_id: str) -> dict[str, Any]:
        """Get backlog statistics for a workspace.

        Args:
            workspace_id: Slack workspace ID

        Returns:
            Dictionary with backlog statistics
        """
        collection = self.cluster_repo.collection

        # Count total
        total_count = await collection.count_documents(
            {
                "slack_workspace_id": workspace_id,
                "promoted_to_candidate": False,
            }
        )

        # Count with conflicts
        conflicts_count = await collection.count_documents(
            {
                "slack_workspace_id": workspace_id,
                "promoted_to_candidate": False,
                "conflicts.0": {"$exists": True},
            }
        )

        # Get high priority items (urgency > 70)
        high_priority_count = await collection.count_documents(
            {
                "slack_workspace_id": workspace_id,
                "promoted_to_candidate": False,
                "priority_scores.urgency": {"$gt": 70},
            }
        )

        return {
            "total_items": total_count,
            "items_with_conflicts": conflicts_count,
            "high_priority_items": high_priority_count,
        }

    async def _get_sample_signals(self, signal_ids: list[ObjectId]) -> list[Signal]:
        """Get sample signals by IDs.

        Args:
            signal_ids: List of signal ObjectIds

        Returns:
            List of Signal instances
        """
        signals = []
        for signal_id in signal_ids:
            signal = await self.signal_repo.get_by_id(signal_id)
            if signal:
                signals.append(signal)
        return signals

    async def _get_all_signals(self, signal_ids: list[ObjectId]) -> list[Signal]:
        """Get all signals by IDs.

        Args:
            signal_ids: List of signal ObjectIds

        Returns:
            List of Signal instances
        """
        return await self._get_sample_signals(signal_ids)


# Global service instance
_backlog_service: Optional[BacklogService] = None


def get_backlog_service() -> BacklogService:
    """Get the global backlog service instance.

    Returns:
        BacklogService singleton
    """
    global _backlog_service
    if _backlog_service is None:
        _backlog_service = BacklogService()
    return _backlog_service
