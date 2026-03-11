"""Unit tests for GeoJSON export service.

Tests:
- GeoJSON model validation
- COP update to GeoJSON conversion
- Location coordinate extraction
- Feature properties mapping
- RFC 7946 compliance
- Error handling for non-exportable updates
"""

import json
import pytest
from datetime import datetime, timedelta

from bson import ObjectId

from integritykit.models.cop_update import (
    COPUpdate,
    COPUpdateStatus,
    EvidenceSnapshot,
    PublishedLineItem,
)
from integritykit.models.geojson import (
    COPFeatureProperties,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONPoint,
    LocationCoordinates,
)
from integritykit.services.geojson_export import GeoJSONExportService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def geojson_service():
    """Provide GeoJSON export service instance."""
    return GeoJSONExportService()


@pytest.fixture
def sample_cop_update_with_location():
    """Provide sample COP update with location data."""
    now = datetime.utcnow()
    user_id = ObjectId()
    candidate_id_1 = ObjectId()
    candidate_id_2 = ObjectId()

    return COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=1,
        title="Shelter Status Update",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[
            PublishedLineItem(
                candidate_id=candidate_id_1,
                section="verified",
                status_label="VERIFIED",
                text="Shelter Alpha at 123 Main St has reached capacity.",
                citations=["https://slack.com/archives/C123/p1234567890"],
                was_edited=False,
            ),
            PublishedLineItem(
                candidate_id=candidate_id_2,
                section="in_review",
                status_label="IN REVIEW",
                text="Shelter Bravo at 456 Oak Ave is now open.",
                citations=["https://slack.com/archives/C123/p1234567891"],
                was_edited=False,
            ),
        ],
        evidence_snapshots=[
            EvidenceSnapshot(
                candidate_id=candidate_id_1,
                risk_tier="elevated",
                readiness_state="verified",
                fields_snapshot={
                    "what": "Shelter capacity reached",
                    "where": "123 Main St, Springfield",
                    "location": {"lat": 39.7817, "lon": -89.6501},
                    "when": {
                        "timestamp": now - timedelta(hours=2),
                        "description": "2 hours ago",
                    },
                    "who": "Emergency Management Agency",
                    "so_what": "Redirecting evacuees to Shelter Bravo",
                },
            ),
            EvidenceSnapshot(
                candidate_id=candidate_id_2,
                risk_tier="routine",
                readiness_state="in_review",
                fields_snapshot={
                    "what": "Shelter opening",
                    "where": "456 Oak Ave, Springfield",
                    "location": {"lat": 39.7890, "lon": -89.6600},
                    "when": {
                        "timestamp": now - timedelta(hours=1),
                        "description": "1 hour ago",
                    },
                    "who": "Red Cross",
                    "so_what": "Additional shelter capacity available",
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
def sample_cop_update_no_location():
    """Provide sample COP update without location data."""
    now = datetime.utcnow()
    user_id = ObjectId()
    candidate_id = ObjectId()

    return COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=2,
        title="General Update",
        status=COPUpdateStatus.PUBLISHED,
        line_items=[
            PublishedLineItem(
                candidate_id=candidate_id,
                section="verified",
                status_label="VERIFIED",
                text="General information update",
                citations=[],
                was_edited=False,
            ),
        ],
        evidence_snapshots=[
            EvidenceSnapshot(
                candidate_id=candidate_id,
                risk_tier="routine",
                readiness_state="verified",
                fields_snapshot={
                    "what": "General update",
                    "where": "Unknown location",
                },
            ),
        ],
        created_by=user_id,
        approved_by=user_id,
        approved_at=now - timedelta(minutes=5),
        published_at=now,
    )


@pytest.fixture
def unpublished_cop_update():
    """Provide unpublished COP update for testing validation."""
    return COPUpdate(
        id=ObjectId(),
        workspace_id="W12345",
        update_number=3,
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
# GeoJSON Model Tests
# ============================================================================


def test_geojson_point_model():
    """Test GeoJSON Point model validation."""
    point = GeoJSONPoint.from_lat_lon(lat=39.7817, lon=-89.6501)

    assert point.type == "Point"
    assert point.coordinates == (-89.6501, 39.7817)  # lon, lat order (GeoJSON standard)


def test_geojson_feature_model():
    """Test GeoJSON Feature model."""
    point = GeoJSONPoint.from_lat_lon(lat=39.7817, lon=-89.6501)
    properties = COPFeatureProperties(
        line_item_id="candidate-123",
        cop_update_id="update-456",
        cop_update_title="Test Update",
        text="Test feature",
        status="verified",
        status_label="VERIFIED",
    )

    feature = GeoJSONFeature(
        id="candidate-123",
        geometry=point,
        properties=properties,
    )

    assert feature.type == "Feature"
    assert feature.id == "candidate-123"
    assert feature.geometry.type == "Point"
    assert feature.properties.text == "Test feature"


def test_geojson_feature_collection_model():
    """Test GeoJSON FeatureCollection model."""
    collection = GeoJSONFeatureCollection(
        features=[],
        metadata={"test": "value"},
    )

    assert collection.type == "FeatureCollection"
    assert len(collection.features) == 0
    assert collection.metadata["test"] == "value"


# ============================================================================
# Export Tests
# ============================================================================


def test_export_cop_update_with_location(geojson_service, sample_cop_update_with_location):
    """Test exporting COP update with location data."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)

    assert collection.type == "FeatureCollection"
    assert len(collection.features) == 2  # Both items have location

    # Check first feature (verified)
    feature1 = collection.features[0]
    assert feature1.type == "Feature"
    assert feature1.geometry is not None
    assert feature1.geometry.type == "Point"
    assert feature1.geometry.coordinates == (-89.6501, 39.7817)
    assert feature1.properties.status == "verified"
    assert feature1.properties.risk_tier == "elevated"
    assert feature1.properties.what == "Shelter capacity reached"
    assert feature1.properties.where == "123 Main St, Springfield"

    # Check second feature (in_review)
    feature2 = collection.features[1]
    assert feature2.properties.status == "in_review"
    assert feature2.properties.risk_tier == "routine"

    # Check metadata
    assert collection.metadata is not None
    assert collection.metadata["cop_update_title"] == "Shelter Status Update"
    assert collection.metadata["feature_count"] == 2


def test_export_cop_update_no_location_exclude(geojson_service, sample_cop_update_no_location):
    """Test exporting COP update without location excludes features by default."""
    collection = geojson_service.export_cop_update(
        sample_cop_update_no_location,
        include_non_spatial=False,
    )

    assert collection.type == "FeatureCollection"
    assert len(collection.features) == 0  # No location, so excluded


def test_export_cop_update_no_location_include(geojson_service, sample_cop_update_no_location):
    """Test exporting COP update without location includes features with null geometry."""
    collection = geojson_service.export_cop_update(
        sample_cop_update_no_location,
        include_non_spatial=True,
    )

    assert collection.type == "FeatureCollection"
    assert len(collection.features) == 1

    feature = collection.features[0]
    assert feature.geometry is None  # No location = null geometry
    assert feature.properties.text == "General information update"
    assert feature.properties.where == "Unknown location"


def test_export_unpublished_update_raises_error(geojson_service, unpublished_cop_update):
    """Test that exporting unpublished COP update raises ValueError."""
    with pytest.raises(ValueError, match="Cannot export unpublished"):
        geojson_service.export_cop_update(unpublished_cop_update)


def test_generate_geojson_string(geojson_service, sample_cop_update_with_location):
    """Test generating GeoJSON as string."""
    geojson_str = geojson_service.generate_geojson_string(
        sample_cop_update_with_location,
        pretty=False,
    )

    # Should be valid JSON
    parsed = json.loads(geojson_str)
    assert parsed["type"] == "FeatureCollection"
    assert len(parsed["features"]) == 2


def test_generate_geojson_string_pretty(geojson_service, sample_cop_update_with_location):
    """Test generating pretty-printed GeoJSON."""
    geojson_str = geojson_service.generate_geojson_string(
        sample_cop_update_with_location,
        pretty=True,
    )

    # Should contain newlines and indentation
    assert "\n" in geojson_str
    assert "  " in geojson_str

    # Should still be valid JSON
    parsed = json.loads(geojson_str)
    assert parsed["type"] == "FeatureCollection"


# ============================================================================
# Location Extraction Tests
# ============================================================================


def test_extract_location_from_lat_lon_dict(geojson_service):
    """Test extracting location from lat/lon dictionary."""
    snapshot = EvidenceSnapshot(
        candidate_id=ObjectId(),
        fields_snapshot={
            "location": {"lat": 40.7128, "lon": -74.0060},
        },
    )

    coords = geojson_service._extract_location_coordinates(snapshot)

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_extract_location_from_coordinates_array(geojson_service):
    """Test extracting location from coordinates array."""
    snapshot = EvidenceSnapshot(
        candidate_id=ObjectId(),
        fields_snapshot={
            "coordinates": [40.7128, -74.0060],  # [lat, lon]
        },
    )

    coords = geojson_service._extract_location_coordinates(snapshot)

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_extract_location_from_geojson_style(geojson_service):
    """Test extracting location from GeoJSON-style coordinates."""
    snapshot = EvidenceSnapshot(
        candidate_id=ObjectId(),
        fields_snapshot={
            "location": {
                "coordinates": [-74.0060, 40.7128],  # [lon, lat] GeoJSON order
            },
        },
    )

    coords = geojson_service._extract_location_coordinates(snapshot)

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_extract_location_from_text(geojson_service):
    """Test extracting location from 'where' field text."""
    snapshot = EvidenceSnapshot(
        candidate_id=ObjectId(),
        fields_snapshot={
            "where": "Location at 40.7128, -74.0060",
        },
    )

    coords = geojson_service._extract_location_coordinates(snapshot)

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_extract_location_no_coordinates(geojson_service):
    """Test extracting location when no coordinates available."""
    snapshot = EvidenceSnapshot(
        candidate_id=ObjectId(),
        fields_snapshot={
            "where": "Unknown location",
        },
    )

    coords = geojson_service._extract_location_coordinates(snapshot)

    assert coords is None


def test_parse_coordinates_with_labels(geojson_service):
    """Test parsing coordinates with lat/lon labels."""
    coords = geojson_service._parse_coordinates_from_text("lat: 40.7128, lon: -74.0060")

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_parse_coordinates_simple_format(geojson_service):
    """Test parsing simple coordinate format."""
    coords = geojson_service._parse_coordinates_from_text("40.7128, -74.0060")

    assert coords is not None
    assert coords.latitude == 40.7128
    assert coords.longitude == -74.0060


def test_parse_coordinates_invalid_text(geojson_service):
    """Test parsing coordinates from text without coordinates."""
    coords = geojson_service._parse_coordinates_from_text("No coordinates here")

    assert coords is None


# ============================================================================
# Statistics Tests
# ============================================================================


def test_get_export_stats(geojson_service, sample_cop_update_with_location):
    """Test getting export statistics."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)
    stats = geojson_service.get_export_stats(collection)

    assert stats["total_features"] == 2
    assert stats["spatial_features"] == 2
    assert stats["non_spatial_features"] == 0
    assert stats["verified_features"] == 1
    assert stats["in_review_features"] == 1
    assert stats["has_metadata"] is True


def test_get_export_stats_with_non_spatial(geojson_service, sample_cop_update_no_location):
    """Test getting stats with non-spatial features."""
    collection = geojson_service.export_cop_update(
        sample_cop_update_no_location,
        include_non_spatial=True,
    )
    stats = geojson_service.get_export_stats(collection)

    assert stats["total_features"] == 1
    assert stats["spatial_features"] == 0
    assert stats["non_spatial_features"] == 1


# ============================================================================
# Feature Properties Tests
# ============================================================================


def test_feature_properties_complete(geojson_service, sample_cop_update_with_location):
    """Test that all expected properties are included in features."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)
    feature = collection.features[0]
    props = feature.properties

    # Check all required fields
    assert props.line_item_id is not None
    assert props.cop_update_id is not None
    assert props.cop_update_title == "Shelter Status Update"
    assert props.text is not None
    assert props.status in ["verified", "in_review"]
    assert props.status_label is not None

    # Check 5W fields
    assert props.what == "Shelter capacity reached"
    assert props.where == "123 Main St, Springfield"
    assert props.when_timestamp is not None
    assert props.when_description is not None
    assert props.who == "Emergency Management Agency"
    assert props.so_what == "Redirecting evacuees to Shelter Bravo"

    # Check metadata fields
    assert props.risk_tier == "elevated"
    assert props.published_at is not None
    assert props.citation_count == 1
    assert len(props.citations) == 1


def test_feature_properties_citations(geojson_service, sample_cop_update_with_location):
    """Test that citations are properly included."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)
    feature = collection.features[0]

    assert len(feature.properties.citations) == 1
    assert "slack.com" in feature.properties.citations[0]
    assert feature.properties.citation_count == 1


# ============================================================================
# RFC 7946 Compliance Tests
# ============================================================================


def test_rfc7946_coordinate_order(geojson_service, sample_cop_update_with_location):
    """Test that coordinates follow RFC 7946 [lon, lat] order."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)
    feature = collection.features[0]

    # GeoJSON requires [longitude, latitude] order (RFC 7946 §3.1.1)
    lon, lat = feature.geometry.coordinates
    assert -180 <= lon <= 180  # Valid longitude range
    assert -90 <= lat <= 90  # Valid latitude range

    # Specific check for our test data
    assert lon == -89.6501  # Longitude
    assert lat == 39.7817  # Latitude


def test_rfc7946_feature_structure(geojson_service, sample_cop_update_with_location):
    """Test that features follow RFC 7946 structure."""
    collection = geojson_service.export_cop_update(sample_cop_update_with_location)

    # FeatureCollection requirements (RFC 7946 §3.3)
    assert collection.type == "FeatureCollection"
    assert isinstance(collection.features, list)

    # Feature requirements (RFC 7946 §3.2)
    for feature in collection.features:
        assert feature.type == "Feature"
        assert hasattr(feature, "geometry")
        assert hasattr(feature, "properties")

        # Geometry requirements (RFC 7946 §3.1)
        if feature.geometry:
            assert hasattr(feature.geometry, "type")
            assert hasattr(feature.geometry, "coordinates")


def test_geojson_serialization(geojson_service, sample_cop_update_with_location):
    """Test that GeoJSON serializes to valid JSON."""
    geojson_str = geojson_service.generate_geojson_string(sample_cop_update_with_location)

    # Should be valid JSON
    parsed = json.loads(geojson_str)

    # Should have required GeoJSON structure
    assert "type" in parsed
    assert "features" in parsed
    assert parsed["type"] == "FeatureCollection"

    # Features should have required structure
    for feature in parsed["features"]:
        assert "type" in feature
        assert "geometry" in feature
        assert "properties" in feature
        assert feature["type"] == "Feature"
