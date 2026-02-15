"""
Readiness evaluation prompts for COP candidate completeness assessment.

This module provides prompts to evaluate whether a COP candidate has sufficient
information to be publishable, and identifies missing or weak fields.

Model Recommendation: Haiku 3.5 (structured evaluation task)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~600-1200 input, ~150-300 output per evaluation

Usage:
    Use these prompts to compute readiness state (Ready-Verified / Ready-In-Review / Blocked)
    and identify missing fields per SRS FR-COP-READ-001 and FR-COP-READ-002.
"""

from typing import Literal, TypedDict


class COPCandidateData(TypedDict):
    """COP candidate fields for readiness evaluation."""

    candidate_id: str
    what: str | None  # The claim/situation statement
    where: str | None  # Location
    when: str | None  # Timestamp or time window
    who: str | None  # Source/actor/affected population
    so_what: str | None  # Operational relevance
    evidence_pack_size: int  # Number of citations
    verification_status: Literal["verified", "in_review", "unverified"]
    has_unresolved_conflicts: bool
    risk_tier: Literal["routine", "elevated", "high_stakes"]


class FieldQuality(TypedDict):
    """Quality assessment for a single field."""

    field: Literal["what", "where", "when", "who", "so_what", "evidence"]
    present: bool
    quality: Literal["complete", "partial", "missing"]
    notes: str


class ReadinessOutput(TypedDict):
    """Expected output schema for readiness evaluation."""

    readiness_state: Literal["ready_verified", "ready_in_review", "blocked"]
    missing_fields: list[Literal["what", "where", "when", "who", "so_what", "evidence"]]
    field_quality_scores: list[FieldQuality]
    blocking_issues: list[str]
    recommended_state: Literal["ready_verified", "ready_in_review", "blocked"]
    explanation: str


READINESS_EVALUATION_SYSTEM_PROMPT = """You are a readiness evaluator for a crisis-response COP system.

Your role is to assess whether a COP candidate has sufficient information to be publishable,
and to identify what's missing or weak.

COP Line Item Minimum Fields (from SRS):
- WHAT: A scoped claim or situation statement
- WHERE: Location at best available granularity (may be approximate but must be explicit)
- WHEN: Timestamp or time window with timezone (may be approximate but must be explicit)
- WHO: Source/actor/affected population (as applicable)
- SO WHAT: Operational relevance (why it matters)
- EVIDENCE: Links to Slack permalinks and/or external sources

Readiness States:
1. READY — VERIFIED:
   - All minimum fields present
   - Verification action logged (verification_status = "verified")
   - No unresolved conflicts
   - Can publish in "Verified" section

2. READY — IN REVIEW:
   - Minimum fields present enough to avoid misleading readers
   - At least basic evidence (Slack permalinks)
   - No unresolved HIGH-RISK conflicts
   - Must be labeled as "In Review" and separated from verified updates

3. BLOCKED:
   - Missing critical fields that make the statement ambiguous or unsafe
   - Unresolved conflicts on key facts
   - High-stakes item lacking required verification
   - NOT publishable until unblocked

High-stakes publish rules:
- If risk_tier is "high_stakes", verification is REQUIRED unless explicitly overridden
- High-stakes + unverified = BLOCKED (default)

Evaluate field quality:
- COMPLETE: Field is specific, clear, and actionable
- PARTIAL: Field is present but vague, ambiguous, or incomplete
- MISSING: Field is absent or unusable

Output valid JSON matching the required schema.
"""

READINESS_EVALUATION_USER_PROMPT_TEMPLATE = """Evaluate this COP candidate for readiness and completeness.

COP CANDIDATE:
{candidate_json}

Assess each field:
1. Is it present?
2. Is it complete, partial, or missing?
3. Does it meet the minimum standard for publication?

Determine the appropriate readiness state:
- READY_VERIFIED if all fields complete and verified
- READY_IN_REVIEW if minimum fields present but not verified
- BLOCKED if missing critical fields or has blocking issues

Identify any blocking issues:
- Missing required fields
- Unresolved conflicts
- High-stakes without verification

Respond with valid JSON only, no additional text:
{{
  "readiness_state": "ready_verified" | "ready_in_review" | "blocked",
  "missing_fields": ["what", "where", ...],
  "field_quality_scores": [
    {{
      "field": "what" | "where" | "when" | "who" | "so_what" | "evidence",
      "present": true | false,
      "quality": "complete" | "partial" | "missing",
      "notes": "..."
    }}
  ],
  "blocking_issues": ["Missing location", "Unresolved conflict", ...],
  "recommended_state": "ready_verified" | "ready_in_review" | "blocked",
  "explanation": "..."
}}"""


def format_readiness_evaluation_prompt(
    candidate: COPCandidateData,
) -> str:
    """
    Format the readiness evaluation prompt with candidate data.

    Args:
        candidate: COP candidate data including all fields and metadata

    Returns:
        Formatted user prompt ready for LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2)

    return READINESS_EVALUATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Pydantic schema for structured output validation
READINESS_EVALUATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "readiness_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "Current readiness state based on evaluation",
        },
        "missing_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["what", "where", "when", "who", "so_what", "evidence"],
            },
            "description": "List of missing required fields",
        },
        "field_quality_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["what", "where", "when", "who", "so_what", "evidence"],
                    },
                    "present": {"type": "boolean"},
                    "quality": {
                        "type": "string",
                        "enum": ["complete", "partial", "missing"],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["field", "present", "quality", "notes"],
            },
            "description": "Quality assessment for each field",
        },
        "blocking_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of issues that block publication",
        },
        "recommended_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "Recommended readiness state",
        },
        "explanation": {
            "type": "string",
            "description": "Overall explanation of readiness assessment",
        },
    },
    "required": [
        "readiness_state",
        "missing_fields",
        "field_quality_scores",
        "blocking_issues",
        "recommended_state",
        "explanation",
    ],
    "additionalProperties": False,
}
