"""EDXL-DE 2.0 export service for COP updates.

Implements:
- FR-INT-002: EDXL-DE export for emergency management systems
- Task S8-19: EDXL-DE export with CAP content wrapping
- OASIS EDXL-DE 2.0 Specification compliance

This service converts verified COP updates into standardized EDXL-DE XML format
with embedded CAP content for integration with broader emergency management
distribution networks.
"""

import logging
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET

from bson import ObjectId

from integritykit.models.cop_update import COPUpdate
from integritykit.models.edxl import (
    DistributionStatus,
    DistributionType,
    EDXLContentObject,
    EDXLDistribution,
    TargetArea,
    ValueScheme,
)
from integritykit.services.cap_export import CAPExportService

logger = logging.getLogger(__name__)

# EDXL-DE namespace
EDXL_NAMESPACE = "urn:oasis:names:tc:emergency:EDXL:DE:2.0"


class EDXLExportService:
    """Service for exporting COP updates to EDXL-DE 2.0 format."""

    def __init__(
        self,
        sender_id: Optional[str] = None,
        cap_sender_id: Optional[str] = None,
    ):
        """Initialize EDXL-DE export service.

        Args:
            sender_id: EDXL sender identifier. Defaults to config setting.
            cap_sender_id: CAP sender identifier for embedded content. Defaults to config setting.
        """
        # Lazy import to avoid requiring settings at module import time
        if sender_id is None:
            try:
                from integritykit.config import settings

                sender_id = getattr(
                    settings, "edxl_sender_id", "integritykit@aidarena.org"
                )
            except Exception:
                sender_id = "integritykit@aidarena.org"

        if cap_sender_id is None:
            try:
                from integritykit.config import settings

                cap_sender_id = getattr(
                    settings, "cap_sender_id", "integritykit@aidarena.org"
                )
            except Exception:
                cap_sender_id = "integritykit@aidarena.org"

        self.sender_id = sender_id
        self.cap_service = CAPExportService(sender_id=cap_sender_id)

    # =========================================================================
    # Public API
    # =========================================================================

    def export_cop_update(
        self,
        cop_update: COPUpdate,
        language: str = "en-US",
    ) -> EDXLDistribution:
        """Export COP update to EDXL-DE Distribution model.

        Args:
            cop_update: COP update to export
            language: Language code (RFC 4646)

        Returns:
            EDXLDistribution model with embedded CAP content

        Raises:
            ValueError: If COP update is not publishable or lacks required data
        """
        # Validate export eligibility
        self._validate_exportable(cop_update)

        # Generate embedded CAP content
        cap_xml = self.cap_service.generate_cap_xml(cop_update, language=language)

        # Build content object with CAP
        content_object = EDXLContentObject(
            contentDescription=f"Common Alerting Protocol message for {cop_update.title}",
            contentKeyword=[
                ValueScheme(
                    value="CAP",
                    scheme="urn:oasis:names:tc:emergency:cap:1.2",
                ),
                ValueScheme(
                    value="COP Update",
                    scheme="urn:aidarena:integritykit",
                ),
            ],
            incidentID=str(cop_update.id),
            incidentDescription=cop_update.title,
            xmlContent=cap_xml,
            contentMimeType="application/xml",
            contentSize=len(cap_xml.encode("utf-8")),
        )

        # Build EDXL-DE distribution envelope
        distribution = EDXLDistribution(
            distributionID=self._generate_distribution_id(cop_update),
            senderID=self.sender_id,
            dateTimeSent=cop_update.published_at or datetime.utcnow(),
            distributionStatus=DistributionStatus.ACTUAL,
            distributionType=DistributionType.UPDATE,
            senderRole=[
                ValueScheme(
                    value="Emergency Management",
                    scheme="urn:aidarena:integritykit:roles",
                ),
            ],
            keyword=[
                ValueScheme(
                    value="COP",
                    scheme="urn:aidarena:integritykit:keywords",
                ),
                ValueScheme(
                    value="Common Operational Picture",
                    scheme="urn:aidarena:integritykit:keywords",
                ),
            ],
            language=language,
            contentObject=[content_object],
        )

        # Add target area if location data available
        target_area = self._build_target_area(cop_update)
        if target_area:
            distribution.targetArea = [target_area]

        return distribution

    def generate_edxl_xml(
        self,
        cop_update: COPUpdate,
        language: str = "en-US",
    ) -> str:
        """Generate EDXL-DE 2.0 XML for COP update.

        Args:
            cop_update: COP update to export
            language: Language code (RFC 4646)

        Returns:
            XML string with declaration

        Raises:
            ValueError: If COP update is not exportable
        """
        distribution = self.export_cop_update(cop_update, language)
        return self._serialize_to_xml(distribution)

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
                "COP update must have at least one verified or in-review item for EDXL-DE export"
            )

    # =========================================================================
    # Content Building
    # =========================================================================

    def _build_target_area(self, cop_update: COPUpdate) -> Optional[TargetArea]:
        """Build EDXL-DE target area from COP update location data.

        Args:
            cop_update: COP update with potential location data

        Returns:
            TargetArea if location data available, None otherwise
        """
        # This is simplified - in a full implementation, we would:
        # 1. Extract location data from evidence snapshots
        # 2. Convert to EDXL-DE circle or polygon format
        # 3. Add country/subdivision codes if available

        # For now, return None (geographic targeting is optional in EDXL-DE)
        # Real implementation would parse evidence_snapshots for location fields
        return None

    # =========================================================================
    # XML Generation
    # =========================================================================

    def _serialize_to_xml(self, distribution: EDXLDistribution) -> str:
        """Serialize EDXL-DE distribution to XML string.

        Args:
            distribution: EDXL-DE distribution model

        Returns:
            XML string with declaration
        """
        # Create root element with namespace
        root = ET.Element("EDXLDistribution", xmlns=EDXL_NAMESPACE)

        # Add required fields
        self._add_element(root, "distributionID", distribution.distributionID)
        self._add_element(root, "senderID", distribution.senderID)
        self._add_element(
            root, "dateTimeSent", self._format_datetime(distribution.dateTimeSent)
        )
        self._add_element(
            root, "distributionStatus", distribution.distributionStatus.value
        )
        self._add_element(
            root, "distributionType", distribution.distributionType.value
        )

        # Add optional fields
        if distribution.distributionReference:
            for ref in distribution.distributionReference:
                self._add_element(root, "distributionReference", ref)

        if distribution.senderRole:
            for role in distribution.senderRole:
                self._add_value_scheme_element(root, "senderRole", role)

        if distribution.recipientRole:
            for role in distribution.recipientRole:
                self._add_value_scheme_element(root, "recipientRole", role)

        if distribution.keyword:
            for keyword in distribution.keyword:
                self._add_value_scheme_element(root, "keyword", keyword)

        if distribution.distributionKind:
            for kind in distribution.distributionKind:
                self._add_value_scheme_element(root, "distributionKind", kind)

        if distribution.combinedConfidentiality:
            self._add_element(
                root, "combinedConfidentiality", distribution.combinedConfidentiality
            )

        if distribution.language:
            self._add_element(root, "language", distribution.language)

        # Add target areas
        if distribution.targetArea:
            for area in distribution.targetArea:
                self._add_target_area_element(root, area)

        # Add content objects
        for content_obj in distribution.contentObject:
            self._add_content_object_element(root, content_obj)

        # Convert to string with XML declaration
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")  # Pretty print
        xml_string = ET.tostring(root, encoding="unicode", method="xml")

        # Add XML declaration
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_string}'

    def _add_content_object_element(
        self, parent: ET.Element, content_obj: EDXLContentObject
    ) -> None:
        """Add content object element to XML tree.

        Args:
            parent: Parent XML element
            content_obj: Content object to add
        """
        content_elem = ET.SubElement(parent, "contentObject")

        # Optional fields
        if content_obj.contentDescription:
            self._add_element(
                content_elem, "contentDescription", content_obj.contentDescription
            )

        if content_obj.contentKeyword:
            for keyword in content_obj.contentKeyword:
                self._add_value_scheme_element(content_elem, "contentKeyword", keyword)

        if content_obj.incidentID:
            self._add_element(content_elem, "incidentID", content_obj.incidentID)

        if content_obj.incidentDescription:
            self._add_element(
                content_elem, "incidentDescription", content_obj.incidentDescription
            )

        # Content payload - add the appropriate one
        if content_obj.xmlContent:
            xml_content_elem = ET.SubElement(content_elem, "xmlContent")
            # Parse the CAP XML and embed it
            try:
                cap_tree = ET.fromstring(content_obj.xmlContent)
                xml_content_elem.append(cap_tree)
            except ET.ParseError:
                # If parsing fails, add as CDATA
                xml_content_elem.text = content_obj.xmlContent

        elif content_obj.jsonContent:
            self._add_element(content_elem, "jsonContent", content_obj.jsonContent)

        elif content_obj.embeddedFileContent:
            self._add_element(
                content_elem, "embeddedFileContent", content_obj.embeddedFileContent
            )

        # Content metadata
        if content_obj.contentMimeType:
            self._add_element(
                content_elem, "contentMimeType", content_obj.contentMimeType
            )

        if content_obj.contentSize:
            self._add_element(content_elem, "contentSize", str(content_obj.contentSize))

    def _add_target_area_element(self, parent: ET.Element, area: TargetArea) -> None:
        """Add target area element to XML tree.

        Args:
            parent: Parent XML element
            area: Target area to add
        """
        area_elem = ET.SubElement(parent, "targetArea")

        if area.circle:
            for circle in area.circle:
                self._add_element(area_elem, "circle", circle)

        if area.polygon:
            for polygon in area.polygon:
                self._add_element(area_elem, "polygon", polygon)

        if area.country:
            for country in area.country:
                self._add_element(area_elem, "country", country)

        if area.subdivision:
            for subdivision in area.subdivision:
                self._add_element(area_elem, "subdivision", subdivision)

        if area.locCodeUN:
            for loc_code in area.locCodeUN:
                self._add_element(area_elem, "locCodeUN", loc_code)

    def _add_value_scheme_element(
        self, parent: ET.Element, tag: str, value_scheme: ValueScheme
    ) -> None:
        """Add value-scheme element to XML tree.

        Args:
            parent: Parent XML element
            tag: Element tag name
            value_scheme: Value-scheme pair
        """
        elem = ET.SubElement(parent, tag)
        self._add_element(elem, "value", value_scheme.value)
        if value_scheme.scheme:
            self._add_element(elem, "scheme", value_scheme.scheme)

    def _add_element(self, parent: ET.Element, tag: str, text: str) -> ET.Element:
        """Add child element with text.

        Args:
            parent: Parent element
            tag: Element tag name
            text: Element text content

        Returns:
            Created element
        """
        elem = ET.SubElement(parent, tag)
        elem.text = str(text)
        return elem

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime to EDXL-DE ISO 8601 format.

        Args:
            dt: Datetime to format

        Returns:
            ISO 8601 formatted string with timezone
        """
        # EDXL-DE requires ISO 8601 with timezone
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        else:
            return dt.isoformat()

    def _generate_distribution_id(self, cop_update: COPUpdate) -> str:
        """Generate unique EDXL-DE distribution identifier.

        Args:
            cop_update: COP update

        Returns:
            Unique identifier string
        """
        # Format: edxl-cop-update-{id}
        return f"edxl-cop-update-{cop_update.id}"
