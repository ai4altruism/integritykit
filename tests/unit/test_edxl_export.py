"""Unit tests for EDXL-DE 2.0 export service.

Tests:
- EDXL-DE model validation
- COP update to EDXL-DE conversion
- CAP content embedding
- Distribution envelope structure
- XML generation and validation
- Error handling for non-exportable updates
"""

import pytest
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

from bson import ObjectId

from integritykit.models.cop_candidate import RiskTier, ReadinessState
from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateStatus,
    EvidenceSnapshot,
    PublishedLineItem,
)
from integritykit.models.edxl import (
    DistributionStatus,
    DistributionType,
    EDXLContentObject,
    EDXLDistribution,
    ValueScheme,
)
from integritykit.services.edxl_export import EDXLExportService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def edxl_service():
    """Provide EDXL-DE export service instance."""
    return EDXLExportService(
        sender_id="test-edxl@integritykit.org",
        cap_sender_id="test-cap@integritykit.org",
    )


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


# ============================================================================
# EDXL-DE Model Tests
# ============================================================================


def test_edxl_distribution_model():
    """Test EDXLDistribution model validation."""
    distribution = EDXLDistribution(
        distributionID="edxl-test-123",
        senderID="test@integritykit.org",
        dateTimeSent=datetime.utcnow(),
        distributionStatus=DistributionStatus.ACTUAL,
        distributionType=DistributionType.UPDATE,
        contentObject=[
            EDXLContentObject(
                contentDescription="Test content",
                xmlContent="<test>content</test>",
                contentMimeType="application/xml",
            )
        ],
    )

    assert distribution.distributionID == "edxl-test-123"
    assert distribution.senderID == "test@integritykit.org"
    assert distribution.distributionStatus == DistributionStatus.ACTUAL
    assert distribution.distributionType == DistributionType.UPDATE
    assert len(distribution.contentObject) == 1


def test_edxl_content_object_model():
    """Test EDXLContentObject model validation."""
    content = EDXLContentObject(
        contentDescription="CAP Alert",
        contentKeyword=[
            ValueScheme(value="CAP", scheme="urn:oasis:names:tc:emergency:cap:1.2")
        ],
        incidentID="incident-123",
        xmlContent="<alert>...</alert>",
        contentMimeType="application/xml",
        contentSize=1024,
    )

    assert content.contentDescription == "CAP Alert"
    assert len(content.contentKeyword) == 1
    assert content.contentKeyword[0].value == "CAP"
    assert content.incidentID == "incident-123"
    assert content.xmlContent == "<alert>...</alert>"
    assert content.contentMimeType == "application/xml"
    assert content.contentSize == 1024


def test_value_scheme_model():
    """Test ValueScheme model validation."""
    vs = ValueScheme(value="Emergency Management", scheme="urn:example:roles")

    assert vs.value == "Emergency Management"
    assert vs.scheme == "urn:example:roles"


# ============================================================================
# Export Service Tests
# ============================================================================


def test_export_cop_update_to_edxl(edxl_service, sample_cop_update):
    """Test exporting COP update to EDXL-DE distribution model."""
    distribution = edxl_service.export_cop_update(sample_cop_update, language="en-US")

    # Validate distribution envelope
    assert distribution.distributionID == f"edxl-cop-update-{sample_cop_update.id}"
    assert distribution.senderID == "test-edxl@integritykit.org"
    assert distribution.dateTimeSent == sample_cop_update.published_at
    assert distribution.distributionStatus == DistributionStatus.ACTUAL
    assert distribution.distributionType == DistributionType.UPDATE
    assert distribution.language == "en-US"

    # Validate sender role
    assert distribution.senderRole is not None
    assert len(distribution.senderRole) == 1
    assert distribution.senderRole[0].value == "Emergency Management"

    # Validate keywords
    assert distribution.keyword is not None
    assert len(distribution.keyword) == 2
    keywords = [kw.value for kw in distribution.keyword]
    assert "COP" in keywords
    assert "Common Operational Picture" in keywords

    # Validate content object
    assert len(distribution.contentObject) == 1
    content = distribution.contentObject[0]
    assert content.contentDescription is not None
    assert "Common Alerting Protocol" in content.contentDescription
    assert content.incidentID == str(sample_cop_update.id)
    assert content.incidentDescription == sample_cop_update.title
    assert content.xmlContent is not None  # CAP XML embedded
    assert content.contentMimeType == "application/xml"
    assert content.contentSize > 0


