"""EDXL-DE 2.0 (Emergency Data Exchange Language - Distribution Element) models.

Implements:
- FR-INT-002: EDXL-DE export for COP updates
- Task S8-19: EDXL-DE 2.0 export service
- OASIS EDXL-DE 2.0 Specification: http://docs.oasis-open.org/emergency/edxl-de/v2.0/

EDXL-DE provides a standardized distribution envelope for routing emergency
messages. It wraps content (such as CAP alerts) for distribution across
emergency management systems.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DistributionStatus(str, Enum):
    """Distribution status values (§3.2.4)."""

    ACTUAL = "Actual"  # Actionable by all targeted recipients
    EXERCISE = "Exercise"  # Actionable only by designated exercise participants
    SYSTEM = "System"  # For messages that support system internal functions
    TEST = "Test"  # Technical testing only, all recipients disregard


class DistributionType(str, Enum):
    """Distribution type values (§3.2.5)."""

    REPORT = "Report"  # Initial information requiring attention
    UPDATE = "Update"  # Updates and supercedes earlier message(s)
    CANCEL = "Cancel"  # Cancels earlier message(s)
    ACK = "Ack"  # Acknowledges receipt and acceptance of message(s)
    ERROR = "Error"  # Indicates rejection of message(s)


class ValueScheme(BaseModel):
    """Value-scheme pair for extensible codes (§3.2.7)."""

    value: str = Field(
        ...,
        description="Value in the specified scheme",
    )
    scheme: Optional[str] = Field(
        default=None,
        description="URI identifying the coding scheme",
    )


class TargetArea(BaseModel):
    """Target area for distribution (§3.2.14)."""

    circle: Optional[list[str]] = Field(
        default=None,
        description="Circle (lat,lon radius_km)",
    )
    polygon: Optional[list[str]] = Field(
        default=None,
        description="Polygon coordinates (space-delimited lat,lon pairs)",
    )
    country: Optional[list[str]] = Field(
        default=None,
        description="ISO 3166-1 country codes",
    )
    subdivision: Optional[list[str]] = Field(
        default=None,
        description="Country subdivisions (e.g., state, province)",
    )
    locCodeUN: Optional[list[str]] = Field(
        default=None,
        description="UN/LOCODE location codes",
    )


class EDXLContentObject(BaseModel):
    """Content object embedded in EDXL-DE distribution (§3.2.15).

    Wraps the actual emergency message content (e.g., CAP XML).
    """

    contentDescription: Optional[str] = Field(
        default=None,
        description="Human-readable description of content",
    )
    contentKeyword: Optional[list[ValueScheme]] = Field(
        default=None,
        description="Keywords describing content",
    )
    incidentID: Optional[str] = Field(
        default=None,
        description="Related incident identifier",
    )
    incidentDescription: Optional[str] = Field(
        default=None,
        description="Human-readable incident description",
    )

    # Content payload - one of these must be present
    xmlContent: Optional[str] = Field(
        default=None,
        description="XML content (e.g., CAP alert)",
    )
    jsonContent: Optional[str] = Field(
        default=None,
        description="JSON content",
    )
    embeddedFileContent: Optional[str] = Field(
        default=None,
        description="Base64-encoded file content",
    )

    # Content metadata
    contentMimeType: Optional[str] = Field(
        default=None,
        description="MIME type of content (e.g., application/xml)",
    )
    contentSize: Optional[int] = Field(
        default=None,
        description="Size of content in bytes",
    )


class EDXLDistribution(BaseModel):
    """EDXL-DE 2.0 Distribution Element root.

    Top-level container for emergency message distribution conforming to
    OASIS EDXL-DE v2.0 specification.
    """

    # Required elements
    distributionID: str = Field(
        ...,
        description="Unique distribution identifier",
    )
    senderID: str = Field(
        ...,
        description="Identifier of distribution originator",
    )
    dateTimeSent: datetime = Field(
        ...,
        description="Time and date of distribution origination",
    )
    distributionStatus: DistributionStatus = Field(
        ...,
        description="Distribution handling status",
    )
    distributionType: DistributionType = Field(
        ...,
        description="Distribution message type",
    )

    # Optional elements
    distributionReference: Optional[list[str]] = Field(
        default=None,
        description="References to prior distributions",
    )
    senderRole: Optional[list[ValueScheme]] = Field(
        default=None,
        description="Sender role codes",
    )
    recipientRole: Optional[list[ValueScheme]] = Field(
        default=None,
        description="Intended recipient role codes",
    )
    keyword: Optional[list[ValueScheme]] = Field(
        default=None,
        description="Keywords describing distribution",
    )
    distributionKind: Optional[list[ValueScheme]] = Field(
        default=None,
        description="Distribution category codes",
    )
    combinedConfidentiality: Optional[str] = Field(
        default=None,
        description="Confidentiality level",
    )
    language: Optional[str] = Field(
        default=None,
        description="Language code (RFC 4646)",
    )

    # Geographic targeting
    targetArea: Optional[list[TargetArea]] = Field(
        default=None,
        description="Geographic distribution areas",
    )

    # Content objects (at least one required in practice)
    contentObject: list[EDXLContentObject] = Field(
        default_factory=list,
        description="Embedded content objects",
    )
