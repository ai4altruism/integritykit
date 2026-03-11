"""External source models for inbound verification data.

Implements:
- FR-INT-003: External verification source integration
- Task S8-20: Inbound verification source API
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from integritykit.models.signal import PyObjectId


class SourceType(str, Enum):
    """Type of external verification source."""

    GOVERNMENT_API = "government_api"
    NGO_FEED = "ngo_feed"
    VERIFIED_REPORTER = "verified_reporter"
    OTHER = "other"


class TrustLevel(str, Enum):
    """Trust level for external sources.

    Determines how imported data is handled:
    - HIGH: Auto-promote to verified candidate
    - MEDIUM: Create in-review candidate (requires facilitator review)
    - LOW: Import as signal (requires full verification)
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AuthType(str, Enum):
    """Authentication type for external API."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    BASIC = "basic"
    OAUTH2 = "oauth2"


class AuthConfig(BaseModel):
    """Authentication configuration for external API.

    Structure varies by auth_type:
    - api_key: {"key_name": "X-API-Key", "key_value": "your_key"}
    - bearer: {"token": "your_token"}
    - basic: {"username": "user", "password": "pass"}
    - oauth2: {"client_id": "...", "client_secret": "...", "token_url": "..."}
    """

    model_config = ConfigDict(extra="allow")

    # API key
    key_name: Optional[str] = None
    key_value: Optional[str] = None

    # Bearer token
    token: Optional[str] = None

    # Basic auth
    username: Optional[str] = None
    password: Optional[str] = None

    # OAuth2
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_url: Optional[str] = None


class SyncStatistics(BaseModel):
    """Statistics for source synchronization."""

    total_syncs: int = Field(default=0, description="Total sync attempts")
    successful_syncs: int = Field(default=0, description="Successful syncs")
    failed_syncs: int = Field(default=0, description="Failed syncs")
    total_items_imported: int = Field(default=0, description="Total items imported")
    duplicates_skipped: int = Field(default=0, description="Duplicate items skipped")
    last_sync_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last sync attempt",
    )
    last_success_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful sync",
    )
    last_failure_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last failed sync",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message",
    )


class ExternalSource(BaseModel):
    """External verification source configuration.

    Represents a configured external API or feed that provides
    pre-verified information for COP candidate creation.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    workspace_id: str = Field(
        ...,
        description="Workspace ID this source belongs to",
    )
    source_id: str = Field(
        ...,
        description="Unique identifier for the source",
    )
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Human-readable source name",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Description of what this source provides",
    )
    source_type: SourceType = Field(
        ...,
        description="Type of source",
    )
    api_endpoint: str = Field(
        ...,
        description="API endpoint URL for fetching data",
    )
    auth_type: AuthType = Field(
        default=AuthType.NONE,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration (encrypted at rest)",
    )
    trust_level: TrustLevel = Field(
        ...,
        description="Trust level determining import behavior",
    )
    sync_interval_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="Sync interval in minutes (5-1440)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether source is active",
    )
    statistics: SyncStatistics = Field(
        default_factory=SyncStatistics,
        description="Sync statistics",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional source-specific metadata",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When source was registered",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When source was last updated",
    )
    created_by: str = Field(
        ...,
        description="User ID who registered the source",
    )


class ExternalSourceCreate(BaseModel):
    """Request model for creating an external source."""

    source_id: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="Unique identifier for the source",
    )
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Human-readable source name",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Description of what this source provides",
    )
    source_type: SourceType = Field(
        ...,
        description="Type of source",
    )
    api_endpoint: str = Field(
        ...,
        description="API endpoint URL for fetching data",
    )
    auth_type: AuthType = Field(
        default=AuthType.NONE,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration",
    )
    trust_level: TrustLevel = Field(
        ...,
        description="Trust level determining import behavior",
    )
    sync_interval_minutes: int = Field(
        default=60,
        ge=5,
        le=1440,
        description="Sync interval in minutes (5-1440)",
    )
    enabled: bool = Field(
        default=True,
        description="Enable source immediately",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional source-specific metadata",
    )


class ExternalSourceUpdate(BaseModel):
    """Request model for updating an external source."""

    name: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Human-readable source name",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Description of what this source provides",
    )
    api_endpoint: Optional[str] = Field(
        default=None,
        description="API endpoint URL",
    )
    auth_type: Optional[AuthType] = Field(
        default=None,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration",
    )
    trust_level: Optional[TrustLevel] = Field(
        default=None,
        description="Trust level",
    )
    sync_interval_minutes: Optional[int] = Field(
        default=None,
        ge=5,
        le=1440,
        description="Sync interval in minutes",
    )
    enabled: Optional[bool] = Field(
        default=None,
        description="Enable/disable source",
    )
    metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )


class ImportStatus(str, Enum):
    """Status of an import job."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ImportedVerification(BaseModel):
    """Record of data imported from an external source.

    Tracks provenance of externally-verified data that becomes
    COP candidates in the system.
    """

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    import_job_id: str = Field(
        ...,
        description="Import job identifier",
    )
    source_id: PyObjectId = Field(
        ...,
        description="External source that provided this data",
    )
    workspace_id: str = Field(
        ...,
        description="Workspace ID",
    )
    external_id: Optional[str] = Field(
        default=None,
        description="ID in the external system (for deduplication)",
    )
    candidate_id: Optional[PyObjectId] = Field(
        default=None,
        description="Created COP candidate ID",
    )
    status: ImportStatus = Field(
        default=ImportStatus.IN_PROGRESS,
        description="Import status",
    )
    trust_level: TrustLevel = Field(
        ...,
        description="Trust level at time of import",
    )
    raw_data: dict[str, Any] = Field(
        ...,
        description="Raw data from external source",
    )
    transformed_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Transformed data for COP candidate",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if import failed",
    )
    imported_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When data was imported",
    )
    imported_by: str = Field(
        ...,
        description="User who triggered the import",
    )


class ImportRequest(BaseModel):
    """Request to import data from an external source."""

    start_time: Optional[datetime] = Field(
        default=None,
        description="Start of time range to import (optional)",
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="End of time range to import (optional)",
    )
    auto_promote: bool = Field(
        default=False,
        description="Auto-promote based on trust level",
    )
    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Source-specific filters",
    )
    max_items: Optional[int] = Field(
        default=None,
        ge=1,
        le=1000,
        description="Maximum number of items to import",
    )


class ImportResult(BaseModel):
    """Result of an import operation."""

    import_id: str = Field(
        ...,
        description="Import job ID",
    )
    status: ImportStatus = Field(
        ...,
        description="Import status",
    )
    items_fetched: int = Field(
        default=0,
        description="Number of items fetched from source",
    )
    items_imported: int = Field(
        default=0,
        description="Number of items successfully imported",
    )
    duplicates_skipped: int = Field(
        default=0,
        description="Number of duplicate items skipped",
    )
    errors: int = Field(
        default=0,
        description="Number of errors encountered",
    )
    candidates_created: int = Field(
        default=0,
        description="Number of COP candidates created",
    )
    started_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When import started",
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        description="When import completed",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if import failed",
    )
