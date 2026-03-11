"""Slack Block Kit UI components for IntegrityKit.

Implements:
- FR-COP-READ-002: Missing/weak fields checklist UI
- Candidate detail views with readiness indicators
- S8-5: Internationalization support for Block Kit templates
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
from integritykit.models.language import LanguageCode
from integritykit.services.readiness import FieldEvaluation, FieldStatus, ReadinessEvaluation
from integritykit.slack.i18n import TranslationKey, build_clarification_message, get_translation


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
    language: str | LanguageCode = LanguageCode.EN,
) -> list[dict[str, Any]]:
    """Build Slack blocks for the missing/weak fields checklist.

    Args:
        candidate: COP candidate to display
        field_evaluations: Field evaluation results
        language: Language code for translations (defaults to English)

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": get_translation(TranslationKey.FIELD_COMPLETENESS_CHECKLIST, language),
            "emoji": True,
        },
    })

    # Summary section
    missing_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.MISSING)
    partial_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.PARTIAL)
    complete_count = sum(1 for fe in field_evaluations if fe.status == FieldStatus.COMPLETE)

    if missing_count == 0 and partial_count == 0:
        summary_text = f":white_check_mark: {get_translation(TranslationKey.ALL_FIELDS_COMPLETE, language)}"
        summary_color = "good"
    elif missing_count > 0:
        summary_text = f":warning: {get_translation(TranslationKey.MISSING_FIELDS_WARNING, language, missing=missing_count, partial=partial_count)}"
        summary_color = "danger"
    else:
        summary_text = f":hourglass: {get_translation(TranslationKey.FIELDS_NEED_IMPROVEMENT, language, partial=partial_count)}"
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
        label = get_translation(fe.field, language) if fe.field in ["what", "where", "when", "who", "so_what"] else fe.field.title()
        status_text = get_translation(fe.status.value if hasattr(fe.status, "value") else str(fe.status), language)

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
    language: str | LanguageCode = LanguageCode.EN,
) -> list[dict[str, Any]]:
    """Build Slack blocks showing readiness status summary.

    Args:
        candidate: COP candidate
        evaluation: Readiness evaluation results
        language: Language code for translations (defaults to English)

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    # Readiness state header
    state_icon = READINESS_STATE_ICONS.get(evaluation.readiness_state, ":grey_question:")
    # Map readiness state to translation key
    state_key_map = {
        ReadinessState.VERIFIED: TranslationKey.READY_VERIFIED,
        ReadinessState.IN_REVIEW: TranslationKey.READY_IN_REVIEW,
        ReadinessState.BLOCKED: TranslationKey.BLOCKED,
    }
    state_key = state_key_map.get(evaluation.readiness_state, TranslationKey.BLOCKED)
    state_text = get_translation(state_key, language)

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{get_translation(TranslationKey.READINESS_STATUS, language)}:* {state_icon} {state_text}",
        },
    })

    # Risk tier
    risk_icon = RISK_TIER_ICONS.get(candidate.risk_tier, ":grey_question:")
    risk_tier_text = get_translation(candidate.risk_tier.value if hasattr(candidate.risk_tier, "value") else str(candidate.risk_tier), language)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{get_translation(TranslationKey.RISK_TIER, language)}:* {risk_icon} {risk_tier_text}",
        },
    })

    # Blocking issues
    if evaluation.blocking_issues:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":no_entry: *{get_translation(TranslationKey.BLOCKING_ISSUES, language)}:*",
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
    language: str | LanguageCode = LanguageCode.EN,
) -> list[dict[str, Any]]:
    """Build Slack blocks showing recommended next action.

    Args:
        candidate: COP candidate
        recommended_action: Recommended action from evaluation
        clarification_template: Optional clarification message template
        language: Language code for translations (defaults to English)

    Returns:
        List of Slack Block Kit blocks
    """
    blocks = []

    if not recommended_action:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":thumbsup: {get_translation(TranslationKey.NO_ACTION_REQUIRED, language)}",
            },
        })
        return blocks

    # Action header
    action_icon = ACTION_TYPE_ICONS.get(recommended_action.action_type, ":arrow_right:")
    # Map action type to translation key
    action_type_value = recommended_action.action_type.value if hasattr(recommended_action.action_type, "value") else str(recommended_action.action_type)
    action_name = get_translation(action_type_value, language)

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": get_translation(TranslationKey.RECOMMENDED_NEXT_ACTION, language),
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

    button_key_map = {
        ActionType.ASSIGN_VERIFICATION: TranslationKey.ASSIGN_VERIFIER,
        ActionType.RESOLVE_CONFLICT: TranslationKey.VIEW_CONFLICTS,
        ActionType.ADD_EVIDENCE: TranslationKey.REQUEST_INFO,
        ActionType.READY_TO_PUBLISH: TranslationKey.PUBLISH,
        ActionType.MERGE_CANDIDATES: TranslationKey.VIEW_DUPLICATES,
    }

    action_id = action_id_map.get(recommended_action.action_type, "view_candidate")
    button_key = button_key_map.get(recommended_action.action_type, TranslationKey.VIEW)
    button_text = get_translation(button_key, language)

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
                "text": f"*{get_translation(TranslationKey.SUGGESTED_MESSAGE, language)}*",
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
                    "text": f":bulb: {get_translation(TranslationKey.COPY_MESSAGE_HINT, language)}",
                },
            ],
        })

    # Alternative actions
    if recommended_action.alternatives:
        blocks.append({"type": "divider"})
        alt_text = ", ".join(
            get_translation(a, language) for a in recommended_action.alternatives[:3]
        )
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":arrows_counterclockwise: *{get_translation(TranslationKey.ALTERNATIVES, language)}* {alt_text}",
                },
            ],
        })

    return blocks


def build_candidate_detail_blocks(
    candidate: COPCandidate,
    field_evaluations: list[FieldEvaluation],
    evaluation: ReadinessEvaluation,
    language: str | LanguageCode = LanguageCode.EN,
) -> list[dict[str, Any]]:
    """Build full candidate detail view with all sections.

    Args:
        candidate: COP candidate
        field_evaluations: Field evaluation results
        evaluation: Readiness evaluation results
        language: Language code for translations (defaults to English)

    Returns:
        List of Slack Block Kit blocks for modal or App Home
    """
    blocks = []

    # Candidate header
    state_icon = READINESS_STATE_ICONS.get(evaluation.readiness_state, ":grey_question:")
    state_key_map = {
        ReadinessState.VERIFIED: TranslationKey.READY_VERIFIED,
        ReadinessState.IN_REVIEW: TranslationKey.READY_IN_REVIEW,
        ReadinessState.BLOCKED: TranslationKey.BLOCKED,
    }
    state_key = state_key_map.get(evaluation.readiness_state, TranslationKey.BLOCKED)
    state_text = get_translation(state_key, language)

    blocks.append({
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": get_translation(TranslationKey.COP_CANDIDATE_DETAILS, language),
            "emoji": True,
        },
    })

    # Status summary
    risk_tier_text = get_translation(candidate.risk_tier.value if hasattr(candidate.risk_tier, "value") else str(candidate.risk_tier), language)
    blocks.append({
        "type": "section",
        "fields": [
            {
                "type": "mrkdwn",
                "text": f"*{get_translation(TranslationKey.READINESS_STATUS, language)}:*\n{state_icon} {state_text}",
            },
            {
                "type": "mrkdwn",
                "text": f"*{get_translation(TranslationKey.VERIFICATIONS, language).title()}:*\n{len(candidate.verifications)}",
            },
            {
                "type": "mrkdwn",
                "text": f"*{get_translation(TranslationKey.RISK_TIER, language)}:*\n{risk_tier_text}",
            },
            {
                "type": "mrkdwn",
                "text": f"*{get_translation(TranslationKey.EVIDENCE, language)}:*\n{len(candidate.evidence.slack_permalinks) + len(candidate.evidence.external_sources)} sources",
            },
        ],
    })

    blocks.append({"type": "divider"})

    # COP Fields
    not_specified = get_translation(TranslationKey.NOT_SPECIFIED, language)
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{get_translation(TranslationKey.COP_INFORMATION, language)}:*",
        },
    })

    # What
    what_status = next((fe for fe in field_evaluations if fe.field == "what"), None)
    what_icon = FIELD_STATUS_ICONS.get(what_status.status if what_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{what_icon} *{get_translation(TranslationKey.WHAT, language)}:* {candidate.fields.what or f'_{not_specified}_'}",
        },
    })

    # Where
    where_status = next((fe for fe in field_evaluations if fe.field == "where"), None)
    where_icon = FIELD_STATUS_ICONS.get(where_status.status if where_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{where_icon} *{get_translation(TranslationKey.WHERE, language)}:* {candidate.fields.where or f'_{not_specified}_'}",
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
            "text": f"{when_icon} *{get_translation(TranslationKey.WHEN, language)}:* {when_value or f'_{not_specified}_'}",
        },
    })

    # Who
    who_status = next((fe for fe in field_evaluations if fe.field == "who"), None)
    who_icon = FIELD_STATUS_ICONS.get(who_status.status if who_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{who_icon} *{get_translation(TranslationKey.WHO, language)}:* {candidate.fields.who or f'_{not_specified}_'}",
        },
    })

    # So What
    so_what_status = next((fe for fe in field_evaluations if fe.field == "so_what"), None)
    so_what_icon = FIELD_STATUS_ICONS.get(so_what_status.status if so_what_status else FieldStatus.MISSING, ":grey_question:")
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"{so_what_icon} *{get_translation(TranslationKey.SO_WHAT, language)}:* {candidate.fields.so_what or f'_{not_specified}_'}",
        },
    })

    blocks.append({"type": "divider"})

    # Add readiness summary
    blocks.extend(build_readiness_summary_blocks(candidate, evaluation, language))

    blocks.append({"type": "divider"})

    # Add next action recommendation
    clarification_template = None
    if evaluation.recommended_action and evaluation.recommended_action.action_type == ActionType.ADD_EVIDENCE:
        # Would get from readiness service
        pass

    blocks.extend(build_next_action_blocks(
        candidate, evaluation.recommended_action, clarification_template, language
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
                    "text": get_translation(TranslationKey.VIEW_FULL_DETAILS, language),
                    "emoji": True,
                },
                "action_id": f"view_candidate_full_{candidate.id}",
                "value": str(candidate.id),
            },
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": get_translation(TranslationKey.REEVALUATE, language),
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
    language: str | LanguageCode = LanguageCode.EN,
) -> list[dict[str, Any]]:
    """Build compact candidate list item for backlog/list views.

    Args:
        candidate: COP candidate
        language: Language code for translations (defaults to English)

    Returns:
        List of Slack Block Kit blocks for a single list item
    """
    state_icon = READINESS_STATE_ICONS.get(candidate.readiness_state, ":grey_question:")
    risk_icon = RISK_TIER_ICONS.get(candidate.risk_tier, ":grey_question:")

    # Truncate what field for preview
    what_preview = candidate.fields.what[:80] + "..." if len(candidate.fields.what or "") > 80 else (candidate.fields.what or get_translation(TranslationKey.UNTITLED, language))

    risk_tier_text = get_translation(candidate.risk_tier.value if hasattr(candidate.risk_tier, "value") else str(candidate.risk_tier), language)
    verifications_text = get_translation(TranslationKey.VERIFICATIONS, language)

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{state_icon} *{what_preview}*\n{risk_icon} {risk_tier_text} | :memo: {len(candidate.verifications)} {verifications_text}",
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": get_translation(TranslationKey.VIEW, language),
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
        blocking_issue_text = get_translation(TranslationKey.BLOCKING_ISSUE_COUNT, language)
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":no_entry: {blocking_count} {blocking_issue_text}",
                },
            ],
        })

    return blocks
