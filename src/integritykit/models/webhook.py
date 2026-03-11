"""Webhook models for external system integrations.

Implements:
- FR-INT-001: Webhook system with retry and logging
- Task S8-17: Outbound webhook system
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from integritykit.models.signal import PyObjectId


class WebhookEvent(str, Enum):
    """Event types that trigger webhooks."""

    COP_UPDATE_PUBLISHED = "cop_update.published"
    COP_UPDATE_APPROVED = "cop_update.approved"
    COP_CANDIDATE_VERIFIED = "cop_candidate.verified"
    COP_CANDIDATE_PROMOTED = "cop_candidate.promoted"
    CLUSTER_CREATED = "cluster.created"


class AuthType(str, Enum):
    """Authentication types for webhooks."""

    NONE = "none"
    BEARER = "bearer"
    BASIC = "basic"
    API_KEY = "api_key"
    CUSTOM_HEADER = "custom_header"
    OAUTH2 = "oauth2"


class WebhookStatus(str, Enum):
    """Webhook delivery status."""

    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"
    RETRYING = "retrying"


class RetryConfig(BaseModel):
    """Retry configuration for webhook delivery."""

    max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum number of retry attempts",
    )
    retry_delay_seconds: int = Field(
        default=60,
        ge=10,
        description="Initial delay in seconds before retry",
    )
    backoff_multiplier: float = Field(
        default=2.0,
        ge=1.0,
        description="Exponential backoff multiplier",
    )


class AuthConfig(BaseModel):
    """Authentication configuration for webhooks.

    Structure varies by auth_type:
    - bearer: {"token": "your_token"}
    - basic: {"username": "user", "password": "pass"}
    - api_key: {"key_name": "X-API-Key", "key_value": "key"}
    - custom_header: {"header_name": "X-Custom", "header_value": "value"}
    - oauth2: {"client_id": "...", "client_secret": "...", "token_url": "..."}
    """

    model_config = ConfigDict(extra="allow")

    # Bearer token
    token: Optional[str] = None

    # Basic auth
    username: Optional[str] = None
    password: Optional[str] = None

    # API key / Custom header
    key_name: Optional[str] = None
    key_value: Optional[str] = None
    header_name: Optional[str] = None
    header_value: Optional[str] = None

    # OAuth2
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    token_url: Optional[str] = None


class WebhookStatistics(BaseModel):
    """Statistics for webhook deliveries."""

    total_deliveries: int = Field(default=0, description="Total delivery attempts")
    successful_deliveries: int = Field(default=0, description="Successful deliveries")
    failed_deliveries: int = Field(default=0, description="Failed deliveries")
    success_rate: float = Field(default=0.0, description="Success rate (0.0 to 1.0)")
    last_success_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last successful delivery",
    )
    last_failure_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp of last failed delivery",
    )
    last_error: Optional[str] = Field(
        default=None,
        description="Last error message",
    )


class Webhook(BaseModel):
    """Webhook configuration for external system integration."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    workspace_id: str = Field(
        ...,
        description="Workspace ID this webhook belongs to",
    )
    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Descriptive webhook name",
    )
    url: str = Field(
        ...,
        description="Target webhook URL (must be HTTPS in production)",
    )
    events: list[WebhookEvent] = Field(
        ...,
        min_length=1,
        description="Event types that trigger this webhook",
    )
    auth_type: AuthType = Field(
        default=AuthType.NONE,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration (encrypted at rest)",
    )
    retry_config: RetryConfig = Field(
        default_factory=RetryConfig,
        description="Retry configuration",
    )
    enabled: bool = Field(
        default=True,
        description="Whether webhook is active",
    )
    statistics: WebhookStatistics = Field(
        default_factory=WebhookStatistics,
        description="Delivery statistics",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When webhook was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When webhook was last updated",
    )
    created_by: str = Field(
        ...,
        description="User ID who created the webhook",
    )


class WebhookCreate(BaseModel):
    """Request model for creating a webhook."""

    name: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Descriptive webhook name",
    )
    url: str = Field(
        ...,
        description="Target webhook URL (must be HTTPS in production)",
    )
    events: list[WebhookEvent] = Field(
        ...,
        min_length=1,
        description="Event types that trigger this webhook",
    )
    auth_type: AuthType = Field(
        default=AuthType.NONE,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration",
    )
    retry_config: Optional[RetryConfig] = Field(
        default=None,
        description="Retry configuration",
    )
    enabled: bool = Field(
        default=True,
        description="Enable webhook immediately",
    )


class WebhookUpdate(BaseModel):
    """Request model for updating a webhook."""

    name: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Descriptive webhook name",
    )
    url: Optional[str] = Field(
        default=None,
        description="Target webhook URL",
    )
    events: Optional[list[WebhookEvent]] = Field(
        default=None,
        min_length=1,
        description="Event types",
    )
    auth_type: Optional[AuthType] = Field(
        default=None,
        description="Authentication type",
    )
    auth_config: Optional[AuthConfig] = Field(
        default=None,
        description="Authentication configuration",
    )
    retry_config: Optional[RetryConfig] = Field(
        default=None,
        description="Retry configuration",
    )
    enabled: Optional[bool] = Field(
        default=None,
        description="Enable/disable webhook",
    )


class WebhookDelivery(BaseModel):
    """Record of a webhook delivery attempt."""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    webhook_id: PyObjectId = Field(
        ...,
        description="Webhook that was triggered",
    )
    event_type: WebhookEvent = Field(
        ...,
        description="Event type that triggered delivery",
    )
    event_id: str = Field(
        ...,
        description="Unique event ID for idempotency",
    )
    payload: dict[str, Any] = Field(
        ...,
        description="Webhook payload sent",
    )
    status: WebhookStatus = Field(
        ...,
        description="Delivery status",
    )
    http_status_code: Optional[int] = Field(
        default=None,
        description="HTTP response code",
    )
    response_time_ms: Optional[int] = Field(
        default=None,
        description="Response time in milliseconds",
    )
    response_body: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="Response body (truncated)",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Error message if delivery failed",
    )
    retry_count: int = Field(
        default=0,
        description="Number of retry attempts",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When delivery was attempted",
    )
    next_retry_at: Optional[datetime] = Field(
        default=None,
        description="When to retry next (if applicable)",
    )


class WebhookPayload(BaseModel):
    """Standard webhook payload structure."""

    event_id: str = Field(
        ...,
        description="Unique event ID for idempotency",
    )
    event_type: WebhookEvent = Field(
        ...,
        description="Type of event",
    )
    timestamp: datetime = Field(
        ...,
        description="When event occurred",
    )
    workspace_id: str = Field(
        ...,
        description="Workspace ID",
    )
    data: dict[str, Any] = Field(
        ...,
        description="Event-specific data",
    )


class WebhookTestResult(BaseModel):
    """Result of testing a webhook."""

    success: bool = Field(
        ...,
        description="Whether test delivery succeeded",
    )
    status_code: Optional[int] = Field(
        default=None,
        description="HTTP status code",
    )
    response_time_ms: Optional[int] = Field(
        default=None,
        description="Response time in milliseconds",
    )
    response_body: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Response body (truncated)",
    )
    error: Optional[str] = Field(
        default=None,
        description="Error message if test failed",
    )
