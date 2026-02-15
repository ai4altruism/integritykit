"""Slack Block Kit UI components for IntegrityKit.

Implements:
- FR-COP-READ-002: Missing/weak fields checklist UI
- Candidate detail views with readiness indicators
"""

from typing import Any, Optional

from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    BlockingIssueSeverity,
    COPCandidate,
    ReadinessState,
    RecommendedAction,
    RiskTier,
)
from integritykit.services.readiness import FieldEvaluation, FieldStatus, ReadinessEvaluation


# ============================================================================
# Field Status Icons
# ============================================================================

FIELD_STATUS_ICONS = {
    FieldStatus.COMPLETE: ":white_check_mark:",
    FieldStatus.PARTIAL: ":warning:",
    FieldStatus.MISSING: ":x:",
}

FIELD_STATUS_TEXT = {
    FieldStatus.COMPLETE: "Complete",
    FieldStatus.PARTIAL: "Needs improvement",
    FieldStatus.MISSING: "Missing",
}

READINESS_STATE_ICONS = {
    ReadinessState.VERIFIED: ":white_check_mark:",
    ReadinessState.IN_REVIEW: ":hourglass:",
    ReadinessState.BLOCKED: ":no_entry:",
}

READINESS_STATE_TEXT = {
    ReadinessState.VERIFIED: "Ready - Verified",
    ReadinessState.IN_REVIEW: "Ready - In Review",
    ReadinessState.BLOCKED: "Blocked",
}

RISK_TIER_ICONS = {
    RiskTier.ROUTINE: ":large_green_circle:",
    RiskTier.ELEVATED: ":large_yellow_circle:",
    RiskTier.HIGH_STAKES: ":red_circle:",
}

ACTION_TYPE_ICONS = {
    ActionType.ASSIGN_VERIFICATION: ":clipboard:",
    ActionType.RESOLVE_CONFLICT: ":scales:",
    ActionType.ADD_EVIDENCE: ":mag:",
    ActionType.READY_TO_PUBLISH: ":rocket:",
    ActionType.MERGE_CANDIDATES: ":link:",
}

FIELD_LABELS = {
    "what": "What",
    "where": "Where",
    "when": "When",
    "who": "Who",
    "so_what": "So What",
    "evidence": "Evidence",
}


# ============================================================================
# Missing Fields Checklist UI (FR-COP-READ-002)
# ============================================================================


def build_fields_checklist_blocks(
    candidate: COPCandidate,
    field_evaluations: list[FieldEvaluation],
) -> list[dict[str, Any]]:
    """Build Slack blocks for the missing/weak fields checklist.

    Args:
        candidate: COP candidate to display
        field_evaluations: Field evaluation results

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "Field Completeness Checklist",
            "emoji": True,
        },
    })

    # Summary section
    missing_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.MISSING)
    partial_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.PARTIAL)
    complete_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.COMPLETE)

    if missing_count == 0 and partial_count == 0:
        summary_text = ":white_check_mark: All fields are complete!"
        summary_color = "good"
    elif missing_count > 0:
        summary_text = f":warning: {missing_count} missing, {partial_count} need improvement"
        summary_color = "danger"
    else:
        summary_text = f":hourglass: {partial_count} fields need improvement"
        summary_color = "warning"

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": summary_text,
        },
    })

    blocks.append({"type": "divider"})

    # Field-by-field breakdown
    for fe in field_evaluations:
        icon = FIELD_STATUS_ICONS.get(fe.status, ":grey_question:")
        label = FIELD_LABELS.get(fe.field, fe.field.title())
        status_text = FIELD_STATUS_TEXT.get(fe.status, "Unknown")

        value_preview = ""
        if fe.value:
            value_preview = f"\n_{fe.value[:50]}{'...' if len(fe.value) > 50 else ''}_"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{icon} *{label}*: {status_text}{value_preview}",
            },
        })

        if fe.notes and fe.status != FieldStatus.COMPLETE:
            blocks.append({
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f":bulb: {fe.notes}",
                    },
                ],
            })

    return blocks


def build_readiness_summary_blocks(
    candidate: COPCandidate,
    evaluation: ReadinessEvaluation,
) -> list[dict[str, Any]]:
    """Build Slack blocks showing readiness status summary.

    Args:
        candidate: COP candidate
        evaluation: Readiness evaluation results

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    # Readiness state header
    state_icon = READINESS_STATE_ICONS.get(evaluation.readiness_state, ":grey_question:")
    state_text = READINESS_STATE_TEXT.get(evaluation.readiness_state, "Unknown")

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Readiness Status:* {state_icon} {state_text}",
        },
    })

    # Risk tier
    risk_icon = RISK_TIER_ICONS.get(candidate.risk_tier, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*Risk Tier:* {risk_icon} {candidate.risk_tier.value.replace('_', ' ').title()}",
        },
    })

    # Blocking issues
    if evaluation.blocking_issues:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":no_entry: *Blocking Issues:*",
            },
        })

        for issue in evaluation.blocking_issues:
            severity_icon = ":red_circle:" if issue.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING else ":large_yellow_circle:"
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"{severity_icon} {issue.description}",
                },
            })

    # Explanation
    if evaluation.explanation:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":information_source: {evaluation.explanation}",
                },
            ],
        })

    return blocks


