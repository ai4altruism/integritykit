"""
End-to-end tests for Sprint 8 external integration features.

Tests the complete workflow for external integrations:
- Webhook registration and delivery flow (S8-17)
- External source registration and import (S8-20)
- CAP export generation (S8-18)
- GeoJSON export generation (S8-21)
- Integration health dashboard (S8-22)

These tests use mongomock for database operations and unittest.mock for HTTP mocking.
"""

import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from xml.etree import ElementTree as ET

import httpx
import pytest
from bson import ObjectId

# Set required environment variables before importing services
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")
os.environ.setdefault("SLACK_WORKSPACE_ID", "T123456")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DEBUG", "true")

from integritykit.models.cap import CAPCertainty, CAPSeverity
from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateStatus,
    EvidenceSnapshot,
    PublishedLineItem,
)
from integritykit.models.edxl import DistributionStatus
from integritykit.models.external_source import (
    AuthConfig,
    AuthType,
    ExternalSourceCreate,
    ImportRequest,
    ImportStatus,
    TrustLevel,
)
from integritykit.models.geojson import GeoJSONFeatureCollection
from integritykit.models.webhook import (
    AuthConfig as WebhookAuthConfig,
    AuthType as WebhookAuthType,
    RetryConfig,
    WebhookCreate,
    WebhookEvent,
    WebhookStatus,
)
from integritykit.services.cap_export import CAPExportService
from integritykit.services.edxl_export import EDXLExportService
from integritykit.services.external_sources import ExternalSourceService
from integritykit.services.geojson_export import GeoJSONExportService
from integritykit.services.webhooks import WebhookService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_cop_update(
    *,
    workspace_id: str = "T123456",
    published: bool = True,
    with_location: bool = False,
) -> COPUpdate:
    """Create a test COP update with verified and in-review items."""
    candidate_id_1 = ObjectId()
    candidate_id_2 = ObjectId()
    candidate_id_3 = ObjectId()

    # Create line items
    line_items = [
        PublishedLineItem(
            candidate_id=candidate_id_1,
            text="Bridge closure on Main Street due to flooding",
            section="verified",
            status_label="Verified",
            citations=["Official city report"],
            was_edited=False,
        ),
        PublishedLineItem(
            candidate_id=candidate_id_2,
            text="Shelter opened at Central High School",
            section="verified",
            status_label="Verified",
            citations=["Emergency management tweet"],
            was_edited=False,
        ),
        PublishedLineItem(
            candidate_id=candidate_id_3,
            text="Power outages reported in northern district",
            section="in_review",
            status_label="Under Review",
            citations=["Social media reports"],
            was_edited=False,
        ),
    ]

    # Create evidence snapshots
    base_fields = {
        "what": "Bridge closure on Main Street",
        "where": "123 Main St, Springfield, IL",
        "when": {"timestamp": datetime(2024, 3, 10, 14, 30, tzinfo=timezone.utc).isoformat()},
        "who": "City Emergency Services",
        "so_what": "Main route into downtown blocked",
    }

    if with_location:
        base_fields["location"] = {
            "lat": 39.7817,
            "lon": -89.6501,
        }

    evidence_snapshots = [
        EvidenceSnapshot(
            candidate_id=candidate_id_1,
            readiness_state="verified",
            risk_tier="elevated",
            fields_snapshot=base_fields,
            verifications_snapshot=[
                {
                    "verified_by": str(ObjectId()),
                    "verified_at": datetime.utcnow().isoformat(),
                    "verification_method": "authoritative_source",
                }
            ],
        ),
        EvidenceSnapshot(
            candidate_id=candidate_id_2,
            readiness_state="verified",
            risk_tier="routine",
            fields_snapshot={
                "what": "Shelter opened at Central High School",
                "where": "456 Central Ave, Springfield, IL",
                "when": {"timestamp": datetime.utcnow().isoformat()},
                "who": "Red Cross",
                "so_what": "Emergency shelter available for displaced residents",
            },
        ),
        EvidenceSnapshot(
            candidate_id=candidate_id_3,
            readiness_state="in_review",
            risk_tier="routine",
            fields_snapshot={
                "what": "Power outages in northern district",
                "where": "Northern Springfield",
                "when": {"description": "Ongoing"},
                "who": "Unknown",
                "so_what": "Residents without electricity",
            },
        ),
    ]

    cop_update = COPUpdate(
        id=ObjectId(),
        workspace_id=workspace_id,
        update_number=42,
        title="Springfield Flooding Emergency - Update #42",
        status=COPUpdateStatus.PUBLISHED if published else COPUpdateStatus.DRAFT,
        line_items=line_items,
        evidence_snapshots=evidence_snapshots,
        created_by=ObjectId(),
        created_at=datetime.utcnow(),
        published_at=datetime.utcnow() if published else None,
        slack_permalink="https://slack.com/archives/C123/p1234567890",
    )

    return cop_update


