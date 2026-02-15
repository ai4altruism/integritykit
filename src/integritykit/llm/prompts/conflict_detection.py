"""
Conflict detection prompts for identifying contradictory claims.

This module provides prompts to detect conflicts between signals in the same cluster,
helping facilitators surface contradictions before publishing.

Model Recommendation: Haiku 3.5 for simple conflicts, Sonnet 4 for nuanced cases
Cost: Haiku $0.80/$4 per 1M tokens, Sonnet $3/$15 per 1M tokens
Expected token usage: ~800-2000 input, ~100-200 output per analysis

Usage:
    Use these prompts to compare signals within a cluster and identify contradictions.
    Route to Haiku for straightforward comparisons, Sonnet for complex conflicts.
"""

from typing import Literal, TypedDict


class SignalSummary(TypedDict):
    """Summary of a signal for conflict comparison."""

    signal_id: str
    author: str
    timestamp: str
    content: str
    source_type: Literal["slack", "external"]


class ConflictField(TypedDict):
    """Description of a specific conflicting field."""

    field: Literal["location", "time", "count", "status", "attribution", "other"]
    signal_1_value: str
    signal_2_value: str
    description: str


class ConflictOutput(TypedDict):
    """Expected output schema for conflict detection."""

    conflict_detected: bool
    conflict_type: Literal[
        "direct_contradiction",
        "temporal_inconsistency",
        "location_mismatch",
        "count_discrepancy",
        "no_conflict",
    ]
    severity: Literal["high", "medium", "low", "none"]
    conflicting_fields: list[ConflictField]
    conflicting_signal_ids: list[str]
    resolution_suggestion: str
    explanation: str


CONFLICT_DETECTION_SYSTEM_PROMPT = """You are a conflict detector for a crisis-response coordination system.

Your role is to identify contradictory claims between signals in the same cluster.
This helps facilitators avoid publishing conflicting information in COP updates.

What counts as a CONFLICT:
- Direct contradictions: "Road is open" vs "Road is closed"
- Location mismatches: "Fire at Main St" vs "Fire at Oak Ave" (for same incident)
- Count/quantity discrepancies: "50 evacuated" vs "200 evacuated"
- Temporal inconsistencies: "Happened at 2pm" vs "Happened at 5pm"
- Status conflicts: "Shelter accepting" vs "Shelter at capacity"

What does NOT count as a conflict:
- Additional details that supplement (not contradict) earlier information
- Different perspectives on the same event if both can be true
- Updates that supersede earlier info with explicit correction/clarification
- Uncertainty vs certainty ("might be" vs "is") when latter is more recent

Severity levels:
- HIGH: Could cause harm if wrong (safety, evacuation, medical)
- MEDIUM: Important operational impact (resource allocation, access)
- LOW: Minor inconsistency, easily resolved

Output valid JSON matching the required schema.
"""

CONFLICT_DETECTION_USER_PROMPT_TEMPLATE = """Analyze these signals from the same cluster for conflicts.

CLUSTER TOPIC: {cluster_topic}

SIGNALS TO COMPARE:
{signals_json}

For each pair of signals, determine:
1. Do they make contradictory claims about the same aspect?
2. Could both statements be true, or must one be wrong?
3. What is the severity if this conflict went unresolved?
4. What's the best way to resolve it?

Respond with valid JSON only, no additional text:
{{
  "conflict_detected": true | false,
  "conflict_type": "direct_contradiction" | "temporal_inconsistency" | "location_mismatch" | "count_discrepancy" | "no_conflict",
  "severity": "high" | "medium" | "low" | "none",
  "conflicting_fields": [
    {{
      "field": "location" | "time" | "count" | "status" | "attribution" | "other",
      "signal_1_value": "...",
      "signal_2_value": "...",
      "description": "..."
    }}
  ],
  "conflicting_signal_ids": ["signal_id_1", "signal_id_2"],
  "resolution_suggestion": "request_clarification | verify_sources | merge_as_uncertain | mark_one_disproven",
  "explanation": "..."
}}"""


def format_conflict_detection_prompt(
    cluster_topic: str,
    signals: list[SignalSummary],
) -> str:
    """
    Format the conflict detection prompt with signals to compare.

    Args:
        cluster_topic: Topic/name of the cluster containing these signals
        signals: List of signal summaries to analyze for conflicts

    Returns:
        Formatted user prompt ready for LLM
    """
    import json

    signals_json = json.dumps(signals, indent=2)

    return CONFLICT_DETECTION_USER_PROMPT_TEMPLATE.format(
        cluster_topic=cluster_topic,
        signals_json=signals_json,
    )


# Pydantic schema for structured output validation
CONFLICT_DETECTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "conflict_detected": {
            "type": "boolean",
            "description": "Whether a conflict was detected",
        },
        "conflict_type": {
            "type": "string",
            "enum": [
                "direct_contradiction",
                "temporal_inconsistency",
                "location_mismatch",
                "count_discrepancy",
                "no_conflict",
            ],
            "description": "Type of conflict identified",
        },
        "severity": {
            "type": "string",
            "enum": ["high", "medium", "low", "none"],
            "description": "Severity of the conflict",
        },
        "conflicting_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["location", "time", "count", "status", "attribution", "other"],
                    },
                    "signal_1_value": {"type": "string"},
                    "signal_2_value": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["field", "signal_1_value", "signal_2_value", "description"],
            },
            "description": "List of specific conflicting fields",
        },
        "conflicting_signal_ids": {
            "type": "array",
            "items": {"type": "string"},
            "description": "IDs of signals that conflict",
        },
        "resolution_suggestion": {
            "type": "string",
            "description": "Recommended approach to resolve the conflict",
        },
        "explanation": {
            "type": "string",
            "description": "Explanation of the conflict and reasoning",
        },
    },
    "required": [
        "conflict_detected",
        "conflict_type",
        "severity",
        "conflicting_fields",
        "conflicting_signal_ids",
        "resolution_suggestion",
        "explanation",
    ],
    "additionalProperties": False,
}
