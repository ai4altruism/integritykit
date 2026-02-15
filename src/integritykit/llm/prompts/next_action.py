"""
Next action recommendation prompts for suggesting best facilitator actions.

This module provides prompts to recommend the best next action for a COP candidate
based on its state, missing fields, and conflicts.

Model Recommendation: Haiku 3.5 (decision tree-style recommendation)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~500-1000 input, ~100-150 output per recommendation

Usage:
    Use these prompts to implement SRS FR-COP-READ-003 (recommend best next action).
    Helps facilitators prioritize and take efficient actions under surge conditions.
"""

from typing import Literal, TypedDict


class COPCandidateState(TypedDict):
    """Current state of a COP candidate for action recommendation."""

    candidate_id: str
    readiness_state: Literal["ready_verified", "ready_in_review", "blocked"]
    missing_fields: list[Literal["what", "where", "when", "who", "so_what", "evidence"]]
    has_unresolved_conflicts: bool
    conflict_severity: Literal["high", "medium", "low", "none"]
    verification_status: Literal["verified", "in_review", "unverified"]
    risk_tier: Literal["routine", "elevated", "high_stakes"]
    has_potential_duplicates: bool
    evidence_pack_size: int


class NextActionOutput(TypedDict):
    """Expected output schema for next action recommendation."""

    primary_action: Literal[
        "request_clarification",
        "assign_verification",
        "merge_duplicate",
        "resolve_conflict",
        "publish_as_in_review",
        "publish_as_verified",
        "defer",
    ]
    alternative_actions: list[
        Literal[
            "request_clarification",
            "assign_verification",
            "merge_duplicate",
            "resolve_conflict",
            "publish_as_in_review",
            "publish_as_verified",
            "defer",
        ]
    ]
    action_target: str  # What field to clarify, who to assign, etc.
    urgency: Literal["immediate", "soon", "when_possible"]
    reasoning: str
    suggested_message: str | None  # Template message for request_clarification


NEXT_ACTION_SYSTEM_PROMPT = """You are an action recommender for a crisis-response COP system.

Your role is to recommend the single best next action a facilitator should take
to improve a COP candidate's readiness, plus 1-3 alternative actions.

Available Actions:

1. REQUEST_CLARIFICATION
   - When: Missing critical fields or field is too vague
   - Target: Specific field to clarify (where, when, who, etc.)
   - Provide a suggested message template

2. ASSIGN_VERIFICATION
   - When: High-stakes item needs verification, or ready for verification
   - Target: Who to assign or what to verify
   - Urgency: High for high-stakes, medium otherwise

3. MERGE_DUPLICATE
   - When: Potential duplicates identified
   - Target: Which candidates to merge
   - Helps reduce redundancy

4. RESOLVE_CONFLICT
   - When: Unresolved conflicts detected
   - Target: Which signals are conflicting
   - Urgency scales with conflict severity

5. PUBLISH_AS_IN_REVIEW
   - When: Minimum fields present, no high-risk blocks
   - Target: Section placement
   - Quick publication option for time-sensitive info

6. PUBLISH_AS_VERIFIED
   - When: All fields complete, verified, no conflicts
   - Target: Verified section
   - Final publication step

7. DEFER
   - When: Incomplete and not urgent, or waiting on external input
   - Target: Reason to defer
   - Appropriate for low-priority items

Priority Logic:
1. High-stakes unverified → ASSIGN_VERIFICATION (immediate)
2. Unresolved high-severity conflict → RESOLVE_CONFLICT (immediate)
3. Missing critical field → REQUEST_CLARIFICATION (soon)
4. Potential duplicate → MERGE_DUPLICATE (when possible)
5. Ready verified → PUBLISH_AS_VERIFIED (soon)
6. Ready in-review (not high-stakes) → PUBLISH_AS_IN_REVIEW (soon)
7. Incomplete, low-risk → REQUEST_CLARIFICATION or DEFER (when possible)

Output valid JSON with primary action, alternatives, and reasoning.
"""

NEXT_ACTION_USER_PROMPT_TEMPLATE = """Recommend the best next action for this COP candidate.

COP CANDIDATE STATE:
{candidate_state_json}

Analyze the state and determine:
1. What is the single most important action to take right now?
2. What are 1-3 alternative actions the facilitator could take?
3. How urgent is this action?
4. If requesting clarification, what message should the facilitator send?

Respond with valid JSON only, no additional text:
{{
  "primary_action": "request_clarification" | "assign_verification" | "merge_duplicate" | "resolve_conflict" | "publish_as_in_review" | "publish_as_verified" | "defer",
  "alternative_actions": ["...", "..."],
  "action_target": "Specific target of action",
  "urgency": "immediate" | "soon" | "when_possible",
  "reasoning": "Why this is the best next action",
  "suggested_message": "Template message for facilitator to use (if request_clarification)" or null
}}"""


def format_next_action_prompt(
    candidate_state: COPCandidateState,
) -> str:
    """
    Format the next action recommendation prompt with candidate state.

    Args:
        candidate_state: Current state of the COP candidate

    Returns:
        Formatted user prompt ready for LLM
    """
    import json

    candidate_state_json = json.dumps(candidate_state, indent=2)

    return NEXT_ACTION_USER_PROMPT_TEMPLATE.format(
        candidate_state_json=candidate_state_json,
    )


# Suggested message templates for common clarification requests
CLARIFICATION_TEMPLATES = {
    "location": """Thanks for the update. To include this in the COP, can you confirm the exact location (city/county/landmark)? If you have coordinates or an address, that would be helpful.""",
    "time": """Quick check: can you confirm the time/date and timezone for this? We want to make sure the COP timeline is accurate.""",
    "location_and_time": """Thanks — to include this in the COP, can you confirm: (1) the exact location (city/county/landmark), and (2) the time/date + timezone? If you have a source link or official confirmation, please share it here.""",
    "source": """Quick check: is this first-hand, second-hand, or from an external source? If external, can you share the link or the name of the originating org?""",
    "conflict": """We're seeing two different values reported (A vs B). Do you know which is current, or can you share where your value came from?""",
}


# Pydantic schema for structured output validation
NEXT_ACTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "primary_action": {
            "type": "string",
            "enum": [
                "request_clarification",
                "assign_verification",
                "merge_duplicate",
                "resolve_conflict",
                "publish_as_in_review",
                "publish_as_verified",
                "defer",
            ],
            "description": "The single best next action to take",
        },
        "alternative_actions": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "request_clarification",
                    "assign_verification",
                    "merge_duplicate",
                    "resolve_conflict",
                    "publish_as_in_review",
                    "publish_as_verified",
                    "defer",
                ],
            },
            "description": "1-3 alternative actions the facilitator could take",
        },
        "action_target": {
            "type": "string",
            "description": "Specific target of the action (field, person, candidates, etc.)",
        },
        "urgency": {
            "type": "string",
            "enum": ["immediate", "soon", "when_possible"],
            "description": "Urgency level for the action",
        },
        "reasoning": {
            "type": "string",
            "description": "Explanation of why this is the best next action",
        },
        "suggested_message": {
            "type": ["string", "null"],
            "description": "Template message for request_clarification action",
        },
    },
    "required": [
        "primary_action",
        "alternative_actions",
        "action_target",
        "urgency",
        "reasoning",
    ],
    "additionalProperties": False,
}
