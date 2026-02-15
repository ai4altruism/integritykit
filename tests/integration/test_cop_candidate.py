"""
Integration tests for COP candidate workflow.

Tests:
- Cluster promotion to COP candidate
- COP candidate readiness state transitions
- Verification workflow
- Blocking issue management

These tests verify full-stack COP candidate operations with database interactions.
"""

import pytest
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from tests.factories import (
    create_admin,
    create_cluster,
    create_cluster_with_signals,
    create_facilitator,
    create_signal,
    create_user,
)


# ============================================================================
# Cluster Promotion Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_promote_cluster_creates_candidate_document(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Promoting cluster should create a COP candidate document."""
    # Arrange
    cluster = create_cluster_with_signals(signal_count=3)
    facilitator = create_facilitator()

    await test_db.clusters.insert_one(cluster)
    await test_db.users.insert_one(facilitator)

    # Act - Create COP candidate from cluster
    candidate = {
        "_id": ObjectId(),
        "cluster_id": cluster["_id"],
        "primary_signal_ids": cluster["signal_ids"],
        "readiness_state": "in_review",
        "risk_tier": "routine",
        "fields": {
            "headline": cluster["name"],
            "summary": cluster.get("ai_summary", ""),
            "location": None,
            "time_info": None,
            "source_attribution": None,
        },
        "evidence": {
            "signal_count": len(cluster["signal_ids"]),
            "unique_sources": 1,
        },
        "verifications": [],
        "blocking_issues": [],
        "created_by": facilitator["_id"],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    await test_db.cop_candidates.insert_one(candidate)

    # Update cluster with candidate reference
    await test_db.clusters.update_one(
        {"_id": cluster["_id"]},
        {
            "$set": {
                "promoted_to_candidate_id": candidate["_id"],
                "promoted_by": facilitator["_id"],
                "promoted_at": datetime.now(timezone.utc),
            }
        },
    )

    # Assert
    created_candidate = await test_db.cop_candidates.find_one(
        {"cluster_id": cluster["_id"]}
    )
    assert created_candidate is not None
    assert created_candidate["readiness_state"] == "in_review"
    assert created_candidate["cluster_id"] == cluster["_id"]

    updated_cluster = await test_db.clusters.find_one({"_id": cluster["_id"]})
    assert updated_cluster["promoted_to_candidate_id"] == candidate["_id"]


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_promote_cluster_copies_conflicts(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Promotion should copy cluster conflicts to candidate blocking issues."""
    # Arrange
    cluster = create_cluster(
        has_conflicts=True,
        conflict_details=[
            {
                "field": "time",
                "values": ["6pm", "6:30pm"],
                "severity": "moderate",
            },
            {
                "field": "location",
                "values": ["Main St", "Oak Ave"],
                "severity": "high",
            },
        ],
    )
    await test_db.clusters.insert_one(cluster)

    # Act - Create candidate with blocking issues from conflicts
    blocking_issues = [
        {
            "_id": ObjectId(),
            "field": conflict["field"],
            "description": f"Conflicting values: {', '.join(conflict['values'])}",
            "severity": conflict["severity"],
            "created_at": datetime.now(timezone.utc),
            "resolved_at": None,
        }
        for conflict in cluster["conflict_details"]
    ]

    candidate = {
        "_id": ObjectId(),
        "cluster_id": cluster["_id"],
        "readiness_state": "blocked",
        "blocking_issues": blocking_issues,
        "created_at": datetime.now(timezone.utc),
    }

    await test_db.cop_candidates.insert_one(candidate)

    # Assert
    created_candidate = await test_db.cop_candidates.find_one(
        {"cluster_id": cluster["_id"]}
    )
    assert created_candidate is not None
    assert created_candidate["readiness_state"] == "blocked"
    assert len(created_candidate["blocking_issues"]) == 2


# ============================================================================
# Readiness State Transition Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_transition_from_in_review_to_verified(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Candidate should transition from in_review to verified."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "verifications": [],
        "blocking_issues": [],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Add verification and transition state
    verifier = create_facilitator()
    await test_db.users.insert_one(verifier)

    verification = {
        "_id": ObjectId(),
        "verified_by": verifier["_id"],
        "method": "source_confirmation",
        "confidence_level": "high",
        "notes": "Confirmed with primary source",
        "verified_at": datetime.now(timezone.utc),
    }

    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"]},
        {
            "$set": {"readiness_state": "verified"},
            "$push": {"verifications": verification},
        },
    )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert updated["readiness_state"] == "verified"
    assert len(updated["verifications"]) == 1


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_transition_to_blocked_with_issue(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Candidate should transition to blocked when issue is raised."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "blocking_issues": [],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Add blocking issue
    blocking_issue = {
        "_id": ObjectId(),
        "field": "accuracy",
        "description": "Source credibility questioned",
        "severity": "high",
        "raised_by": ObjectId(),
        "created_at": datetime.now(timezone.utc),
        "resolved_at": None,
    }

    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"]},
        {
            "$set": {"readiness_state": "blocked"},
            "$push": {"blocking_issues": blocking_issue},
        },
    )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert updated["readiness_state"] == "blocked"
    assert len(updated["blocking_issues"]) == 1
    assert updated["blocking_issues"][0]["resolved_at"] is None


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_resolve_blocking_issue_transitions_state(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Resolving last blocking issue should allow state transition."""
    # Arrange
    issue_id = ObjectId()
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "blocked",
        "blocking_issues": [
            {
                "_id": issue_id,
                "field": "accuracy",
                "description": "Source credibility questioned",
                "severity": "high",
                "created_at": datetime.now(timezone.utc),
                "resolved_at": None,
            }
        ],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Resolve the blocking issue
    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"], "blocking_issues._id": issue_id},
        {
            "$set": {
                "readiness_state": "in_review",
                "blocking_issues.$.resolved_at": datetime.now(timezone.utc),
                "blocking_issues.$.resolution": "Source verified independently",
            }
        },
    )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert updated["readiness_state"] == "in_review"
    assert updated["blocking_issues"][0]["resolved_at"] is not None


# ============================================================================
# Verification Workflow Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_multiple_verifications_can_be_added(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Candidate can receive multiple verifications."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "verifications": [],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Add multiple verifications
    verifiers = [create_facilitator() for _ in range(3)]
    for v in verifiers:
        v["_id"] = ObjectId()  # Ensure unique IDs
    await test_db.users.insert_many(verifiers)

    for verifier in verifiers:
        verification = {
            "_id": ObjectId(),
            "verified_by": verifier["_id"],
            "method": "source_confirmation",
            "confidence_level": "high",
            "verified_at": datetime.now(timezone.utc),
        }
        await test_db.cop_candidates.update_one(
            {"_id": candidate["_id"]},
            {"$push": {"verifications": verification}},
        )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert len(updated["verifications"]) == 3


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_verification_methods(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Different verification methods should be recorded."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "verifications": [],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Add verifications with different methods
    methods = [
        "source_confirmation",
        "cross_reference",
        "direct_observation",
        "expert_validation",
    ]

    for method in methods:
        verification = {
            "_id": ObjectId(),
            "verified_by": ObjectId(),
            "method": method,
            "confidence_level": "high",
            "verified_at": datetime.now(timezone.utc),
        }
        await test_db.cop_candidates.update_one(
            {"_id": candidate["_id"]},
            {"$push": {"verifications": verification}},
        )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    recorded_methods = [v["method"] for v in updated["verifications"]]
    assert set(recorded_methods) == set(methods)


# ============================================================================
# Risk Tier Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_set_risk_tier_on_candidate(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Risk tier can be set on candidate."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "risk_tier": "routine",
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Escalate risk tier
    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"]},
        {"$set": {"risk_tier": "high_stakes"}},
    )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert updated["risk_tier"] == "high_stakes"


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_high_stakes_requires_more_verification(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """High stakes candidates should track verification threshold."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "risk_tier": "high_stakes",
        "verification_threshold": 3,  # Requires 3 verifications
        "verifications": [],
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Add verifications
    for i in range(2):
        await test_db.cop_candidates.update_one(
            {"_id": candidate["_id"]},
            {
                "$push": {
                    "verifications": {
                        "_id": ObjectId(),
                        "verified_by": ObjectId(),
                        "method": "source_confirmation",
                        "verified_at": datetime.now(timezone.utc),
                    }
                }
            },
        )

    # Assert - Not yet at threshold
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert len(updated["verifications"]) < updated["verification_threshold"]


# ============================================================================
# COP Fields Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_update_cop_fields(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """COP fields should be updateable."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "fields": {
            "headline": "Initial headline",
            "summary": "Initial summary",
            "location": None,
            "time_info": None,
        },
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Act - Update fields
    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"]},
        {
            "$set": {
                "fields.headline": "Updated headline",
                "fields.location": "Downtown Area",
                "fields.time_info": "Ongoing as of 14:00",
            }
        },
    )

    # Assert
    updated = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert updated["fields"]["headline"] == "Updated headline"
    assert updated["fields"]["location"] == "Downtown Area"
    assert updated["fields"]["summary"] == "Initial summary"  # Unchanged


