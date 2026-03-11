"""
Prompts de LLM en español para el Aid Arena Integrity Kit.

Este paquete contiene todos los prompts del sistema en español para:
- Clustering de señales
- Generación de borradores de COP
- Evaluación de preparación
- Orientación de redacción (tentativa vs directa)

Todos los prompts están culturalmente adaptados para usuarios hispanohablantes
e incluyen frases tentativas apropiadas y convenciones de formato de fecha/hora.
"""

from .clustering_es import (
    CLUSTERING_OUTPUT_SCHEMA,
    CLUSTERING_SYSTEM_PROMPT,
    CLUSTERING_USER_PROMPT_TEMPLATE,
    ClusteringOutput,
    ClusterSummary,
    format_clustering_prompt,
)
from .cop_draft_generation_es import (
    COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
    COP_DRAFT_GENERATION_SYSTEM_PROMPT,
    COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE,
    COPCandidateFull,
    COPDraftOutput,
    EvidenceItem,
    format_cop_draft_generation_prompt,
)
from .readiness_evaluation_es import (
    READINESS_EVALUATION_OUTPUT_SCHEMA,
    READINESS_EVALUATION_SYSTEM_PROMPT,
    READINESS_EVALUATION_USER_PROMPT_TEMPLATE,
    COPCandidateData,
    FieldQuality,
    ReadinessOutput,
    format_readiness_evaluation_prompt,
)
from .wording_guidance_es import (
    CORRECTION_PHRASES_SPANISH,
    DIRECT_PHRASES_SPANISH,
    EXAMPLE_LINE_ITEMS_SPANISH,
    FACILITATOR_GUIDANCE_SPANISH,
    HEDGED_PHRASES_SPANISH,
    VERIFICATION_VERBS,
    format_timestamp_spanish,
    get_date_format_spanish,
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
    "HEDGED_PHRASES_SPANISH",
    "DIRECT_PHRASES_SPANISH",
    "CORRECTION_PHRASES_SPANISH",
    "VERIFICATION_VERBS",
    "EXAMPLE_LINE_ITEMS_SPANISH",
    "FACILITATOR_GUIDANCE_SPANISH",
    "get_wording_guidance",
    "format_timestamp_spanish",
    "get_date_format_spanish",
]
