"""Language detection and preference API routes.

Implements:
- FR-I18N-001: Language detection for signals
- FR-I18N-003: Facilitator language preference configuration
- v1.0 Multi-language support
"""

from typing import Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from integritykit.config import settings
from integritykit.models.language import (
    Language,
    LanguageCode,
    LanguageDetectionResponse,
    LanguagePreference,
    LanguagePreferenceResponse,
    SUPPORTED_LANGUAGES,
)
from integritykit.services.database import SignalRepository
from integritykit.services.language_detection import LanguageDetectionService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Languages"])


# Dependency injection helpers
def get_signal_repository() -> SignalRepository:
    """Get signal repository instance."""
    return SignalRepository()


def get_language_detection_service() -> LanguageDetectionService:
    """Get language detection service instance."""
    # Get settings from config
    confidence_threshold = getattr(
        settings,
        "language_detection_confidence_threshold",
        0.8,
    )
    enabled = getattr(settings, "language_detection_enabled", True)
    supported_langs_str = getattr(settings, "supported_languages", "en,es,fr")
    supported_langs = [lang.strip() for lang in supported_langs_str.split(",")]

    return LanguageDetectionService(
        confidence_threshold=confidence_threshold,
        enabled=enabled,
        supported_languages=supported_langs,
    )


# In-memory storage for language preferences (should be MongoDB in production)
# TODO: Replace with proper database storage
_language_preferences: dict[str, LanguagePreference] = {}


# Request/Response models
class LanguageListResponse(BaseModel):
    """Response for list languages endpoint."""

    data: list[Language]


class DetectLanguageRequest(BaseModel):
    """Request body for language detection endpoint."""

    force_language: Optional[LanguageCode] = Field(
        default=None,
        description="Optional manual override to set language without detection",
    )


class SetLanguagePreferenceRequest(BaseModel):
    """Request body for setting language preference."""

    language_code: LanguageCode = Field(
        ...,
        description="Preferred language code",
    )
    auto_detect_override: bool = Field(
        default=False,
        description="If true, always use preferred language regardless of signal language",
    )


# Routes
@router.get("/languages", response_model=LanguageListResponse)
async def list_languages() -> LanguageListResponse:
    """List all supported languages.

    Public endpoint that returns available languages with metadata
    about translation quality and capabilities.

    Returns:
        LanguageListResponse with supported languages
    """
    languages = list(SUPPORTED_LANGUAGES.values())

    logger.info(
        "Listed supported languages",
        language_count=len(languages),
    )

    return LanguageListResponse(data=languages)


@router.get(
    "/users/{user_id}/language-preference",
    response_model=LanguagePreferenceResponse,
)
async def get_user_language_preference(
    user_id: str,
) -> LanguagePreferenceResponse:
    """Get user's language preference.

    Returns the configured language preference for a user, or defaults
    to English if not set.

    Args:
        user_id: User ID (Slack user ID)

    Returns:
        LanguagePreferenceResponse with user's preference

    Raises:
        HTTPException: If user not found
    """
    # Check in-memory storage
    if user_id in _language_preferences:
        preference = _language_preferences[user_id]
    else:
        # Default to English
        from datetime import datetime
        preference = LanguagePreference(
            user_id=user_id,
            language_code=LanguageCode.EN,
            auto_detect_override=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    logger.info(
        "Retrieved language preference",
        user_id=user_id,
        language_code=preference.language_code.value,
    )

    return LanguagePreferenceResponse(
        user_id=preference.user_id,
        language_code=preference.language_code,
        auto_detect_override=preference.auto_detect_override,
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )


@router.put(
    "/users/{user_id}/language-preference",
    response_model=LanguagePreferenceResponse,
)
async def set_user_language_preference(
    user_id: str,
    request: SetLanguagePreferenceRequest,
) -> LanguagePreferenceResponse:
    """Set user's language preference.

    Updates the default language for COP drafts, system messages,
    and Block Kit templates for this user.

    Args:
        user_id: User ID (Slack user ID)
        request: Language preference settings

    Returns:
        LanguagePreferenceResponse with updated preference

    Raises:
        HTTPException: If language code not supported
    """
    # Validate language is supported
    if request.language_code not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Language {request.language_code.value} is not supported",
        )

    from datetime import datetime

    # Update or create preference
    if user_id in _language_preferences:
        preference = _language_preferences[user_id]
        preference.language_code = request.language_code
        preference.auto_detect_override = request.auto_detect_override
        preference.updated_at = datetime.utcnow()
    else:
        preference = LanguagePreference(
            user_id=user_id,
            language_code=request.language_code,
            auto_detect_override=request.auto_detect_override,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    _language_preferences[user_id] = preference

    logger.info(
        "Updated language preference",
        user_id=user_id,
        language_code=request.language_code.value,
        auto_detect_override=request.auto_detect_override,
    )

    return LanguagePreferenceResponse(
        user_id=preference.user_id,
        language_code=preference.language_code,
        auto_detect_override=preference.auto_detect_override,
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )


@router.post(
    "/signals/{signal_id}/detect-language",
    response_model=LanguageDetectionResponse,
)
async def detect_signal_language(
    signal_id: str,
    request: Optional[DetectLanguageRequest] = None,
    signal_repo: SignalRepository = Depends(get_signal_repository),
    language_service: LanguageDetectionService = Depends(get_language_detection_service),
) -> LanguageDetectionResponse:
    """Detect language of a signal.

    Manually triggers language detection for a specific signal.
    Useful for reprocessing signals or overriding automatic detection.

    Args:
        signal_id: Signal ID to analyze
        request: Optional request with force_language override
        signal_repo: Signal repository dependency
        language_service: Language detection service dependency

    Returns:
        LanguageDetectionResponse with detection results

    Raises:
        HTTPException: If signal not found or detection fails
    """
    try:
        # Get signal
        signal = await signal_repo.get_by_id(ObjectId(signal_id))
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {signal_id} not found",
            )

        # Extract force_language if provided
        force_language = None
        if request and request.force_language:
            force_language = request.force_language

        # Detect language
        result = language_service.detect_signal_language(
            signal=signal,
            force_language=force_language,
        )

        # Update signal with detected language
        await signal_repo.update_by_id(
            signal_id=ObjectId(signal_id),
            update_data={
                "detected_language": result.detected_language.value,
                "language_confidence": result.confidence,
            },
        )

        logger.info(
            "Detected language for signal",
            signal_id=signal_id,
            detected_language=result.detected_language.value,
            confidence=result.confidence,
            meets_threshold=result.meets_threshold,
        )

        # Build response
        return LanguageDetectionResponse(
            signal_id=signal_id,
            original_text=signal.content[:200],
            detected_language=result.detected_language,
            confidence=result.confidence,
            alternative_languages=result.alternative_languages,
            detection_method=result.detection_method,
            meets_threshold=result.meets_threshold,
            threshold=result.threshold,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to detect language for signal",
            signal_id=signal_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to detect language",
        )
