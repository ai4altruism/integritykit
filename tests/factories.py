"""
Test data factories for Aid Arena Integrity Kit.

Factories generate realistic test data for:
- Signals (Slack messages with metadata)
- Clusters (grouped signals)
- COP Candidates (items in verification workflow)
- COP Updates (published artifacts)
- Users (with roles)
- Audit Log Entries

Each factory accepts optional overrides for any field and generates
realistic defaults based on the MongoDB schema.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from bson import ObjectId


# ============================================================================
# Signal Factories
# ============================================================================


def create_signal(
    *,
    _id: ObjectId | None = None,
    slack_channel_id: str = "C01TESTCHAN",
    slack_thread_ts: str | None = None,
    slack_message_ts: str | None = None,
    slack_user_id: str = "U01TESTUSER",
    slack_team_id: str = "T01TESTTEAM",
    text: str = "Test signal message",
    attachments: list[dict[str, Any]] | None = None,
    reactions: list[dict[str, Any]] | None = None,
    posted_at: datetime | None = None,
    ingested_at: datetime | None = None,
    permalink: str | None = None,
    embedding_id: str | None = None,
    cluster_ids: list[ObjectId] | None = None,
    ai_flags: dict[str, Any] | None = None,
    source_quality: dict[str, Any] | None = None,
    redaction: dict[str, Any] | None = None,
    retention: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate a signal document (Slack message with metadata).

    Args:
        _id: Document ObjectId (auto-generated if None)
        slack_channel_id: Slack channel ID
        slack_thread_ts: Parent thread timestamp (None for top-level)
        slack_message_ts: Unique message timestamp
        slack_user_id: Posting user's Slack ID
        slack_team_id: Workspace/team ID
        text: Message text content
        attachments: Slack attachments array
        reactions: Reaction metadata
        posted_at: Message timestamp (defaults to now)
        ingested_at: System ingestion timestamp
        permalink: Slack permalink
        embedding_id: ChromaDB embedding reference
        cluster_ids: Array of cluster ObjectIds
        ai_flags: AI-generated flags (duplicate, conflict, quality)
        source_quality: Source quality indicators
        redaction: Redaction tracking
        retention: Retention policy settings
        **kwargs: Additional fields to override

    Returns:
        Signal document dictionary

    Example:
        signal = create_signal(
            text="Shelter Alpha closing at 6pm",
            slack_channel_id="C01CRISIS",
            ai_flags={"quality_score": 0.85}
        )
    """
    now = datetime.now(timezone.utc)
    _posted_at = posted_at or now - timedelta(minutes=5)
    _ingested_at = ingested_at or now
    _message_ts = slack_message_ts or f"{int(_posted_at.timestamp())}.123456"

    signal = {
        "_id": _id or ObjectId(),
        "slack_channel_id": slack_channel_id,
        "slack_thread_ts": slack_thread_ts,
        "slack_message_ts": _message_ts,
        "slack_user_id": slack_user_id,
        "slack_team_id": slack_team_id,
        "text": text,
        "attachments": attachments or [],
        "reactions": reactions or [],
        "posted_at": _posted_at,
        "ingested_at": _ingested_at,
        "permalink": permalink
        or f"https://test.slack.com/archives/{slack_channel_id}/p{_message_ts.replace('.', '')}",
        "embedding_id": embedding_id,
        "cluster_ids": cluster_ids or [],
        "ai_flags": ai_flags
        or {
            "is_duplicate": False,
            "duplicate_of_signal_id": None,
            "has_conflict": False,
            "conflict_signal_ids": [],
            "quality_score": 0.75,
        },
        "source_quality": source_quality
        or {
            "is_firsthand": True,
            "has_external_link": False,
            "external_links": [],
            "author_credibility_score": 0.8,
        },
        "redaction": redaction or {"is_redacted": False},
        "retention": retention
        or {
            "expires_at": now + timedelta(days=90),
            "is_archived": False,
        },
        "created_at": _ingested_at,
        "updated_at": _ingested_at,
    }

    # Apply additional overrides
    signal.update(kwargs)

    return signal


