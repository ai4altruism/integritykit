"""Metrics collection service for operational metrics.

Implements:
- FR-METRICS-001: Five operational metrics collection
- FR-METRICS-002: Metrics export capability
"""

from datetime import datetime

from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.audit import AuditActionType
from integritykit.models.cop_candidate import ReadinessState
from integritykit.models.cop_update import COPUpdateStatus
from integritykit.models.metrics import (
    ConflictingReportRateMetric,
    MetricsSnapshot,
    ModeratorBurdenMetric,
    ProvenanceCoverageMetric,
    ReadinessDistributionMetric,
    TimeToValidatedUpdateMetric,
)
from integritykit.services.database import get_collection


class MetricsService:
    """Service for collecting and computing operational metrics (FR-METRICS-001)."""

    def __init__(
        self,
        signals_collection: AsyncIOMotorCollection | None = None,
        clusters_collection: AsyncIOMotorCollection | None = None,
        candidates_collection: AsyncIOMotorCollection | None = None,
        cop_updates_collection: AsyncIOMotorCollection | None = None,
        audit_log_collection: AsyncIOMotorCollection | None = None,
    ):
        """Initialize metrics service.

        Args:
            signals_collection: Signals collection (optional)
            clusters_collection: Clusters collection (optional)
            candidates_collection: COP candidates collection (optional)
            cop_updates_collection: COP updates collection (optional)
            audit_log_collection: Audit log collection (optional)
        """
        self.signals = signals_collection or get_collection("signals")
        self.clusters = clusters_collection or get_collection("clusters")
        self.candidates = candidates_collection or get_collection("cop_candidates")
        self.cop_updates = cop_updates_collection or get_collection("cop_updates")
        self.audit_log = audit_log_collection or get_collection("audit_log")

    async def compute_time_to_validated_update(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> TimeToValidatedUpdateMetric:
        """Compute time-to-validated-update metric.

        Measures the time from earliest signal in a candidate to COP publication.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            TimeToValidatedUpdateMetric with computed values
        """
        # Find published COP updates in the time range
        pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "status": COPUpdateStatus.PUBLISHED.value,
                    "published_at": {"$gte": start_time, "$lte": end_time},
                }
            },
            {
                "$lookup": {
                    "from": "cop_candidates",
                    "localField": "candidate_ids",
                    "foreignField": "_id",
                    "as": "candidates",
                }
            },
            {
                "$unwind": {"path": "$candidates", "preserveNullAndEmptyArrays": True}
            },
            {
                "$lookup": {
                    "from": "signals",
                    "localField": "candidates.primary_signal_ids",
                    "foreignField": "_id",
                    "as": "signals",
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "published_at": 1,
                    "risk_tier": "$candidates.risk_tier",
                    "earliest_signal_time": {"$min": "$signals.created_at"},
                }
            },
            {
                "$match": {
                    "earliest_signal_time": {"$exists": True, "$ne": None}
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "published_at": 1,
                    "risk_tier": 1,
                    "time_to_publish_seconds": {
                        "$divide": [
                            {"$subtract": ["$published_at", "$earliest_signal_time"]},
                            1000,  # Convert ms to seconds
                        ]
                    },
                }
            },
        ]

        results = []
        async for doc in self.cop_updates.aggregate(pipeline):
            results.append(doc)

        if not results:
            return TimeToValidatedUpdateMetric(
                average_seconds=0,
                median_seconds=0,
                min_seconds=0,
                max_seconds=0,
                p90_seconds=0,
                sample_count=0,
                breakdown_by_risk_tier={},
            )

        # Calculate statistics
        times = [r["time_to_publish_seconds"] for r in results if r.get("time_to_publish_seconds")]

        if not times:
            return TimeToValidatedUpdateMetric(
                average_seconds=0,
                median_seconds=0,
                min_seconds=0,
                max_seconds=0,
                p90_seconds=0,
                sample_count=0,
                breakdown_by_risk_tier={},
            )

        times.sort()
        n = len(times)

        average = sum(times) / n
        median = times[n // 2] if n % 2 == 1 else (times[n // 2 - 1] + times[n // 2]) / 2
        p90_idx = int(n * 0.9)
        p90 = times[min(p90_idx, n - 1)]

        # Breakdown by risk tier
        by_tier: dict[str, list[float]] = {}
        for r in results:
            tier = r.get("risk_tier", "routine")
            if tier not in by_tier:
                by_tier[tier] = []
            if r.get("time_to_publish_seconds"):
                by_tier[tier].append(r["time_to_publish_seconds"])

        tier_averages = {
            tier: sum(vals) / len(vals) if vals else 0
            for tier, vals in by_tier.items()
        }

        return TimeToValidatedUpdateMetric(
            average_seconds=average,
            median_seconds=median,
            min_seconds=min(times),
            max_seconds=max(times),
            p90_seconds=p90,
            sample_count=n,
            breakdown_by_risk_tier=tier_averages,
        )

    async def compute_conflicting_report_rate(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ConflictingReportRateMetric:
        """Compute conflicting report rate metric.

        Measures the rate of conflicts detected in clusters.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            ConflictingReportRateMetric with computed values
        """
        # Count total clusters
        total_clusters = await self.clusters.count_documents({
            "slack_workspace_id": workspace_id,
            "created_at": {"$gte": start_time, "$lte": end_time},
        })

        # Count clusters with conflicts
        clusters_with_conflicts = await self.clusters.count_documents({
            "slack_workspace_id": workspace_id,
            "created_at": {"$gte": start_time, "$lte": end_time},
            "conflicts": {"$exists": True, "$ne": []},
        })

        # Aggregate conflict details
        pipeline = [
            {
                "$match": {
                    "slack_workspace_id": workspace_id,
                    "created_at": {"$gte": start_time, "$lte": end_time},
                    "conflicts": {"$exists": True, "$ne": []},
                }
            },
            {"$unwind": "$conflicts"},
            {
                "$group": {
                    "_id": None,
                    "total_conflicts": {"$sum": 1},
                    "resolved_conflicts": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$conflicts.status", "resolved"]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]

        conflict_stats = {"total_conflicts": 0, "resolved_conflicts": 0}
        async for doc in self.clusters.aggregate(pipeline):
            conflict_stats = doc

        total_conflicts = conflict_stats.get("total_conflicts", 0)
        resolved_conflicts = conflict_stats.get("resolved_conflicts", 0)

        conflict_rate = (
            (clusters_with_conflicts / total_clusters * 100)
            if total_clusters > 0
            else 0
        )
        resolution_rate = (
            (resolved_conflicts / total_conflicts * 100)
            if total_conflicts > 0
            else 0
        )

        # Calculate average resolution time from audit log
        resolution_time_pipeline = [
            {
                "$match": {
                    "action_type": {"$in": [
                        "cluster.conflict_resolved",
                        "cop_candidate.resolve_conflict",
                    ]},
                    "timestamp": {"$gte": start_time, "$lte": end_time},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "avg_resolution_time": {"$avg": "$system_context.resolution_time_seconds"},
                }
            },
        ]

        avg_resolution_time = None
        async for doc in self.audit_log.aggregate(resolution_time_pipeline):
            avg_resolution_time = doc.get("avg_resolution_time")

        return ConflictingReportRateMetric(
            total_clusters=total_clusters,
            clusters_with_conflicts=clusters_with_conflicts,
            conflict_rate=conflict_rate,
            total_conflicts_detected=total_conflicts,
            conflicts_resolved=resolved_conflicts,
            resolution_rate=resolution_rate,
            average_resolution_time_seconds=avg_resolution_time,
        )

    async def compute_moderator_burden(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ModeratorBurdenMetric:
        """Compute moderator burden metric.

        Measures facilitator workload and actions.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            ModeratorBurdenMetric with computed values
        """
        # Facilitator action types to count
        facilitator_actions = [
            AuditActionType.COP_CANDIDATE_PROMOTE.value,
            AuditActionType.COP_CANDIDATE_UPDATE_STATE.value,
            AuditActionType.COP_CANDIDATE_UPDATE_RISK_TIER.value,
            AuditActionType.COP_CANDIDATE_VERIFY.value,
            AuditActionType.COP_CANDIDATE_MERGE.value,
            AuditActionType.COP_UPDATE_PUBLISH.value,
            AuditActionType.COP_UPDATE_OVERRIDE.value,
        ]

        # Count actions by type
        pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_time, "$lte": end_time},
                    "action_type": {"$in": facilitator_actions},
                    "actor_role": {"$in": ["facilitator", "workspace_admin"]},
                }
            },
            {
                "$group": {
                    "_id": "$action_type",
                    "count": {"$sum": 1},
                }
            },
        ]

        actions_by_type: dict[str, int] = {}
        async for doc in self.audit_log.aggregate(pipeline):
            actions_by_type[doc["_id"]] = doc["count"]

        total_actions = sum(actions_by_type.values())

        # Count unique facilitators
        unique_facilitators_pipeline = [
            {
                "$match": {
                    "timestamp": {"$gte": start_time, "$lte": end_time},
                    "action_type": {"$in": facilitator_actions},
                    "actor_role": {"$in": ["facilitator", "workspace_admin"]},
                }
            },
            {
                "$group": {
                    "_id": "$actor_id",
                }
            },
            {"$count": "unique_count"},
        ]

        unique_facilitators = 0
        async for doc in self.audit_log.aggregate(unique_facilitators_pipeline):
            unique_facilitators = doc.get("unique_count", 0)

        # Count published COP updates
        cop_updates_count = await self.cop_updates.count_documents({
            "workspace_id": workspace_id,
            "status": COPUpdateStatus.PUBLISHED.value,
            "published_at": {"$gte": start_time, "$lte": end_time},
        })

        # Count high-stakes overrides
        high_stakes_overrides = actions_by_type.get(
            AuditActionType.COP_UPDATE_OVERRIDE.value, 0
        )

        # Count edits to AI drafts
        edits_pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "status": COPUpdateStatus.PUBLISHED.value,
                    "published_at": {"$gte": start_time, "$lte": end_time},
                }
            },
            {
                "$project": {
                    "edit_count": 1,
                    "edited_items": {
                        "$size": {
                            "$filter": {
                                "input": "$line_items",
                                "as": "item",
                                "cond": {"$eq": ["$$item.was_edited", True]},
                            }
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_edits": {"$sum": "$edit_count"},
                    "total_edited_items": {"$sum": "$edited_items"},
                }
            },
        ]

        edits_to_ai_drafts = 0
        async for doc in self.cop_updates.aggregate(edits_pipeline):
            edits_to_ai_drafts = doc.get("total_edited_items", 0)

        actions_per_update = (
            total_actions / cop_updates_count if cop_updates_count > 0 else 0
        )
        actions_per_facilitator = (
            total_actions / unique_facilitators if unique_facilitators > 0 else 0
        )

        return ModeratorBurdenMetric(
            total_facilitator_actions=total_actions,
            actions_per_cop_update=actions_per_update,
            actions_by_type=actions_by_type,
            unique_facilitators_active=unique_facilitators,
            actions_per_facilitator=actions_per_facilitator,
            high_stakes_overrides=high_stakes_overrides,
            edits_to_ai_drafts=edits_to_ai_drafts,
        )

    async def compute_provenance_coverage(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ProvenanceCoverageMetric:
        """Compute provenance coverage metric.

        Measures citation and evidence coverage in published COP updates.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            ProvenanceCoverageMetric with computed values
        """
        pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "status": COPUpdateStatus.PUBLISHED.value,
                    "published_at": {"$gte": start_time, "$lte": end_time},
                }
            },
            {"$unwind": "$line_items"},
            {
                "$project": {
                    "has_citations": {
                        "$cond": [
                            {"$gt": [{"$size": "$line_items.citations"}, 0]},
                            1,
                            0,
                        ]
                    },
                    "citation_count": {"$size": "$line_items.citations"},
                    "citations": "$line_items.citations",
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_items": {"$sum": 1},
                    "items_with_citations": {"$sum": "$has_citations"},
                    "total_citations": {"$sum": "$citation_count"},
                    "all_citations": {"$push": "$citations"},
                }
            },
        ]

        result = {
            "total_items": 0,
            "items_with_citations": 0,
            "total_citations": 0,
            "all_citations": [],
        }
        async for doc in self.cop_updates.aggregate(pipeline):
            result = doc

        total_items = result.get("total_items", 0)
        items_with_citations = result.get("items_with_citations", 0)
        total_citations = result.get("total_citations", 0)

        # Count citation types
        all_citations = []
        for citation_list in result.get("all_citations", []):
            all_citations.extend(citation_list)

        slack_citations = sum(
            1 for c in all_citations
            if c and ("slack.com" in c or c.startswith("slack://"))
        )
        external_citations = len(all_citations) - slack_citations

        coverage_rate = (
            (items_with_citations / total_items * 100) if total_items > 0 else 0
        )
        avg_citations = total_citations / total_items if total_items > 0 else 0

        return ProvenanceCoverageMetric(
            total_published_line_items=total_items,
            line_items_with_citations=items_with_citations,
            coverage_rate=coverage_rate,
            average_citations_per_item=avg_citations,
            slack_permalink_citations=slack_citations,
            external_source_citations=external_citations,
        )

    async def compute_readiness_distribution(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> ReadinessDistributionMetric:
        """Compute readiness distribution metric.

        Measures distribution of COP candidates across readiness states.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            ReadinessDistributionMetric with computed values
        """
        # First get cluster IDs for this workspace
        cluster_ids = []
        async for doc in self.clusters.find(
            {"slack_workspace_id": workspace_id},
            {"_id": 1},
        ):
            cluster_ids.append(doc["_id"])

        if not cluster_ids:
            return ReadinessDistributionMetric(
                total_candidates=0,
                in_review_count=0,
                verified_count=0,
                blocked_count=0,
                archived_count=0,
                in_review_percentage=0,
                verified_percentage=0,
                blocked_percentage=0,
                archived_percentage=0,
                by_risk_tier={},
            )

        # Count by readiness state
        pipeline = [
            {
                "$match": {
                    "cluster_id": {"$in": cluster_ids},
                    "created_at": {"$lte": end_time},
                }
            },
            {
                "$group": {
                    "_id": "$readiness_state",
                    "count": {"$sum": 1},
                }
            },
        ]

        state_counts: dict[str, int] = {
            ReadinessState.IN_REVIEW.value: 0,
            ReadinessState.VERIFIED.value: 0,
            ReadinessState.BLOCKED.value: 0,
            ReadinessState.ARCHIVED.value: 0,
        }

        async for doc in self.candidates.aggregate(pipeline):
            state_counts[doc["_id"]] = doc["count"]

        total = sum(state_counts.values())

        # Breakdown by risk tier
        tier_pipeline = [
            {
                "$match": {
                    "cluster_id": {"$in": cluster_ids},
                    "created_at": {"$lte": end_time},
                }
            },
            {
                "$group": {
                    "_id": {
                        "risk_tier": "$risk_tier",
                        "readiness_state": "$readiness_state",
                    },
                    "count": {"$sum": 1},
                }
            },
        ]

        by_risk_tier: dict[str, dict[str, int]] = {}
        async for doc in self.candidates.aggregate(tier_pipeline):
            tier = doc["_id"]["risk_tier"]
            state = doc["_id"]["readiness_state"]
            if tier not in by_risk_tier:
                by_risk_tier[tier] = {}
            by_risk_tier[tier][state] = doc["count"]

        def pct(count: int) -> float:
            return (count / total * 100) if total > 0 else 0

        return ReadinessDistributionMetric(
            total_candidates=total,
            in_review_count=state_counts[ReadinessState.IN_REVIEW.value],
            verified_count=state_counts[ReadinessState.VERIFIED.value],
            blocked_count=state_counts[ReadinessState.BLOCKED.value],
            archived_count=state_counts[ReadinessState.ARCHIVED.value],
            in_review_percentage=pct(state_counts[ReadinessState.IN_REVIEW.value]),
            verified_percentage=pct(state_counts[ReadinessState.VERIFIED.value]),
            blocked_percentage=pct(state_counts[ReadinessState.BLOCKED.value]),
            archived_percentage=pct(state_counts[ReadinessState.ARCHIVED.value]),
            by_risk_tier=by_risk_tier,
        )

    async def compute_metrics_snapshot(
        self,
        workspace_id: str,
        start_time: datetime,
        end_time: datetime,
    ) -> MetricsSnapshot:
        """Compute complete metrics snapshot for a time period.

        Args:
            workspace_id: Slack workspace ID
            start_time: Period start
            end_time: Period end

        Returns:
            MetricsSnapshot with all five operational metrics
        """
        # Compute all metrics
        time_to_validated = await self.compute_time_to_validated_update(
            workspace_id, start_time, end_time
        )
        conflict_rate = await self.compute_conflicting_report_rate(
            workspace_id, start_time, end_time
        )
        moderator_burden = await self.compute_moderator_burden(
            workspace_id, start_time, end_time
        )
        provenance = await self.compute_provenance_coverage(
            workspace_id, start_time, end_time
        )
        readiness = await self.compute_readiness_distribution(
            workspace_id, start_time, end_time
        )

        # Build summary
        summary = {
            "period_hours": (end_time - start_time).total_seconds() / 3600,
            "cop_updates_published": time_to_validated.sample_count,
            "average_time_to_publish_minutes": time_to_validated.average_seconds / 60,
            "conflict_rate_percent": conflict_rate.conflict_rate,
            "provenance_coverage_percent": provenance.coverage_rate,
            "facilitator_actions_total": moderator_burden.total_facilitator_actions,
            "candidates_verified": readiness.verified_count,
            "candidates_blocked": readiness.blocked_count,
        }

        return MetricsSnapshot(
            workspace_id=workspace_id,
            period_start=start_time,
            period_end=end_time,
            time_to_validated_update=time_to_validated,
            conflicting_report_rate=conflict_rate,
            moderator_burden=moderator_burden,
            provenance_coverage=provenance,
            readiness_distribution=readiness,
            summary=summary,
        )


# Global service instance
_metrics_service: MetricsService | None = None


def get_metrics_service() -> MetricsService:
    """Get the global metrics service instance.

    Returns:
        MetricsService singleton
    """
    global _metrics_service
    if _metrics_service is None:
        _metrics_service = MetricsService()
    return _metrics_service


async def get_metrics_service_dependency() -> MetricsService:
    """Get metrics service instance (for FastAPI dependency injection).

    Returns:
        MetricsService instance
    """
    return MetricsService()
