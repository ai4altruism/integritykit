"""Unit tests for CAP 1.2 export service.

Tests:
- CAP model validation
- COP update to CAP conversion
- Readiness state to certainty mapping
- Risk tier to urgency/severity mapping
- XML generation and validation
- Error handling for non-exportable updates
"""

import pytest
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from bson import ObjectId

from integritykit.models.cap import (
    CAPAlert,
    CAPArea,
    CAPCategory,
    CAPCertainty,
    CAPInfo,
    CAPMsgType,
    CAPScope,
    CAPSeverity,
    CAPStatus,
    CAPUrgency,
)
from integritykit.models.cop_candidate import RiskTier, ReadinessState
from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateStatus,
    EvidenceSnapshot,
    PublishedLineItem,
)
from integritykit.services.cap_export import CAPExportService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def cap_service():
    """Provide CAP export service instance."""
    return CAPExportService(sender_id="test@integritykit.org")


@pytest.fixture
def sample_cop_update():
    """Provide sample published COP update for testing."""
    now = datetime.utcnow()
    user_id = ObjectId()

    return COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=1,
        title="Shelter Status Update",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="verified",
                status_label="VERIFIED",
                text="Shelter Alpha at 123 Main St has reached capacity and is no longer accepting new evacuees.",
                citations=["https://slack.com/archives/C123/p1234567890"],
                was_edited=False,
            ),
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="in_review",
                status_label="IN REVIEW",
                text="Shelter Bravo at 456 Oak Ave is now open and accepting evacuees.",
                citations=["https://slack.com/archives/C123/p1234567891"],
                was_edited=False,
            ),
        ],
        evidence_snapshots=[
            EvidenceSnapshot(
                candidate_id=ObjectId(),
                risk_tier="elevated",
                readiness_state="verified",
                fields_snapshot={
                    "what": "Shelter capacity reached",
                    "where": "123 Main St",
                },
            ),
        ],
        created_by=user_id,
        approved_by=user_id,
        approved_at=now - timedelta(minutes=5),
        published_at=now,
        slack_channel_id="C123456",
        slack_permalink="https://slack.com/archives/C123456/p1234567892",
    )


@pytest.fixture
def unpublished_cop_update():
    """Provide unpublished COP update for testing validation."""
    return COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=2,
        title="Draft Update",
        status=COPUpdateStatus.DRAFT,
        line_items=[
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="verified",
                status_label="VERIFIED",
                text="Test item",
                citations=[],
            ),
        ],
        created_by=ObjectId(),
    )


# ============================================================================
# CAP Model Tests
# ============================================================================


def test_cap_alert_model_validation():
    """Test CAP alert model validates required fields."""
    alert = CAPAlert(
        identifier="test-alert-001",
        sender="test@example.org",
        sent=datetime.utcnow(),
        status=CAPStatus.ACTUAL,
        msgType=CAPMsgType.ALERT,
        scope=CAPScope.PUBLIC,
        info=[
            CAPInfo(
                language="en-US",
                category=[CAPCategory.SAFETY],
                event="Test Event",
                urgency=CAPUrgency.IMMEDIATE,
                severity=CAPSeverity.SEVERE,
                certainty=CAPCertainty.OBSERVED,
            )
        ],
    )

    assert alert.identifier == "test-alert-001"
    assert alert.status == CAPStatus.ACTUAL
    assert len(alert.info) == 1
    assert alert.info[0].category[0] == CAPCategory.SAFETY


def test_cap_info_block_with_area():
    """Test CAP info block with geographic area."""
    info = CAPInfo(
        language="en-US",
        category=[CAPCategory.SAFETY, CAPCategory.INFRA],
        event="Shelter Closure",
        urgency=CAPUrgency.EXPECTED,
        severity=CAPSeverity.MODERATE,
        certainty=CAPCertainty.OBSERVED,
        headline="Shelter Alpha Closure",
        description="Shelter has reached capacity.",
        area=[
            CAPArea(
                areaDesc="Springfield Downtown",
                circle=["39.7817,-89.6501 0"],
            )
        ],
    )

    assert len(info.category) == 2
    assert info.headline == "Shelter Alpha Closure"
    assert info.area is not None
    assert len(info.area) == 1
    assert info.area[0].areaDesc == "Springfield Downtown"


# ============================================================================
# Export Validation Tests
# ============================================================================


