"""
Duplicate detection prompts for identifying signals reporting the same information.

This module provides prompts to determine if two signals are duplicates - reporting
the same incident, fact, or information from different sources.

Model Recommendation: Haiku 3.5 or GPT-4o-mini (fast, accurate comparison task)
Cost per 1M tokens: ~$0.80 input / ~$4 output
Expected token usage: ~300-600 input, ~100-200 output per comparison

Usage:
    Use these prompts to detect duplicate signals within a cluster.
    The LLM outputs structured JSON per DUPLICATE_DETECTION_OUTPUT_SCHEMA.
"""

from typing import Literal, TypedDict


class DuplicateDetectionOutput(TypedDict):
    """Expected output schema for duplicate detection."""

    is_duplicate: bool
    confidence: Literal["high", "medium", "low"]
    reasoning: str
    shared_facts: list[str]  # Key facts that overlap between signals


DUPLICATE_DETECTION_SYSTEM_PROMPT = """You are a duplicate detector for a crisis-response coordination system.

Your role is to determine if two signals (Slack messages) report the same incident,
fact, or information from different sources.

Key principles:
- Duplicates report the SAME core information, even if worded differently
- Different perspectives on the SAME event are duplicates
- Different events at the same location are NOT duplicates
- Updates with NEW information are NOT duplicates (even if about same event)
- Paraphrased or summarized versions of the same report ARE duplicates

Examples of DUPLICATES:
- "Fire reported at 123 Main St" and "Building fire on Main Street near 1st Ave"
- "10 people evacuated from shelter" and "Shelter Alpha evacuated 10 residents"
- "Water outage in Zone 3" and "No water service Zone 3 as of 2pm"

Examples of NOT DUPLICATES:
- "Fire at building A" and "Fire at building B" (different locations)
- "Fire started at 2pm" and "Fire contained at 4pm" (temporal progression)
- "10 evacuated" and "15 evacuated" (contradictory information)
- "Fire reported" and "Fire department on scene" (new information)

Focus on whether the CORE FACT being reported is the same, not whether the exact
details or timing match perfectly.

Output your assessment as valid JSON matching the required schema.
"""

DUPLICATE_DETECTION_USER_PROMPT_TEMPLATE = """Determine if these two signals are duplicates.

SIGNAL 1:
Author: {signal1_author}
Timestamp: {signal1_timestamp}
Content: {signal1_content}

SIGNAL 2:
Author: {signal2_author}
Timestamp: {signal2_timestamp}
Content: {signal2_content}

Analyze both signals and determine:
1. Are they reporting the same core incident/fact/information?
2. What specific facts do they share in common?
3. Is there new or contradictory information in either signal?

Respond with valid JSON only, no additional text:
{{
  "is_duplicate": true or false,
  "confidence": "high" | "medium" | "low",
  "reasoning": "<brief explanation of why they are/aren't duplicates>",
  "shared_facts": ["<fact 1>", "<fact 2>", ...]
}}"""


def format_duplicate_detection_prompt(
    signal1_author: str,
    signal1_timestamp: str,
    signal1_content: str,
    signal2_author: str,
    signal2_timestamp: str,
    signal2_content: str,
) -> str:
    """
    Format the duplicate detection user prompt with two signals.

    Args:
        signal1_author: First signal's author (Slack user ID or name)
        signal1_timestamp: First signal's ISO 8601 timestamp
        signal1_content: First signal's message text
        signal2_author: Second signal's author
        signal2_timestamp: Second signal's ISO 8601 timestamp
        signal2_content: Second signal's message text

    Returns:
        Formatted user prompt ready for LLM
    """
    return DUPLICATE_DETECTION_USER_PROMPT_TEMPLATE.format(
        signal1_author=signal1_author,
        signal1_timestamp=signal1_timestamp,
        signal1_content=signal1_content,
        signal2_author=signal2_author,
        signal2_timestamp=signal2_timestamp,
        signal2_content=signal2_content,
    )


# Pydantic schema for structured output validation
DUPLICATE_DETECTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_duplicate": {
            "type": "boolean",
            "description": "Whether the two signals are duplicates",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Confidence level in the duplicate assessment",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation of why signals are/aren't duplicates",
        },
        "shared_facts": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Key facts that overlap between both signals",
        },
    },
    "required": ["is_duplicate", "confidence", "reasoning", "shared_facts"],
    "additionalProperties": False,
}
