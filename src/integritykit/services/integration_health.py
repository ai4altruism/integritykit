"""Integration health monitoring service.

Implements:
- Task S8-22: Integration health monitoring dashboard
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.integration_health import (
    ExportHealthMetrics,
    ExternalSourceHealthMetrics,
    HealthStatus,
    IntegrationHealth,
    IntegrationHealthDashboard,
    IntegrationType,
    WebhookHealthMetrics,
)
from integritykit.models.webhook import WebhookStatus
from integritykit.services.database import get_collection

logger = logging.getLogger(__name__)


# Thresholds for health status determination
SUCCESS_RATE_HEALTHY = 0.95  # 95% success rate = healthy
SUCCESS_RATE_DEGRADED = 0.80  # 80% success rate = degraded, below = unhealthy
SYNC_OVERDUE_HOURS = 2  # Hours before a sync is considered overdue


class IntegrationHealthService:
    """Service for monitoring integration health."""

    def __init__(
        self,
        webhooks_collection: Optional[AsyncIOMotorCollection] = None,
        deliveries_collection: Optional[AsyncIOMotorCollection] = None,
        sources_collection: Optional[AsyncIOMotorCollection] = None,
        imports_collection: Optional[AsyncIOMotorCollection] = None,
        exports_collection: Optional[AsyncIOMotorCollection] = None,
    ):
        """Initialize health monitoring service.

        Args:
            webhooks_collection: MongoDB collection for webhooks
            deliveries_collection: MongoDB collection for webhook deliveries
            sources_collection: MongoDB collection for external sources
            imports_collection: MongoDB collection for source imports
            exports_collection: MongoDB collection for export logs
        """
        self.webhooks = webhooks_collection or get_collection("webhooks")
        self.deliveries = deliveries_collection or get_collection("webhook_deliveries")
        self.sources = sources_collection or get_collection("external_sources")
        self.imports = imports_collection or get_collection("external_source_imports")
        self.exports = exports_collection or get_collection("export_logs")

    async def get_health_dashboard(
        self,
        workspace_id: str,
    ) -> IntegrationHealthDashboard:
        """Get complete health dashboard for a workspace.

        Args:
            workspace_id: Workspace ID

        Returns:
            Complete health dashboard with all integration statuses
        """
        dashboard = IntegrationHealthDashboard(workspace_id=workspace_id)

        # Gather health for each integration type
        dashboard.webhooks = await self._get_webhook_health(workspace_id)
        dashboard.external_sources = await self._get_external_source_health(workspace_id)
        dashboard.cap_export = await self._get_export_health(workspace_id, "cap")
        dashboard.edxl_export = await self._get_export_health(workspace_id, "edxl")
        dashboard.geojson_export = await self._get_export_health(workspace_id, "geojson")

        # Compute overall status
        dashboard.compute_overall_status()

        # Generate alerts and recommendations
        dashboard.alerts = self._generate_alerts(dashboard)
        dashboard.recommendations = self._generate_recommendations(dashboard)

        logger.info(
            "Generated health dashboard",
            extra={
                "workspace_id": workspace_id,
                "overall_status": dashboard.overall_status.value,
                "alerts_count": len(dashboard.alerts),
            },
        )

        return dashboard

    async def _get_webhook_health(
        self,
        workspace_id: str,
    ) -> IntegrationHealth:
        """Get webhook integration health.

        Args:
            workspace_id: Workspace ID

        Returns:
            Webhook health status and metrics
        """
        now = datetime.utcnow()
        yesterday = now - timedelta(hours=24)

        # Get webhook counts
        total_webhooks = await self.webhooks.count_documents(
            {"workspace_id": workspace_id}
        )
        active_webhooks = await self.webhooks.count_documents(
            {"workspace_id": workspace_id, "enabled": True}
        )

        if total_webhooks == 0:
            return IntegrationHealth(
                integration_type=IntegrationType.WEBHOOKS,
                status=HealthStatus.UNKNOWN,
                status_message="No webhooks configured",
                metrics=WebhookHealthMetrics().model_dump(),
            )

        # Get delivery stats for last 24 hours
        pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "created_at": {"$gte": yesterday},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "successful": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", WebhookStatus.SUCCESS.value]},
                                1,
                                0,
                            ]
                        }
                    },
                    "failed": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", WebhookStatus.FAILED.value]},
                                1,
                                0,
                            ]
                        }
                    },
                    "avg_latency": {"$avg": "$latency_ms"},
                    "last_delivery": {"$max": "$created_at"},
                }
            },
        ]

        stats = await self.deliveries.aggregate(pipeline).to_list(1)
        stats = stats[0] if stats else {}

        total_deliveries = stats.get("total", 0)
        successful = stats.get("successful", 0)
        failed = stats.get("failed", 0)
        success_rate = successful / total_deliveries if total_deliveries > 0 else 1.0
        avg_latency = stats.get("avg_latency", 0) or 0

        # Get webhooks with recent failures
        failed_webhooks_pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "created_at": {"$gte": yesterday},
                    "status": WebhookStatus.FAILED.value,
                }
            },
            {"$group": {"_id": "$webhook_id"}},
            {"$limit": 10},
        ]
        failed_webhook_docs = await self.deliveries.aggregate(
            failed_webhooks_pipeline
        ).to_list(10)
        webhooks_with_failures = [str(doc["_id"]) for doc in failed_webhook_docs]

        # Determine health status
        if total_deliveries == 0:
            status = HealthStatus.HEALTHY
            status_message = "No deliveries in last 24h"
        elif success_rate >= SUCCESS_RATE_HEALTHY:
            status = HealthStatus.HEALTHY
            status_message = f"{success_rate:.1%} success rate"
        elif success_rate >= SUCCESS_RATE_DEGRADED:
            status = HealthStatus.DEGRADED
            status_message = f"{success_rate:.1%} success rate - some failures"
        else:
            status = HealthStatus.UNHEALTHY
            status_message = f"{success_rate:.1%} success rate - critical failure rate"

        metrics = WebhookHealthMetrics(
            total_webhooks=total_webhooks,
            active_webhooks=active_webhooks,
            deliveries_24h=total_deliveries,
            successful_24h=successful,
            failed_24h=failed,
            success_rate_24h=success_rate,
            avg_latency_ms=avg_latency,
            last_delivery_at=stats.get("last_delivery"),
            webhooks_with_failures=webhooks_with_failures,
        )

        return IntegrationHealth(
            integration_type=IntegrationType.WEBHOOKS,
            status=status,
            status_message=status_message,
            metrics=metrics.model_dump(),
        )

    async def _get_external_source_health(
        self,
        workspace_id: str,
    ) -> IntegrationHealth:
        """Get external source integration health.

        Args:
            workspace_id: Workspace ID

        Returns:
            External source health status and metrics
        """
        now = datetime.utcnow()
        yesterday = now - timedelta(hours=24)

        # Get source counts
        total_sources = await self.sources.count_documents(
            {"workspace_id": workspace_id}
        )
        active_sources = await self.sources.count_documents(
            {"workspace_id": workspace_id, "enabled": True}
        )

        if total_sources == 0:
            return IntegrationHealth(
                integration_type=IntegrationType.EXTERNAL_SOURCES,
                status=HealthStatus.UNKNOWN,
                status_message="No external sources configured",
                metrics=ExternalSourceHealthMetrics().model_dump(),
            )

        # Get import stats for last 24 hours
        pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "started_at": {"$gte": yesterday},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "successful": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "completed"]}, 1, 0]
                        }
                    },
                    "failed": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "failed"]}, 1, 0]
                        }
                    },
                    "items_imported": {"$sum": "$items_imported"},
                    "last_sync": {"$max": "$started_at"},
                }
            },
        ]

        stats = await self.imports.aggregate(pipeline).to_list(1)
        stats = stats[0] if stats else {}

        total_syncs = stats.get("total", 0)
        successful = stats.get("successful", 0)
        failed = stats.get("failed", 0)
        success_rate = successful / total_syncs if total_syncs > 0 else 1.0
        items_imported = stats.get("items_imported", 0)

        # Get sources with recent failures
        failed_sources_pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "started_at": {"$gte": yesterday},
                    "status": "failed",
                }
            },
            {"$group": {"_id": "$source_id"}},
            {"$limit": 10},
        ]
        failed_source_docs = await self.imports.aggregate(
            failed_sources_pipeline
        ).to_list(10)
        sources_with_failures = [str(doc["_id"]) for doc in failed_source_docs]

        # Check for overdue syncs
        overdue_threshold = now - timedelta(hours=SYNC_OVERDUE_HOURS)
        overdue_cursor = self.sources.find(
            {
                "workspace_id": workspace_id,
                "enabled": True,
                "$or": [
                    {"statistics.last_sync_at": {"$lt": overdue_threshold}},
                    {"statistics.last_sync_at": None},
                ],
            },
            {"_id": 1},
        ).limit(10)
        overdue_docs = await overdue_cursor.to_list(10)
        overdue_syncs = [str(doc["_id"]) for doc in overdue_docs]

        # Determine health status
        if total_syncs == 0 and not overdue_syncs:
            status = HealthStatus.HEALTHY
            status_message = "No syncs in last 24h"
        elif overdue_syncs:
            status = HealthStatus.DEGRADED
            status_message = f"{len(overdue_syncs)} source(s) overdue for sync"
        elif success_rate >= SUCCESS_RATE_HEALTHY:
            status = HealthStatus.HEALTHY
            status_message = f"{success_rate:.1%} sync success rate"
        elif success_rate >= SUCCESS_RATE_DEGRADED:
            status = HealthStatus.DEGRADED
            status_message = f"{success_rate:.1%} sync success rate"
        else:
            status = HealthStatus.UNHEALTHY
            status_message = f"{success_rate:.1%} sync success rate - critical"

        metrics = ExternalSourceHealthMetrics(
            total_sources=total_sources,
            active_sources=active_sources,
            syncs_24h=total_syncs,
            successful_syncs_24h=successful,
            failed_syncs_24h=failed,
            success_rate_24h=success_rate,
            items_imported_24h=items_imported,
            last_sync_at=stats.get("last_sync"),
            sources_with_failures=sources_with_failures,
            overdue_syncs=overdue_syncs,
        )

        return IntegrationHealth(
            integration_type=IntegrationType.EXTERNAL_SOURCES,
            status=status,
            status_message=status_message,
            metrics=metrics.model_dump(),
        )

    async def _get_export_health(
        self,
        workspace_id: str,
        export_type: str,
    ) -> IntegrationHealth:
        """Get export integration health (CAP, EDXL, GeoJSON).

        Args:
            workspace_id: Workspace ID
            export_type: Type of export (cap, edxl, geojson)

        Returns:
            Export health status and metrics
        """
        now = datetime.utcnow()
        yesterday = now - timedelta(hours=24)

        integration_type_map = {
            "cap": IntegrationType.CAP_EXPORT,
            "edxl": IntegrationType.EDXL_EXPORT,
            "geojson": IntegrationType.GEOJSON_EXPORT,
        }
        integration_type = integration_type_map.get(
            export_type, IntegrationType.CAP_EXPORT
        )

        # Get export stats for last 24 hours
        pipeline = [
            {
                "$match": {
                    "workspace_id": workspace_id,
                    "export_type": export_type,
                    "created_at": {"$gte": yesterday},
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "successful": {
                        "$sum": {"$cond": [{"$eq": ["$status", "success"]}, 1, 0]}
                    },
                    "failed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}
                    },
                    "avg_time": {"$avg": "$export_time_ms"},
                    "last_export": {"$max": "$created_at"},
                }
            },
        ]

        stats = await self.exports.aggregate(pipeline).to_list(1)
        stats = stats[0] if stats else {}

        total_exports = stats.get("total", 0)
        successful = stats.get("successful", 0)
        failed = stats.get("failed", 0)
        success_rate = successful / total_exports if total_exports > 0 else 1.0
        avg_time = stats.get("avg_time", 0) or 0

        # Determine health status
        if total_exports == 0:
            status = HealthStatus.UNKNOWN
            status_message = f"No {export_type.upper()} exports in last 24h"
        elif success_rate >= SUCCESS_RATE_HEALTHY:
            status = HealthStatus.HEALTHY
            status_message = f"{total_exports} exports, {success_rate:.1%} success"
        elif success_rate >= SUCCESS_RATE_DEGRADED:
            status = HealthStatus.DEGRADED
            status_message = f"{failed} export(s) failed"
        else:
            status = HealthStatus.UNHEALTHY
            status_message = f"High export failure rate: {failed}/{total_exports}"

        metrics = ExportHealthMetrics(
            exports_24h=total_exports,
            successful_24h=successful,
            failed_24h=failed,
            success_rate_24h=success_rate,
            last_export_at=stats.get("last_export"),
            avg_export_time_ms=avg_time,
        )

        return IntegrationHealth(
            integration_type=integration_type,
            status=status,
            status_message=status_message,
            metrics=metrics.model_dump(),
        )

    def _generate_alerts(
        self,
        dashboard: IntegrationHealthDashboard,
    ) -> list[str]:
        """Generate alerts from health dashboard.

        Args:
            dashboard: Health dashboard

        Returns:
            List of alert messages
        """
        alerts = []

        # Check webhooks
        if dashboard.webhooks and dashboard.webhooks.status == HealthStatus.UNHEALTHY:
            metrics = WebhookHealthMetrics(**dashboard.webhooks.metrics)
            alerts.append(
                f"Webhook delivery failure rate critical: {metrics.failed_24h} failures in 24h"
            )
            if metrics.webhooks_with_failures:
                alerts.append(
                    f"Webhooks with failures: {', '.join(metrics.webhooks_with_failures[:3])}"
                )

        # Check external sources
        if dashboard.external_sources:
            if dashboard.external_sources.status == HealthStatus.UNHEALTHY:
                metrics = ExternalSourceHealthMetrics(**dashboard.external_sources.metrics)
                alerts.append(
                    f"External source sync failure rate critical: {metrics.failed_syncs_24h} failures"
                )
            elif dashboard.external_sources.status == HealthStatus.DEGRADED:
                metrics = ExternalSourceHealthMetrics(**dashboard.external_sources.metrics)
                if metrics.overdue_syncs:
                    alerts.append(
                        f"{len(metrics.overdue_syncs)} external source(s) overdue for sync"
                    )

        # Check exports
        for export_health in [
            dashboard.cap_export,
            dashboard.edxl_export,
            dashboard.geojson_export,
        ]:
            if export_health and export_health.status == HealthStatus.UNHEALTHY:
                metrics = ExportHealthMetrics(**export_health.metrics)
                alerts.append(
                    f"{export_health.integration_type.value} exports failing: "
                    f"{metrics.failed_24h}/{metrics.exports_24h}"
                )

        return alerts

    def _generate_recommendations(
        self,
        dashboard: IntegrationHealthDashboard,
    ) -> list[str]:
        """Generate recommendations from health dashboard.

        Args:
            dashboard: Health dashboard

        Returns:
            List of recommendation messages
        """
        recommendations = []

        # Webhook recommendations
        if dashboard.webhooks:
            metrics = WebhookHealthMetrics(**dashboard.webhooks.metrics)
            if metrics.total_webhooks == 0:
                recommendations.append(
                    "Configure webhooks to enable real-time notifications to external systems"
                )
            elif metrics.active_webhooks == 0:
                recommendations.append(
                    "Enable at least one webhook to receive event notifications"
                )
            elif metrics.webhooks_with_failures:
                recommendations.append(
                    "Review webhook endpoints for failing webhooks and check connectivity"
                )

        # External source recommendations
        if dashboard.external_sources:
            metrics = ExternalSourceHealthMetrics(**dashboard.external_sources.metrics)
            if metrics.total_sources == 0:
                recommendations.append(
                    "Configure external verification sources to import pre-verified data"
                )
            elif metrics.overdue_syncs:
                recommendations.append(
                    "Check network connectivity and API credentials for overdue sources"
                )
            elif metrics.sources_with_failures:
                recommendations.append(
                    "Review API endpoint configurations for failing external sources"
                )

        # Export recommendations
        export_healths = [
            dashboard.cap_export,
            dashboard.edxl_export,
            dashboard.geojson_export,
        ]
        failed_exports = [e for e in export_healths if e and e.status == HealthStatus.UNHEALTHY]
        if failed_exports:
            recommendations.append(
                "Review export configurations and data format compliance"
            )

        return recommendations

    async def get_integration_summary(
        self,
        workspace_id: str,
    ) -> dict[str, Any]:
        """Get a quick summary of integration health.

        Args:
            workspace_id: Workspace ID

        Returns:
            Summary dict with counts and status
        """
        dashboard = await self.get_health_dashboard(workspace_id)

        return {
            "workspace_id": workspace_id,
            "overall_status": dashboard.overall_status.value,
            "overall_message": dashboard.overall_message,
            "integrations": {
                "webhooks": {
                    "status": dashboard.webhooks.status.value if dashboard.webhooks else "unknown",
                    "message": dashboard.webhooks.status_message if dashboard.webhooks else "",
                },
                "external_sources": {
                    "status": dashboard.external_sources.status.value if dashboard.external_sources else "unknown",
                    "message": dashboard.external_sources.status_message if dashboard.external_sources else "",
                },
                "cap_export": {
                    "status": dashboard.cap_export.status.value if dashboard.cap_export else "unknown",
                    "message": dashboard.cap_export.status_message if dashboard.cap_export else "",
                },
                "edxl_export": {
                    "status": dashboard.edxl_export.status.value if dashboard.edxl_export else "unknown",
                    "message": dashboard.edxl_export.status_message if dashboard.edxl_export else "",
                },
                "geojson_export": {
                    "status": dashboard.geojson_export.status.value if dashboard.geojson_export else "unknown",
                    "message": dashboard.geojson_export.status_message if dashboard.geojson_export else "",
                },
            },
            "alerts_count": len(dashboard.alerts),
            "generated_at": dashboard.generated_at.isoformat(),
        }