def test_export_unpublished_cop_update_fails(edxl_service, sample_cop_update):
    """Test that exporting unpublished COP update raises ValueError."""
    sample_cop_update.published_at = None

    with pytest.raises(ValueError, match="Cannot export unpublished COP update"):
        edxl_service.export_cop_update(sample_cop_update)


def test_export_cop_update_without_items_fails(edxl_service, sample_cop_update):
    """Test that exporting COP update without verified/in-review items fails."""
    sample_cop_update.line_items = []

    with pytest.raises(
        ValueError, match="must have at least one verified or in-review item"
    ):
        edxl_service.export_cop_update(sample_cop_update)


# ============================================================================
# XML Generation Tests
# ============================================================================


def test_generate_edxl_xml(edxl_service, sample_cop_update):
    """Test generating EDXL-DE XML string."""
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update, language="en-US")

    # Validate XML declaration
    assert xml_string.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    # Parse XML
    # Remove XML declaration for parsing
    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)

    # Validate root element
    assert root.tag.endswith("EDXLDistribution")
    assert "urn:oasis:names:tc:emergency:EDXL:DE:2.0" in root.tag

    # Validate required fields
    assert root.find(".//{*}distributionID") is not None
    assert root.find(".//{*}senderID") is not None
    assert root.find(".//{*}dateTimeSent") is not None
    assert root.find(".//{*}distributionStatus") is not None
    assert root.find(".//{*}distributionType") is not None

    # Validate content object
    content_objects = root.findall(".//{*}contentObject")
    assert len(content_objects) == 1

    # Validate embedded CAP content
    xml_content_elem = content_objects[0].find(".//{*}xmlContent")
    assert xml_content_elem is not None

    # Check for CAP alert element
    cap_alert = xml_content_elem.find(".//{*}alert")
    assert cap_alert is not None


def test_xml_contains_cap_content(edxl_service, sample_cop_update):
    """Test that EDXL-DE XML contains embedded CAP alert."""
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update)

    # Parse XML
    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)

    # Find CAP alert
    cap_alert = root.find(".//{urn:oasis:names:tc:emergency:cap:1.2}alert")
    assert cap_alert is not None

    # Validate CAP structure
    cap_identifier = cap_alert.find(".//{*}identifier")
    assert cap_identifier is not None
    assert cap_identifier.text == f"cop-update-{sample_cop_update.id}"

    # Validate CAP sender (from cap_sender_id)
    cap_sender = cap_alert.find(".//{*}sender")
    assert cap_sender is not None
    assert cap_sender.text == "test-cap@integritykit.org"


def test_xml_structure_validation(edxl_service, sample_cop_update):
    """Test EDXL-DE XML structure against specification."""
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update)

    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)

    # Required elements (§3.2)
    assert root.find(".//{*}distributionID").text == f"edxl-cop-update-{sample_cop_update.id}"
    assert root.find(".//{*}senderID").text == "test-edxl@integritykit.org"
    assert root.find(".//{*}dateTimeSent") is not None
    assert root.find(".//{*}distributionStatus").text == "Actual"
    assert root.find(".//{*}distributionType").text == "Update"

    # Optional elements
    assert root.find(".//{*}language").text == "en-US"

    # Sender role
    sender_roles = root.findall(".//{*}senderRole")
    assert len(sender_roles) > 0
    assert sender_roles[0].find(".//{*}value").text == "Emergency Management"

    # Keywords
    keywords = root.findall(".//{*}keyword")
    assert len(keywords) >= 2