# ============================================================================
# Webhook E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_registration_and_delivery_e2e(test_db):
    """Test complete webhook registration and delivery flow."""
    workspace_id = "T123456"
    webhook_url = "https://example.com/webhook"

    service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )

    # Step 1: Register webhook
    webhook_data = WebhookCreate(
        name="Test Webhook",
        url=webhook_url,
        events=[WebhookEvent.COP_UPDATE_PUBLISHED, WebhookEvent.COP_CANDIDATE_VERIFIED],
        auth_type=WebhookAuthType.BEARER,
        auth_config=WebhookAuthConfig(token="test_bearer_token"),
        enabled=True,
    )

    webhook = await service.create_webhook(
        webhook_data=webhook_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    assert webhook.id is not None
    assert webhook.enabled is True
    assert len(webhook.events) == 2

    # Step 2: Mock HTTP endpoint
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.text = '{"status": "received"}'

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        # Step 3: Trigger webhook
        event_data = {
            "cop_update_id": str(ObjectId()),
            "update_number": 42,
            "title": "Test Update",
        }

        triggered_ids = await service.trigger_webhook(
            event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
            workspace_id=workspace_id,
            event_data=event_data,
        )

        # Verify webhook was triggered
        assert len(triggered_ids) == 1
        assert str(webhook.id) in triggered_ids

        # Wait for async delivery
        import asyncio
        await asyncio.sleep(0.2)

        # Verify HTTP call made
        assert mock_post.called
        call_args = mock_post.call_args

        # Verify authentication header
        headers = call_args.kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer test_bearer_token"
        assert headers["X-Webhook-Event"] == WebhookEvent.COP_UPDATE_PUBLISHED

    # Step 4: Verify webhook can be retrieved
    retrieved = await service.get_webhook(webhook.id, workspace_id)
    assert retrieved is not None
    assert retrieved.name == "Test Webhook"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_retry_configuration_e2e(test_db):
    """Test webhook retry configuration and behavior."""
    workspace_id = "T123456"

    service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )

    # Create webhook with custom retry config
    webhook_data = WebhookCreate(
        name="Retry Test Webhook",
        url="https://example.com/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        retry_config=RetryConfig(
            max_retries=2,
            retry_delay_seconds=10,
            backoff_multiplier=2.0,
        ),
        enabled=True,
    )

    webhook = await service.create_webhook(
        webhook_data=webhook_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    # Verify retry configuration
    assert webhook.retry_config is not None
    assert webhook.retry_config.max_retries == 2
    assert webhook.retry_config.retry_delay_seconds == 10
    assert webhook.retry_config.backoff_multiplier == 2.0


# ============================================================================
# External Source Import E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_external_source_registration_and_import_e2e(test_db):
    """Test complete external source registration and import flow."""
    workspace_id = "T123456"
    api_endpoint = "https://api.example.com/verified-data"

    service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.imported_verifications,
        candidates_collection=test_db.cop_candidates,
    )

    # Step 1: Register external source
    source_data = ExternalSourceCreate(
        source_id="example-api",
        name="Example Verified Data API",
        source_type="government_api",
        api_endpoint=api_endpoint,
        auth_type=AuthType.BEARER,
        auth_config=AuthConfig(token="test_api_token"),
        trust_level=TrustLevel.MEDIUM,
        enabled=True,
    )

    source = await service.create_source(
        source_data=source_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    assert source.id is not None
    assert source.trust_level == TrustLevel.MEDIUM
    assert source.enabled is True

    # Step 2: Mock external API response
    mock_response_data = [
        {
            "id": "ext-001",
            "what": "Road closure on Highway 101",
            "where": "Highway 101 Mile Marker 42",
            "when": "2024-03-10T14:30:00Z",
            "who": "State Highway Patrol",
            "so_what": "Traffic diverted to alternate routes",
            "timestamp": "2024-03-10T14:30:00Z",
        },
        {
            "id": "ext-002",
            "what": "Emergency shelter established",
            "where": "County Fairgrounds",
            "when": "2024-03-10T15:00:00Z",
            "who": "County Emergency Services",
            "so_what": "Capacity for 500 people",
            "timestamp": "2024-03-10T15:00:00Z",
        },
    ]

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"items": mock_response_data})
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response) as mock_get:
        # Step 3: Execute import
        import_request = ImportRequest(
            auto_promote=False,
            filters={},
        )

        result = await service.import_verified_data(
            source_id=source.id,
            workspace_id=workspace_id,
            import_request=import_request,
            imported_by=str(ObjectId()),
        )

        # Verify API was called with correct auth
        assert mock_get.called
        call_args = mock_get.call_args
        headers = call_args.kwargs.get("headers", {})
        assert headers["Authorization"] == "Bearer test_api_token"

    # Step 4: Verify import result
    assert result.status == ImportStatus.COMPLETED
    assert result.items_fetched == 2
    assert result.items_imported == 2
    assert result.candidates_created == 2
    assert result.errors == 0

    # Step 5: Verify source can be retrieved
    retrieved = await service.get_source(source.id, workspace_id)
    assert retrieved is not None
    assert retrieved.name == "Example Verified Data API"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_external_source_high_trust_auto_promotion_e2e(test_db):
    """Test auto-promotion for high-trust external sources."""
    workspace_id = "T123456"

    service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.imported_verifications,
        candidates_collection=test_db.cop_candidates,
    )

    # Register high-trust source
    source_data = ExternalSourceCreate(
        source_id="trusted-gov-api",
        name="Trusted Government API",
        source_type="government_api",
        api_endpoint="https://api.trusted.gov/incidents",
        auth_type=AuthType.API_KEY,
        auth_config=AuthConfig(key_name="X-API-Key", key_value="gov_api_key"),
        trust_level=TrustLevel.HIGH,
        enabled=True,
    )

    source = await service.create_source(
        source_data=source_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    # Mock API response
    mock_data = [
        {
            "id": "gov-001",
            "description": "Official evacuation order issued",
            "location": "Zone A",
            "timestamp": "2024-03-10T16:00:00Z",
        }
    ]

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=mock_data)
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        # Import with auto_promote=True
        import_request = ImportRequest(auto_promote=True, filters={})

        result = await service.import_verified_data(
            source_id=source.id,
            workspace_id=workspace_id,
            import_request=import_request,
            imported_by=str(ObjectId()),
        )

    # Verify import succeeded
    assert result.status == ImportStatus.COMPLETED
    assert result.items_imported == 1


