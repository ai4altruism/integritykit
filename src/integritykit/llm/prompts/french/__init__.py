"""
Prompts LLM en français pour le Aid Arena Integrity Kit.

Ce paquet contient tous les prompts système en français pour :
- Clustering de signaux
- Génération de brouillons COP
- Évaluation de préparation
- Directives de rédaction (nuancée vs directe)

Tous les prompts sont culturellement adaptés pour les utilisateurs francophones
et incluent des phrases nuancées appropriées et des conventions de format de date/heure.
"""

from .clustering_fr import (
    CLUSTERING_OUTPUT_SCHEMA,
    CLUSTERING_SYSTEM_PROMPT,
    CLUSTERING_USER_PROMPT_TEMPLATE,
    ClusteringOutput,
    ClusterSummary,
    format_clustering_prompt,
)
from .cop_draft_generation_fr import (
    COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
    COP_DRAFT_GENERATION_SYSTEM_PROMPT,
    COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE,
    COPCandidateFull,
    COPDraftOutput,
    EvidenceItem,
    format_cop_draft_generation_prompt,
)
from .readiness_evaluation_fr import (
    READINESS_EVALUATION_OUTPUT_SCHEMA,
    READINESS_EVALUATION_SYSTEM_PROMPT,
    READINESS_EVALUATION_USER_PROMPT_TEMPLATE,
    COPCandidateData,
    FieldQuality,
    ReadinessOutput,
    format_readiness_evaluation_prompt,
)
from .wording_guidance_fr import (
    CORRECTION_PHRASES_FRENCH,
    DIRECT_PHRASES_FRENCH,
    EXAMPLE_LINE_ITEMS_FRENCH,
    FACILITATOR_GUIDANCE_FRENCH,
    HEDGED_PHRASES_FRENCH,
    VERIFICATION_VERBS,
    format_timestamp_french,
    get_date_format_french,
    get_wording_guidance,
)

__all__ = [
    # Clustering
    "CLUSTERING_SYSTEM_PROMPT",
    "CLUSTERING_USER_PROMPT_TEMPLATE",
    "CLUSTERING_OUTPUT_SCHEMA",
    "ClusterSummary",
    "ClusteringOutput",
    "format_clustering_prompt",
    # COP Draft Generation
    "COP_DRAFT_GENERATION_SYSTEM_PROMPT",
    "COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE",
    "COP_DRAFT_GENERATION_OUTPUT_SCHEMA",
    "COPCandidateFull",
    "COPDraftOutput",
    "EvidenceItem",
    "format_cop_draft_generation_prompt",
    # Readiness Evaluation
    "READINESS_EVALUATION_SYSTEM_PROMPT",
    "READINESS_EVALUATION_USER_PROMPT_TEMPLATE",
    "READINESS_EVALUATION_OUTPUT_SCHEMA",
    "COPCandidateData",
    "FieldQuality",
    "ReadinessOutput",
    "format_readiness_evaluation_prompt",
    # Wording Guidance
    "HEDGED_PHRASES_FRENCH",
    "DIRECT_PHRASES_FRENCH",
    "CORRECTION_PHRASES_FRENCH",
    "VERIFICATION_VERBS",
    "EXAMPLE_LINE_ITEMS_FRENCH",
    "FACILITATOR_GUIDANCE_FRENCH",
    "get_wording_guidance",
    "format_timestamp_french",
    "get_date_format_french",
]
