"""GeoJSON export service for COP updates.

Implements:
- FR-INT-003: GeoJSON export for mapping platforms
- Task S8-21: GeoJSON export endpoint
- RFC 7946 GeoJSON Specification compliance

This service converts COP updates into RFC 7946 compliant GeoJSON
for integration with mapping platforms (ArcGIS, Mapbox, QGIS, Leaflet).
"""

import json
import logging
import re
from datetime import datetime
from typing import Optional

from bson import ObjectId

from integritykit.models.cop_update import COPUpdate, EvidenceSnapshot, PublishedLineItem
from integritykit.models.geojson import (
    COPFeatureProperties,
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    GeoJSONPoint,
    LocationCoordinates,
)

logger = logging.getLogger(__name__)


class GeoJSONExportService:
    """Service for exporting COP updates to GeoJSON format."""

    def __init__(self):
        """Initialize GeoJSON export service."""
        pass

    # =========================================================================
    # Public API
    # =========================================================================

    def export_cop_update(
        self,
        cop_update: COPUpdate,
        include_non_spatial: bool = False,
    ) -> GeoJSONFeatureCollection:
        """Export COP update to GeoJSON FeatureCollection.

        Args:
            cop_update: COP update to export
            include_non_spatial: If True, include items without location as features
                                with null geometry. Default: False (skip items without location)

        Returns:
            GeoJSON FeatureCollection

        Raises:
            ValueError: If COP update is not exportable
        """
        # Validate export eligibility
        self._validate_exportable(cop_update)

        # Build features from line items
        features = []

        for line_item in cop_update.line_items:
            # Only export verified and in-review items
            if line_item.section not in ["verified", "in_review"]:
                continue

            # Get evidence snapshot for this candidate
            evidence_snapshot = self._get_evidence_snapshot(
                cop_update, line_item.candidate_id
            )

            # Extract location from evidence snapshot
            location_coords = None
            if evidence_snapshot:
                location_coords = self._extract_location_coordinates(evidence_snapshot)

            # Skip items without location unless include_non_spatial is True
            if location_coords is None and not include_non_spatial:
                continue

            # Build feature
            feature = self._build_feature(
                cop_update=cop_update,
                line_item=line_item,
                evidence_snapshot=evidence_snapshot,
                location_coords=location_coords,
            )

            features.append(feature)

        # Build collection with metadata
        collection = GeoJSONFeatureCollection(
            features=features,
            metadata={
                "cop_update_id": str(cop_update.id),
                "cop_update_title": cop_update.title,
                "update_number": cop_update.update_number,
                "published_at": cop_update.published_at.isoformat()
                if cop_update.published_at
                else None,
                "workspace_id": cop_update.workspace_id,
                "feature_count": len(features),
                "export_timestamp": datetime.utcnow().isoformat(),
                "export_format": "GeoJSON RFC 7946",
                "coordinate_system": "WGS84 (EPSG:4326)",
            },
        )

        return collection

    def generate_geojson_string(
        self,
        cop_update: COPUpdate,
        include_non_spatial: bool = False,
        pretty: bool = False,
    ) -> str:
        """Generate GeoJSON as formatted JSON string.

        Args:
            cop_update: COP update to export
            include_non_spatial: Include items without location
            pretty: Pretty-print JSON with indentation

        Returns:
            GeoJSON string

        Raises:
            ValueError: If COP update is not exportable
        """
        collection = self.export_cop_update(cop_update, include_non_spatial)

        # Convert to JSON
        if pretty:
            return collection.model_dump_json(indent=2, exclude_none=True)
        else:
            return collection.model_dump_json(exclude_none=True)

    # =========================================================================
    # Validation
    # =========================================================================

    def _validate_exportable(self, cop_update: COPUpdate) -> None:
        """Validate that COP update can be exported.

        Args:
            cop_update: COP update to validate

        Raises:
            ValueError: If not exportable
        """
        # Must be published
        if cop_update.published_at is None:
            raise ValueError("Cannot export unpublished COP update")

        # Must have at least one verified or in-review item
        exportable_items = [
            item
            for item in cop_update.line_items
            if item.section in ["verified", "in_review"]
        ]

        if not exportable_items:
            raise ValueError(
                "COP update must have at least one verified or in-review item for GeoJSON export"
            )

    # =========================================================================
    # Feature Building
    # =========================================================================

    def _build_feature(
        self,
        cop_update: COPUpdate,
        line_item: PublishedLineItem,
        evidence_snapshot: Optional[EvidenceSnapshot],
        location_coords: Optional[LocationCoordinates],
    ) -> GeoJSONFeature:
        """Build GeoJSON Feature from line item.

        Args:
            cop_update: Parent COP update
            line_item: Line item to convert
            evidence_snapshot: Evidence snapshot for metadata
            location_coords: Parsed location coordinates (or None)

        Returns:
            GeoJSON Feature
        """
        # Build geometry (Point if coordinates available, else null)
        geometry = None
        if location_coords:
            geometry = GeoJSONPoint.from_lat_lon(
                lat=location_coords.latitude,
                lon=location_coords.longitude,
            )

        # Extract fields from evidence snapshot
        what = None
        where = None
        when_timestamp = None
        when_description = None
        who = None
        so_what = None
        risk_tier = None

        if evidence_snapshot:
            fields = evidence_snapshot.fields_snapshot
            what = fields.get("what")
            where = fields.get("where")
            who = fields.get("who")
            so_what = fields.get("so_what")
            risk_tier = evidence_snapshot.risk_tier

            # Extract when information
            when_data = fields.get("when", {})
            if isinstance(when_data, dict):
                when_timestamp = when_data.get("timestamp")
                when_description = when_data.get("description")
            elif isinstance(when_data, str):
                when_description = when_data

        # Build properties
        properties = COPFeatureProperties(
            line_item_id=str(line_item.candidate_id),
            cop_update_id=str(cop_update.id),
            cop_update_title=cop_update.title,
            text=line_item.text,
            what=what,
            where=where,
            when_timestamp=when_timestamp,
            when_description=when_description,
            who=who,
            so_what=so_what,
            status=line_item.section,
            status_label=line_item.status_label,
            risk_tier=risk_tier,
            published_at=cop_update.published_at,
            slack_permalink=cop_update.slack_permalink,
            citations=line_item.citations,
            citation_count=len(line_item.citations),
            was_edited=line_item.was_edited,
        )

        # Build feature
        feature = GeoJSONFeature(
            id=str(line_item.candidate_id),
            geometry=geometry,
            properties=properties,
        )

        return feature

    # =========================================================================
    # Location Extraction
    # =========================================================================

    def _get_evidence_snapshot(
        self, cop_update: COPUpdate, candidate_id: ObjectId
    ) -> Optional[EvidenceSnapshot]:
        """Get evidence snapshot for a candidate.

        Args:
            cop_update: COP update containing snapshots
            candidate_id: Candidate ID to find

        Returns:
            Evidence snapshot or None if not found
        """
        for snapshot in cop_update.evidence_snapshots:
            if snapshot.candidate_id == candidate_id:
                return snapshot
        return None

    def _extract_location_coordinates(
        self, evidence_snapshot: EvidenceSnapshot
    ) -> Optional[LocationCoordinates]:
        """Extract location coordinates from evidence snapshot.

        This method attempts to parse location data from the fields_snapshot.
        It looks for coordinates in various formats:

        1. Explicit coordinates object: {"lat": 40.7, "lon": -74.0}
        2. Coordinates array: [lat, lon] or [lon, lat]
        3. Parsed from "where" field if it contains coordinate patterns

        Args:
            evidence_snapshot: Evidence snapshot containing fields

        Returns:
            LocationCoordinates if found, None otherwise
        """
        fields = evidence_snapshot.fields_snapshot

        # Check for explicit location/coordinates field
        if "location" in fields:
            location_data = fields["location"]
            coords = self._parse_coordinates_object(location_data)
            if coords:
                return coords

        # Check for coordinates in fields_snapshot
        if "coordinates" in fields:
            coords_data = fields["coordinates"]
            coords = self._parse_coordinates_object(coords_data)
            if coords:
                return coords

        # Try to parse from "where" field
        where = fields.get("where", "")
        if where and isinstance(where, str):
            coords = self._parse_coordinates_from_text(where)
            if coords:
                return coords

        return None

    def _parse_coordinates_object(self, data: any) -> Optional[LocationCoordinates]:
        """Parse coordinates from an object.

        Handles formats:
        - {"lat": 40.7, "lon": -74.0}
        - {"latitude": 40.7, "longitude": -74.0}
        - [40.7, -74.0] (lat, lon order)
        - {"coordinates": [lon, lat]} (GeoJSON order)

        Args:
            data: Data to parse

        Returns:
            LocationCoordinates if valid, None otherwise
        """
        if isinstance(data, dict):
            # Check for lat/lon or latitude/longitude keys
            lat = data.get("lat") or data.get("latitude")
            lon = data.get("lon") or data.get("longitude")

            if lat is not None and lon is not None:
                try:
                    return LocationCoordinates(
                        latitude=float(lat),
                        longitude=float(lon),
                        altitude=data.get("altitude"),
                        accuracy=data.get("accuracy"),
                    )
                except (ValueError, TypeError):
                    pass

            # Check for GeoJSON-style coordinates array
            if "coordinates" in data:
                coords_array = data["coordinates"]
                if isinstance(coords_array, list) and len(coords_array) >= 2:
                    try:
                        # GeoJSON uses [lon, lat] order
                        return LocationCoordinates(
                            longitude=float(coords_array[0]),
                            latitude=float(coords_array[1]),
                        )
                    except (ValueError, TypeError, IndexError):
                        pass

        elif isinstance(data, (list, tuple)) and len(data) >= 2:
            # Array format - assume [lat, lon] (common convention)
            try:
                return LocationCoordinates(
                    latitude=float(data[0]),
                    longitude=float(data[1]),
                )
            except (ValueError, TypeError, IndexError):
                pass

        return None

    def _parse_coordinates_from_text(self, text: str) -> Optional[LocationCoordinates]:
        """Parse coordinates from text using regex patterns.

        Handles formats:
        - "40.7128° N, 74.0060° W"
        - "40.7128, -74.0060"
        - "(40.7128, -74.0060)"
        - "lat: 40.7128, lon: -74.0060"

        Args:
            text: Text to parse

        Returns:
            LocationCoordinates if found, None otherwise
        """
        # Pattern 1: Decimal degrees with optional labels
        # Example: "40.7128, -74.0060" or "lat: 40.7128, lon: -74.0060"
        pattern1 = r"(?:lat(?:itude)?:?\s*)?(-?\d+\.?\d*)[°,\s]+(?:lon(?:gitude)?:?\s*)?(-?\d+\.?\d*)"
        match = re.search(pattern1, text, re.IGNORECASE)

        if match:
            try:
                lat = float(match.group(1))
                lon = float(match.group(2))

                # Validate ranges
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return LocationCoordinates(latitude=lat, longitude=lon)
            except ValueError:
                pass

        # Pattern 2: Degrees/minutes/seconds (DMS) format
        # Example: "40°42'46\"N 74°00'22\"W"
        # This is more complex - for now, skip DMS parsing
        # Could be added in future enhancement

        return None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_export_stats(self, collection: GeoJSONFeatureCollection) -> dict:
        """Get statistics about exported GeoJSON.

        Args:
            collection: GeoJSON FeatureCollection

        Returns:
            Dictionary with export statistics
        """
        total_features = len(collection.features)
        spatial_features = sum(1 for f in collection.features if f.geometry is not None)
        non_spatial_features = total_features - spatial_features

        verified_features = sum(
            1 for f in collection.features if f.properties.status == "verified"
        )
        in_review_features = sum(
            1 for f in collection.features if f.properties.status == "in_review"
        )

        return {
            "total_features": total_features,
            "spatial_features": spatial_features,
            "non_spatial_features": non_spatial_features,
            "verified_features": verified_features,
            "in_review_features": in_review_features,
            "has_metadata": collection.metadata is not None,
        }
