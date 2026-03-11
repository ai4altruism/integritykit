"""Language detection and preference models."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from bson import ObjectId
from pydantic import BaseModel, ConfigDict, Field

from integritykit.models.signal import PyObjectId


class LanguageCode(str, Enum):
    """Supported language codes (ISO 639-1)."""

    EN = "en"  # English
    ES = "es"  # Spanish (Español)
    FR = "fr"  # French (Français)


class DetectionMethod(str, Enum):
    """Method used for language detection."""

    LANGDETECT = "langdetect"
    OPENAI_CLASSIFICATION = "openai_classification"
    MANUAL_OVERRIDE = "manual_override"


class Language(BaseModel):
    """Language metadata with quality information."""

    model_config = ConfigDict(use_enum_values=True)

    code: LanguageCode = Field(
        ...,
        description="ISO 639-1 language code",
    )
    name: str = Field(
        ...,
        description="Language name in English",
    )
    native_name: str = Field(
        ...,
        description="Language name in native script",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this language is currently enabled",
    )
    quality_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="LLM translation quality score (1.0 = native quality)",
    )
    supports_cop_generation: bool = Field(
        default=True,
        description="Whether COP draft generation is available in this language",
    )
    supports_wording_guidance: bool = Field(
        default=True,
        description="Whether language-specific hedged phrasing is available",
    )


class AlternativeLanguage(BaseModel):
    """Alternative language candidate with confidence."""

    model_config = ConfigDict(use_enum_values=True)

    language_code: LanguageCode = Field(
        ...,
        description="Language code",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for this language",
    )


class LanguageDetectionResult(BaseModel):
    """Result of language detection operation."""

    model_config = ConfigDict(use_enum_values=True)

    detected_language: LanguageCode = Field(
        ...,
        description="Detected primary language",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for language detection",
    )
    alternative_languages: list[AlternativeLanguage] = Field(
        default_factory=list,
        description="Alternative language candidates with their confidence scores",
    )
    detection_method: DetectionMethod = Field(
        ...,
        description="Method used for language detection",
    )
    meets_threshold: bool = Field(
        ...,
        description="Whether confidence meets the configured threshold",
    )
    threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Configured confidence threshold",
    )


class LanguageDetectionResponse(BaseModel):
    """API response for language detection."""

    model_config = ConfigDict(use_enum_values=True)

    signal_id: str = Field(
        ...,
        description="Signal ID that was analyzed",
    )
    original_text: str = Field(
        ...,
        max_length=200,
        description="First 200 characters of signal text",
    )
    detected_language: LanguageCode = Field(
        ...,
        description="Detected primary language",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score for language detection",
    )
    alternative_languages: list[AlternativeLanguage] = Field(
        default_factory=list,
        description="Alternative language candidates",
    )
    detection_method: DetectionMethod = Field(
        ...,
        description="Method used for language detection",
    )
    meets_threshold: bool = Field(
        ...,
        description="Whether confidence meets the configured threshold",
    )
    threshold: float = Field(
        ...,
        description="Configured confidence threshold",
    )


class LanguagePreference(BaseModel):
    """User language preference configuration."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        populate_by_name=True,
        json_encoders={ObjectId: str},
        use_enum_values=True,
    )

    id: Optional[PyObjectId] = Field(
        default=None,
        alias="_id",
        description="MongoDB document ID",
    )
    user_id: str = Field(
        ...,
        description="User ID (Slack user ID)",
    )
    language_code: LanguageCode = Field(
        ...,
        description="Preferred language code",
    )
    auto_detect_override: bool = Field(
        default=False,
        description="If true, always use preferred language regardless of signal language",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When preference was created",
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When preference was last updated",
    )


class LanguagePreferenceResponse(BaseModel):
    """API response for language preference."""

    model_config = ConfigDict(use_enum_values=True)

    user_id: str = Field(
        ...,
        description="User ID",
    )
    language_code: LanguageCode = Field(
        ...,
        description="Preferred language code",
    )
    auto_detect_override: bool = Field(
        ...,
        description="Whether to override auto-detection",
    )
    created_at: datetime = Field(
        ...,
        description="When preference was created",
    )
    updated_at: datetime = Field(
        ...,
        description="When preference was last updated",
    )


# Predefined language metadata
SUPPORTED_LANGUAGES: dict[LanguageCode, Language] = {
    LanguageCode.EN: Language(
        code=LanguageCode.EN,
        name="English",
        native_name="English",
        enabled=True,
        quality_score=1.0,
    ),
    LanguageCode.ES: Language(
        code=LanguageCode.ES,
        name="Spanish",
        native_name="Español",
        enabled=True,
        quality_score=0.95,
    ),
    LanguageCode.FR: Language(
        code=LanguageCode.FR,
        name="French",
        native_name="Français",
        enabled=True,
        quality_score=0.95,
    ),
}
