"""Unit tests for integration health monitoring service.

Tests:
- Task S8-22: Integration health monitoring dashboard
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from integritykit.models.integration_health import (
    ExportHealthMetrics,
    ExternalSourceHealthMetrics,
    HealthStatus,
    IntegrationHealthDashboard,
    IntegrationType,
    WebhookHealthMetrics,
)
from integritykit.services.integration_health import IntegrationHealthService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_collections():
    """Create mock MongoDB collections."""
    return {
        "webhooks": AsyncMock(),
        "deliveries": AsyncMock(),
        "sources": AsyncMock(),
        "imports": AsyncMock(),
        "exports": AsyncMock(),
    }


@pytest.fixture
def health_service(mock_collections):
    """Create health service with mock collections."""
    return IntegrationHealthService(
        webhooks_collection=mock_collections["webhooks"],
        deliveries_collection=mock_collections["deliveries"],
        sources_collection=mock_collections["sources"],
        imports_collection=mock_collections["imports"],
        exports_collection=mock_collections["exports"],
    )


# ============================================================================
# Model Tests
# ============================================================================


class TestIntegrationHealthDashboard:
    """Tests for IntegrationHealthDashboard model."""

    def test_compute_overall_status_all_healthy(self):
        """Overall status is healthy when all integrations are healthy."""
        from integritykit.models.integration_health import IntegrationHealth

        dashboard = IntegrationHealthDashboard(workspace_id="W123")
        dashboard.webhooks = IntegrationHealth(
            integration_type=IntegrationType.WEBHOOKS,
            status=HealthStatus.HEALTHY,
        )
        dashboard.external_sources = IntegrationHealth(
            integration_type=IntegrationType.EXTERNAL_SOURCES,
            status=HealthStatus.HEALTHY,
        )

        dashboard.compute_overall_status()

        assert dashboard.overall_status == HealthStatus.HEALTHY
        assert "healthy" in dashboard.overall_message.lower()

    def test_compute_overall_status_one_unhealthy(self):
        """Overall status is unhealthy when any integration is unhealthy."""
        from integritykit.models.integration_health import IntegrationHealth

        dashboard = IntegrationHealthDashboard(workspace_id="W123")
        dashboard.webhooks = IntegrationHealth(
            integration_type=IntegrationType.WEBHOOKS,
            status=HealthStatus.HEALTHY,
        )
        dashboard.external_sources = IntegrationHealth(
            integration_type=IntegrationType.EXTERNAL_SOURCES,
            status=HealthStatus.UNHEALTHY,
        )

        dashboard.compute_overall_status()

        assert dashboard.overall_status == HealthStatus.UNHEALTHY
        assert "unhealthy" in dashboard.overall_message.lower()

    def test_compute_overall_status_degraded(self):
        """Overall status is degraded when any integration is degraded."""
        from integritykit.models.integration_health import IntegrationHealth

        dashboard = IntegrationHealthDashboard(workspace_id="W123")
        dashboard.webhooks = IntegrationHealth(
            integration_type=IntegrationType.WEBHOOKS,
            status=HealthStatus.HEALTHY,
        )
        dashboard.external_sources = IntegrationHealth(
            integration_type=IntegrationType.EXTERNAL_SOURCES,
            status=HealthStatus.DEGRADED,
        )

        dashboard.compute_overall_status()

        assert dashboard.overall_status == HealthStatus.DEGRADED
        assert "degraded" in dashboard.overall_message.lower()

    def test_compute_overall_status_no_integrations(self):
        """Overall status is unknown when no integrations configured."""
        dashboard = IntegrationHealthDashboard(workspace_id="W123")

        dashboard.compute_overall_status()

        assert dashboard.overall_status == HealthStatus.UNKNOWN


# ============================================================================
# Webhook Health Tests
# ============================================================================


@pytest.mark.asyncio
class TestWebhookHealth:
    """Tests for webhook health monitoring."""

    async def test_no_webhooks_configured(self, health_service, mock_collections):
        """Unknown status when no webhooks configured."""
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=0)

        health = await health_service._get_webhook_health("W123")

        assert health.status == HealthStatus.UNKNOWN
        assert "no webhooks" in health.status_message.lower()

    async def test_healthy_webhooks(self, health_service, mock_collections):
        """Healthy status with high success rate."""
        mock_collections["webhooks"].count_documents = AsyncMock(
            side_effect=[5, 4]  # total=5, active=4
        )

        # Mock delivery stats
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 100,
                    "successful": 98,
                    "failed": 2,
                    "avg_latency": 150.5,
                    "last_delivery": datetime.utcnow(),
                }
            ]
        )
        mock_collections["deliveries"].aggregate = MagicMock(return_value=mock_cursor)

        # Mock no failed webhooks
        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(return_value=[])
        mock_collections["deliveries"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        health = await health_service._get_webhook_health("W123")

        assert health.status == HealthStatus.HEALTHY
        assert health.integration_type == IntegrationType.WEBHOOKS
        metrics = WebhookHealthMetrics(**health.metrics)
        assert metrics.total_webhooks == 5
        assert metrics.active_webhooks == 4
        assert metrics.success_rate_24h >= 0.95

    async def test_degraded_webhooks(self, health_service, mock_collections):
        """Degraded status with moderate failure rate."""
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=3)

        # Mock delivery stats with 85% success rate
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 100,
                    "successful": 85,
                    "failed": 15,
                    "avg_latency": 200.0,
                    "last_delivery": datetime.utcnow(),
                }
            ]
        )

        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(
            return_value=[{"_id": ObjectId()}]
        )

        mock_collections["deliveries"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        health = await health_service._get_webhook_health("W123")

        assert health.status == HealthStatus.DEGRADED
        metrics = WebhookHealthMetrics(**health.metrics)
        assert 0.80 <= metrics.success_rate_24h < 0.95

    async def test_unhealthy_webhooks(self, health_service, mock_collections):
        """Unhealthy status with high failure rate."""
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=2)

        # Mock delivery stats with 70% success rate (below threshold)
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 100,
                    "successful": 70,
                    "failed": 30,
                    "avg_latency": 500.0,
                    "last_delivery": datetime.utcnow(),
                }
            ]
        )

        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(
            return_value=[{"_id": ObjectId()}, {"_id": ObjectId()}]
        )

        mock_collections["deliveries"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        health = await health_service._get_webhook_health("W123")

        assert health.status == HealthStatus.UNHEALTHY
        metrics = WebhookHealthMetrics(**health.metrics)
        assert metrics.success_rate_24h < 0.80


# ============================================================================
# External Source Health Tests
# ============================================================================


@pytest.mark.asyncio
class TestExternalSourceHealth:
    """Tests for external source health monitoring."""

    async def test_no_sources_configured(self, health_service, mock_collections):
        """Unknown status when no sources configured."""
        mock_collections["sources"].count_documents = AsyncMock(return_value=0)

        health = await health_service._get_external_source_health("W123")

        assert health.status == HealthStatus.UNKNOWN
        assert "no external sources" in health.status_message.lower()

    async def test_healthy_sources(self, health_service, mock_collections):
        """Healthy status with high sync success rate."""
        mock_collections["sources"].count_documents = AsyncMock(
            side_effect=[3, 3]  # total=3, active=3
        )

        # Mock import stats
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 20,
                    "successful": 19,
                    "failed": 1,
                    "items_imported": 150,
                    "last_sync": datetime.utcnow(),
                }
            ]
        )

        # Mock no failed sources
        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(return_value=[])

        mock_collections["imports"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        # Mock no overdue syncs
        mock_overdue = AsyncMock()
        mock_overdue.limit = MagicMock(return_value=mock_overdue)
        mock_overdue.to_list = AsyncMock(return_value=[])
        mock_collections["sources"].find = MagicMock(return_value=mock_overdue)

        health = await health_service._get_external_source_health("W123")

        assert health.status == HealthStatus.HEALTHY
        metrics = ExternalSourceHealthMetrics(**health.metrics)
        assert metrics.success_rate_24h >= 0.95

    async def test_degraded_sources_overdue(self, health_service, mock_collections):
        """Degraded status when sources are overdue for sync."""
        mock_collections["sources"].count_documents = AsyncMock(
            side_effect=[2, 2]
        )

        # Mock import stats (good success rate)
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 10,
                    "successful": 10,
                    "failed": 0,
                    "items_imported": 50,
                    "last_sync": datetime.utcnow() - timedelta(hours=3),
                }
            ]
        )

        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(return_value=[])

        mock_collections["imports"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        # Mock overdue sync
        mock_overdue = AsyncMock()
        mock_overdue.limit = MagicMock(return_value=mock_overdue)
        mock_overdue.to_list = AsyncMock(return_value=[{"_id": ObjectId()}])
        mock_collections["sources"].find = MagicMock(return_value=mock_overdue)

        health = await health_service._get_external_source_health("W123")

        assert health.status == HealthStatus.DEGRADED
        assert "overdue" in health.status_message.lower()


# ============================================================================
# Export Health Tests
# ============================================================================


@pytest.mark.asyncio
class TestExportHealth:
    """Tests for export health monitoring."""

    async def test_no_exports(self, health_service, mock_collections):
        """Unknown status when no exports in timeframe."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collections["exports"].aggregate = MagicMock(return_value=mock_cursor)

        health = await health_service._get_export_health("W123", "cap")

        assert health.status == HealthStatus.UNKNOWN
        assert "no cap exports" in health.status_message.lower()

    async def test_healthy_exports(self, health_service, mock_collections):
        """Healthy status with high export success rate."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 50,
                    "successful": 49,
                    "failed": 1,
                    "avg_time": 120.5,
                    "last_export": datetime.utcnow(),
                }
            ]
        )
        mock_collections["exports"].aggregate = MagicMock(return_value=mock_cursor)

        health = await health_service._get_export_health("W123", "geojson")

        assert health.status == HealthStatus.HEALTHY
        assert health.integration_type == IntegrationType.GEOJSON_EXPORT
        metrics = ExportHealthMetrics(**health.metrics)
        assert metrics.success_rate_24h >= 0.95


# ============================================================================
# Full Dashboard Tests
# ============================================================================


@pytest.mark.asyncio
class TestHealthDashboard:
    """Tests for full health dashboard generation."""

    async def test_generates_dashboard(self, health_service, mock_collections):
        """Dashboard includes all integration types."""
        # Setup mocks for all integrations (simplified)
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=0)
        mock_collections["sources"].count_documents = AsyncMock(return_value=0)

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collections["deliveries"].aggregate = MagicMock(return_value=mock_cursor)
        mock_collections["imports"].aggregate = MagicMock(return_value=mock_cursor)
        mock_collections["exports"].aggregate = MagicMock(return_value=mock_cursor)

        dashboard = await health_service.get_health_dashboard("W123")

        assert dashboard.workspace_id == "W123"
        assert dashboard.webhooks is not None
        assert dashboard.external_sources is not None
        assert dashboard.cap_export is not None
        assert dashboard.edxl_export is not None
        assert dashboard.geojson_export is not None
        assert dashboard.generated_at is not None

    async def test_generates_alerts(self, health_service, mock_collections):
        """Dashboard includes alerts for unhealthy integrations."""
        # Setup mocks
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=2)
        mock_collections["sources"].count_documents = AsyncMock(return_value=0)

        # Unhealthy webhook stats
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(
            return_value=[
                {
                    "_id": None,
                    "total": 100,
                    "successful": 50,
                    "failed": 50,
                    "avg_latency": 500.0,
                    "last_delivery": datetime.utcnow(),
                }
            ]
        )

        mock_failed_cursor = AsyncMock()
        mock_failed_cursor.to_list = AsyncMock(
            return_value=[{"_id": ObjectId()}]
        )

        mock_collections["deliveries"].aggregate = MagicMock(
            side_effect=[mock_cursor, mock_failed_cursor]
        )

        mock_empty = AsyncMock()
        mock_empty.to_list = AsyncMock(return_value=[])
        mock_collections["imports"].aggregate = MagicMock(return_value=mock_empty)
        mock_collections["exports"].aggregate = MagicMock(return_value=mock_empty)

        dashboard = await health_service.get_health_dashboard("W123")

        assert dashboard.overall_status == HealthStatus.UNHEALTHY
        assert len(dashboard.alerts) > 0
        assert any("webhook" in alert.lower() for alert in dashboard.alerts)


# ============================================================================
# Summary Tests
# ============================================================================


@pytest.mark.asyncio
class TestHealthSummary:
    """Tests for health summary endpoint."""

    async def test_returns_summary(self, health_service, mock_collections):
        """Summary includes all required fields."""
        # Setup basic mocks
        mock_collections["webhooks"].count_documents = AsyncMock(return_value=0)
        mock_collections["sources"].count_documents = AsyncMock(return_value=0)

        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_collections["deliveries"].aggregate = MagicMock(return_value=mock_cursor)
        mock_collections["imports"].aggregate = MagicMock(return_value=mock_cursor)
        mock_collections["exports"].aggregate = MagicMock(return_value=mock_cursor)

        summary = await health_service.get_integration_summary("W123")

        assert "workspace_id" in summary
        assert "overall_status" in summary
        assert "integrations" in summary
        assert "webhooks" in summary["integrations"]
        assert "external_sources" in summary["integrations"]
        assert "alerts_count" in summary
        assert "generated_at" in summary