def test_validate_exportable_published_update(cap_service, sample_cop_update):
    """Test validation passes for published update."""
    # Should not raise
    cap_service._validate_exportable(sample_cop_update)


def test_validate_exportable_unpublished_update(cap_service, unpublished_cop_update):
    """Test validation fails for unpublished update."""
    with pytest.raises(ValueError, match="Cannot export unpublished"):
        cap_service._validate_exportable(unpublished_cop_update)


def test_validate_exportable_no_items(cap_service):
    """Test validation fails when no exportable items."""
    cop_update = COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=3,
        title="Empty Update",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[],  # No items
        created_by=ObjectId(),
        published_at=datetime.utcnow(),
    )

    with pytest.raises(ValueError, match="at least one verified or in-review"):
        cap_service._validate_exportable(cop_update)


def test_validate_exportable_only_disproven_items(cap_service):
    """Test validation fails when only disproven items present."""
    cop_update = COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=4,
        title="Disproven Only",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="disproven",
                status_label="DISPROVEN",
                text="This was incorrect",
                citations=[],
            ),
        ],
        created_by=ObjectId(),
        published_at=datetime.utcnow(),
    )

    with pytest.raises(ValueError, match="at least one verified or in-review"):
        cap_service._validate_exportable(cop_update)


# ============================================================================
# Mapping Tests
# ============================================================================


def test_map_readiness_to_certainty(cap_service):
    """Test readiness state to CAP certainty mapping."""
    assert (
        cap_service._map_readiness_to_certainty(ReadinessState.VERIFIED)
        == CAPCertainty.OBSERVED
    )
    assert (
        cap_service._map_readiness_to_certainty(ReadinessState.IN_REVIEW)
        == CAPCertainty.LIKELY
    )
    assert (
        cap_service._map_readiness_to_certainty(ReadinessState.BLOCKED)
        == CAPCertainty.POSSIBLE
    )


def test_map_risk_tier_high_stakes(cap_service, sample_cop_update):
    """Test high stakes risk tier mapping."""
    # Update evidence snapshot to high_stakes
    sample_cop_update.evidence_snapshots[0].risk_tier = "high_stakes"

    urgency, severity = cap_service._map_risk_tier_to_urgency_severity(
        sample_cop_update
    )

    assert urgency == CAPUrgency.IMMEDIATE
    assert severity == CAPSeverity.SEVERE


def test_map_risk_tier_elevated(cap_service, sample_cop_update):
    """Test elevated risk tier mapping."""
    # Already set to elevated in fixture
    urgency, severity = cap_service._map_risk_tier_to_urgency_severity(
        sample_cop_update
    )

    assert urgency == CAPUrgency.EXPECTED
    assert severity == CAPSeverity.MODERATE


def test_map_risk_tier_routine(cap_service, sample_cop_update):
    """Test routine risk tier mapping."""
    # Update evidence snapshot to routine
    sample_cop_update.evidence_snapshots[0].risk_tier = "routine"

    urgency, severity = cap_service._map_risk_tier_to_urgency_severity(
        sample_cop_update
    )

    assert urgency == CAPUrgency.FUTURE
    assert severity == CAPSeverity.MINOR


def test_determine_categories_shelter(cap_service):
    """Test category determination for shelter-related items."""
    line_items = [
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="Shelter Alpha has reached capacity",
            citations=[],
        ),
    ]

    categories = cap_service._determine_categories(line_items)

    assert CAPCategory.SAFETY in categories
    assert CAPCategory.INFRA in categories


def test_determine_categories_health(cap_service):
    """Test category determination for health-related items."""
    line_items = [
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="Medical supplies running low at hospital",
            citations=[],
        ),
    ]

    categories = cap_service._determine_categories(line_items)

    assert CAPCategory.SAFETY in categories
    assert CAPCategory.HEALTH in categories


def test_determine_categories_fire(cap_service):
    """Test category determination for fire-related items."""
    line_items = [
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="Wildfire spreading near residential area",
            citations=[],
        ),
    ]

    categories = cap_service._determine_categories(line_items)

    assert CAPCategory.SAFETY in categories
    assert CAPCategory.FIRE in categories


# ============================================================================
# Export Tests
# ============================================================================


