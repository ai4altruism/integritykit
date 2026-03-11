"""GeoJSON models for spatial data export.

Implements:
- FR-INT-003: GeoJSON export for mapping platforms
- Task S8-21: GeoJSON export endpoint
- RFC 7946 GeoJSON Specification compliance

This module provides RFC 7946 compliant GeoJSON models for exporting
COP updates to mapping and GIS platforms.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class GeometryType(str, Enum):
    """GeoJSON geometry types."""

    POINT = "Point"
    LINE_STRING = "LineString"
    POLYGON = "Polygon"
    MULTI_POINT = "MultiPoint"
    MULTI_LINE_STRING = "MultiLineString"
    MULTI_POLYGON = "MultiPolygon"
    GEOMETRY_COLLECTION = "GeometryCollection"


class GeoJSONPoint(BaseModel):
    """GeoJSON Point geometry (RFC 7946 §3.1.2).

    A Point geometry represents a single position in geographic space.
    Coordinates are [longitude, latitude] in WGS84 (EPSG:4326).
    """

    type: Literal["Point"] = Field(
        default="Point",
        description="Geometry type",
    )
    coordinates: tuple[float, float] = Field(
        ...,
        description="[longitude, latitude] in decimal degrees (WGS84)",
    )

    @classmethod
    def from_lat_lon(cls, lat: float, lon: float) -> "GeoJSONPoint":
        """Create Point from latitude/longitude.

        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees

        Returns:
            GeoJSON Point geometry
        """
        return cls(coordinates=(lon, lat))


class GeoJSONPolygon(BaseModel):
    """GeoJSON Polygon geometry (RFC 7946 §3.1.6).

    A Polygon geometry represents a closed shape. The first and last
    coordinates must be identical to close the ring.
    """

    type: Literal["Polygon"] = Field(
        default="Polygon",
        description="Geometry type",
    )
    coordinates: list[list[tuple[float, float]]] = Field(
        ...,
        description="Array of linear rings, first is exterior, rest are holes",
    )


class GeoJSONLineString(BaseModel):
    """GeoJSON LineString geometry (RFC 7946 §3.1.4).

    A LineString geometry represents a series of connected points.
    """

    type: Literal["LineString"] = Field(
        default="LineString",
        description="Geometry type",
    )
    coordinates: list[tuple[float, float]] = Field(
        ...,
        description="Array of [longitude, latitude] positions",
    )


# Union of supported geometry types
GeoJSONGeometry = Union[GeoJSONPoint, GeoJSONPolygon, GeoJSONLineString]


class COPFeatureProperties(BaseModel):
    """Properties for a COP update feature.

    These properties provide the non-spatial attributes for each
    COP line item exported to GeoJSON.
    """

    # Line item identification
    line_item_id: str = Field(
        ...,
        description="COP candidate ID",
    )
    cop_update_id: str = Field(
        ...,
        description="Parent COP update ID",
    )
    cop_update_title: str = Field(
        ...,
        description="COP update title",
    )

    # Content fields (5W framework)
    text: str = Field(
        ...,
        description="Line item text content",
    )
    what: Optional[str] = Field(
        default=None,
        description="What is happening/happened",
    )
    where: Optional[str] = Field(
        default=None,
        description="Location description",
    )
    when_timestamp: Optional[datetime] = Field(
        default=None,
        description="Event timestamp (ISO 8601)",
    )
    when_description: Optional[str] = Field(
        default=None,
        description="Human-readable time description",
    )
    who: Optional[str] = Field(
        default=None,
        description="Who is affected or involved",
    )
    so_what: Optional[str] = Field(
        default=None,
        description="Operational relevance",
    )

    # Status and classification
    status: str = Field(
        ...,
        description="Verification status (verified, in_review)",
    )
    status_label: str = Field(
        ...,
        description="Display status (VERIFIED, IN REVIEW)",
    )
    risk_tier: Optional[str] = Field(
        default=None,
        description="Risk tier (routine, elevated, high_stakes)",
    )
    category: Optional[str] = Field(
        default=None,
        description="Category or topic type",
    )

    # Publishing metadata
    published_at: Optional[datetime] = Field(
        default=None,
        description="When COP update was published",
    )
    slack_permalink: Optional[str] = Field(
        default=None,
        description="Link to published Slack message",
    )

    # Evidence and citations
    citations: list[str] = Field(
        default_factory=list,
        description="Citation URLs (Slack permalinks, external sources)",
    )
    citation_count: int = Field(
        default=0,
        description="Number of citations",
    )

    # Editing metadata
    was_edited: bool = Field(
        default=False,
        description="Whether facilitator edited the text",
    )


class GeoJSONFeature(BaseModel):
    """GeoJSON Feature (RFC 7946 §3.2).

    A Feature represents a spatially bounded entity with properties.
    """

    type: Literal["Feature"] = Field(
        default="Feature",
        description="Feature type",
    )
    id: Optional[str] = Field(
        default=None,
        description="Feature identifier (line item ID)",
    )
    geometry: Optional[GeoJSONGeometry] = Field(
        default=None,
        description="Feature geometry (can be null for non-spatial features)",
    )
    properties: COPFeatureProperties = Field(
        ...,
        description="Feature properties",
    )


class GeoJSONFeatureCollection(BaseModel):
    """GeoJSON FeatureCollection (RFC 7946 §3.3).

    A FeatureCollection contains multiple Features.
    """

    type: Literal["FeatureCollection"] = Field(
        default="FeatureCollection",
        description="Collection type",
    )
    features: list[GeoJSONFeature] = Field(
        default_factory=list,
        description="Array of features",
    )
    # Optional metadata
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Collection-level metadata (not part of RFC 7946, custom extension)",
    )


# ============================================================================
# Helper Models for Location Parsing
# ============================================================================


class LocationCoordinates(BaseModel):
    """Parsed location coordinates.

    Helper model for extracting location data from COP candidate fields.
    """

    latitude: float = Field(
        ...,
        description="Latitude in decimal degrees (WGS84)",
        ge=-90.0,
        le=90.0,
    )
    longitude: float = Field(
        ...,
        description="Longitude in decimal degrees (WGS84)",
        ge=-180.0,
        le=180.0,
    )
    altitude: Optional[float] = Field(
        default=None,
        description="Altitude in meters (optional)",
    )
    accuracy: Optional[float] = Field(
        default=None,
        description="Horizontal accuracy in meters (optional)",
    )


class LocationData(BaseModel):
    """Complete location data for a COP item.

    Helper model for managing location information before
    converting to GeoJSON geometry.
    """

    coordinates: Optional[LocationCoordinates] = Field(
        default=None,
        description="Parsed coordinates",
    )
    address: Optional[str] = Field(
        default=None,
        description="Human-readable address or location description",
    )
    place_name: Optional[str] = Field(
        default=None,
        description="Named location (e.g., 'Shelter Alpha', 'City Hall')",
    )
    geocoded: bool = Field(
        default=False,
        description="Whether coordinates were obtained via geocoding",
    )
