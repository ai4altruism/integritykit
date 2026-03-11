"""
Prompt registry for multi-language LLM prompts.

This module provides a centralized registry for loading prompts in different languages
with caching for performance optimization.

Supported Languages:
- English (en) - Default
- Spanish (es)
- French (fr)

Usage:
    from integritykit.llm.prompts.registry import get_prompts

    # Get prompts for a specific language
    prompts = get_prompts("es")  # Spanish
    system_prompt = prompts.clustering.CLUSTERING_SYSTEM_PROMPT

    # Falls back to English if language not supported
    prompts = get_prompts("de")  # Falls back to English with warning
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

logger = logging.getLogger(__name__)

# Supported language codes
SupportedLanguage = Literal["en", "es", "fr"]

# Language names for display
LANGUAGE_NAMES = {
    "en": "English",
    "es": "Español",
    "fr": "Français",
}

# Language detection to supported language mapping
LANGUAGE_CODE_MAPPING = {
    "en": "en",
    "es": "es",
    "fr": "fr",
    "eng": "en",
    "spa": "es",
    "fra": "fr",
    "english": "en",
    "spanish": "es",
    "french": "fr",
}


@dataclass
class ClusteringPrompts:
    """Clustering prompt templates for a specific language."""

    CLUSTERING_SYSTEM_PROMPT: str
    CLUSTERING_USER_PROMPT_TEMPLATE: str
    CLUSTERING_OUTPUT_SCHEMA: dict[str, Any]
    format_clustering_prompt: Any
    ClusterSummary: type
    ClusteringOutput: type


@dataclass
class COPDraftGenerationPrompts:
    """COP draft generation prompt templates for a specific language."""

    COP_DRAFT_GENERATION_SYSTEM_PROMPT: str
    COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE: str
    COP_DRAFT_GENERATION_OUTPUT_SCHEMA: dict[str, Any]
    format_cop_draft_generation_prompt: Any
    COPCandidateFull: type
    COPDraftOutput: type
    EvidenceItem: type


@dataclass
class ReadinessEvaluationPrompts:
    """Readiness evaluation prompt templates for a specific language."""

    READINESS_EVALUATION_SYSTEM_PROMPT: str
    READINESS_EVALUATION_USER_PROMPT_TEMPLATE: str
    READINESS_EVALUATION_OUTPUT_SCHEMA: dict[str, Any]
    format_readiness_evaluation_prompt: Any
    COPCandidateData: type
    FieldQuality: type
    ReadinessOutput: type


@dataclass
class WordingGuidance:
    """Wording guidance for a specific language."""

    HEDGED_PHRASES: list[str]
    DIRECT_PHRASES: list[str]
    CORRECTION_PHRASES: list[str]
    VERIFICATION_VERBS: dict[str, dict[str, str]]
    EXAMPLE_LINE_ITEMS: dict[str, str]
    FACILITATOR_GUIDANCE: str
    get_wording_guidance: Any
    format_timestamp: Any
    get_date_format: Any


@dataclass
class LanguagePrompts:
    """All prompts for a specific language."""

    language_code: SupportedLanguage
    language_name: str
    clustering: ClusteringPrompts
    cop_draft_generation: COPDraftGenerationPrompts
    readiness_evaluation: ReadinessEvaluationPrompts
    wording_guidance: WordingGuidance


def _load_english_prompts() -> LanguagePrompts:
    """Load English prompts (default language)."""
    from . import clustering, cop_draft_generation, readiness_evaluation

    # Create a minimal wording guidance for English
    # (Note: English doesn't have a separate wording_guidance module yet)
    english_wording = WordingGuidance(
        HEDGED_PHRASES=[
            "Unconfirmed:",
            "Reports indicate",
            "Seeking confirmation of",
            "According to preliminary reports",
            "Requires verification",
        ],
        DIRECT_PHRASES=[
            "Confirmed",
            "Verified",
            "Officially",
            "According to official sources",
        ],
        CORRECTION_PHRASES=[
            "CORRECTION:",
            "DISPROVEN:",
            "Earlier reports of... are incorrect",
        ],
        VERIFICATION_VERBS={
            "verified": {
                "to_be": "is",
                "to_have": "has",
                "to_confirm": "confirmed",
                "to_report": "reports",
            },
            "in_review": {
                "to_be": "may be",
                "to_have": "may have",
                "to_confirm": "seeking confirmation",
                "to_report": "is reported",
            },
            "disproven": {
                "to_be": "is not",
                "to_have": "has not",
                "to_confirm": "is disproven",
                "to_report": "is corrected",
            },
        },
        EXAMPLE_LINE_ITEMS={
            "verified": "[VERIFIED] Main Street Bridge is closed to all traffic as of 14:00 PST due to structural damage.",
            "in_review": "[IN REVIEW] Unconfirmed: Reports indicate Main Street Bridge may be closed. Seeking official confirmation from county DOT.",
            "disproven": "[DISPROVEN] CORRECTION: Earlier reports of Main Street Bridge closure are incorrect. Bridge remains open per county DOT as of 15:00 PST.",
        },
        FACILITATOR_GUIDANCE="Use direct language for verified items, hedged language for in-review items.",
        get_wording_guidance=lambda vs, rt: {"style": "direct_factual" if vs == "verified" else "hedged_uncertain"},
        format_timestamp=lambda ts, tz="PST": f"{ts} {tz}",
        get_date_format=lambda: "%Y-%m-%d %H:%M",
    )

    return LanguagePrompts(
        language_code="en",
        language_name="English",
        clustering=ClusteringPrompts(
            CLUSTERING_SYSTEM_PROMPT=clustering.CLUSTERING_SYSTEM_PROMPT,
            CLUSTERING_USER_PROMPT_TEMPLATE=clustering.CLUSTERING_USER_PROMPT_TEMPLATE,
            CLUSTERING_OUTPUT_SCHEMA=clustering.CLUSTERING_OUTPUT_SCHEMA,
            format_clustering_prompt=clustering.format_clustering_prompt,
            ClusterSummary=clustering.ClusterSummary,
            ClusteringOutput=clustering.ClusteringOutput,
        ),
        cop_draft_generation=COPDraftGenerationPrompts(
            COP_DRAFT_GENERATION_SYSTEM_PROMPT=cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT,
            COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE=cop_draft_generation.COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE,
            COP_DRAFT_GENERATION_OUTPUT_SCHEMA=cop_draft_generation.COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
            format_cop_draft_generation_prompt=cop_draft_generation.format_cop_draft_generation_prompt,
            COPCandidateFull=cop_draft_generation.COPCandidateFull,
            COPDraftOutput=cop_draft_generation.COPDraftOutput,
            EvidenceItem=cop_draft_generation.EvidenceItem,
        ),
        readiness_evaluation=ReadinessEvaluationPrompts(
            READINESS_EVALUATION_SYSTEM_PROMPT=readiness_evaluation.READINESS_EVALUATION_SYSTEM_PROMPT,
            READINESS_EVALUATION_USER_PROMPT_TEMPLATE=readiness_evaluation.READINESS_EVALUATION_USER_PROMPT_TEMPLATE,
            READINESS_EVALUATION_OUTPUT_SCHEMA=readiness_evaluation.READINESS_EVALUATION_OUTPUT_SCHEMA,
            format_readiness_evaluation_prompt=readiness_evaluation.format_readiness_evaluation_prompt,
            COPCandidateData=readiness_evaluation.COPCandidateData,
            FieldQuality=readiness_evaluation.FieldQuality,
            ReadinessOutput=readiness_evaluation.ReadinessOutput,
        ),
        wording_guidance=english_wording,
    )


def _load_spanish_prompts() -> LanguagePrompts:
    """Load Spanish prompts."""
    from .spanish import (
        clustering_es,
        cop_draft_generation_es,
        readiness_evaluation_es,
        wording_guidance_es,
    )

    return LanguagePrompts(
        language_code="es",
        language_name="Español",
        clustering=ClusteringPrompts(
            CLUSTERING_SYSTEM_PROMPT=clustering_es.CLUSTERING_SYSTEM_PROMPT,
            CLUSTERING_USER_PROMPT_TEMPLATE=clustering_es.CLUSTERING_USER_PROMPT_TEMPLATE,
            CLUSTERING_OUTPUT_SCHEMA=clustering_es.CLUSTERING_OUTPUT_SCHEMA,
            format_clustering_prompt=clustering_es.format_clustering_prompt,
            ClusterSummary=clustering_es.ClusterSummary,
            ClusteringOutput=clustering_es.ClusteringOutput,
        ),
        cop_draft_generation=COPDraftGenerationPrompts(
            COP_DRAFT_GENERATION_SYSTEM_PROMPT=cop_draft_generation_es.COP_DRAFT_GENERATION_SYSTEM_PROMPT,
            COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE=cop_draft_generation_es.COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE,
            COP_DRAFT_GENERATION_OUTPUT_SCHEMA=cop_draft_generation_es.COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
            format_cop_draft_generation_prompt=cop_draft_generation_es.format_cop_draft_generation_prompt,
            COPCandidateFull=cop_draft_generation_es.COPCandidateFull,
            COPDraftOutput=cop_draft_generation_es.COPDraftOutput,
            EvidenceItem=cop_draft_generation_es.EvidenceItem,
        ),
        readiness_evaluation=ReadinessEvaluationPrompts(
            READINESS_EVALUATION_SYSTEM_PROMPT=readiness_evaluation_es.READINESS_EVALUATION_SYSTEM_PROMPT,
            READINESS_EVALUATION_USER_PROMPT_TEMPLATE=readiness_evaluation_es.READINESS_EVALUATION_USER_PROMPT_TEMPLATE,
            READINESS_EVALUATION_OUTPUT_SCHEMA=readiness_evaluation_es.READINESS_EVALUATION_OUTPUT_SCHEMA,
            format_readiness_evaluation_prompt=readiness_evaluation_es.format_readiness_evaluation_prompt,
            COPCandidateData=readiness_evaluation_es.COPCandidateData,
            FieldQuality=readiness_evaluation_es.FieldQuality,
            ReadinessOutput=readiness_evaluation_es.ReadinessOutput,
        ),
        wording_guidance=WordingGuidance(
            HEDGED_PHRASES=wording_guidance_es.HEDGED_PHRASES_SPANISH,
            DIRECT_PHRASES=wording_guidance_es.DIRECT_PHRASES_SPANISH,
            CORRECTION_PHRASES=wording_guidance_es.CORRECTION_PHRASES_SPANISH,
            VERIFICATION_VERBS=wording_guidance_es.VERIFICATION_VERBS,
            EXAMPLE_LINE_ITEMS=wording_guidance_es.EXAMPLE_LINE_ITEMS_SPANISH,
            FACILITATOR_GUIDANCE=wording_guidance_es.FACILITATOR_GUIDANCE_SPANISH,
            get_wording_guidance=wording_guidance_es.get_wording_guidance,
            format_timestamp=wording_guidance_es.format_timestamp_spanish,
            get_date_format=wording_guidance_es.get_date_format_spanish,
        ),
    )


def _load_french_prompts() -> LanguagePrompts:
    """Load French prompts."""
    from .french import (
        clustering_fr,
        cop_draft_generation_fr,
        readiness_evaluation_fr,
        wording_guidance_fr,
    )

    return LanguagePrompts(
        language_code="fr",
        language_name="Français",
        clustering=ClusteringPrompts(
            CLUSTERING_SYSTEM_PROMPT=clustering_fr.CLUSTERING_SYSTEM_PROMPT,
            CLUSTERING_USER_PROMPT_TEMPLATE=clustering_fr.CLUSTERING_USER_PROMPT_TEMPLATE,
            CLUSTERING_OUTPUT_SCHEMA=clustering_fr.CLUSTERING_OUTPUT_SCHEMA,
            format_clustering_prompt=clustering_fr.format_clustering_prompt,
            ClusterSummary=clustering_fr.ClusterSummary,
            ClusteringOutput=clustering_fr.ClusteringOutput,
        ),
        cop_draft_generation=COPDraftGenerationPrompts(
            COP_DRAFT_GENERATION_SYSTEM_PROMPT=cop_draft_generation_fr.COP_DRAFT_GENERATION_SYSTEM_PROMPT,
            COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE=cop_draft_generation_fr.COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE,
            COP_DRAFT_GENERATION_OUTPUT_SCHEMA=cop_draft_generation_fr.COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
            format_cop_draft_generation_prompt=cop_draft_generation_fr.format_cop_draft_generation_prompt,
            COPCandidateFull=cop_draft_generation_fr.COPCandidateFull,
            COPDraftOutput=cop_draft_generation_fr.COPDraftOutput,
            EvidenceItem=cop_draft_generation_fr.EvidenceItem,
        ),
        readiness_evaluation=ReadinessEvaluationPrompts(
            READINESS_EVALUATION_SYSTEM_PROMPT=readiness_evaluation_fr.READINESS_EVALUATION_SYSTEM_PROMPT,
            READINESS_EVALUATION_USER_PROMPT_TEMPLATE=readiness_evaluation_fr.READINESS_EVALUATION_USER_PROMPT_TEMPLATE,
            READINESS_EVALUATION_OUTPUT_SCHEMA=readiness_evaluation_fr.READINESS_EVALUATION_OUTPUT_SCHEMA,
            format_readiness_evaluation_prompt=readiness_evaluation_fr.format_readiness_evaluation_prompt,
            COPCandidateData=readiness_evaluation_fr.COPCandidateData,
            FieldQuality=readiness_evaluation_fr.FieldQuality,
            ReadinessOutput=readiness_evaluation_fr.ReadinessOutput,
        ),
        wording_guidance=WordingGuidance(
            HEDGED_PHRASES=wording_guidance_fr.HEDGED_PHRASES_FRENCH,
            DIRECT_PHRASES=wording_guidance_fr.DIRECT_PHRASES_FRENCH,
            CORRECTION_PHRASES=wording_guidance_fr.CORRECTION_PHRASES_FRENCH,
            VERIFICATION_VERBS=wording_guidance_fr.VERIFICATION_VERBS,
            EXAMPLE_LINE_ITEMS=wording_guidance_fr.EXAMPLE_LINE_ITEMS_FRENCH,
            FACILITATOR_GUIDANCE=wording_guidance_fr.FACILITATOR_GUIDANCE_FRENCH,
            get_wording_guidance=wording_guidance_fr.get_wording_guidance,
            format_timestamp=wording_guidance_fr.format_timestamp_french,
            get_date_format=wording_guidance_fr.get_date_format_french,
        ),
    )


@lru_cache(maxsize=10)
def get_prompts(language_code: str) -> LanguagePrompts:
    """
    Get prompts for a specific language with caching.

    This function is cached to avoid repeated module imports for the same language.
    The cache is thread-safe and limited to 10 entries (more than enough for 3 languages).

    Args:
        language_code: ISO language code (en, es, fr) or extended code

    Returns:
        LanguagePrompts object containing all prompts for the specified language

    Raises:
        None - Falls back to English with warning if language not supported

    Examples:
        >>> prompts = get_prompts("es")
        >>> system_prompt = prompts.clustering.CLUSTERING_SYSTEM_PROMPT
        >>> prompts = get_prompts("spanish")  # Also works
        >>> prompts = get_prompts("de")  # Falls back to English
    """
    # Normalize language code
    normalized_code = language_code.lower().strip()

    # Map extended codes to supported codes
    normalized_code = LANGUAGE_CODE_MAPPING.get(normalized_code, normalized_code)

    # Load prompts based on language
    if normalized_code == "en":
        logger.debug("Loading English prompts")
        return _load_english_prompts()
    elif normalized_code == "es":
        logger.debug("Loading Spanish prompts")
        return _load_spanish_prompts()
    elif normalized_code == "fr":
        logger.debug("Loading French prompts")
        return _load_french_prompts()
    else:
        logger.warning(
            f"Language '{language_code}' not supported. Falling back to English. "
            f"Supported languages: {', '.join(LANGUAGE_NAMES.values())}"
        )
        return _load_english_prompts()


def get_supported_languages() -> list[dict[str, str]]:
    """
    Get list of supported languages.

    Returns:
        List of dictionaries with language code and name

    Example:
        >>> languages = get_supported_languages()
        >>> [{'code': 'en', 'name': 'English'}, {'code': 'es', 'name': 'Español'}, ...]
    """
    return [{"code": code, "name": name} for code, name in LANGUAGE_NAMES.items()]


def is_language_supported(language_code: str) -> bool:
    """
    Check if a language is supported.

    Args:
        language_code: Language code to check

    Returns:
        True if language is supported, False otherwise

    Example:
        >>> is_language_supported("es")
        True
        >>> is_language_supported("de")
        False
    """
    normalized_code = language_code.lower().strip()
    normalized_code = LANGUAGE_CODE_MAPPING.get(normalized_code, normalized_code)
    return normalized_code in LANGUAGE_NAMES


def clear_prompt_cache() -> None:
    """
    Clear the prompt cache.

    Useful for testing or if prompts need to be reloaded after updates.
    """
    get_prompts.cache_clear()
    logger.info("Prompt cache cleared")
