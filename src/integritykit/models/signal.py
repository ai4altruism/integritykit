"""Signal model representing ingested Slack messages."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic v2."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: Any) -> Any:
        """Define Pydantic schema for ObjectId."""
        from pydantic_core import core_schema

        return core_schema.union_schema(
            [
                core_schema.is_instance_schema(ObjectId),
                core_schema.chain_schema(
                    [
                        core_schema.str_schema(),
                        core_schema.no_info_plain_validator_function(cls.validate),
                    ]
                ),
            ],
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda x: str(x)
            ),
        )

    @classmethod
    def validate(cls, v: Any) -> ObjectId:
        """Validate and convert to ObjectId."""
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str):
            try:
                return ObjectId(v)
            except Exception as e:
                raise ValueError(f"Invalid ObjectId: {v}") from e
        raise ValueError(f"Invalid ObjectId type: {type(v)}")


class SourceQualityType(str, Enum):
    """Source quality type classification."""

    PRIMARY = "primary"
    SECONDARY = "secondary"
    EXTERNAL = "external"


class SourceQuality(BaseModel):
    """Source quality indicators for a signal."""

    model_config = ConfigDict(use_enum_values=True)

    type: SourceQualityType = Field(
        default=SourceQualityType.SECONDARY,
        description="Source type classification",
    )
    confidence: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Confidence score for source quality",
    )
    is_firsthand: bool = Field(
        default=False,
        description="Whether this is a first-hand observation",
    )
    has_external_link: bool = Field(
        default=False,
        description="Whether message contains external authoritative links",
    )
    external_links: list[str] = Field(
        default_factory=list,
        description="List of external URLs in message",
    )
    author_credibility_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Author credibility based on historical accuracy",
    )


class AIFlags(BaseModel):
    """AI-generated flags for duplicate and conflict detection."""

    is_duplicate: bool = Field(
        default=False,
        description="Whether AI detected this as duplicate",
    )
    duplicate_of: Optional[PyObjectId] = Field(
        default=None,
        description="Reference to canonical signal if duplicate",
    )
    has_conflict: bool = Field(
        default=False,
        description="Whether AI detected conflicts with other signals",
    )
    conflict_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="References to conflicting signals",
    )
    quality_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Overall AI-estimated quality score",
    )


class SignalCreate(BaseModel):
    """Schema for creating a new signal."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    slack_workspace_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    slack_channel_id: str = Field(
        ...,
        description="Slack channel ID where message was posted",
    )
    slack_thread_ts: Optional[str] = Field(
        default=None,
        description="Thread timestamp if this is a reply",
    )
    slack_message_ts: str = Field(
        ...,
        description="Unique message timestamp from Slack",
    )
    slack_user_id: str = Field(
        ...,
        description="Slack user ID who posted the message",
    )
    slack_permalink: str = Field(
        ...,
        description="Permanent link to the Slack message",
    )
    content: str = Field(
        ...,
        description="Message text content",
    )
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Slack message attachments",
    )
    source_quality: SourceQuality = Field(
        default_factory=SourceQuality,
        description="Source quality indicators",
    )


class Signal(BaseModel):
    """Signal representing an ingested Slack message.

    Signals are the core data structure representing individual messages from Slack.
    They are clustered, analyzed for duplicates and conflicts, and serve as the
    foundation for COP candidates.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
    )

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    slack_workspace_id: str = Field(
        ...,
        description="Slack workspace/team ID",
    )
    slack_channel_id: str = Field(
        ...,
        description="Slack channel ID where message was posted",
    )
    slack_thread_ts: Optional[str] = Field(
        default=None,
        description="Thread timestamp if this is a reply",
    )
    slack_message_ts: str = Field(
        ...,
        description="Unique message timestamp from Slack",
    )
    slack_user_id: str = Field(
        ...,
        description="Slack user ID who posted the message",
    )
    slack_permalink: str = Field(
        ...,
        description="Permanent link to the Slack message",
    )
    content: str = Field(
        ...,
        description="Message text content",
    )
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Slack message attachments",
    )
    cluster_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="Clusters this signal belongs to",
    )
    embedding_id: Optional[str] = Field(
        default=None,
        description="Reference to ChromaDB embedding",
    )
    source_quality: SourceQuality = Field(
        default_factory=SourceQuality,
        description="Source quality indicators",
    )
    ai_flags: AIFlags = Field(
        default_factory=AIFlags,
        description="AI-generated duplicate/conflict flags",
    )
    ai_generated_metadata: Optional[dict[str, Any]] = Field(
        default=None,
        description="Metadata about AI processing",
    )
    redacted: bool = Field(
        default=False,
        description="Whether this signal has been redacted",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When signal was created in system",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When signal was last updated",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="TTL expiration date for data retention",
    )

    @field_validator("updated_at", mode="before")
    @classmethod
    def set_updated_at(cls, v: Any) -> datetime:
        """Always update the updated_at timestamp."""
        return datetime.utcnow()