# ============================================================================
# CAP Export E2E Tests
# ============================================================================


@pytest.mark.e2e
def test_cap_export_generation_e2e():
    """Test complete CAP 1.2 export generation flow."""
    # Create published COP update
    cop_update = create_test_cop_update(published=True)

    service = CAPExportService(sender_id="integritykit@aidarena.org")

    # Generate CAP export
    cap_alert = service.export_cop_update(cop_update, language="en-US")

    # Verify CAP structure
    assert cap_alert.identifier == f"cop-update-{cop_update.id}"
    assert cap_alert.sender == "integritykit@aidarena.org"
    assert cap_alert.status.value == "Actual"
    assert cap_alert.msgType.value == "Update"

    # Should have info blocks
    assert len(cap_alert.info) >= 1

    # Verify info block properties
    verified_info = cap_alert.info[0]
    assert verified_info.certainty == CAPCertainty.OBSERVED
    assert verified_info.event == cop_update.title
    assert "Bridge closure" in verified_info.description


@pytest.mark.e2e
def test_cap_export_xml_generation_e2e():
    """Test CAP XML generation and validation."""
    cop_update = create_test_cop_update(published=True)
    service = CAPExportService(sender_id="integritykit@aidarena.org")

    # Generate CAP XML
    cap_xml = service.generate_cap_xml(cop_update, language="en-US")

    # Verify XML structure
    assert cap_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "urn:oasis:names:tc:emergency:cap:1.2" in cap_xml

    # Parse and validate XML
    root = ET.fromstring(cap_xml.split("\n", 1)[1])
    assert root.tag == "{urn:oasis:names:tc:emergency:cap:1.2}alert"

    # Verify required CAP fields
    identifier_elem = root.find("{urn:oasis:names:tc:emergency:cap:1.2}identifier")
    assert identifier_elem is not None

    sender_elem = root.find("{urn:oasis:names:tc:emergency:cap:1.2}sender")
    assert sender_elem is not None

    info_elems = root.findall("{urn:oasis:names:tc:emergency:cap:1.2}info")
    assert len(info_elems) >= 1


@pytest.mark.e2e
def test_cap_export_validation_unpublished_e2e():
    """Test CAP export validation rejects unpublished updates."""
    cop_update = create_test_cop_update(published=False)
    service = CAPExportService()

    # Should raise error for unpublished update
    with pytest.raises(ValueError, match="Cannot export unpublished COP update"):
        service.export_cop_update(cop_update)


