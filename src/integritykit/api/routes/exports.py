"""Export API routes for external data formats.

Implements:
- FR-INT-002: CAP 1.2 export, EDXL-DE export
- FR-INT-003: GeoJSON export
- Task S8-18: CAP export endpoint
- Task S8-19: EDXL-DE export endpoint
- Task S8-21: GeoJSON export endpoint
"""

import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from motor.motor_asyncio import AsyncIOMotorCollection

from integritykit.models.cop_update import COPUpdate
from integritykit.services.cap_export import CAPExportService
from integritykit.services.edxl_export import EDXLExportService
from integritykit.services.geojson_export import GeoJSONExportService
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


# =========================================================================
# EDXL-DE Export Endpoints
# =========================================================================


@router.get(
    "/edxl/{update_id}",
    response_class=Response,
    summary="Export COP update as EDXL-DE 2.0 XML",
    description="""
    Export a published COP update in EDXL-DE (Emergency Data Exchange Language) 2.0 format.

    EDXL-DE provides a standardized distribution envelope for routing emergency messages
    across emergency management systems. The COP update is exported as CAP 1.2 content
    wrapped in an EDXL-DE distribution envelope.

    **Mapping:**
    - COP update → CAP 1.2 alert (embedded in EDXL-DE contentObject)
    - `verified` items → CAP certainty: Observed
    - `in_review` items → CAP certainty: Likely
    - Distribution status: Actual
    - Distribution type: Update

    **Returns:**
    - Content-Type: application/xml
    - Content-Disposition: attachment; filename="edxl-{update_id}.xml"

    **References:**
    - OASIS EDXL-DE 2.0: http://docs.oasis-open.org/emergency/edxl-de/v2.0/
    - OASIS CAP 1.2: http://docs.oasis-open.org/emergency/cap/v1.2/
    """,
    responses={
        200: {
            "description": "EDXL-DE XML document with embedded CAP content",
            "content": {
                "application/xml": {
                    "example": '<?xml version="1.0"?><EDXLDistribution>...</EDXLDistribution>'
                }
            },
        },
        404: {"description": "COP update not found"},
        422: {
            "description": "COP update cannot be exported (not published, no exportable items)"
        },
    },
)
async def export_edxl(
    update_id: str,
    language: str = "en-US",
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
) -> Response:
    """Export COP update as EDXL-DE 2.0 XML with embedded CAP content.

    Args:
        update_id: COP update ID
        language: Language code (RFC 4646), default: en-US
        cop_updates: MongoDB collection (injected)

    Returns:
        XML response with EDXL-DE document containing CAP alert

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

    # Export to EDXL-DE
    edxl_service = EDXLExportService()

    try:
        edxl_xml = edxl_service.generate_edxl_xml(cop_update, language=language)
    except ValueError as e:
        # Not exportable (e.g., not published, no verified items)
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "EDXL_EXPORT_ERROR",
                    "message": "COP update cannot be exported to EDXL-DE format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(f"EDXL-DE export failed for update {update_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "EDXL_EXPORT_FAILED",
                    "message": "Failed to generate EDXL-DE export",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    # Return XML response with proper headers
    return Response(
        content=edxl_xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="edxl-{update_id}.xml"',
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
        },
    )


@router.get(
    "/edxl/{update_id}/preview",
    summary="Preview EDXL-DE export as JSON",
    description="""
    Preview the EDXL-DE export as a JSON representation before downloading XML.

    Useful for debugging and validation of EDXL-DE field mappings and embedded CAP content.
    """,
)
async def preview_edxl_export(
    update_id: str,
    language: str = "en-US",
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
):
    """Preview EDXL-DE export as JSON.

    Args:
        update_id: COP update ID
        language: Language code (RFC 4646), default: en-US
        cop_updates: MongoDB collection (injected)

    Returns:
        JSON representation of EDXL-DE distribution

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

    # Export to EDXL-DE model
    edxl_service = EDXLExportService()

    try:
        edxl_distribution = edxl_service.export_cop_update(cop_update, language=language)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "EDXL_EXPORT_ERROR",
                    "message": "COP update cannot be exported to EDXL-DE format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(
            f"EDXL-DE preview failed for update {update_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "EDXL_PREVIEW_FAILED",
                    "message": "Failed to generate EDXL-DE preview",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    return {
        "data": {
            "update_id": update_id,
            "language": language,
            "edxl_distribution": edxl_distribution.model_dump(mode="json"),
        }
    }


# =========================================================================
# GeoJSON Export Endpoints
# =========================================================================


