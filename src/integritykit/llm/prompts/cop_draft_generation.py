"""
COP draft generation prompts for creating line items with verification-aware wording.

This module provides prompts to generate COP line items from candidates, applying
appropriate wording based on verification state (hedged for In-Review, direct for Verified).

Model Recommendation: Sonnet 4 (requires nuanced writing and context understanding)
Cost per 1M tokens: $3 input / $15 output
Expected token usage: ~1000-2000 input, ~200-400 output per draft

Usage:
    Use these prompts to generate publication-ready COP line items from COP candidates.
    The system applies wording guidance per SRS FR-COP-WORDING-001.
"""

from typing import Literal, TypedDict


class EvidenceItem(TypedDict):
    """A single piece of evidence in the evidence pack."""

    source_type: Literal["slack_permalink", "external_url"]
    url: str
    description: str
    timestamp: str | None


class COPCandidateFull(TypedDict):
    """Full COP candidate data for draft generation."""

    candidate_id: str
    what: str
    where: str
    when: str
    who: str | None
    so_what: str
    evidence_pack: list[EvidenceItem]
    verification_status: Literal["verified", "in_review", "disproven"]
    risk_tier: Literal["routine", "elevated", "high_stakes"]
    conflicts_resolved: bool
    recheck_time: str | None  # For high-stakes in-review items


class COPDraftOutput(TypedDict):
    """Expected output schema for COP draft generation."""

    line_item_text: str
    status_label: Literal["VERIFIED", "IN REVIEW", "DISPROVEN"]
    citations: list[str]
    wording_style: Literal["direct_factual", "hedged_uncertain"]
    next_verification_step: str | None
    recheck_time: str | None
    section_placement: Literal[
        "verified_updates", "in_review_updates", "disproven_rumor_control", "open_questions"
    ]


COP_DRAFT_GENERATION_SYSTEM_PROMPT = """You are a COP draft writer for a crisis-response coordination system.

Your role is to generate publication-ready COP line items from COP candidates, applying
appropriate wording based on verification status.

Wording Guidelines (SRS FR-COP-WORDING-001):

VERIFIED items (direct, factual phrasing):
- Use definitive language: "is", "has", "confirmed"
- State facts directly without hedging
- Example: "Main Street Bridge is closed to all traffic as of 14:00 PST due to structural damage."

IN-REVIEW items (hedged, uncertain phrasing):
- Use cautious language: "Reports indicate...", "Unconfirmed:", "Seeking confirmation of..."
- Make uncertainty explicit
- State what is known and what is not
- Example: "Unconfirmed: Reports indicate Main Street Bridge may be closed. Seeking official confirmation from county DOT."

DISPROVEN items (clear correction):
- Lead with "CORRECTION:" or "DISPROVEN:"
- State what was incorrect
- Provide the correct information if known
- Example: "CORRECTION: Earlier reports of Main Street Bridge closure are incorrect. Bridge remains open per county DOT as of 15:00 PST."

High-stakes In-Review items must include:
- Next verification step
- Recheck time
- Example: "Unconfirmed: Reports of shelter closure at Lincoln Elementary. Next step: Contact shelter coordinator. Recheck: 16:00 PST."

COP Line Item Structure:
1. Status label: [VERIFIED] or [IN REVIEW] or [DISPROVEN]
2. Main statement with appropriate wording
3. Citations in parentheses or footnotes
4. For in-review: Next verification step and recheck time if high-stakes

Output valid JSON with the complete line item text and metadata.
"""

COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE = """Generate a COP line item from this candidate.

COP CANDIDATE:
{candidate_json}

Apply the appropriate wording style:
- If verification_status is "verified": Use direct, factual phrasing
- If verification_status is "in_review": Use hedged, uncertain phrasing
- If verification_status is "disproven": Lead with CORRECTION/DISPROVEN

Include:
1. Status label
2. Complete statement with who/what/when/where/so-what
3. Citations to evidence pack items
4. For high-stakes in-review: next verification step and recheck time

Respond with valid JSON only, no additional text:
{{
  "line_item_text": "Full COP line item text with citations",
  "status_label": "VERIFIED" | "IN REVIEW" | "DISPROVEN",
  "citations": ["https://slack.com/...", "https://example.com/..."],
  "wording_style": "direct_factual" | "hedged_uncertain",
  "next_verification_step": "Contact shelter coordinator" or null,
  "recheck_time": "16:00 PST" or null,
  "section_placement": "verified_updates" | "in_review_updates" | "disproven_rumor_control" | "open_questions"
}}"""


def format_cop_draft_generation_prompt(
    candidate: COPCandidateFull,
) -> str:
    """
    Format the COP draft generation prompt with candidate data.

    Args:
        candidate: Full COP candidate data including all fields and evidence pack

    Returns:
        Formatted user prompt ready for LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2)

    return COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Pydantic schema for structured output validation
COP_DRAFT_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line_item_text": {
            "type": "string",
            "description": "Complete COP line item text ready for publication",
        },
        "status_label": {
            "type": "string",
            "enum": ["VERIFIED", "IN REVIEW", "DISPROVEN"],
            "description": "Verification status label for the line item",
        },
        "citations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "List of citation URLs from evidence pack",
        },
        "wording_style": {
            "type": "string",
            "enum": ["direct_factual", "hedged_uncertain"],
            "description": "Wording style applied to the line item",
        },
        "next_verification_step": {
            "type": ["string", "null"],
            "description": "Next verification step for in-review high-stakes items",
        },
        "recheck_time": {
            "type": ["string", "null"],
            "description": "Recheck time for in-review high-stakes items",
        },
        "section_placement": {
            "type": "string",
            "enum": [
                "verified_updates",
                "in_review_updates",
                "disproven_rumor_control",
                "open_questions",
            ],
            "description": "Which COP section this line item belongs in",
        },
    },
    "required": [
        "line_item_text",
        "status_label",
        "citations",
        "wording_style",
        "section_placement",
    ],
    "additionalProperties": False,
}