def build_next_action_blocks(
    candidate: COPCandidate,
    recommended_action: Optional[RecommendedAction],
    clarification_template: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Build Slack blocks showing recommended next action.

    Args:
        candidate: COP candidate
        recommended_action: Recommended action from evaluation
        clarification_template: Optional clarification message template

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    if not recommended_action:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":thumbsup: No action required at this time.",
            },
        })
        return blocks

    # Action header
    action_icon = ACTION_TYPE_ICONS.get(recommended_action.action_type, ":arrow_right:")
    action_name = recommended_action.action_type.value.replace("_", " ").title()

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": "Recommended Next Action",
            "emoji": True,
        },
    })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{action_icon} *{action_name}*\n{recommended_action.reason}",
        },
    })

    # Action button
    action_id_map = {
        ActionType.ASSIGN_VERIFICATION: "assign_verification",
        ActionType.RESOLVE_CONFLICT: "resolve_conflict",
        ActionType.ADD_EVIDENCE: "request_clarification",
        ActionType.READY_TO_PUBLISH: "publish_candidate",
        ActionType.MERGE_CANDIDATES: "merge_candidates",
    }

    button_text_map = {
        ActionType.ASSIGN_VERIFICATION: "Assign Verifier",
        ActionType.RESOLVE_CONFLICT: "View Conflicts",
        ActionType.ADD_EVIDENCE: "Request Info",
        ActionType.READY_TO_PUBLISH: "Publish",
        ActionType.MERGE_CANDIDATES: "View Duplicates",
    }

    action_id = action_id_map.get(recommended_action.action_type, "view_candidate")
    button_text = button_text_map.get(recommended_action.action_type, "Take Action")

    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": button_text,
                    "emoji": True,
                },
                "style": "primary",
                "action_id": f"{action_id}_{candidate.id}",
                "value": str(candidate.id),
            },
        ],
    })

    # Clarification template if applicable
    if clarification_template:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Suggested Message:*",
            },
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{clarification_template}```",
            },
        })
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": ":bulb: Copy this message to request clarification from the source.",
                },
            ],
        })

    # Alternative actions
    if recommended_action.alternatives:
        blocks.append({"type": "divider"})
        alt_text = ", ".join(
            a.replace("_", " ").title() for a in recommended_action.alternatives[:3]
        )
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":arrows_counterclockwise: *Alternatives:* {alt_text}",
                },
            ],
        })

    return blocks


def build_candidate_detail_blocks(
    candidate: COPCandidate,
    field_evaluations: list[FieldEvaluation],
    evaluation: ReadinessEvaluation,
) -> list[dict[str, Any]]:
    """Build full candidate detail view with all sections.

    Args:
        candidate: COP candidate
        field_evaluations: Field evaluation results
        evaluation: Readiness evaluation results

    Returns:
        List of Slack Block Kit blocks for modal or App Home
    """
    blocks = []

    # Candidate header
    state_icon = READINESS_STATE_ICONS.get(evaluation.readiness_state, ":grey_question:")
    state_text = READINESS_STATE_TEXT.get(evaluation.readiness_state, "Unknown")

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"COP Candidate Details",
            "emoji": True,
        },
    })

    # Status summary
    blocks.append({
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": f"*Status:*\n{state_icon} {state_text}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Verifications:*\n{len(candidate.verifications)}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Risk Tier:*\n{candidate.risk_tier.value.replace('_', ' ').title()}",
            },
            {
                "type": "mrkdwn",
                "text": f"*Evidence:*\n{len(candidate.evidence.slack_permalinks) + len(candidate.evidence.external_sources)} sources",
            },
        ],
    })

    blocks.append({"type": "divider"})

    # COP Fields
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "*COP Information:*",
        },
    })

    # What
    what_status = next((fe for fe in field_evaluations if fe.field == "what"), None)
    what_icon = FIELD_STATUS_ICONS.get(what_status.status if what_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{what_icon} *What:* {candidate.fields.what or '_Not specified_'}",
        },
    })

    # Where
    where_status = next((fe for fe in field_evaluations if fe.field == "where"), None)
    where_icon = FIELD_STATUS_ICONS.get(where_status.status if where_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{where_icon} *Where:* {candidate.fields.where or '_Not specified_'}",
        },
    })

    # When
    when_value = candidate.fields.when.description or (
        candidate.fields.when.timestamp.isoformat() if candidate.fields.when.timestamp else ""
    )
    when_status = next((fe for fe in field_evaluations if fe.field == "when"), None)
    when_icon = FIELD_STATUS_ICONS.get(when_status.status if when_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{when_icon} *When:* {when_value or '_Not specified_'}",
        },
    })

    # Who
    who_status = next((fe for fe in field_evaluations if fe.field == "who"), None)
    who_icon = FIELD_STATUS_ICONS.get(who_status.status if who_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{who_icon} *Who:* {candidate.fields.who or '_Not specified_'}",
        },
    })

    # So What
    so_what_status = next((fe for fe in field_evaluations if fe.field == "so_what"), None)
    so_what_icon = FIELD_STATUS_ICONS.get(so_what_status.status if so_what_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{so_what_icon} *So What:* {candidate.fields.so_what or '_Not specified_'}",
        },
    })

    blocks.append({"type": "divider"})

    # Add readiness summary
    blocks.extend(build_readiness_summary_blocks(candidate, evaluation))

    blocks.append({"type": "divider"})

    # Add next action recommendation
    clarification_template = None
    if evaluation.recommended_action and evaluation.recommended_action.action_type == ActionType.ADD_EVIDENCE:
        # Would get from readiness service
        pass

    blocks.extend(build_next_action_blocks(
        candidate, evaluation.recommended_action, clarification_template
    ))

    # Action buttons
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Full Details",
                    "emoji": True,
                },
                "action_id": f"view_candidate_full_{candidate.id}",
                "value": str(candidate.id),
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "Re-evaluate",
                    "emoji": True,
                },
                "action_id": f"reevaluate_candidate_{candidate.id}",
                "value": str(candidate.id),
            },
        ],
    })

    return blocks


def build_candidate_list_item_blocks(
    candidate: COPCandidate,
) -> list[dict[str, Any]]:
    """Build compact candidate list item for backlog/list views.

    Args:
        candidate: COP candidate

    Returns:
        List of Slack Block Kit blocks for a single list item
    """
    state_icon = READINESS_STATE_ICONS.get(candidate.readiness_state, ":grey_question:")
    risk_icon = RISK_TIER_ICONS.get(candidate.risk_tier, ":grey_question:")

    # Truncate what field for preview
    what_preview = candidate.fields.what[:80] + "..." if len(candidate.fields.what or "") > 80 else (candidate.fields.what or "Untitled")

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{state_icon} *{what_preview}*\n{risk_icon} {candidate.risk_tier.value.replace('_', ' ').title()} | :memo: {len(candidate.verifications)} verifications",
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View",
                    "emoji": True,
                },
                "action_id": f"view_candidate_{candidate.id}",
                "value": str(candidate.id),
            },
        },
    ]

    # Add blocking issue indicator if present
    blocking_count = sum(
        1 for bi in candidate.blocking_issues
        if bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING
    )
    if blocking_count > 0:
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":no_entry: {blocking_count} blocking issue(s)",
                },
            ],
        })

    return blocks