def test_datetime_formatting(edxl_service, sample_cop_update):
    """Test that datetimes are formatted correctly in XML."""
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update)

    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)

    date_time_sent = root.find(".//{*}dateTimeSent").text

    # Should be ISO 8601 format with timezone
    assert "T" in date_time_sent  # Date-time separator
    assert ("+" in date_time_sent or "-" in date_time_sent or "Z" in date_time_sent)  # Timezone


def test_content_size_calculation(edxl_service, sample_cop_update):
    """Test that content size is calculated correctly."""
    distribution = edxl_service.export_cop_update(sample_cop_update)

    content = distribution.contentObject[0]
    actual_size = len(content.xmlContent.encode("utf-8"))

    assert content.contentSize == actual_size


# ============================================================================
# Language Support Tests
# ============================================================================


def test_export_with_different_languages(edxl_service, sample_cop_update):
    """Test exporting with different language codes."""
    languages = ["en-US", "es-ES", "fr-FR"]

    for lang in languages:
        distribution = edxl_service.export_cop_update(sample_cop_update, language=lang)
        assert distribution.language == lang


# ============================================================================
# Content Object Tests
# ============================================================================


def test_content_object_keywords(edxl_service, sample_cop_update):
    """Test that content object has appropriate keywords."""
    distribution = edxl_service.export_cop_update(sample_cop_update)

    content = distribution.contentObject[0]
    assert content.contentKeyword is not None
    assert len(content.contentKeyword) >= 2

    keywords = {kw.value for kw in content.contentKeyword}
    assert "CAP" in keywords
    assert "COP Update" in keywords


def test_content_object_incident_info(edxl_service, sample_cop_update):
    """Test that content object includes incident information."""
    distribution = edxl_service.export_cop_update(sample_cop_update)

    content = distribution.contentObject[0]
    assert content.incidentID == str(sample_cop_update.id)
    assert content.incidentDescription == sample_cop_update.title


# ============================================================================
# Error Handling Tests
# ============================================================================


def test_export_validates_published_status(edxl_service, sample_cop_update):
    """Test that export validates published status."""
    # Unpublished COP update should fail (regardless of status)
    sample_cop_update.published_at = None

    with pytest.raises(ValueError, match="Cannot export unpublished COP update"):
        edxl_service.export_cop_update(sample_cop_update)


def test_export_requires_exportable_items(edxl_service, sample_cop_update):
    """Test that export requires at least one exportable item."""
    # Change all items to non-exportable section
    for item in sample_cop_update.line_items:
        item.section = "archived"

    with pytest.raises(ValueError, match="at least one verified or in-review item"):
        edxl_service.export_cop_update(sample_cop_update)


# ============================================================================
# Integration Tests
# ============================================================================


def test_full_export_workflow(edxl_service, sample_cop_update):
    """Test complete export workflow from COP update to EDXL-DE XML."""
    # Export to model
    distribution = edxl_service.export_cop_update(sample_cop_update)
    assert isinstance(distribution, EDXLDistribution)

    # Generate XML
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update)
    assert isinstance(xml_string, str)
    assert len(xml_string) > 0

    # Validate XML is parseable
    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)
    assert root is not None


def test_edxl_wraps_cap_correctly(edxl_service, sample_cop_update):
    """Test that EDXL-DE correctly wraps CAP content."""
    xml_string = edxl_service.generate_edxl_xml(sample_cop_update)

    xml_content = xml_string.split("\n", 1)[1]
    root = ET.fromstring(xml_content)

    # Find EDXL-DE elements
    distribution_id = root.find(".//{*}distributionID")
    assert distribution_id is not None

    # Find CAP elements within content object
    cap_alert = root.find(".//{urn:oasis:names:tc:emergency:cap:1.2}alert")
    assert cap_alert is not None

    # Verify CAP is inside contentObject
    content_object = root.find(".//{*}contentObject")
    assert content_object is not None

    # Verify CAP alert is child of xmlContent which is child of contentObject
    xml_content_elem = content_object.find(".//{*}xmlContent")
    assert xml_content_elem is not None

    cap_in_content = xml_content_elem.find(".//{*}alert")
    assert cap_in_content is not None
