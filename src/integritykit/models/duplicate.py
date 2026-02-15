"""Models for duplicate detection."""

from typing import Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from integritykit.models.signal import PyObjectId


class DuplicateConfirmation(BaseModel):
    """LLM confirmation of whether two signals are duplicates."""

    is_duplicate: bool = Field(
        ...,
        description="Whether signals are duplicates",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="Confidence level in duplicate assessment",
    )
    reasoning: str = Field(
        ...,
        description="Explanation of duplicate determination",
    )
    shared_facts: list[str] = Field(
        default_factory=list,
        description="Key facts that overlap between signals",
    )


class DuplicateMatch(BaseModel):
    """A detected duplicate match between signals."""

    signal_id: PyObjectId = Field(
        ...,
        description="ID of the duplicate signal",
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Embedding similarity score (0-1)",
    )
    confidence: Literal["high", "medium", "low"] = Field(
        ...,
        description="LLM confidence in duplicate determination",
    )
    reasoning: str = Field(
        ...,
        description="LLM explanation of why signals are duplicates",
    )
    shared_facts: list[str] = Field(
        default_factory=list,
        description="Key facts shared between signals",
    )


class DuplicateGroup(BaseModel):
    """A group of duplicate signals with a canonical reference."""

    canonical_id: PyObjectId = Field(
        ...,
        description="ID of the canonical (primary) signal",
    )
    duplicate_ids: list[PyObjectId] = Field(
        default_factory=list,
        description="IDs of signals that are duplicates of canonical",
    )
    cluster_id: Optional[PyObjectId] = Field(
        default=None,
        description="Cluster these duplicates belong to",
    )
