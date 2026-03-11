"""CAP 1.2 (Common Alerting Protocol) models for emergency alert export.

Implements:
- FR-INT-002: CAP 1.2 export for COP updates
- Task S8-18: CAP 1.2 export service
- OASIS CAP 1.2 Specification: http://docs.oasis-open.org/emergency/cap/v1.2/

CAP provides a standardized format for public alerting and emergency notifications.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class CAPStatus(str, Enum):
    """CAP alert status values (§3.2.2.1)."""

    ACTUAL = "Actual"  # Actionable by all targeted recipients
    EXERCISE = "Exercise"  # Actionable only by designated exercise participants
    SYSTEM = "System"  # For messages that support alert network internal functions
    TEST = "Test"  # Technical testing only, all recipients disregard
    DRAFT = "Draft"  # A preliminary template or draft


class CAPMsgType(str, Enum):
    """CAP message type values (§3.2.2.2)."""

    ALERT = "Alert"  # Initial information requiring attention
    UPDATE = "Update"  # Updates and supercedes earlier message(s)
    CANCEL = "Cancel"  # Cancels earlier message(s)
    ACK = "Ack"  # Acknowledges receipt and acceptance of message(s)
    ERROR = "Error"  # Indicates rejection of message(s)


class CAPScope(str, Enum):
    """CAP scope values (§3.2.2.3)."""

    PUBLIC = "Public"  # For general dissemination to unrestricted audiences
    RESTRICTED = "Restricted"  # For dissemination only to specified addresses
    PRIVATE = "Private"  # For dissemination only to addresses in addresses field


class CAPCategory(str, Enum):
    """CAP category values (§3.2.3.1)."""

    GEO = "Geo"  # Geophysical (inc. landslide)
    MET = "Met"  # Meteorological (inc. flood)
    SAFETY = "Safety"  # General emergency and public safety
    SECURITY = "Security"  # Law enforcement, military, homeland and local/private security
    RESCUE = "Rescue"  # Rescue and recovery
    FIRE = "Fire"  # Fire suppression and rescue
    HEALTH = "Health"  # Medical and public health
    ENV = "Env"  # Pollution and other environmental
    TRANSPORT = "Transport"  # Public and private transportation
    INFRA = "Infra"  # Utility, telecommunication, other non-transport infrastructure
    CBRNE = "CBRNE"  # Chemical, Biological, Radiological, Nuclear or High-Yield Explosive threat or attack
    OTHER = "Other"  # Other events


class CAPUrgency(str, Enum):
    """CAP urgency values (§3.2.3.4)."""

    IMMEDIATE = "Immediate"  # Responsive action SHOULD be taken immediately
    EXPECTED = "Expected"  # Responsive action SHOULD be taken soon (within next hour)
    FUTURE = "Future"  # Responsive action SHOULD be taken in the near future
    PAST = "Past"  # Responsive action is no longer required
    UNKNOWN = "Unknown"  # Urgency not known


class CAPSeverity(str, Enum):
    """CAP severity values (§3.2.3.5)."""

    EXTREME = "Extreme"  # Extraordinary threat to life or property
    SEVERE = "Severe"  # Significant threat to life or property
    MODERATE = "Moderate"  # Possible threat to life or property
    MINOR = "Minor"  # Minimal to no known threat to life or property
    UNKNOWN = "Unknown"  # Severity unknown


class CAPCertainty(str, Enum):
    """CAP certainty values (§3.2.3.6)."""

    OBSERVED = "Observed"  # Determined to have occurred or to be ongoing
    LIKELY = "Likely"  # Likely (p > ~50%)
    POSSIBLE = "Possible"  # Possible but not likely (p <= ~50%)
    UNLIKELY = "Unlikely"  # Not expected to occur (p ~ 0)
    UNKNOWN = "Unknown"  # Certainty unknown


class CAPGeocode(BaseModel):
    """Geographic code for area definition (§3.2.4.3)."""

    valueName: str = Field(
        ...,
        description="Name of geocode system (e.g., FIPS6, UGC, etc.)",
    )
    value: str = Field(
        ...,
        description="Value in that geocode system",
    )


class CAPArea(BaseModel):
    """Geographic area affected by alert (§3.2.4).

    At least one of polygon, circle, or geocode MUST be present.
    """

    areaDesc: str = Field(
        ...,
        description="Text description of the affected area",
    )
    polygon: Optional[list[str]] = Field(
        default=None,
        description="Polygon coordinates (space-delimited lat,lon pairs)",
    )
    circle: Optional[list[str]] = Field(
        default=None,
        description="Circle (lat,lon radius_km)",
    )
    geocode: Optional[list[CAPGeocode]] = Field(
        default=None,
        description="Geographic codes identifying area",
    )
    altitude: Optional[float] = Field(
        default=None,
        description="Altitude in feet",
    )
    ceiling: Optional[float] = Field(
        default=None,
        description="Maximum altitude in feet",
    )


class CAPResource(BaseModel):
    """Digital asset associated with alert (§3.2.5)."""

    resourceDesc: str = Field(
        ...,
        description="Text description of the resource",
    )
    mimeType: str = Field(
        ...,
        description="MIME content type",
    )
    size: Optional[int] = Field(
        default=None,
        description="Size in bytes",
    )
    uri: Optional[str] = Field(
        default=None,
        description="URI to resource",
    )
    derefUri: Optional[str] = Field(
        default=None,
        description="Base64-encoded resource content",
    )
    digest: Optional[str] = Field(
        default=None,
        description="SHA-1 hash of resource",
    )


class CAPInfo(BaseModel):
    """Information block containing alert details (§3.2.3).

    Multiple info blocks allow for multi-language alerts.
    """

    language: str = Field(
        default="en-US",
        description="Language code (RFC 3066)",
    )
    category: list[CAPCategory] = Field(
        ...,
        description="Event categories (at least one required)",
    )
    event: str = Field(
        ...,
        description="Text denoting the type of event",
    )
    urgency: CAPUrgency = Field(
        ...,
        description="Urgency of response",
    )
    severity: CAPSeverity = Field(
        ...,
        description="Severity of event",
    )
    certainty: CAPCertainty = Field(
        ...,
        description="Certainty of event",
    )

    # Optional fields
    audience: Optional[str] = Field(
        default=None,
        description="Intended audience",
    )
    eventCode: Optional[list[dict[str, str]]] = Field(
        default=None,
        description="System-specific event codes",
    )
    effective: Optional[datetime] = Field(
        default=None,
        description="Effective time of information",
    )
    onset: Optional[datetime] = Field(
        default=None,
        description="Expected onset time",
    )
    expires: Optional[datetime] = Field(
        default=None,
        description="Expiry time of information",
    )
    senderName: Optional[str] = Field(
        default=None,
        description="Human-readable sender name",
    )
    headline: Optional[str] = Field(
        default=None,
        description="Brief human-readable headline",
    )
    description: Optional[str] = Field(
        default=None,
        description="Extended human-readable description",
    )
    instruction: Optional[str] = Field(
        default=None,
        description="Recommended action",
    )
    web: Optional[str] = Field(
        default=None,
        description="URL for additional information",
    )
    contact: Optional[str] = Field(
        default=None,
        description="Contact information",
    )
    parameter: Optional[list[dict[str, str]]] = Field(
        default=None,
        description="System-specific parameters",
    )

    # Geographic information
    area: Optional[list[CAPArea]] = Field(
        default=None,
        description="Affected areas",
    )

    # Resources
    resource: Optional[list[CAPResource]] = Field(
        default=None,
        description="Attached resources",
    )


class CAPAlert(BaseModel):
    """CAP 1.2 Alert root element (§3.2).

    Top-level container for emergency alert information conforming to
    OASIS Common Alerting Protocol v1.2 specification.
    """

    # Required elements
    identifier: str = Field(
        ...,
        description="Unique alert identifier",
    )
    sender: str = Field(
        ...,
        description="Identifier of alert originator (email or OID)",
    )
    sent: datetime = Field(
        ...,
        description="Time and date of alert origination",
    )
    status: CAPStatus = Field(
        ...,
        description="Alert handling status",
    )
    msgType: CAPMsgType = Field(
        ...,
        description="Message type",
    )
    scope: CAPScope = Field(
        ...,
        description="Distribution scope",
    )

    # Conditional elements
    source: Optional[str] = Field(
        default=None,
        description="Source of alert (for msgType=Error)",
    )
    restriction: Optional[str] = Field(
        default=None,
        description="Handling restrictions (required if scope=Restricted)",
    )
    addresses: Optional[str] = Field(
        default=None,
        description="Recipient addresses (required if scope=Private)",
    )
    code: Optional[list[str]] = Field(
        default=None,
        description="Special handling codes",
    )
    note: Optional[str] = Field(
        default=None,
        description="Clarifying note",
    )
    references: Optional[str] = Field(
        default=None,
        description="References to prior alerts",
    )
    incidents: Optional[str] = Field(
        default=None,
        description="Related incident identifiers",
    )

    # Info blocks (at least one required)
    info: list[CAPInfo] = Field(
        ...,
        description="Alert information blocks",
    )
