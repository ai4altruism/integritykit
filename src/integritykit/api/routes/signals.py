"""API routes for signal operations including duplicate detection."""

from typing import Optional

import structlog
from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from integritykit.models.duplicate import DuplicateMatch
from integritykit.models.signal import PyObjectId, Signal
from integritykit.services.database import SignalRepository
from integritykit.services.duplicate_detection import DuplicateDetectionService
from integritykit.services.embedding import EmbeddingService
from integritykit.services.llm import LLMService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


# Dependency injection helpers
def get_signal_repository() -> SignalRepository:
    """Get signal repository instance."""
    return SignalRepository()


def get_duplicate_detection_service(
    signal_repo: SignalRepository = Depends(get_signal_repository),
) -> DuplicateDetectionService:
    """Get duplicate detection service instance.

    Note: This is a simplified dependency injection. In production,
    you'd want to properly inject configured service instances.
    """
    # This would normally come from app state or dependency injection
    # For now, we'll raise an error indicating setup is needed
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Duplicate detection service not configured. Please set up service dependencies.",
    )


# Response models
class DuplicateMatchResponse(BaseModel):
    """Response model for duplicate match."""

    signal_id: str = Field(..., description="ID of the duplicate signal")
    similarity_score: float = Field(..., description="Embedding similarity score")
    confidence: str = Field(..., description="LLM confidence level")
    reasoning: str = Field(..., description="Explanation from LLM")
    shared_facts: list[str] = Field(default_factory=list, description="Shared facts between signals")


class DuplicatesResponse(BaseModel):
    """Response model for duplicate suggestions."""

    signal_id: str = Field(..., description="ID of the signal checked")
    cluster_id: Optional[str] = Field(None, description="Cluster the signal belongs to")
    duplicates: list[DuplicateMatchResponse] = Field(
        default_factory=list,
        description="List of detected duplicates",
    )
    count: int = Field(..., description="Number of duplicates found")


class ConfirmDuplicateRequest(BaseModel):
    """Request model for confirming a duplicate."""

    canonical_id: str = Field(
        ...,
        description="ID of the canonical (primary) signal",
    )
    reasoning: Optional[str] = Field(
        None,
        description="Optional facilitator notes on why this is a duplicate",
    )


class RejectDuplicateRequest(BaseModel):
    """Request model for rejecting a duplicate suggestion."""

    duplicate_id: str = Field(
        ...,
        description="ID of the signal suggested as duplicate",
    )
    reasoning: Optional[str] = Field(
        None,
        description="Optional facilitator notes on why this is NOT a duplicate",
    )


@router.get(
    "/{signal_id}/duplicates",
    response_model=DuplicatesResponse,
    summary="Get duplicate suggestions for a signal",
    description="Returns AI-detected duplicate signals within the same cluster.",
)
async def get_duplicate_suggestions(
    signal_id: str,
    signal_repo: SignalRepository = Depends(get_signal_repository),
    duplicate_service: DuplicateDetectionService = Depends(get_duplicate_detection_service),
) -> DuplicatesResponse:
    """Get duplicate suggestions for a signal.

    This endpoint is used by facilitators to review AI-detected duplicates.

    Args:
        signal_id: Signal ID to check for duplicates
        signal_repo: Signal repository dependency
        duplicate_service: Duplicate detection service dependency

    Returns:
        DuplicatesResponse with duplicate suggestions

    Raises:
        HTTPException: If signal not found or not in a cluster
    """
    try:
        # Get signal
        signal = await signal_repo.get_by_id(ObjectId(signal_id))
        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {signal_id} not found",
            )

        # Check if signal belongs to a cluster
        if not signal.cluster_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Signal must belong to a cluster for duplicate detection",
            )

        # Use the first cluster (signals typically belong to one cluster)
        cluster_id = signal.cluster_ids[0]

        # Detect duplicates
        duplicate_matches = await duplicate_service.detect_duplicates_for_signal(
            signal=signal,
            cluster_id=cluster_id,
        )

        # Convert to response format
        duplicates = [
            DuplicateMatchResponse(
                signal_id=str(match.signal_id),
                similarity_score=match.similarity_score,
                confidence=match.confidence,
                reasoning=match.reasoning,
                shared_facts=match.shared_facts,
            )
            for match in duplicate_matches
        ]

        logger.info(
            "Retrieved duplicate suggestions",
            signal_id=signal_id,
            duplicate_count=len(duplicates),
        )

        return DuplicatesResponse(
            signal_id=signal_id,
            cluster_id=str(cluster_id),
            duplicates=duplicates,
            count=len(duplicates),
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to get duplicate suggestions",
            signal_id=signal_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to detect duplicates",
        )


