"""
Prompt templates for LLM operations in the Integrity Kit.

This package contains all system and user prompt templates, plus output schemas
for structured LLM responses.

Multi-Language Support:
    The prompt registry supports English, Spanish, and French prompts with
    culturally appropriate wording guidance and hedging phrases.

    Usage:
        from integritykit.llm.prompts.registry import get_prompts

        prompts = get_prompts("es")  # Spanish
        system_prompt = prompts.clustering.CLUSTERING_SYSTEM_PROMPT

Modules:
    clustering: Signal-to-cluster assignment prompts
    conflict_detection: Contradiction and conflict identification prompts
    readiness_evaluation: COP candidate completeness assessment prompts
    cop_draft_generation: COP line item drafting with verification-aware wording
    next_action: Best-action recommendation prompts for facilitators
    registry: Multi-language prompt registry with caching
    spanish: Spanish language prompts
    french: French language prompts
"""

from . import (
    clustering,
    conflict_detection,
    cop_draft_generation,
    next_action,
    readiness_evaluation,
    registry,
)

__all__ = [
    "clustering",
    "conflict_detection",
    "readiness_evaluation",
    "cop_draft_generation",
    "next_action",
    "registry",
]
