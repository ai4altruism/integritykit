"""Export API routes for external data formats.

Implements:
- FR-INT-002: CAP 1.2 export
- Task S8-18: CAP export endpoint
"""

import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Response
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.cop_update import COPUpdate
from integritykit.services.cap_export import CAPExportService
from integritykit.services.database import get_collection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


async def get_cop_updates_collection() -> AsyncIOMotorCollection:
    """Dependency to get COP updates collection."""
    return get_collection("cop_updates")


# =========================================================================
# CAP Export Endpoints
# =========================================================================


@router.get(
    "/cap/{update_id}",
    response_class=Response,
    summary="Export COP update as CAP 1.2 XML",
    description="""
    Export a published COP update in Common Alerting Protocol (CAP) 1.2 format.

    CAP is an OASIS standard for emergency alerts and public warnings.
    Only published COP updates with verified or in-review items can be exported.

    **Mapping:**
    - `verified` items → CAP certainty: Observed
    - `in_review` items → CAP certainty: Likely
    - `high_stakes` risk tier → CAP severity: Severe, urgency: Immediate
    - `elevated` risk tier → CAP severity: Moderate, urgency: Expected
    - `routine` risk tier → CAP severity: Minor, urgency: Future

    **Returns:**
    - Content-Type: application/xml
    - Content-Disposition: attachment; filename="cap-{update_id}.xml"

    **References:**
    - OASIS CAP 1.2: http://docs.oasis-open.org/emergency/cap/v1.2/
    """,
    responses={
        200: {
            "description": "CAP XML document",
            "content": {"application/xml": {"example": '<?xml version="1.0"?><alert>...</alert>'}},
        },
        404: {"description": "COP update not found"},
        422: {"description": "COP update cannot be exported (not published, no exportable items)"},
    },
)
async def export_cap(
    update_id: str,
    language: str = "en-US",
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
) -> Response:
    """Export COP update as CAP 1.2 XML.

    Args:
        update_id: COP update ID
        language: Language code (RFC 3066), default: en-US
        cop_updates: MongoDB collection (injected)

    Returns:
        XML response with CAP document

    Raises:
        HTTPException: 404 if not found, 422 if not exportable
    """
    # Validate ObjectId
    try:
        update_oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update ID format")

    # Fetch COP update
    update_dict = await cop_updates.find_one({"_id": update_oid})
    if not update_dict:
        raise HTTPException(
            status_code=404, detail=f"COP update {update_id} not found"
        )

    cop_update = COPUpdate(**update_dict)

    # Export to CAP
    cap_service = CAPExportService()

    try:
        cap_xml = cap_service.generate_cap_xml(cop_update, language=language)
    except ValueError as e:
        # Not exportable (e.g., not published, no verified items)
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CAP_EXPORT_ERROR",
                    "message": "COP update cannot be exported to CAP format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(f"CAP export failed for update {update_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CAP_EXPORT_FAILED",
                    "message": "Failed to generate CAP export",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    # Return XML response with proper headers
    return Response(
        content=cap_xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="cap-{update_id}.xml"',
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
        },
    )


@router.get(
    "/cap/{update_id}/preview",
    summary="Preview CAP export as JSON",
    description="""
    Preview the CAP export as a JSON representation before downloading XML.

    Useful for debugging and validation of CAP field mappings.
    """,
)
async def preview_cap_export(
    update_id: str,
    language: str = "en-US",
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
):
    """Preview CAP export as JSON.

    Args:
        update_id: COP update ID
        language: Language code (RFC 3066), default: en-US
        cop_updates: MongoDB collection (injected)

    Returns:
        JSON representation of CAP alert

    Raises:
        HTTPException: 404 if not found, 422 if not exportable
    """
    # Validate ObjectId
    try:
        update_oid = ObjectId(update_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid update ID format")

    # Fetch COP update
    update_dict = await cop_updates.find_one({"_id": update_oid})
    if not update_dict:
        raise HTTPException(
            status_code=404, detail=f"COP update {update_id} not found"
        )

    cop_update = COPUpdate(**update_dict)

    # Export to CAP model
    cap_service = CAPExportService()

    try:
        cap_alert = cap_service.export_cop_update(cop_update, language=language)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "CAP_EXPORT_ERROR",
                    "message": "COP update cannot be exported to CAP format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(
            f"CAP preview failed for update {update_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "CAP_PREVIEW_FAILED",
                    "message": "Failed to generate CAP preview",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    return {
        "data": {
            "update_id": update_id,
            "language": language,
            "cap_alert": cap_alert.model_dump(mode="json"),
        }
    }