@router.post(
    "/{signal_id}/confirm-duplicate",
    status_code=status.HTTP_200_OK,
    summary="Facilitator confirms a signal as duplicate",
    description="Mark a signal as a duplicate of a canonical signal (facilitator override).",
)
async def confirm_duplicate(
    signal_id: str,
    request: ConfirmDuplicateRequest,
    signal_repo: SignalRepository = Depends(get_signal_repository),
    duplicate_service: DuplicateDetectionService = Depends(get_duplicate_detection_service),
) -> dict:
    """Facilitator confirms a signal is a duplicate.

    This allows facilitators to manually confirm AI suggestions or
    mark duplicates that AI may have missed.

    Args:
        signal_id: Signal ID to mark as duplicate
        request: Confirmation request with canonical ID
        signal_repo: Signal repository dependency
        duplicate_service: Duplicate detection service dependency

    Returns:
        Success message

    Raises:
        HTTPException: If signals not found
    """
    try:
        # Validate both signals exist
        signal = await signal_repo.get_by_id(ObjectId(signal_id))
        canonical = await signal_repo.get_by_id(ObjectId(request.canonical_id))

        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {signal_id} not found",
            )

        if not canonical:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Canonical signal {request.canonical_id} not found",
            )

        # Mark as duplicate
        await duplicate_service.mark_duplicates(
            signal_ids=[ObjectId(signal_id)],
            canonical_id=ObjectId(request.canonical_id),
        )

        logger.info(
            "Facilitator confirmed duplicate",
            signal_id=signal_id,
            canonical_id=request.canonical_id,
            facilitator_reasoning=request.reasoning,
        )

        return {
            "status": "success",
            "message": f"Signal {signal_id} marked as duplicate of {request.canonical_id}",
            "signal_id": signal_id,
            "canonical_id": request.canonical_id,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to confirm duplicate",
            signal_id=signal_id,
            canonical_id=request.canonical_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm duplicate",
        )


@router.post(
    "/{signal_id}/reject-duplicate",
    status_code=status.HTTP_200_OK,
    summary="Facilitator rejects a duplicate suggestion",
    description="Mark an AI-suggested duplicate as NOT a duplicate (facilitator override).",
)
async def reject_duplicate(
    signal_id: str,
    request: RejectDuplicateRequest,
    signal_repo: SignalRepository = Depends(get_signal_repository),
) -> dict:
    """Facilitator rejects a duplicate suggestion.

    This allows facilitators to override AI suggestions when they
    determine signals are NOT duplicates.

    Args:
        signal_id: Signal ID that was checked
        request: Rejection request with duplicate ID to reject
        signal_repo: Signal repository dependency

    Returns:
        Success message

    Raises:
        HTTPException: If signals not found
    """
    try:
        # Validate both signals exist
        signal = await signal_repo.get_by_id(ObjectId(signal_id))
        rejected = await signal_repo.get_by_id(ObjectId(request.duplicate_id))

        if not signal:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {signal_id} not found",
            )

        if not rejected:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Signal {request.duplicate_id} not found",
            )

        # Store rejection in signal metadata
        # This could be extended to persist facilitator feedback
        # for model improvement

        logger.info(
            "Facilitator rejected duplicate suggestion",
            signal_id=signal_id,
            rejected_duplicate_id=request.duplicate_id,
            facilitator_reasoning=request.reasoning,
        )

        return {
            "status": "success",
            "message": f"Duplicate suggestion rejected for signal {signal_id}",
            "signal_id": signal_id,
            "rejected_duplicate_id": request.duplicate_id,
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(
            "Failed to reject duplicate suggestion",
            signal_id=signal_id,
            error=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject duplicate suggestion",
        )