@router.get(
    "/geojson/{update_id}",
    response_class=Response,
    summary="Export COP update as GeoJSON",
    description="""
    Export a published COP update in GeoJSON format (RFC 7946).

    GeoJSON is the standard format for web mapping and GIS applications.
    Only published COP updates with verified or in-review items can be exported.

    **Feature Properties:**
    - `line_item_id`: COP candidate ID
    - `text`: Line item text content
    - `status`: Verification status (verified, in_review)
    - `risk_tier`: Risk classification (routine, elevated, high_stakes)
    - `what`, `where`, `when`, `who`, `so_what`: 5W framework fields
    - `citations`: Array of evidence URLs
    - `published_at`: Publication timestamp
    - `slack_permalink`: Link to Slack message

    **Geometry:**
    - Point geometry for items with location coordinates
    - Items without location are excluded by default (use `include_non_spatial=true` to include)

    **Coordinate System:**
    - WGS84 (EPSG:4326) - standard for web mapping

    **Returns:**
    - Content-Type: application/geo+json
    - Content-Disposition: attachment; filename="geojson-{update_id}.json"

    **References:**
    - RFC 7946 GeoJSON: https://tools.ietf.org/html/rfc7946
    """,
    responses={
        200: {
            "description": "GeoJSON FeatureCollection",
            "content": {
                "application/geo+json": {
                    "example": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "id": "candidate-123",
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [-74.0060, 40.7128],
                                },
                                "properties": {
                                    "text": "Shelter Alpha closure",
                                    "status": "verified",
                                },
                            }
                        ],
                    }
                }
            },
        },
        404: {"description": "COP update not found"},
        422: {"description": "COP update cannot be exported (not published, no exportable items)"},
    },
)
async def export_geojson(
    update_id: str,
    include_non_spatial: bool = Query(
        default=False,
        description="Include items without location as features with null geometry",
    ),
    pretty: bool = Query(
        default=False,
        description="Pretty-print JSON with indentation",
    ),
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
) -> Response:
    """Export COP update as GeoJSON FeatureCollection.

    Args:
        update_id: COP update ID
        include_non_spatial: Include items without location (default: False)
        pretty: Pretty-print JSON (default: False)
        cop_updates: MongoDB collection (injected)

    Returns:
        JSON response with GeoJSON FeatureCollection

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

    # Export to GeoJSON
    geojson_service = GeoJSONExportService()

    try:
        geojson_str = geojson_service.generate_geojson_string(
            cop_update,
            include_non_spatial=include_non_spatial,
            pretty=pretty,
        )
    except ValueError as e:
        # Not exportable (e.g., not published, no verified items)
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "GEOJSON_EXPORT_ERROR",
                    "message": "COP update cannot be exported to GeoJSON format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(
            f"GeoJSON export failed for update {update_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "GEOJSON_EXPORT_FAILED",
                    "message": "Failed to generate GeoJSON export",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    # Return GeoJSON response with proper headers
    return Response(
        content=geojson_str,
        media_type="application/geo+json",
        headers={
            "Content-Disposition": f'attachment; filename="geojson-{update_id}.json"',
            "Cache-Control": "public, max-age=300",  # Cache for 5 minutes
        },
    )


@router.get(
    "/geojson/{update_id}/preview",
    summary="Preview GeoJSON export",
    description="""
    Preview the GeoJSON export with statistics before downloading.

    Useful for debugging and validation of GeoJSON structure.
    Returns the FeatureCollection along with export statistics.
    """,
)
async def preview_geojson_export(
    update_id: str,
    include_non_spatial: bool = Query(
        default=False,
        description="Include items without location",
    ),
    cop_updates: AsyncIOMotorCollection = Depends(get_cop_updates_collection),
):
    """Preview GeoJSON export with statistics.

    Args:
        update_id: COP update ID
        include_non_spatial: Include items without location (default: False)
        cop_updates: MongoDB collection (injected)

    Returns:
        JSON with GeoJSON FeatureCollection and export statistics

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

    # Export to GeoJSON
    geojson_service = GeoJSONExportService()

    try:
        collection = geojson_service.export_cop_update(
            cop_update,
            include_non_spatial=include_non_spatial,
        )
        stats = geojson_service.get_export_stats(collection)
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "error": {
                    "code": "GEOJSON_EXPORT_ERROR",
                    "message": "COP update cannot be exported to GeoJSON format",
                    "details": [{"reason": str(e)}],
                }
            },
        )
    except Exception as e:
        logger.error(
            f"GeoJSON preview failed for update {update_id}: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail={
                "error": {
                    "code": "GEOJSON_PREVIEW_FAILED",
                    "message": "Failed to generate GeoJSON preview",
                    "details": [{"reason": "Internal server error"}],
                }
            },
        )

    return {
        "data": {
            "update_id": update_id,
            "geojson": collection.model_dump(mode="json", exclude_none=True),
            "stats": stats,
        }
    }
