"""Integration health monitoring models.

Implements:
- Task S8-22: Integration health monitoring dashboard
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class HealthStatus(str, Enum):
    """Health status for an integration."""

    HEALTHY = "healthy"  # All systems operational
    DEGRADED = "degraded"  # Some issues but functional
    UNHEALTHY = "unhealthy"  # Critical issues
    UNKNOWN = "unknown"  # No data available


class IntegrationType(str, Enum):
    """Types of integrations to monitor."""

    WEBHOOKS = "webhooks"
    EXTERNAL_SOURCES = "external_sources"
    CAP_EXPORT = "cap_export"
    EDXL_EXPORT = "edxl_export"
    GEOJSON_EXPORT = "geojson_export"


class WebhookHealthMetrics(BaseModel):
    """Health metrics for webhook integrations."""

    total_webhooks: int = Field(default=0, description="Total configured webhooks")
    active_webhooks: int = Field(default=0, description="Active (enabled) webhooks")
    deliveries_24h: int = Field(default=0, description="Deliveries in last 24 hours")
    successful_24h: int = Field(default=0, description="Successful deliveries in last 24h")
    failed_24h: int = Field(default=0, description="Failed deliveries in last 24h")
    success_rate_24h: float = Field(default=0.0, description="Success rate (0-1) in last 24h")
    avg_latency_ms: float = Field(default=0.0, description="Average delivery latency in ms")
    last_delivery_at: Optional[datetime] = Field(default=None, description="Last delivery timestamp")
    webhooks_with_failures: list[str] = Field(
        default_factory=list,
        description="Webhook IDs with recent failures",
    )


class ExternalSourceHealthMetrics(BaseModel):
    """Health metrics for external source integrations."""

    total_sources: int = Field(default=0, description="Total configured sources")
    active_sources: int = Field(default=0, description="Active (enabled) sources")
    syncs_24h: int = Field(default=0, description="Sync attempts in last 24 hours")
    successful_syncs_24h: int = Field(default=0, description="Successful syncs in last 24h")
    failed_syncs_24h: int = Field(default=0, description="Failed syncs in last 24h")
    success_rate_24h: float = Field(default=0.0, description="Success rate (0-1) in last 24h")
    items_imported_24h: int = Field(default=0, description="Items imported in last 24h")
    last_sync_at: Optional[datetime] = Field(default=None, description="Last sync timestamp")
    sources_with_failures: list[str] = Field(
        default_factory=list,
        description="Source IDs with recent failures",
    )
    overdue_syncs: list[str] = Field(
        default_factory=list,
        description="Source IDs overdue for sync",
    )


class ExportHealthMetrics(BaseModel):
    """Health metrics for export integrations (CAP, EDXL, GeoJSON)."""

    exports_24h: int = Field(default=0, description="Exports in last 24 hours")
    successful_24h: int = Field(default=0, description="Successful exports in last 24h")
    failed_24h: int = Field(default=0, description="Failed exports in last 24h")
    success_rate_24h: float = Field(default=0.0, description="Success rate (0-1) in last 24h")
    last_export_at: Optional[datetime] = Field(default=None, description="Last export timestamp")
    avg_export_time_ms: float = Field(default=0.0, description="Average export time in ms")


class IntegrationHealth(BaseModel):
    """Health status for a single integration type."""

    integration_type: IntegrationType = Field(..., description="Type of integration")
    status: HealthStatus = Field(default=HealthStatus.UNKNOWN, description="Overall health status")
    status_message: str = Field(default="", description="Human-readable status message")
    last_checked_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When health was last checked",
    )
    metrics: dict[str, Any] = Field(
        default_factory=dict,
        description="Integration-specific metrics",
    )


class IntegrationHealthDashboard(BaseModel):
    """Complete integration health dashboard."""

    workspace_id: str = Field(..., description="Workspace ID")
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When dashboard was generated",
    )
    overall_status: HealthStatus = Field(
        default=HealthStatus.UNKNOWN,
        description="Overall system health",
    )
    overall_message: str = Field(default="", description="Overall status message")

    # Individual integration health
    webhooks: Optional[IntegrationHealth] = Field(
        default=None,
        description="Webhook integration health",
    )
    external_sources: Optional[IntegrationHealth] = Field(
        default=None,
        description="External sources health",
    )
    cap_export: Optional[IntegrationHealth] = Field(
        default=None,
        description="CAP export health",
    )
    edxl_export: Optional[IntegrationHealth] = Field(
        default=None,
        description="EDXL-DE export health",
    )
    geojson_export: Optional[IntegrationHealth] = Field(
        default=None,
        description="GeoJSON export health",
    )

    # Alerts and recommendations
    alerts: list[str] = Field(
        default_factory=list,
        description="Active alerts requiring attention",
    )
    recommendations: list[str] = Field(
        default_factory=list,
        description="Recommendations for improving health",
    )

    def compute_overall_status(self) -> None:
        """Compute overall status from individual integration statuses."""
        statuses = []
        for integration in [
            self.webhooks,
            self.external_sources,
            self.cap_export,
            self.edxl_export,
            self.geojson_export,
        ]:
            if integration:
                statuses.append(integration.status)

        if not statuses:
            self.overall_status = HealthStatus.UNKNOWN
            self.overall_message = "No integrations configured"
            return

        if HealthStatus.UNHEALTHY in statuses:
            self.overall_status = HealthStatus.UNHEALTHY
            unhealthy_count = statuses.count(HealthStatus.UNHEALTHY)
            self.overall_message = f"{unhealthy_count} integration(s) unhealthy"
        elif HealthStatus.DEGRADED in statuses:
            self.overall_status = HealthStatus.DEGRADED
            degraded_count = statuses.count(HealthStatus.DEGRADED)
            self.overall_message = f"{degraded_count} integration(s) degraded"
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            self.overall_status = HealthStatus.HEALTHY
            self.overall_message = "All integrations healthy"
        else:
            self.overall_status = HealthStatus.UNKNOWN
            self.overall_message = "Some integrations have unknown status"
