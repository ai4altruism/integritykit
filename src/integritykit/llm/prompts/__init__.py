"""
Prompt templates for LLM operations in the Integrity Kit.

This package contains all system and user prompt templates, plus output schemas
for structured LLM responses.

Modules:
    clustering: Signal-to-cluster assignment prompts
    conflict_detection: Contradiction and conflict identification prompts
    readiness_evaluation: COP candidate completeness assessment prompts
    cop_draft_generation: COP line item drafting with verification-aware wording
    next_action: Best-action recommendation prompts for facilitators
"""

from . import (
    clustering,
    conflict_detection,
    cop_draft_generation,
    next_action,
    readiness_evaluation,
)

__all__ = [
    "clustering",
    "conflict_detection",
    "readiness_evaluation",
    "cop_draft_generation",
    "next_action",
]