def test_export_cop_update_to_cap_alert(cap_service, sample_cop_update):
    """Test full COP update to CAP alert export."""
    alert = cap_service.export_cop_update(sample_cop_update)

    # Validate alert structure
    assert alert.identifier == f"cop-update-{sample_cop_update.id}"
    assert alert.sender == "test@integritykit.org"
    assert alert.status == CAPStatus.ACTUAL
    assert alert.msgType == CAPMsgType.UPDATE
    assert alert.scope == CAPScope.PUBLIC

    # Should have two info blocks (verified and in_review)
    assert len(alert.info) == 2

    # First info block should be for verified items
    verified_info = alert.info[0]
    assert verified_info.certainty == CAPCertainty.OBSERVED
    assert verified_info.event == "Shelter Status Update"
    assert "Shelter Alpha" in verified_info.description

    # Second info block should be for in_review items
    in_review_info = alert.info[1]
    assert in_review_info.certainty == CAPCertainty.LIKELY
    assert "Shelter Bravo" in in_review_info.description


def test_export_verified_only(cap_service):
    """Test export with only verified items."""
    cop_update = COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=5,
        title="Verified Only Update",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[
            PublishedLineItem(
                candidate_id=ObjectId(),
                section="verified",
                status_label="VERIFIED",
                text="Verified information",
                citations=[],
            ),
        ],
        evidence_snapshots=[
            EvidenceSnapshot(
                candidate_id=ObjectId(),
                risk_tier="routine",
                readiness_state="verified",
            ),
        ],
        created_by=ObjectId(),
        published_at=datetime.utcnow(),
    )

    alert = cap_service.export_cop_update(cop_update)

    # Should have only one info block
    assert len(alert.info) == 1
    assert alert.info[0].certainty == CAPCertainty.OBSERVED


# ============================================================================
# XML Generation Tests
# ============================================================================


def test_generate_cap_xml(cap_service, sample_cop_update):
    """Test XML generation from COP update."""
    xml_string = cap_service.generate_cap_xml(sample_cop_update)

    # Validate XML is well-formed
    assert xml_string.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    # Parse to verify structure
    root = ET.fromstring(xml_string.split("\n", 1)[1])  # Skip declaration

    # Verify namespace
    assert root.tag == f"{{{CAP_NAMESPACE}}}alert"

    # Verify required elements present
    assert root.find(f"{{{CAP_NAMESPACE}}}identifier") is not None
    assert root.find(f"{{{CAP_NAMESPACE}}}sender") is not None
    assert root.find(f"{{{CAP_NAMESPACE}}}sent") is not None
    assert root.find(f"{{{CAP_NAMESPACE}}}status") is not None
    assert root.find(f"{{{CAP_NAMESPACE}}}msgType") is not None
    assert root.find(f"{{{CAP_NAMESPACE}}}scope") is not None

    # Verify info blocks present
    info_blocks = root.findall(f"{{{CAP_NAMESPACE}}}info")
    assert len(info_blocks) == 2  # verified and in_review


def test_xml_element_values(cap_service, sample_cop_update):
    """Test XML element values are correct."""
    CAP_NS = "{" + CAP_NAMESPACE + "}"
    xml_string = cap_service.generate_cap_xml(sample_cop_update)
    root = ET.fromstring(xml_string.split("\n", 1)[1])

    # Check specific values
    assert (
        root.find(f"{CAP_NS}identifier").text
        == f"cop-update-{sample_cop_update.id}"
    )
    assert root.find(f"{CAP_NS}sender").text == "test@integritykit.org"
    assert root.find(f"{CAP_NS}status").text == "Actual"
    assert root.find(f"{CAP_NS}msgType").text == "Update"
    assert root.find(f"{CAP_NS}scope").text == "Public"

    # Check info block
    info = root.find(f"{CAP_NS}info")
    assert info is not None
    assert info.find(f"{CAP_NS}language").text == "en-US"
    assert info.find(f"{CAP_NS}event").text == "Shelter Status Update"
    assert info.find(f"{CAP_NS}certainty").text == "Observed"


