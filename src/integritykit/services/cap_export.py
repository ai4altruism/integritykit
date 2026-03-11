"""CAP 1.2 export service for COP updates.

Implements:
- FR-INT-002: CAP 1.2 export for public alerting systems
- Task S8-18: CAP export with geospatial encoding
- OASIS CAP 1.2 Specification compliance

This service converts verified COP updates into standardized CAP XML format
for integration with public alerting platforms and emergency management systems.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
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
from integritykit.models.cop_candidate import ReadinessState, RiskTier
from integritykit.models.cop_update import COPUpdate, PublishedLineItem

logger = logging.getLogger(__name__)

# CAP namespace
CAP_NAMESPACE = "urn:oasis:names:tc:emergency:cap:1.2"


class CAPExportService:
    """Service for exporting COP updates to CAP 1.2 format."""

    def __init__(self, sender_id: Optional[str] = None):
        """Initialize CAP export service.

        Args:
            sender_id: Sender identifier (email or OID). Defaults to config setting.
        """
        # Lazy import to avoid requiring settings at module import time
        if sender_id is None:
            try:
                from integritykit.config import settings
                sender_id = getattr(settings, "cap_sender_id", "integritykit@aidarena.org")
            except Exception:
                sender_id = "integritykit@aidarena.org"

        self.sender_id = sender_id

    # =========================================================================
    # Public API
    # =========================================================================

    def export_cop_update(
        self,
        cop_update: COPUpdate,
        language: str = "en-US",
    ) -> CAPAlert:
        """Export COP update to CAP Alert model.

        Args:
            cop_update: COP update to export
            language: Language code (RFC 3066)

        Returns:
            CAPAlert model

        Raises:
            ValueError: If COP update is not publishable or lacks required data
        """
        # Validate export eligibility
        self._validate_exportable(cop_update)

        # Build CAP alert
        alert = CAPAlert(
            identifier=self._generate_identifier(cop_update),
            sender=self.sender_id,
            sent=cop_update.published_at or datetime.utcnow(),
            status=CAPStatus.ACTUAL,
            msgType=CAPMsgType.UPDATE,
            scope=CAPScope.PUBLIC,
            info=[],
        )

        # Add info block for verified items
        verified_items = [
            item for item in cop_update.line_items if item.section == "verified"
        ]

        if verified_items:
            info = self._build_info_block(
                cop_update=cop_update,
                line_items=verified_items,
                language=language,
                certainty=CAPCertainty.OBSERVED,
            )
            alert.info.append(info)

        # Add info block for in-review items (with lower certainty)
        in_review_items = [
            item for item in cop_update.line_items if item.section == "in_review"
        ]

        if in_review_items:
            info = self._build_info_block(
                cop_update=cop_update,
                line_items=in_review_items,
                language=language,
                certainty=CAPCertainty.LIKELY,
            )
            alert.info.append(info)

        if not alert.info:
            raise ValueError("No verified or in-review items to export")

        return alert

    def generate_cap_xml(
        self,
        cop_update: COPUpdate,
        language: str = "en-US",
    ) -> str:
        """Generate CAP 1.2 XML for COP update.

        Args:
            cop_update: COP update to export
            language: Language code (RFC 3066)

        Returns:
            XML string with declaration

        Raises:
            ValueError: If COP update is not exportable
        """
        alert = self.export_cop_update(cop_update, language)
        return self._serialize_to_xml(alert)

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
                "COP update must have at least one verified or in-review item for CAP export"
            )

    # =========================================================================
    # CAP Info Block Construction
    # =========================================================================

    def _build_info_block(
        self,
        cop_update: COPUpdate,
        line_items: list[PublishedLineItem],
        language: str,
        certainty: CAPCertainty,
    ) -> CAPInfo:
        """Build CAP info block from line items.

        Args:
            cop_update: Source COP update
            line_items: Line items to include
            language: Language code
            certainty: Certainty level for this info block

        Returns:
            CAPInfo block
        """
        # Determine category from line items
        categories = self._determine_categories(line_items)

        # Determine urgency and severity from risk tier
        urgency, severity = self._map_risk_tier_to_urgency_severity(cop_update)

        # Build headline and description
        headline = cop_update.title
        description = self._build_description(line_items)

        # Build areas from line items with location data
        areas = self._build_areas(line_items)

        info = CAPInfo(
            language=language,
            category=categories,
            event=cop_update.title,
            urgency=urgency,
            severity=severity,
            certainty=certainty,
            headline=headline,
            description=description,
            effective=cop_update.published_at or datetime.utcnow(),
            senderName="Aid Arena Integrity Kit",
            web=cop_update.slack_permalink,
        )

        if areas:
            info.area = areas

        return info

    # =========================================================================
    # Mapping Logic
    # =========================================================================

    def _determine_categories(
        self, line_items: list[PublishedLineItem]
    ) -> list[CAPCategory]:
        """Determine CAP categories from line items.

        Uses heuristics based on line item text content.

        Args:
            line_items: Line items to analyze

        Returns:
            List of CAP categories
        """
        categories = set()

        # Default to Safety for general emergency info
        categories.add(CAPCategory.SAFETY)

        # Analyze text for category hints
        combined_text = " ".join(item.text.lower() for item in line_items)

        if any(
            keyword in combined_text
            for keyword in [
                "shelter",
                "evacuation",
                "displaced",
                "refugee",
                "housing",
            ]
        ):
            categories.add(CAPCategory.INFRA)

        if any(
            keyword in combined_text
            for keyword in ["medical", "health", "hospital", "clinic", "injury"]
        ):
            categories.add(CAPCategory.HEALTH)

        if any(
            keyword in combined_text
            for keyword in ["fire", "wildfire", "burning", "smoke"]
        ):
            categories.add(CAPCategory.FIRE)

        if any(
            keyword in combined_text
            for keyword in ["rescue", "search", "missing", "trapped"]
        ):
            categories.add(CAPCategory.RESCUE)

        if any(
            keyword in combined_text
            for keyword in ["road", "bridge", "transport", "route", "highway"]
        ):
            categories.add(CAPCategory.TRANSPORT)

        return list(categories)

    def _map_risk_tier_to_urgency_severity(
        self, cop_update: COPUpdate
    ) -> tuple[CAPUrgency, CAPSeverity]:
        """Map risk tier to CAP urgency and severity.

        Args:
            cop_update: COP update containing risk tier info

        Returns:
            Tuple of (urgency, severity)
        """
        # Determine highest risk tier from line items
        # This requires looking at evidence snapshots if available
        risk_tiers = []
        for snapshot in cop_update.evidence_snapshots:
            risk_tier_str = snapshot.risk_tier
            try:
                risk_tiers.append(RiskTier(risk_tier_str))
            except ValueError:
                pass

        # Default to routine if no risk tiers found
        highest_risk = RiskTier.ROUTINE
        if risk_tiers:
            if RiskTier.HIGH_STAKES in risk_tiers:
                highest_risk = RiskTier.HIGH_STAKES
            elif RiskTier.ELEVATED in risk_tiers:
                highest_risk = RiskTier.ELEVATED

        # Map to CAP values
        if highest_risk == RiskTier.HIGH_STAKES:
            return CAPUrgency.IMMEDIATE, CAPSeverity.SEVERE
        elif highest_risk == RiskTier.ELEVATED:
            return CAPUrgency.EXPECTED, CAPSeverity.MODERATE
        else:
            return CAPUrgency.FUTURE, CAPSeverity.MINOR

    def _map_readiness_to_certainty(
        self, readiness_state: ReadinessState
    ) -> CAPCertainty:
        """Map readiness state to CAP certainty.

        Args:
            readiness_state: Readiness state from candidate

        Returns:
            CAP certainty level
        """
        if readiness_state == ReadinessState.VERIFIED:
            return CAPCertainty.OBSERVED
        elif readiness_state == ReadinessState.IN_REVIEW:
            return CAPCertainty.LIKELY
        else:
            return CAPCertainty.POSSIBLE

    # =========================================================================
    # Content Building
    # =========================================================================

    def _build_description(self, line_items: list[PublishedLineItem]) -> str:
        """Build description from line items.

        Args:
            line_items: Line items to include

        Returns:
            Combined description text
        """
        descriptions = []

        for item in line_items:
            # Include status label for context
            status = item.status_label
            text = item.text

            descriptions.append(f"[{status}] {text}")

        return "\n\n".join(descriptions)

    def _build_areas(self, line_items: list[PublishedLineItem]) -> list[CAPArea]:
        """Build CAP areas from line items with location data.

        Args:
            line_items: Line items to extract locations from

        Returns:
            List of CAP areas
        """
        areas = []

        # This is simplified - in a full implementation, we would:
        # 1. Extract location data from candidate fields
        # 2. Convert to CAP circle or polygon format
        # 3. Add geocodes if available

        # For now, return a single generic area if any items exist
        if line_items:
            areas.append(
                CAPArea(
                    areaDesc="Area of operations",
                    # Could add circle/polygon/geocode if location data available
                )
            )

        return areas

    # =========================================================================
    # XML Generation
    # =========================================================================

    def _serialize_to_xml(self, alert: CAPAlert) -> str:
        """Serialize CAP alert to XML string.

        Args:
            alert: CAP alert model

        Returns:
            XML string with declaration
        """
        # Create root element with namespace
        root = ET.Element("alert", xmlns=CAP_NAMESPACE)

        # Add required fields
        self._add_element(root, "identifier", alert.identifier)
        self._add_element(root, "sender", alert.sender)
        self._add_element(root, "sent", self._format_datetime(alert.sent))
        self._add_element(root, "status", alert.status.value)
        self._add_element(root, "msgType", alert.msgType.value)
        self._add_element(root, "scope", alert.scope.value)

        # Add optional fields
        if alert.source:
            self._add_element(root, "source", alert.source)
        if alert.restriction:
            self._add_element(root, "restriction", alert.restriction)
        if alert.addresses:
            self._add_element(root, "addresses", alert.addresses)
        if alert.code:
            for code in alert.code:
                self._add_element(root, "code", code)
        if alert.note:
            self._add_element(root, "note", alert.note)
        if alert.references:
            self._add_element(root, "references", alert.references)
        if alert.incidents:
            self._add_element(root, "incidents", alert.incidents)

        # Add info blocks
        for info in alert.info:
            self._add_info_element(root, info)

        # Convert to string with XML declaration
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")  # Pretty print
        xml_string = ET.tostring(root, encoding="unicode", method="xml")

        # Add XML declaration
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_string}'

    def _add_info_element(self, parent: ET.Element, info: CAPInfo) -> None:
        """Add info block to XML tree.

        Args:
            parent: Parent XML element
            info: CAP info block
        """
        info_elem = ET.SubElement(parent, "info")

        # Required fields
        self._add_element(info_elem, "language", info.language)
        for category in info.category:
            self._add_element(info_elem, "category", category.value)
        self._add_element(info_elem, "event", info.event)
        self._add_element(info_elem, "urgency", info.urgency.value)
        self._add_element(info_elem, "severity", info.severity.value)
        self._add_element(info_elem, "certainty", info.certainty.value)

        # Optional fields
        if info.audience:
            self._add_element(info_elem, "audience", info.audience)
        if info.eventCode:
            for code in info.eventCode:
                code_elem = ET.SubElement(info_elem, "eventCode")
                self._add_element(code_elem, "valueName", code.get("valueName", ""))
                self._add_element(code_elem, "value", code.get("value", ""))
        if info.effective:
            self._add_element(
                info_elem, "effective", self._format_datetime(info.effective)
            )
        if info.onset:
            self._add_element(info_elem, "onset", self._format_datetime(info.onset))
        if info.expires:
            self._add_element(info_elem, "expires", self._format_datetime(info.expires))
        if info.senderName:
            self._add_element(info_elem, "senderName", info.senderName)
        if info.headline:
            self._add_element(info_elem, "headline", info.headline)
        if info.description:
            self._add_element(info_elem, "description", info.description)
        if info.instruction:
            self._add_element(info_elem, "instruction", info.instruction)
        if info.web:
            self._add_element(info_elem, "web", info.web)
        if info.contact:
            self._add_element(info_elem, "contact", info.contact)

        # Area elements
        if info.area:
            for area in info.area:
                self._add_area_element(info_elem, area)

        # Resource elements
        if info.resource:
            for resource in info.resource:
                resource_elem = ET.SubElement(info_elem, "resource")
                self._add_element(
                    resource_elem, "resourceDesc", resource.resourceDesc
                )
                self._add_element(resource_elem, "mimeType", resource.mimeType)
                if resource.size:
                    self._add_element(resource_elem, "size", str(resource.size))
                if resource.uri:
                    self._add_element(resource_elem, "uri", resource.uri)
                if resource.derefUri:
                    self._add_element(resource_elem, "derefUri", resource.derefUri)
                if resource.digest:
                    self._add_element(resource_elem, "digest", resource.digest)

    def _add_area_element(self, parent: ET.Element, area: CAPArea) -> None:
        """Add area element to XML tree.

        Args:
            parent: Parent XML element
            area: CAP area
        """
        area_elem = ET.SubElement(parent, "area")

        # Required field
        self._add_element(area_elem, "areaDesc", area.areaDesc)

        # Optional fields
        if area.polygon:
            for polygon in area.polygon:
                self._add_element(area_elem, "polygon", polygon)
        if area.circle:
            for circle in area.circle:
                self._add_element(area_elem, "circle", circle)
        if area.geocode:
            for geocode in area.geocode:
                geocode_elem = ET.SubElement(area_elem, "geocode")
                self._add_element(geocode_elem, "valueName", geocode.valueName)
                self._add_element(geocode_elem, "value", geocode.value)
        if area.altitude:
            self._add_element(area_elem, "altitude", str(area.altitude))
        if area.ceiling:
            self._add_element(area_elem, "ceiling", str(area.ceiling))

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
        """Format datetime to CAP ISO 8601 format.

        Args:
            dt: Datetime to format

        Returns:
            ISO 8601 formatted string with timezone
        """
        # CAP requires ISO 8601 with timezone (§2.3.1)
        # Format: YYYY-MM-DDThh:mm:ss±hh:mm
        if dt.tzinfo is None:
            # Assume UTC if no timezone
            return dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        else:
            return dt.isoformat()

    def _generate_identifier(self, cop_update: COPUpdate) -> str:
        """Generate unique CAP identifier.

        Args:
            cop_update: COP update

        Returns:
            Unique identifier string
        """
        # Format: cop-update-{id}
        return f"cop-update-{cop_update.id}"
