"""Webhook payload builders for various event types.

Implements:
- FR-INT-001: Webhook event payloads
- Task S8-17: Webhook payload structure
"""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from integritykit.models.cop_candidate import COPCandidate, RiskTier
from integritykit.models.cop_update import COPUpdate


def build_cop_update_published_payload(
    update: COPUpdate,
    workspace_id: str,
    published_by: str,
    slack_permalink: Optional[str] = None,
) -> dict[str, Any]:
    """Build webhook payload for cop_update.published event.

    Args:
        update: COP update that was published
        workspace_id: Workspace ID
        published_by: User ID who published the update
        slack_permalink: Slack message permalink (optional)

    Returns:
        Webhook payload data dictionary
    """
    # Build line items from candidates
    line_items = []
    for candidate_ref in update.candidate_refs:
        # In a real implementation, you'd fetch the actual candidate
        # For now, we'll create a simplified structure
        line_items.append({
            "id": str(candidate_ref.candidate_id),
            "status": candidate_ref.readiness_state,
            "headline": candidate_ref.headline or "N/A",
            "body": candidate_ref.body or "",
            "location": {
                "address": candidate_ref.location.get("address") if candidate_ref.location else None,
                "coordinates": {
                    "lat": candidate_ref.location.get("coordinates", {}).get("lat")
                    if candidate_ref.location
                    else None,
                    "lon": candidate_ref.location.get("coordinates", {}).get("lon")
                    if candidate_ref.location
                    else None,
                }
                if candidate_ref.location and candidate_ref.location.get("coordinates")
                else None,
            },
            "risk_tier": candidate_ref.risk_tier or "routine",
            "citations": candidate_ref.citations or [],
        })

    # Build export links
    base_url = "https://api.integritykit.aidarena.org"  # TODO: Make configurable
    update_id = str(update.id)
    export_links = {
        "cap": f"{base_url}/api/v1/exports/cap/{update_id}",
        "edxl": f"{base_url}/api/v1/exports/edxl/{update_id}",
        "geojson": f"{base_url}/api/v1/exports/geojson/{update_id}",
    }

    return {
        "update_id": update_id,
        "version": update.version or 1,
        "language": update.language or "en",
        "published_by": published_by,
        "published_at": update.published_at.isoformat() if update.published_at else datetime.utcnow().isoformat(),
        "slack_channel_id": update.channel_id,
        "slack_permalink": slack_permalink,
        "line_items": line_items,
        "export_links": export_links,
    }


def build_cop_candidate_verified_payload(
    candidate: COPCandidate,
    workspace_id: str,
    verified_by: str,
    verification_method: str,
    confidence_level: str,
) -> dict[str, Any]:
    """Build webhook payload for cop_candidate.verified event.

    Args:
        candidate: COP candidate that was verified
        workspace_id: Workspace ID
        verified_by: User ID who verified the candidate
        verification_method: Method used for verification
        confidence_level: Confidence level of verification

    Returns:
        Webhook payload data dictionary
    """
    return {
        "candidate_id": str(candidate.id),
        "readiness_state": candidate.readiness_state,
        "risk_tier": candidate.risk_tier,
        "verified_by": verified_by,
        "verified_at": datetime.utcnow().isoformat(),
        "verification_method": verification_method,
        "confidence_level": confidence_level,
        "what": candidate.what,
        "where": candidate.where,
        "when": candidate.when.isoformat() if candidate.when else None,
        "who": candidate.who,
        "so_what": candidate.so_what,
        "location": candidate.location,
        "citations": [str(c.url) for c in candidate.citations] if candidate.citations else [],
    }


def build_cop_candidate_promoted_payload(
    candidate: COPCandidate,
    workspace_id: str,
    promoted_by: str,
    cluster_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build webhook payload for cop_candidate.promoted event.

    Args:
        candidate: COP candidate that was promoted from cluster
        workspace_id: Workspace ID
        promoted_by: User ID who promoted the cluster
        cluster_id: Source cluster ID (optional)

    Returns:
        Webhook payload data dictionary
    """
    return {
        "candidate_id": str(candidate.id),
        "cluster_id": cluster_id,
        "readiness_state": candidate.readiness_state,
        "risk_tier": candidate.risk_tier,
        "promoted_by": promoted_by,
        "promoted_at": datetime.utcnow().isoformat(),
        "what": candidate.what,
        "where": candidate.where,
        "when": candidate.when.isoformat() if candidate.when else None,
        "who": candidate.who,
        "signal_count": len(candidate.signal_ids) if candidate.signal_ids else 0,
    }


def build_cluster_created_payload(
    cluster_id: str,
    workspace_id: str,
    topic_type: str,
    signal_count: int,
    priority_score: float,
    created_at: Optional[datetime] = None,
) -> dict[str, Any]:
    """Build webhook payload for cluster.created event.

    Args:
        cluster_id: Cluster ID
        workspace_id: Workspace ID
        topic_type: Topic type of the cluster
        signal_count: Number of signals in cluster
        priority_score: Priority score for the cluster
        created_at: When cluster was created (optional)

    Returns:
        Webhook payload data dictionary
    """
    return {
        "cluster_id": cluster_id,
        "topic_type": topic_type,
        "signal_count": signal_count,
        "priority_score": priority_score,
        "created_at": (created_at or datetime.utcnow()).isoformat(),
    }


# Example usage function for integration with publish service
async def trigger_cop_update_published_webhook(
    update: COPUpdate,
    workspace_id: str,
    published_by: str,
    slack_permalink: Optional[str] = None,
) -> None:
    """Trigger webhook for COP update published event.

    This is a convenience function that can be called from the publish service.

    Args:
        update: Published COP update
        workspace_id: Workspace ID
        published_by: User ID who published
        slack_permalink: Slack message permalink (optional)
    """
    from integritykit.models.webhook import WebhookEvent
    from integritykit.services.webhooks import WebhookService

    # Build payload
    event_data = build_cop_update_published_payload(
        update=update,
        workspace_id=workspace_id,
        published_by=published_by,
        slack_permalink=slack_permalink,
    )

    # Trigger webhook
    service = WebhookService()
    await service.trigger_webhook(
        event_type=WebhookEvent.COP_UPDATE_PUBLISHED,
        workspace_id=workspace_id,
        event_data=event_data,
        event_id=f"cop_update_{update.id}",
    )