def test_xml_info_block_structure(cap_service, sample_cop_update):
    """Test XML info block structure."""
    CAP_NS = "{" + CAP_NAMESPACE + "}"
    xml_string = cap_service.generate_cap_xml(sample_cop_update)
    root = ET.fromstring(xml_string.split("\n", 1)[1])

    info = root.find(f"{CAP_NS}info")

    # Required info elements
    assert info.find(f"{CAP_NS}language") is not None
    assert info.find(f"{CAP_NS}category") is not None
    assert info.find(f"{CAP_NS}event") is not None
    assert info.find(f"{CAP_NS}urgency") is not None
    assert info.find(f"{CAP_NS}severity") is not None
    assert info.find(f"{CAP_NS}certainty") is not None

    # Optional info elements
    assert info.find(f"{CAP_NS}headline") is not None
    assert info.find(f"{CAP_NS}description") is not None
    assert info.find(f"{CAP_NS}effective") is not None
    assert info.find(f"{CAP_NS}senderName") is not None
    assert info.find(f"{CAP_NS}web") is not None


def test_format_datetime(cap_service):
    """Test datetime formatting for CAP."""
    dt = datetime(2026, 3, 10, 14, 30, 0)
    formatted = cap_service._format_datetime(dt)

    # Should be ISO 8601 with timezone
    assert formatted == "2026-03-10T14:30:00+00:00"


def test_generate_identifier(cap_service, sample_cop_update):
    """Test CAP identifier generation."""
    identifier = cap_service._generate_identifier(sample_cop_update)

    assert identifier == f"cop-update-{sample_cop_update.id}"
    assert identifier.startswith("cop-update-")


# ============================================================================
# Description Building Tests
# ============================================================================


def test_build_description(cap_service):
    """Test description building from line items."""
    line_items = [
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="First item text",
            citations=[],
        ),
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="Second item text",
            citations=[],
        ),
    ]

    description = cap_service._build_description(line_items)

    assert "[VERIFIED] First item text" in description
    assert "[VERIFIED] Second item text" in description
    assert "\n\n" in description  # Items separated by double newline


def test_build_description_mixed_status(cap_service):
    """Test description with mixed status labels."""
    line_items = [
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="verified",
            status_label="VERIFIED",
            text="Verified item",
            citations=[],
        ),
        PublishedLineItem(
            candidate_id=ObjectId(),
            section="in_review",
            status_label="IN REVIEW",
            text="In review item",
            citations=[],
        ),
    ]

    description = cap_service._build_description(line_items)

    assert "[VERIFIED]" in description
    assert "[IN REVIEW]" in description


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_export_workflow(cap_service, sample_cop_update):
    """Test complete export workflow from COP update to valid CAP XML."""
    # Export to XML
    xml_string = cap_service.generate_cap_xml(sample_cop_update, language="en-US")

    # Verify XML is parseable
    try:
        # Parse full XML including declaration
        xml_lines = xml_string.split("\n")
        assert xml_lines[0].startswith('<?xml version="1.0"')

        # Parse XML content (skip declaration)
        root = ET.fromstring("\n".join(xml_lines[1:]))
    except ET.ParseError as e:
        pytest.fail(f"Generated XML is not valid: {e}")

    # Verify required CAP elements are present
    CAP_NS = "{" + CAP_NAMESPACE + "}"
    assert root.find(f"{CAP_NS}identifier") is not None
    assert root.find(f"{CAP_NS}sender") is not None
    assert root.find(f"{CAP_NS}sent") is not None
    assert root.find(f"{CAP_NS}status") is not None
    assert root.find(f"{CAP_NS}msgType") is not None
    assert root.find(f"{CAP_NS}scope") is not None
    assert root.findall(f"{CAP_NS}info")  # At least one info block

    # Verify info block completeness
    info = root.find(f"{CAP_NS}info")
    assert info.find(f"{CAP_NS}language") is not None
    assert info.find(f"{CAP_NS}category") is not None
    assert info.find(f"{CAP_NS}event") is not None
    assert info.find(f"{CAP_NS}urgency") is not None
    assert info.find(f"{CAP_NS}severity") is not None
    assert info.find(f"{CAP_NS}certainty") is not None


def test_export_with_custom_language(cap_service, sample_cop_update):
    """Test export with custom language code."""
    alert = cap_service.export_cop_update(sample_cop_update, language="es-ES")

    # Language should be set in info blocks
    assert all(info.language == "es-ES" for info in alert.info)


def test_multiple_exports_same_update(cap_service, sample_cop_update):
    """Test multiple exports of same update produce consistent results."""
    xml1 = cap_service.generate_cap_xml(sample_cop_update)
    xml2 = cap_service.generate_cap_xml(sample_cop_update)

    # Should produce identical XML (deterministic)
    assert xml1 == xml2


# Import CAP namespace for test assertions
CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"