# ============================================================================
# GeoJSON Export E2E Tests
# ============================================================================


@pytest.mark.e2e
def test_geojson_export_generation_e2e():
    """Test complete GeoJSON export generation flow."""
    # Create COP update with location data
    cop_update = create_test_cop_update(published=True, with_location=True)

    service = GeoJSONExportService()

    # Generate GeoJSON export
    feature_collection = service.export_cop_update(
        cop_update,
        include_non_spatial=False,
    )

    # Verify GeoJSON structure
    assert feature_collection.type == "FeatureCollection"
    assert feature_collection.metadata is not None
    assert feature_collection.metadata["cop_update_id"] == str(cop_update.id)

    # Should have features with locations
    assert len(feature_collection.features) > 0

    # Verify feature structure
    feature = feature_collection.features[0]
    assert feature.type == "Feature"
    assert feature.geometry is not None
    assert feature.geometry.type == "Point"
    assert len(feature.geometry.coordinates) == 2

    # GeoJSON uses [lon, lat] order
    assert feature.geometry.coordinates[0] == -89.6501  # longitude
    assert feature.geometry.coordinates[1] == 39.7817  # latitude


@pytest.mark.e2e
def test_geojson_export_json_string_e2e():
    """Test GeoJSON JSON string generation and parsing."""
    cop_update = create_test_cop_update(published=True, with_location=True)
    service = GeoJSONExportService()

    # Generate JSON string
    geojson_str = service.generate_geojson_string(
        cop_update,
        include_non_spatial=False,
        pretty=True,
    )

    # Verify valid JSON
    parsed = json.loads(geojson_str)
    assert parsed["type"] == "FeatureCollection"
    assert "features" in parsed
    assert "metadata" in parsed
    assert len(parsed["features"]) > 0


@pytest.mark.e2e
def test_geojson_export_with_non_spatial_e2e():
    """Test GeoJSON export including items without location data."""
    cop_update = create_test_cop_update(published=True, with_location=False)
    service = GeoJSONExportService()

    # Export with non-spatial features
    feature_collection = service.export_cop_update(
        cop_update,
        include_non_spatial=True,
    )

    # Should have all line items
    assert len(feature_collection.features) == 3

    # Features without location have null geometry
    non_spatial = [f for f in feature_collection.features if f.geometry is None]
    assert len(non_spatial) > 0

    # Get export stats
    stats = service.get_export_stats(feature_collection)
    assert stats["total_features"] == 3
    assert stats["non_spatial_features"] > 0


# ============================================================================
# EDXL-DE Export E2E Tests
# ============================================================================


@pytest.mark.e2e
def test_edxl_export_with_embedded_cap_e2e():
    """Test EDXL-DE export with embedded CAP alert."""
    cop_update = create_test_cop_update(published=True)

    service = EDXLExportService(
        sender_id="integritykit@aidarena.org",
        cap_sender_id="integritykit@aidarena.org",
    )

    # Generate EDXL export
    edxl_distribution = service.export_cop_update(cop_update, language="en-US")

    # Verify EDXL structure
    assert edxl_distribution.distributionID == f"edxl-cop-update-{cop_update.id}"
    assert edxl_distribution.senderID == "integritykit@aidarena.org"
    assert edxl_distribution.distributionStatus == DistributionStatus.ACTUAL

    # Should have content object with embedded CAP
    assert len(edxl_distribution.contentObject) == 1
    content_obj = edxl_distribution.contentObject[0]

    assert content_obj.xmlContent is not None
    assert "urn:oasis:names:tc:emergency:cap:1.2" in content_obj.xmlContent
    assert content_obj.contentMimeType == "application/xml"


@pytest.mark.e2e
def test_edxl_export_xml_generation_e2e():
    """Test EDXL-DE XML generation with embedded CAP."""
    cop_update = create_test_cop_update(published=True)

    service = EDXLExportService(
        sender_id="integritykit@aidarena.org",
        cap_sender_id="integritykit@aidarena.org",
    )

    # Generate EDXL XML
    edxl_xml = service.generate_edxl_xml(cop_update, language="en-US")

    # Verify XML structure
    assert edxl_xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "urn:oasis:names:tc:emergency:EDXL:DE:2.0" in edxl_xml

    # Parse XML
    root = ET.fromstring(edxl_xml.split("\n", 1)[1])
    assert root.tag == "{urn:oasis:names:tc:emergency:EDXL:DE:2.0}EDXLDistribution"

    # Verify embedded CAP
    content_obj_elem = root.find("{urn:oasis:names:tc:emergency:EDXL:DE:2.0}contentObject")
    assert content_obj_elem is not None

    xml_content_elem = content_obj_elem.find(
        "{urn:oasis:names:tc:emergency:EDXL:DE:2.0}xmlContent"
    )
    assert xml_content_elem is not None

    # Should contain embedded CAP alert
    cap_alert_elem = xml_content_elem.find("{urn:oasis:names:tc:emergency:cap:1.2}alert")
    assert cap_alert_elem is not None