# ============================================================================
# Evidence Tracking Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_evidence_includes_signal_references(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """Evidence should track signal references."""
    # Arrange
    signals = [create_signal() for _ in range(5)]
    for s in signals:
        s["_id"] = ObjectId()
    await test_db.signals.insert_many(signals)

    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "primary_signal_ids": [s["_id"] for s in signals],
        "readiness_state": "in_review",
        "evidence": {
            "signal_count": len(signals),
            "unique_sources": 3,
            "time_span_hours": 2.5,
        },
        "created_at": datetime.now(timezone.utc),
    }
    await test_db.cop_candidates.insert_one(candidate)

    # Assert
    created = await test_db.cop_candidates.find_one({"_id": candidate["_id"]})
    assert len(created["primary_signal_ids"]) == 5
    assert created["evidence"]["signal_count"] == 5
    assert created["evidence"]["unique_sources"] == 3


# ============================================================================
# Candidate Workspace Isolation Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_candidates_isolated_by_workspace(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """COP candidates should be isolated by workspace."""
    # Arrange
    workspace_a_candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "workspace_id": "T01TEAMA",
        "readiness_state": "in_review",
        "created_at": datetime.now(timezone.utc),
    }
    workspace_b_candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "workspace_id": "T01TEAMB",
        "readiness_state": "verified",
        "created_at": datetime.now(timezone.utc),
    }

    await test_db.cop_candidates.insert_many(
        [workspace_a_candidate, workspace_b_candidate]
    )

    # Act
    workspace_a_results = await test_db.cop_candidates.find(
        {"workspace_id": "T01TEAMA"}
    ).to_list(None)

    # Assert
    assert len(workspace_a_results) == 1
    assert workspace_a_results[0]["workspace_id"] == "T01TEAMA"


