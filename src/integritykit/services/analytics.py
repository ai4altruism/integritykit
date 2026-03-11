"""Time-series analytics service for Sprint 8.

Implements:
- FR-ANALYTICS-001: Time-series analysis of signal volume and readiness
- S8-9: Time-series analytics with MongoDB aggregation pipelines
"""

from datetime import datetime, timedelta
from typing import Optional

import structlog
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.analytics import (
    FacilitatorActionDataPoint,
    Granularity,
    ReadinessTransitionDataPoint,
    SignalVolumeDataPoint,
    TimeSeriesAnalyticsRequest,
    TimeSeriesAnalyticsResponse,
    TopicTrend,
    TopicTrendsResponse,
    TrendDirection,
)
from integritykit.models.audit import AuditActionType
from integritykit.services.database import get_collection

logger = structlog.get_logger(__name__)


class AnalyticsService:
    """Service for time-series analytics computations (FR-ANALYTICS-001, S8-9)."""

    def __init__(
        self,
        signals_collection: Optional[AsyncIOMotorCollection] = None,
        candidates_collection: Optional[AsyncIOMotorCollection] = None,
        audit_log_collection: Optional[AsyncIOMotorCollection] = None,
        clusters_collection: Optional[AsyncIOMotorCollection] = None,
        max_time_range_days: int = 90,
        retention_days: int = 365,
    ):
        """Initialize analytics service.

        Args:
            signals_collection: Signals collection (optional)
            candidates_collection: COP candidates collection (optional)
            audit_log_collection: Audit log collection (optional)
            clusters_collection: Clusters collection (optional)
            max_time_range_days: Maximum time range for queries (default: 90)
            retention_days: Analytics data retention period (default: 365)
        """
        self.signals = signals_collection or get_collection("signals")
        self.candidates = candidates_collection or get_collection("cop_candidates")
        self.audit_log = audit_log_collection or get_collection("audit_log")
        self.clusters = clusters_collection or get_collection("clusters")
        self.max_time_range_days = max_time_range_days
        self.retention_days = retention_days

    def _get_date_format_string(self, granularity: Granularity) -> str:
        """Get MongoDB date format string for time bucketing.

        Args:
            granularity: Time granularity (hour, day, week)

        Returns:
            MongoDB date format string
        """
        if granularity == Granularity.HOUR:
            return "%Y-%m-%d %H:00:00"
        elif granularity == Granularity.DAY:
            return "%Y-%m-%d"
        elif granularity == Granularity.WEEK:
            # Week format: YYYY-Www (ISO week)
            return "%Y-W%V"
        return "%Y-%m-%d"

    def _parse_bucket_timestamp(
        self,
        bucket_str: str,
        granularity: Granularity,
    ) -> datetime:
        """Parse bucket string back to datetime.

        Args:
            bucket_str: Bucket string from MongoDB
            granularity: Time granularity used

        Returns:
            datetime for bucket start
        """
        if granularity == Granularity.HOUR:
            return datetime.strptime(bucket_str, "%Y-%m-%d %H:00:00")
        elif granularity == Granularity.DAY:
            return datetime.strptime(bucket_str, "%Y-%m-%d")
        elif granularity == Granularity.WEEK:
            # Parse ISO week format (YYYY-Www)
            year, week = bucket_str.split("-W")
            # Get Monday of that week
            return datetime.strptime(f"{year}-W{week}-1", "%Y-W%W-%w")
        return datetime.strptime(bucket_str, "%Y-%m-%d")

    async def compute_signal_volume_time_series(
        self,
        workspace_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: Granularity,
    ) -> list[SignalVolumeDataPoint]:
        """Compute time-series of signal ingestion volume.

        Uses MongoDB aggregation pipeline with $dateToString for time bucketing.

        Args:
            workspace_id: Slack workspace ID
            start_date: Start of analysis period
            end_date: End of analysis period
            granularity: Time bucket granularity

        Returns:
            List of SignalVolumeDataPoint time-series
        """
        date_format = self._get_date_format_string(granularity)

        pipeline = [
            {
                "$match": {
                    "slack_workspace_id": workspace_id,
                    "created_at": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$group": {
                    "_id": {
                        "time_bucket": {
                            "$dateToString": {
                                "format": date_format,
                                "date": "$created_at",
                            }
                        },
                        "channel_id": "$slack_channel_id",
                    },
                    "count": {"$sum": 1},
                }
            },
            {
                "$group": {
                    "_id": "$_id.time_bucket",
                    "total_count": {"$sum": "$count"},
                    "by_channel": {
                        "$push": {
                            "k": "$_id.channel_id",
                            "v": "$count",
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = []
        async for doc in self.signals.aggregate(pipeline):
            bucket_timestamp = self._parse_bucket_timestamp(doc["_id"], granularity)

            # Convert channel breakdown to dict
            by_channel = {item["k"]: item["v"] for item in doc.get("by_channel", [])}

            results.append(
                SignalVolumeDataPoint(
                    timestamp=bucket_timestamp,
                    signal_count=doc["total_count"],
                    by_channel=by_channel,
                )
            )

        logger.info(
            "Computed signal volume time-series",
            workspace_id=workspace_id,
            data_points=len(results),
            granularity=granularity,
        )

        return results

    async def compute_readiness_transitions_time_series(
        self,
        workspace_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: Granularity,
    ) -> list[ReadinessTransitionDataPoint]:
        """Compute time-series of readiness state transitions.

        Tracks transitions like IN_REVIEW -> VERIFIED, VERIFIED -> BLOCKED, etc.

        Args:
            workspace_id: Slack workspace ID
            start_date: Start of analysis period
            end_date: End of analysis period
            granularity: Time bucket granularity

        Returns:
            List of ReadinessTransitionDataPoint time-series
        """
        # First get cluster IDs for this workspace
        cluster_ids = []
        async for doc in self.clusters.find(
            {"slack_workspace_id": workspace_id},
            {"_id": 1},
        ):
            cluster_ids.append(doc["_id"])

        if not cluster_ids:
            return []

        date_format = self._get_date_format_string(granularity)

        # Query audit log for readiness state changes
        pipeline = [
            {
                "$match": {
                    "action_type": AuditActionType.COP_CANDIDATE_UPDATE_STATE.value,
                    "timestamp": {"$gte": start_date, "$lte": end_date},
                }
            },
            {
                "$project": {
                    "time_bucket": {
                        "$dateToString": {
                            "format": date_format,
                            "date": "$timestamp",
                        }
                    },
                    "old_state": "$before_state.readiness_state",
                    "new_state": "$after_state.readiness_state",
                }
            },
            {
                "$group": {
                    "_id": {
                        "time_bucket": "$time_bucket",
                        "transition": {
                            "$concat": ["$old_state", "->", "$new_state"]
                        },
                    },
                    "count": {"$sum": 1},
                }
            },
            {
                "$group": {
                    "_id": "$_id.time_bucket",
                    "total_transitions": {"$sum": "$count"},
                    "transitions": {
                        "$push": {
                            "k": "$_id.transition",
                            "v": "$count",
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = []
        async for doc in self.audit_log.aggregate(pipeline):
            bucket_timestamp = self._parse_bucket_timestamp(doc["_id"], granularity)

            # Convert transitions to dict
            transitions = {item["k"]: item["v"] for item in doc.get("transitions", [])}

            results.append(
                ReadinessTransitionDataPoint(
                    timestamp=bucket_timestamp,
                    transitions=transitions,
                    total_transitions=doc["total_transitions"],
                )
            )

        logger.info(
            "Computed readiness transitions time-series",
            workspace_id=workspace_id,
            data_points=len(results),
            granularity=granularity,
        )

        return results

    async def compute_facilitator_actions_time_series(
        self,
        workspace_id: str,
        start_date: datetime,
        end_date: datetime,
        granularity: Granularity,
        facilitator_id: Optional[str] = None,
    ) -> list[FacilitatorActionDataPoint]:
        """Compute time-series of facilitator action velocity.

        Tracks facilitator actions over time with breakdown by action type.

        Args:
            workspace_id: Slack workspace ID (used for filtering)
            start_date: Start of analysis period
            end_date: End of analysis period
            granularity: Time bucket granularity
            facilitator_id: Filter by specific facilitator (optional)

        Returns:
            List of FacilitatorActionDataPoint time-series
        """
        date_format = self._get_date_format_string(granularity)

        # Facilitator action types to track
        facilitator_actions = [
            AuditActionType.COP_CANDIDATE_PROMOTE.value,
            AuditActionType.COP_CANDIDATE_UPDATE_STATE.value,
            AuditActionType.COP_CANDIDATE_UPDATE_RISK_TIER.value,
            AuditActionType.COP_CANDIDATE_VERIFY.value,
            AuditActionType.COP_CANDIDATE_MERGE.value,
            AuditActionType.COP_UPDATE_PUBLISH.value,
            AuditActionType.COP_UPDATE_OVERRIDE.value,
        ]

        match_stage = {
            "action_type": {"$in": facilitator_actions},
            "actor_role": {"$in": ["facilitator", "workspace_admin"]},
            "timestamp": {"$gte": start_date, "$lte": end_date},
        }

        # Add facilitator filter if specified
        if facilitator_id:
            match_stage["actor_id"] = facilitator_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": {
                        "time_bucket": {
                            "$dateToString": {
                                "format": date_format,
                                "date": "$timestamp",
                            }
                        },
                        "action_type": "$action_type",
                        "actor_id": "$actor_id",
                    },
                    "count": {"$sum": 1},
                }
            },
            {
                "$group": {
                    "_id": "$_id.time_bucket",
                    "total_actions": {"$sum": "$count"},
                    "by_action_type": {
                        "$push": {
                            "k": "$_id.action_type",
                            "v": "$count",
                        }
                    },
                    "by_facilitator": {
                        "$push": {
                            "k": "$_id.actor_id",
                            "v": "$count",
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]

        results = []
        async for doc in self.audit_log.aggregate(pipeline):
            bucket_timestamp = self._parse_bucket_timestamp(doc["_id"], granularity)

            # Convert to dicts and aggregate duplicate keys
            by_action_type = {}
            for item in doc.get("by_action_type", []):
                key = item["k"]
                by_action_type[key] = by_action_type.get(key, 0) + item["v"]

            by_facilitator = {}
            for item in doc.get("by_facilitator", []):
                key = item["k"]
                by_facilitator[key] = by_facilitator.get(key, 0) + item["v"]

            # Calculate action velocity (actions per hour)
            total_actions = doc["total_actions"]
            if granularity == Granularity.HOUR:
                velocity = float(total_actions)
            elif granularity == Granularity.DAY:
                velocity = total_actions / 24.0
            elif granularity == Granularity.WEEK:
                velocity = total_actions / (24.0 * 7.0)
            else:
                velocity = float(total_actions)

            results.append(
                FacilitatorActionDataPoint(
                    timestamp=bucket_timestamp,
                    total_actions=total_actions,
                    by_action_type=by_action_type,
                    by_facilitator=by_facilitator,
                    action_velocity=velocity,
                )
            )

        logger.info(
            "Computed facilitator actions time-series",
            workspace_id=workspace_id,
            facilitator_id=facilitator_id,
            data_points=len(results),
            granularity=granularity,
        )

        return results

    async def compute_time_series_analytics(
        self,
        request: TimeSeriesAnalyticsRequest,
    ) -> TimeSeriesAnalyticsResponse:
        """Compute comprehensive time-series analytics.

        Supports multiple metrics in a single query for efficiency.

        Args:
            request: Analytics request with parameters

        Returns:
            TimeSeriesAnalyticsResponse with requested metrics

        Raises:
            ValueError: If time range exceeds maximum
        """
        # Validate time range
        time_range = (request.end_date - request.start_date).days
        if time_range > self.max_time_range_days:
            raise ValueError(
                f"Time range ({time_range} days) exceeds maximum "
                f"({self.max_time_range_days} days)"
            )

        response = TimeSeriesAnalyticsResponse(
            workspace_id=request.workspace_id,
            start_date=request.start_date,
            end_date=request.end_date,
            granularity=request.granularity.value,
        )

        # Compute requested metrics
        from integritykit.models.analytics import MetricType

        if MetricType.SIGNAL_VOLUME in request.metrics:
            response.signal_volume = await self.compute_signal_volume_time_series(
                workspace_id=request.workspace_id,
                start_date=request.start_date,
                end_date=request.end_date,
                granularity=request.granularity,
            )

        if MetricType.READINESS_TRANSITIONS in request.metrics:
            response.readiness_transitions = (
                await self.compute_readiness_transitions_time_series(
                    workspace_id=request.workspace_id,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    granularity=request.granularity,
                )
            )

        if MetricType.FACILITATOR_ACTIONS in request.metrics:
            response.facilitator_actions = (
                await self.compute_facilitator_actions_time_series(
                    workspace_id=request.workspace_id,
                    start_date=request.start_date,
                    end_date=request.end_date,
                    granularity=request.granularity,
                    facilitator_id=request.facilitator_id,
                )
            )

        # Compute summary statistics
        summary = {
            "time_range_days": time_range,
            "granularity": request.granularity.value,
            "metrics_computed": [m.value for m in request.metrics],
        }

        if response.signal_volume:
            total_signals = sum(dp.signal_count for dp in response.signal_volume)
            summary["total_signals"] = total_signals
            summary["avg_signals_per_bucket"] = (
                total_signals / len(response.signal_volume)
                if response.signal_volume
                else 0
            )

        if response.readiness_transitions:
            total_transitions = sum(
                dp.total_transitions for dp in response.readiness_transitions
            )
            summary["total_readiness_transitions"] = total_transitions

        if response.facilitator_actions:
            total_actions = sum(
                dp.total_actions for dp in response.facilitator_actions
            )
            summary["total_facilitator_actions"] = total_actions
            summary["avg_action_velocity"] = (
                sum(dp.action_velocity for dp in response.facilitator_actions)
                / len(response.facilitator_actions)
                if response.facilitator_actions
                else 0
            )

        response.summary = summary

        logger.info(
            "Computed time-series analytics",
            workspace_id=request.workspace_id,
            metrics=request.metrics,
            time_range_days=time_range,
            granularity=request.granularity,
        )

        return response

    async def compute_topic_trends(
        self,
        workspace_id: str,
        start_date: datetime,
        end_date: datetime,
        min_signals: int = 5,
        direction_filter: str | None = None,
        topic_type_filter: str | None = None,
    ) -> TopicTrendsResponse:
        """Compute topic trend analysis using cluster data.

        Analyzes cluster data to identify emerging, declining, stable, new, and peaked topics.
        Uses volume changes over time to classify trend directions.

        Trend classification:
        - emerging: >20% increase in signal volume
        - declining: >20% decrease in signal volume
        - stable: within ±20% volume change
        - new: first appeared in time range
        - peaked: reached maximum volume and now declining

        Args:
            workspace_id: Slack workspace ID
            start_date: Start of analysis period
            end_date: End of analysis period
            min_signals: Minimum signal count for topic to be included (default: 5)
            direction_filter: Filter by trend direction (optional)
            topic_type_filter: Filter by topic type (optional)

        Returns:
            TopicTrendsResponse with detected trends and summary

        Raises:
            ValueError: If time range exceeds maximum
        """
        # Validate time range
        time_range = (end_date - start_date).days
        if time_range > self.max_time_range_days:
            raise ValueError(
                f"Time range ({time_range} days) exceeds maximum "
                f"({self.max_time_range_days} days)"
            )

        # Calculate period boundaries for comparison
        # Split time range into current and previous periods
        period_duration = end_date - start_date
        period_midpoint = start_date + (period_duration / 2)

        # Build aggregation pipeline to group signals by cluster and time period
        match_stage = {
            "slack_workspace_id": workspace_id,
            "created_at": {"$gte": start_date, "$lte": end_date},
        }

        # Get all clusters for this workspace with their signal counts over time
        pipeline = [
            {"$match": match_stage},
            # Lookup cluster information
            {
                "$lookup": {
                    "from": "clusters",
                    "localField": "cluster_id",
                    "foreignField": "_id",
                    "as": "cluster_info",
                }
            },
            {"$unwind": "$cluster_info"},
            # Group by cluster and time period (current vs previous half)
            {
                "$group": {
                    "_id": {
                        "cluster_id": "$cluster_info._id",
                        "topic": "$cluster_info.topic",
                        "topic_type": "$cluster_info.incident_type",
                        "period": {
                            "$cond": [
                                {"$lt": ["$created_at", period_midpoint]},
                                "previous",
                                "current",
                            ]
                        },
                    },
                    "signal_count": {"$sum": 1},
                    "first_seen": {"$min": "$created_at"},
                    "last_seen": {"$max": "$created_at"},
                    "keywords": {"$addToSet": "$cluster_info.topic"},
                }
            },
            # Group again by cluster to get both period counts
            {
                "$group": {
                    "_id": {
                        "cluster_id": "$_id.cluster_id",
                        "topic": "$_id.topic",
                        "topic_type": "$_id.topic_type",
                    },
                    "periods": {
                        "$push": {
                            "period": "$_id.period",
                            "count": "$signal_count",
                            "first_seen": "$first_seen",
                            "last_seen": "$last_seen",
                        }
                    },
                    "total_signals": {"$sum": "$signal_count"},
                    "keywords": {"$first": "$keywords"},
                }
            },
            # Filter by minimum signals
            {"$match": {"total_signals": {"$gte": min_signals}}},
            {"$sort": {"total_signals": -1}},
        ]

        trends: list[TopicTrend] = []
        peak_volumes: dict[str, tuple[datetime, int]] = {}

        # Execute aggregation
        async for doc in self.signals.aggregate(pipeline):
            cluster_id = str(doc["_id"]["cluster_id"])
            topic = doc["_id"]["topic"] or "Unknown Topic"
            topic_type = doc["_id"]["topic_type"] or "general"
            total_signals = doc["total_signals"]

            # Parse period data
            previous_count = 0
            current_count = 0
            first_seen = start_date
            last_seen = end_date

            for period_data in doc["periods"]:
                if period_data["period"] == "previous":
                    previous_count = period_data["count"]
                    first_seen = period_data["first_seen"]
                elif period_data["period"] == "current":
                    current_count = period_data["count"]
                    last_seen = period_data["last_seen"]

            # Calculate volume change percentage
            if previous_count > 0:
                volume_change_pct = (
                    (current_count - previous_count) / previous_count
                ) * 100
            elif current_count > 0:
                # New topic - no previous period data
                volume_change_pct = 100.0
            else:
                volume_change_pct = 0.0

            # Classify trend direction
            direction = self._classify_trend_direction(
                previous_count=previous_count,
                current_count=current_count,
                volume_change_pct=volume_change_pct,
                first_seen=first_seen,
                start_date=start_date,
            )

            # Calculate velocity score (0.0 - 1.0)
            velocity_score = min(abs(volume_change_pct) / 100.0, 1.0)

            # Determine peak time and volume by bucketing signals
            # For now, use the midpoint as peak if current > previous, otherwise use start
            peak_time = None
            peak_volume = max(previous_count, current_count)
            if current_count > previous_count:
                peak_time = period_midpoint
            elif previous_count > 0:
                peak_time = start_date

            # Apply filters
            if direction_filter and direction_filter != "all":
                if direction.value != direction_filter:
                    continue

            if topic_type_filter and topic_type != topic_type_filter:
                continue

            # Extract keywords from cluster topic
            keywords = [topic] + (doc.get("keywords", []))
            keywords = list(set(keywords))[:5]  # Limit to 5 unique keywords

            trend = TopicTrend(
                topic=topic,
                topic_type=topic_type,
                direction=direction,
                signal_count=total_signals,
                volume_change_pct=round(volume_change_pct, 2),
                first_seen=first_seen,
                peak_time=peak_time,
                peak_volume=peak_volume,
                keywords=keywords,
                related_clusters=[cluster_id],
                velocity_score=round(velocity_score, 3),
            )

            trends.append(trend)

        # Calculate summary statistics
        summary = {
            "total_topics": len(trends),
            "emerging_count": sum(
                1 for t in trends if t.direction == TrendDirection.EMERGING
            ),
            "declining_count": sum(
                1 for t in trends if t.direction == TrendDirection.DECLINING
            ),
            "stable_count": sum(
                1 for t in trends if t.direction == TrendDirection.STABLE
            ),
            "new_topics_count": sum(
                1 for t in trends if t.direction == TrendDirection.NEW
            ),
            "peaked_count": sum(
                1 for t in trends if t.direction == TrendDirection.PEAKED
            ),
        }

        if trends:
            most_active = max(trends, key=lambda t: t.signal_count)
            summary["most_active_topic"] = most_active.topic
            summary["most_active_signal_count"] = most_active.signal_count

        logger.info(
            "Computed topic trends",
            workspace_id=workspace_id,
            trends_count=len(trends),
            emerging=summary["emerging_count"],
            declining=summary["declining_count"],
            new=summary["new_topics_count"],
        )

        return TopicTrendsResponse(
            workspace_id=workspace_id,
            start_date=start_date,
            end_date=end_date,
            trends=trends,
            summary=summary,
        )

    def _classify_trend_direction(
        self,
        previous_count: int,
        current_count: int,
        volume_change_pct: float,
        first_seen: datetime,
        start_date: datetime,
    ) -> TrendDirection:
        """Classify trend direction based on volume changes.

        Args:
            previous_count: Signal count in previous period
            current_count: Signal count in current period
            volume_change_pct: Percentage change in volume
            first_seen: First signal timestamp
            start_date: Analysis start date

        Returns:
            TrendDirection classification
        """
        # New topic - first appeared in time range
        if previous_count == 0 and current_count > 0:
            return TrendDirection.NEW

        # Peaked - had activity before, declining now
        if previous_count > current_count and previous_count > 0:
            # If significant decline, mark as peaked
            if volume_change_pct < -20:
                return TrendDirection.PEAKED
            # Minor decline, still stable
            return TrendDirection.STABLE

        # Emerging - significant increase
        if volume_change_pct > 20:
            return TrendDirection.EMERGING

        # Declining - significant decrease
        if volume_change_pct < -20:
            return TrendDirection.DECLINING

        # Stable - within ±20%
        return TrendDirection.STABLE


# Global service instance
_analytics_service: Optional[AnalyticsService] = None


def get_analytics_service(
    max_time_range_days: int = 90,
    retention_days: int = 365,
) -> AnalyticsService:
    """Get the global analytics service instance.

    Args:
        max_time_range_days: Maximum time range for queries
        retention_days: Analytics data retention period

    Returns:
        AnalyticsService singleton
    """
    global _analytics_service
    if _analytics_service is None:
        _analytics_service = AnalyticsService(
            max_time_range_days=max_time_range_days,
            retention_days=retention_days,
        )
    return _analytics_service


async def get_analytics_service_dependency() -> AnalyticsService:
    """Get analytics service instance (for FastAPI dependency injection).

    Returns:
        AnalyticsService instance
    """
    from integritykit.config import settings

    max_range = getattr(settings, "max_analytics_time_range_days", 90)
    retention = getattr(settings, "analytics_retention_days", 365)

    return AnalyticsService(
        max_time_range_days=max_range,
        retention_days=retention,
    )