# ============================================================================
# Integration Health E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_integration_health_monitoring_e2e(test_db):
    """Test integration health monitoring for webhooks and external sources."""
    workspace_id = "T123456"

    # Create webhook service
    webhook_service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )

    # Create external source service
    source_service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.imported_verifications,
        candidates_collection=test_db.cop_candidates,
    )

    # Register webhook
    webhook_data = WebhookCreate(
        name="Health Test Webhook",
        url="https://example.com/webhook",
        events=[WebhookEvent.COP_UPDATE_PUBLISHED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
    )

    webhook = await webhook_service.create_webhook(
        webhook_data=webhook_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    # Register external source
    source_data = ExternalSourceCreate(
        source_id="health-test-api",
        name="Health Test API",
        source_type="other",
        api_endpoint="https://api.example.com/data",
        auth_type=AuthType.NONE,
        trust_level=TrustLevel.MEDIUM,
        enabled=True,
    )

    source = await source_service.create_source(
        source_data=source_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    # Verify both integrations are registered
    retrieved_webhook = await webhook_service.get_webhook(webhook.id, workspace_id)
    retrieved_source = await source_service.get_source(source.id, workspace_id)

    assert retrieved_webhook is not None
    assert retrieved_source is not None
    assert retrieved_webhook.enabled is True
    assert retrieved_source.enabled is True


# ============================================================================
# Cross-Integration E2E Tests
# ============================================================================


@pytest.mark.e2e
def test_multi_format_export_consistency_e2e():
    """Test exporting same COP update to multiple formats maintains consistency."""
    cop_update = create_test_cop_update(published=True, with_location=True)

    # Export to all formats
    geojson_service = GeoJSONExportService()
    cap_service = CAPExportService()
    edxl_service = EDXLExportService()

    geojson_collection = geojson_service.export_cop_update(cop_update)
    cap_alert = cap_service.export_cop_update(cop_update)
    edxl_distribution = edxl_service.export_cop_update(cop_update)

    # Verify all exports reference same COP update
    assert geojson_collection.metadata["cop_update_id"] == str(cop_update.id)
    assert cap_alert.identifier == f"cop-update-{cop_update.id}"
    assert edxl_distribution.distributionID == f"edxl-cop-update-{cop_update.id}"

    # Verify all have content
    assert len(geojson_collection.features) > 0
    assert len(cap_alert.info) > 0
    assert len(edxl_distribution.contentObject) > 0


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_webhook_and_external_source_workflow_e2e(test_db):
    """Test workflow: import from external source, then trigger webhook."""
    workspace_id = "T123456"

    # Setup services
    webhook_service = WebhookService(
        webhooks_collection=test_db.webhooks,
        deliveries_collection=test_db.webhook_deliveries,
    )

    source_service = ExternalSourceService(
        sources_collection=test_db.external_sources,
        imports_collection=test_db.imported_verifications,
        candidates_collection=test_db.cop_candidates,
    )

    # Create webhook to listen for candidate events
    webhook_data = WebhookCreate(
        name="Candidate Import Webhook",
        url="https://example.com/webhook",
        events=[WebhookEvent.COP_CANDIDATE_VERIFIED],
        auth_type=WebhookAuthType.NONE,
        enabled=True,
    )

    webhook = await webhook_service.create_webhook(
        webhook_data=webhook_data,
        workspace_id=workspace_id,
        created_by="U123456",
    )

    # Mock webhook endpoint
    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch("httpx.AsyncClient.post", return_value=mock_response) as mock_post:
        # Simulate candidate verification event
        event_data = {
            "candidate_id": str(ObjectId()),
            "verified_by": "external_source",
        }

        triggered_ids = await webhook_service.trigger_webhook(
            event_type=WebhookEvent.COP_CANDIDATE_VERIFIED,
            workspace_id=workspace_id,
            event_data=event_data,
        )

        # Give async delivery time
        import asyncio
        await asyncio.sleep(0.2)

        # Verify webhook was triggered
        assert len(triggered_ids) > 0
        assert mock_post.called