# ============================================================================
# Audit Trail Tests
# ============================================================================


@pytest.mark.integration
@pytest.mark.requires_mongodb
@pytest.mark.asyncio
async def test_candidate_state_change_creates_audit_entry(
    test_db: AsyncIOMotorDatabase,
) -> None:
    """State changes should create audit log entries."""
    # Arrange
    candidate = {
        "_id": ObjectId(),
        "cluster_id": ObjectId(),
        "readiness_state": "in_review",
        "created_at": datetime.now(timezone.utc),
    }
    facilitator = create_facilitator()

    await test_db.cop_candidates.insert_one(candidate)
    await test_db.users.insert_one(facilitator)

    # Act - Change state and create audit entry
    await test_db.cop_candidates.update_one(
        {"_id": candidate["_id"]},
        {"$set": {"readiness_state": "verified"}},
    )

    audit_entry = {
        "_id": ObjectId(),
        "action_type": "cop_candidate.state_change",
        "actor_id": facilitator["_id"],
        "target_entity_type": "cop_candidate",
        "target_entity_id": candidate["_id"],
        "changes": {
            "before": {"readiness_state": "in_review"},
            "after": {"readiness_state": "verified"},
        },
        "timestamp": datetime.now(timezone.utc),
    }
    await test_db.audit_log.insert_one(audit_entry)

    # Assert
    audit_logs = await test_db.audit_log.find(
        {
            "action_type": "cop_candidate.state_change",
            "target_entity_id": candidate["_id"],
        }
    ).to_list(None)

    assert len(audit_logs) == 1
    assert audit_logs[0]["changes"]["before"]["readiness_state"] == "in_review"
    assert audit_logs[0]["changes"]["after"]["readiness_state"] == "verified"