def create_signal_with_reaction(
    reaction_name: str = "heavy_check_mark",
    reaction_count: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Create signal with reactions applied.

    Args:
        reaction_name: Emoji name (without colons)
        reaction_count: Number of reactions
        **kwargs: Additional signal fields

    Returns:
        Signal with reactions
    """
    reactions = [
        {
            "name": reaction_name,
            "count": reaction_count,
            "users": [f"U{i:08d}" for i in range(reaction_count)],
        }
    ]
    return create_signal(reactions=reactions, **kwargs)


# ============================================================================
# Cluster Factories
# ============================================================================


def create_cluster(
    *,
    _id: ObjectId | None = None,
    name: str = "Test Cluster",
    topic_type: Literal[
        "incident", "need", "resource_offer", "infrastructure", "rumor", "general"
    ] = "general",
    keywords: list[str] | None = None,
    signal_ids: list[ObjectId] | None = None,
    signal_count: int | None = None,
    first_signal_at: datetime | None = None,
    last_signal_at: datetime | None = None,
    has_conflicts: bool = False,
    conflict_details: list[dict[str, Any]] | None = None,
    urgency_score: float = 0.5,
    impact_score: float = 0.5,
    risk_score: float = 0.5,
    priority_score: float = 0.5,
    promoted_to_candidate_id: ObjectId | None = None,
    promoted_at: datetime | None = None,
    promoted_by: ObjectId | None = None,
    ai_summary: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate a cluster document (grouped signals by topic).

    Args:
        _id: Document ObjectId
        name: Human-readable cluster name
        topic_type: Topic classification
        keywords: Extracted keywords
        signal_ids: Array of signal ObjectIds
        signal_count: Denormalized count
        first_signal_at: Earliest signal timestamp
        last_signal_at: Latest signal timestamp
        has_conflicts: True if signals contradict
        conflict_details: Array of conflict descriptions
        urgency_score: Time-sensitive urgency (0.0-1.0)
        impact_score: Estimated impact (0.0-1.0)
        risk_score: Safety/harm risk (0.0-1.0)
        priority_score: Composite score for sorting (0.0-1.0)
        promoted_to_candidate_id: COP candidate reference
        promoted_at: Promotion timestamp
        promoted_by: User who promoted
        ai_summary: AI-generated summary
        **kwargs: Additional fields

    Returns:
        Cluster document dictionary
    """
    now = datetime.now(timezone.utc)
    _signal_ids = signal_ids or []
    _signal_count = signal_count if signal_count is not None else len(_signal_ids)
    _first_signal_at = first_signal_at or now - timedelta(hours=2)
    _last_signal_at = last_signal_at or now - timedelta(minutes=10)

    cluster = {
        "_id": _id or ObjectId(),
        "name": name,
        "topic_type": topic_type,
        "keywords": keywords or ["test", "cluster"],
        "signal_ids": _signal_ids,
        "signal_count": _signal_count,
        "first_signal_at": _first_signal_at,
        "last_signal_at": _last_signal_at,
        "has_conflicts": has_conflicts,
        "conflict_details": conflict_details or [],
        "urgency_score": urgency_score,
        "impact_score": impact_score,
        "risk_score": risk_score,
        "priority_score": priority_score,
        "promoted_to_candidate_id": promoted_to_candidate_id,
        "promoted_at": promoted_at,
        "promoted_by": promoted_by,
        "ai_summary": ai_summary or f"Summary of {name}",
        "created_at": _first_signal_at,
        "updated_at": _last_signal_at,
    }

    cluster.update(kwargs)
    return cluster


def create_cluster_with_signals(
    signal_count: int = 3,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Create cluster with auto-generated signal references.

    Args:
        signal_count: Number of signals to reference
        **kwargs: Additional cluster fields

    Returns:
        Cluster with signal_ids populated
    """
    signal_ids = [ObjectId() for _ in range(signal_count)]
    return create_cluster(signal_ids=signal_ids, signal_count=signal_count, **kwargs)


# ============================================================================
# COP Candidate Factories
# ============================================================================


def create_cop_candidate(
    *,
    _id: ObjectId | None = None,
    cluster_id: ObjectId | None = None,
    primary_signal_ids: list[ObjectId] | None = None,
    readiness_state: Literal["verified", "in_review", "blocked"] = "in_review",
    readiness_updated_at: datetime | None = None,
    readiness_updated_by: ObjectId | None = None,
    risk_tier: Literal["routine", "elevated", "high_stakes"] = "routine",
    risk_tier_override: dict[str, Any] | None = None,
    fields: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    verifications: list[dict[str, Any]] | None = None,
    missing_fields: list[str] | None = None,
    blocking_issues: list[dict[str, Any]] | None = None,
    recommended_action: dict[str, Any] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    draft_wording: dict[str, Any] | None = None,
    facilitator_notes: list[dict[str, Any]] | None = None,
    published_in_cop_update_ids: list[ObjectId] | None = None,
    merged_into_candidate_id: ObjectId | None = None,
    created_at: datetime | None = None,
    created_by: ObjectId | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate a COP candidate document.

    Args:
        _id: Document ObjectId
        cluster_id: Source cluster reference
        primary_signal_ids: Key supporting signals
        readiness_state: Workflow state (verified/in_review/blocked)
        readiness_updated_at: Last state change timestamp
        readiness_updated_by: User who changed state
        risk_tier: Risk classification
        risk_tier_override: Override tracking if tier manually changed
        fields: Structured COP fields (what/where/when/who/so_what)
        evidence: Evidence pack (Slack permalinks, external sources)
        verifications: Verification records
        missing_fields: Array of missing field names
        blocking_issues: Issues preventing publication
        recommended_action: Suggested next action
        conflicts: Conflict tracking
        draft_wording: Draft COP text
        facilitator_notes: Facilitator comments
        published_in_cop_update_ids: COP updates containing this candidate
        merged_into_candidate_id: Merge tracking
        created_at: Creation timestamp
        created_by: Creating user
        **kwargs: Additional fields

    Returns:
        COP candidate document dictionary
    """
    now = datetime.now(timezone.utc)
    _created_at = created_at or now - timedelta(hours=1)
    _readiness_updated_at = readiness_updated_at or now - timedelta(minutes=30)

    candidate = {
        "_id": _id or ObjectId(),
        "cluster_id": cluster_id or ObjectId(),
        "primary_signal_ids": primary_signal_ids or [ObjectId()],
        "readiness_state": readiness_state,
        "readiness_updated_at": _readiness_updated_at,
        "readiness_updated_by": readiness_updated_by or ObjectId(),
        "risk_tier": risk_tier,
        "risk_tier_override": risk_tier_override,
        "fields": fields
        or {
            "what": "Test situation",
            "where": "Test location",
            "when": {
                "timestamp": now,
                "timezone": "America/New_York",
                "is_approximate": False,
                "description": "Now",
            },
            "who": "Test affected population",
            "so_what": "Test operational relevance",
        },
        "evidence": evidence
        or {
            "slack_permalinks": [
                {
                    "url": "https://test.slack.com/archives/C01/p123456",
                    "signal_id": ObjectId(),
                    "description": "Test evidence",
                }
            ],
            "external_sources": [],
        },
        "verifications": verifications or [],
        "missing_fields": missing_fields or [],
        "blocking_issues": blocking_issues or [],
        "recommended_action": recommended_action
        or {
            "action_type": "assign_verification",
            "reason": "Needs verification",
            "alternatives": [],
        },
        "conflicts": conflicts or [],
        "draft_wording": draft_wording
        or {
            "headline": "Test Headline",
            "body": "Test body content",
            "hedging_applied": False,
            "recheck_time": None,
            "next_verification_step": None,
        },
        "facilitator_notes": facilitator_notes or [],
        "published_in_cop_update_ids": published_in_cop_update_ids or [],
        "merged_into_candidate_id": merged_into_candidate_id,
        "merged_at": None,
        "merged_by": None,
        "created_at": _created_at,
        "created_by": created_by or ObjectId(),
        "updated_at": _readiness_updated_at,
    }

    candidate.update(kwargs)
    return candidate


def create_verified_candidate(**kwargs: Any) -> dict[str, Any]:
    """
    Create candidate in verified state with complete verification.

    Returns:
        Verified COP candidate
    """
    verifications = [
        {
            "verified_by": ObjectId(),
            "verified_at": datetime.now(timezone.utc),
            "verification_method": "authoritative_source",
            "verification_notes": "Verified via official source",
            "confidence_level": "high",
        }
    ]

    return create_cop_candidate(
        readiness_state="verified",
        verifications=verifications,
        missing_fields=[],
        blocking_issues=[],
        **kwargs,
    )


def create_blocked_candidate(**kwargs: Any) -> dict[str, Any]:
    """
    Create candidate in blocked state with issues.

    Returns:
        Blocked COP candidate
    """
    return create_cop_candidate(
        readiness_state="blocked",
        missing_fields=["where", "when"],
        blocking_issues=[
            {
                "issue_type": "missing_field",
                "description": "Missing location and time",
                "severity": "blocks_publishing",
            }
        ],
        **kwargs,
    )


# ============================================================================
# COP Update Factories
# ============================================================================


def create_cop_update(
    *,
    _id: ObjectId | None = None,
    version_number: int = 1,
    previous_version_id: ObjectId | None = None,
    published_at: datetime | None = None,
    published_by: ObjectId | None = None,
    publisher_role: str = "facilitator",
    slack_channel_id: str = "C01COPCHAN",
    slack_message_ts: str | None = None,
    slack_permalink: str | None = None,
    content: dict[str, Any] | None = None,
    candidates_snapshot: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
    overrides: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate a COP update document (published artifact).

    Args:
        _id: Document ObjectId
        version_number: Monotonic version number
        previous_version_id: Prior COP update reference
        published_at: Publication timestamp
        published_by: Publishing user
        publisher_role: Role at publication time
        slack_channel_id: Target Slack channel
        slack_message_ts: Posted message timestamp
        slack_permalink: Permalink to posted message
        content: COP structure (header, sections, footer)
        candidates_snapshot: Immutable candidate snapshots
        metrics: Update metrics
        overrides: Override tracking
        **kwargs: Additional fields

    Returns:
        COP update document dictionary
    """
    now = datetime.now(timezone.utc)
    _published_at = published_at or now

    candidate = {
        "_id": _id or ObjectId(),
        "version_number": version_number,
        "previous_version_id": previous_version_id,
        "published_at": _published_at,
        "published_by": published_by or ObjectId(),
        "publisher_role": publisher_role,
        "slack_channel_id": slack_channel_id,
        "slack_message_ts": slack_message_ts,
        "slack_permalink": slack_permalink,
        "content": content
        or {
            "header": {
                "title": "Common Operating Picture (COP) — Test",
                "timestamp": _published_at,
                "timezone": "America/New_York",
                "disclaimer": "Verified updates are confirmed by evidence noted below.",
            },
            "sections": {
                "verified": [],
                "in_review": [],
                "disproven": [],
                "gaps": [],
            },
            "footer": {
                "change_summary": "Initial COP",
                "next_update_time": None,
                "contact_info": "Questions? Post in #cop-questions",
            },
        },
        "candidates_snapshot": candidates_snapshot or [],
        "metrics": metrics
        or {
            "total_verified_items": 0,
            "total_in_review_items": 0,
            "total_disproven_items": 0,
            "total_gaps": 0,
            "provenance_coverage_pct": 100.0,
            "time_since_last_update_minutes": 0,
        },
        "overrides": overrides or [],
        "created_at": _published_at,
    }

    candidate.update(kwargs)
    return candidate


# ============================================================================
# User Factories
# ============================================================================


def create_user(
    *,
    _id: ObjectId | None = None,
    slack_user_id: str = "U01TESTUSER",
    slack_team_id: str = "T01TESTTEAM",
    slack_email: str | None = None,
    slack_display_name: str = "Test User",
    slack_real_name: str = "Test User",
    roles: list[str] | None = None,
    role_history: list[dict[str, Any]] | None = None,
    is_suspended: bool = False,
    suspension_history: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
    activity_stats: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate a user document with roles.

    Args:
        _id: Document ObjectId
        slack_user_id: Unique Slack user ID
        slack_team_id: Workspace ID
        slack_email: User email
        slack_display_name: Display name
        slack_real_name: Real name
        roles: Assigned roles array
        role_history: Role change history
        is_suspended: Suspension status
        suspension_history: Suspension records
        preferences: User preferences
        activity_stats: Activity tracking
        **kwargs: Additional fields

    Returns:
        User document dictionary
    """
    now = datetime.now(timezone.utc)
    _roles = roles or ["general_participant"]

    user = {
        "_id": _id or ObjectId(),
        "slack_user_id": slack_user_id,
        "slack_team_id": slack_team_id,
        "slack_email": slack_email or f"{slack_user_id.lower()}@test.com",
        "slack_display_name": slack_display_name,
        "slack_real_name": slack_real_name,
        "roles": _roles,
        "role_history": role_history or [],
        "is_suspended": is_suspended,
        "suspension_history": suspension_history or [],
        "preferences": preferences
        or {
            "timezone": "America/New_York",
            "notification_settings": {},
        },
        "activity_stats": activity_stats
        or {
            "last_action_at": now,
            "total_actions": 0,
            "high_stakes_overrides_count": 0,
            "publish_count": 0,
        },
        "created_at": now,
        "updated_at": now,
    }

    user.update(kwargs)
    return user


def create_facilitator(**kwargs: Any) -> dict[str, Any]:
    """Create user with facilitator role."""
    return create_user(
        roles=["general_participant", "facilitator", "verifier"],
        slack_display_name="Facilitator User",
        **kwargs,
    )


def create_admin(**kwargs: Any) -> dict[str, Any]:
    """Create user with workspace_admin role."""
    return create_user(
        roles=["general_participant", "facilitator", "verifier", "workspace_admin"],
        slack_display_name="Admin User",
        **kwargs,
    )


# ============================================================================
# Audit Log Factories
# ============================================================================


def create_audit_entry(
    *,
    _id: ObjectId | None = None,
    timestamp: datetime | None = None,
    actor_id: ObjectId | None = None,
    actor_role: str = "general_participant",
    actor_ip: str | None = None,
    action_type: str = "signal.ingest",
    target_entity_type: str = "signal",
    target_entity_id: ObjectId | None = None,
    changes: dict[str, Any] | None = None,
    justification: str | None = None,
    system_context: dict[str, Any] | None = None,
    is_flagged: bool = False,
    flag_reason: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Generate an audit log entry.

    Args:
        _id: Document ObjectId
        timestamp: Action timestamp
        actor_id: User who performed action
        actor_role: Role at time of action
        actor_ip: IP address
        action_type: Action type enum
        target_entity_type: Entity type affected
        target_entity_id: Entity ID affected
        changes: Before/after state
        justification: User-provided reason
        system_context: System state snapshot
        is_flagged: Abuse detection flag
        flag_reason: Reason for flagging
        **kwargs: Additional fields

    Returns:
        Audit log entry dictionary
    """
    now = datetime.now(timezone.utc)
    _timestamp = timestamp or now

    entry = {
        "_id": _id or ObjectId(),
        "timestamp": _timestamp,
        "actor_id": actor_id or ObjectId(),
        "actor_role": actor_role,
        "actor_ip": actor_ip,
        "action_type": action_type,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id or ObjectId(),
        "changes": changes or {"before": None, "after": {}},
        "justification": justification,
        "system_context": system_context or {},
        "is_flagged": is_flagged,
        "flag_reason": flag_reason,
        "created_at": _timestamp,
    }

    entry.update(kwargs)
    return entry
