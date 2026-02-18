"""Redaction rules and patterns for sensitive information.

Implements:
- NFR-PRIVACY-002: Configurable redaction rules for sensitive info
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class SensitiveCategory(StrEnum):
    """Categories of sensitive information that can be redacted."""

    PII_EMAIL = "pii_email"
    PII_PHONE = "pii_phone"
    PII_ADDRESS = "pii_address"
    PII_NAME = "pii_name"
    VULNERABLE_LOCATION = "vulnerable_location"
    FINANCIAL = "financial"
    MEDICAL = "medical"
    CUSTOM = "custom"


class RedactionRuleType(StrEnum):
    """Types of redaction rules."""

    REGEX = "regex"
    KEYWORD = "keyword"
    PATTERN = "pattern"


class RedactionRule(BaseModel):
    """A configurable redaction rule.

    Rules can be regex patterns, keyword lists, or named patterns
    for detecting sensitive information.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    id: PyObjectId | None = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    workspace_id: str = Field(
        ...,
        description="Slack workspace ID this rule applies to",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable rule name",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of what this rule detects",
    )
    category: SensitiveCategory = Field(
        ...,
        description="Category of sensitive information",
    )
    rule_type: RedactionRuleType = Field(
        ...,
        description="Type of matching rule",
    )
    pattern: str = Field(
        ...,
        description="Regex pattern, keyword, or pattern name",
    )
    replacement: str = Field(
        default="[REDACTED]",
        description="Replacement text for redacted content",
    )
    is_enabled: bool = Field(
        default=True,
        description="Whether this rule is active",
    )
    priority: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Rule priority (lower = higher priority)",
    )
    created_by: PyObjectId = Field(
        ...,
        description="User who created the rule",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Creation timestamp",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp",
    )


class RedactionRuleCreate(BaseModel):
    """Schema for creating a redaction rule."""

    workspace_id: str
    name: str
    description: str | None = None
    category: SensitiveCategory
    rule_type: RedactionRuleType
    pattern: str
    replacement: str = "[REDACTED]"
    is_enabled: bool = True
    priority: int = 100
    created_by: PyObjectId


class RedactionMatch(BaseModel):
    """A detected match for redaction."""

    rule_id: str = Field(
        ...,
        description="ID of the rule that matched",
    )
    rule_name: str = Field(
        ...,
        description="Name of the rule",
    )
    category: SensitiveCategory = Field(
        ...,
        description="Category of sensitive information",
    )
    matched_text: str = Field(
        ...,
        description="The text that matched the pattern",
    )
    start_position: int = Field(
        ...,
        description="Start position in text",
    )
    end_position: int = Field(
        ...,
        description="End position in text",
    )
    suggested_replacement: str = Field(
        ...,
        description="Suggested replacement text",
    )
    field_path: str = Field(
        ...,
        description="Path to field containing the match (e.g., 'text', 'fields.what')",
    )


class RedactionSuggestion(BaseModel):
    """Redaction suggestions for a piece of content."""

    content_id: str = Field(
        ...,
        description="ID of the content (signal, candidate, COP update)",
    )
    content_type: str = Field(
        ...,
        description="Type of content (signal, cop_candidate, cop_update)",
    )
    matches: list[RedactionMatch] = Field(
        default_factory=list,
        description="List of detected matches",
    )
    total_matches: int = Field(
        default=0,
        description="Total number of matches found",
    )
    categories_detected: list[str] = Field(
        default_factory=list,
        description="Categories of sensitive info found",
    )
    suggested_text: str | None = Field(
        default=None,
        description="Text with all suggested redactions applied",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When suggestions were generated",
    )


class RedactionOverride(BaseModel):
    """Record of a facilitator overriding a redaction suggestion."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    content_id: PyObjectId = Field(
        ...,
        description="ID of the content",
    )
    content_type: str = Field(
        ...,
        description="Type of content",
    )
    match: RedactionMatch = Field(
        ...,
        description="The match that was overridden",
    )
    overridden_by: PyObjectId = Field(
        ...,
        description="User who overrode the redaction",
    )
    justification: str = Field(
        ...,
        min_length=10,
        description="Justification for override (required)",
    )
    overridden_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the override occurred",
    )


class AppliedRedaction(BaseModel):
    """Record of an applied redaction."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    rule_id: PyObjectId = Field(
        ...,
        description="Rule that was applied",
    )
    rule_name: str = Field(
        ...,
        description="Name of the rule",
    )
    category: SensitiveCategory = Field(
        ...,
        description="Category of information redacted",
    )
    field_path: str = Field(
        ...,
        description="Field where redaction was applied",
    )
    original_text: str = Field(
        ...,
        description="Original text before redaction",
    )
    redacted_text: str = Field(
        ...,
        description="Text after redaction",
    )
    applied_by: PyObjectId = Field(
        ...,
        description="User who applied the redaction",
    )
    applied_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When redaction was applied",
    )


class RedactionStatus(BaseModel):
    """Redaction status for a piece of content."""

    is_redacted: bool = Field(
        default=False,
        description="Whether any redactions have been applied",
    )
    redacted_fields: list[str] = Field(
        default_factory=list,
        description="List of field paths that have been redacted",
    )
    applied_redactions: list[AppliedRedaction] = Field(
        default_factory=list,
        description="Details of applied redactions",
    )
    overrides: list[RedactionOverride] = Field(
        default_factory=list,
        description="Redaction overrides with justifications",
    )
    pending_suggestions: int = Field(
        default=0,
        description="Number of pending redaction suggestions",
    )
    last_scanned_at: datetime | None = Field(
        default=None,
        description="When content was last scanned for sensitive info",
    )


# Default regex patterns for common sensitive information
DEFAULT_PATTERNS: dict[SensitiveCategory, list[dict[str, str]]] = {
    SensitiveCategory.PII_EMAIL: [
        {
            "name": "Email Address",
            "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "replacement": "[EMAIL REDACTED]",
        },
    ],
    SensitiveCategory.PII_PHONE: [
        {
            "name": "US Phone Number",
            "pattern": r"\b(?:\+1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
            "replacement": "[PHONE REDACTED]",
        },
        {
            "name": "International Phone",
            "pattern": r"\b\+?[1-9]\d{1,14}\b",
            "replacement": "[PHONE REDACTED]",
        },
    ],
    SensitiveCategory.PII_ADDRESS: [
        {
            "name": "Street Address",
            "pattern": r"\b\d{1,5}\s+(?:[A-Za-z]+\s+){1,4}(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl)\b",
            "replacement": "[ADDRESS REDACTED]",
        },
        {
            "name": "ZIP Code",
            "pattern": r"\b\d{5}(?:-\d{4})?\b",
            "replacement": "[ZIP REDACTED]",
        },
    ],
    SensitiveCategory.FINANCIAL: [
        {
            "name": "Credit Card Number",
            "pattern": r"\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b",
            "replacement": "[CARD REDACTED]",
        },
        {
            "name": "Bank Account",
            "pattern": r"\b[0-9]{8,17}\b(?=.*(?:account|acct|routing))",
            "replacement": "[ACCOUNT REDACTED]",
        },
    ],
    SensitiveCategory.MEDICAL: [
        {
            "name": "SSN",
            "pattern": r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
            "replacement": "[SSN REDACTED]",
        },
    ],
}
