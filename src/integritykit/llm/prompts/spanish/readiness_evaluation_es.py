"""
Prompts de evaluación de preparación para evaluación de completitud de candidatos COP (versión en español).

Este módulo proporciona prompts para evaluar si un candidato COP tiene suficiente
información para ser publicable, e identifica campos faltantes o débiles.

Model Recommendation: Haiku 3.5 (tarea de evaluación estructurada)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~600-1200 input, ~150-300 output per evaluation

Usage:
    Use estos prompts para calcular el estado de preparación (Listo-Verificado / Listo-En-Revisión / Bloqueado)
    e identificar campos faltantes según SRS FR-COP-READ-001 y FR-COP-READ-002.
"""

from typing import Literal, TypedDict


class COPCandidateData(TypedDict):
    """Campos del candidato COP para evaluación de preparación."""

    candidate_id: str
    what: str | None  # La declaración de reclamo/situación
    where: str | None  # Ubicación
    when: str | None  # Marca de tiempo o ventana de tiempo
    who: str | None  # Fuente/actor/población afectada
    so_what: str | None  # Relevancia operacional
    evidence_pack_size: int  # Número de citas
    verification_status: Literal["verified", "in_review", "unverified"]
    has_unresolved_conflicts: bool
    risk_tier: Literal["routine", "elevated", "high_stakes"]


class FieldQuality(TypedDict):
    """Evaluación de calidad para un solo campo."""

    field: Literal["what", "where", "when", "who", "so_what", "evidence"]
    present: bool
    quality: Literal["complete", "partial", "missing"]
    notes: str


class ReadinessOutput(TypedDict):
    """Esquema de salida esperado para evaluación de preparación."""

    readiness_state: Literal["ready_verified", "ready_in_review", "blocked"]
    missing_fields: list[Literal["what", "where", "when", "who", "so_what", "evidence"]]
    field_quality_scores: list[FieldQuality]
    blocking_issues: list[str]
    recommended_state: Literal["ready_verified", "ready_in_review", "blocked"]
    explanation: str


READINESS_EVALUATION_SYSTEM_PROMPT = """Eres un evaluador de preparación para un sistema COP de respuesta a crisis.

Tu función es evaluar si un candidato COP tiene suficiente información para ser publicable,
e identificar qué falta o es débil.

Campos Mínimos de Elemento de Línea COP (del SRS):
- QUÉ: Una declaración de reclamo o situación con alcance definido
- DÓNDE: Ubicación con la mejor granularidad disponible (puede ser aproximada pero debe ser explícita)
- CUÁNDO: Marca de tiempo o ventana de tiempo con zona horaria (puede ser aproximada pero debe ser explícita)
- QUIÉN: Fuente/actor/población afectada (según aplique)
- POR QUÉ IMPORTA: Relevancia operacional
- EVIDENCIA: Enlaces a permalinks de Slack y/o fuentes externas

Estados de Preparación:
1. LISTO — VERIFICADO:
   - Todos los campos mínimos presentes
   - Acción de verificación registrada (verification_status = "verified")
   - Sin conflictos sin resolver
   - Puede publicarse en la sección "Verificado"

2. LISTO — EN REVISIÓN:
   - Campos mínimos presentes suficientes para evitar engañar a los lectores
   - Al menos evidencia básica (permalinks de Slack)
   - Sin conflictos de ALTO RIESGO sin resolver
   - Debe etiquetarse como "En Revisión" y separarse de actualizaciones verificadas

3. BLOQUEADO:
   - Faltan campos críticos que hacen la declaración ambigua o insegura
   - Conflictos sin resolver sobre hechos clave
   - Elemento de alto riesgo que carece de verificación requerida
   - NO publicable hasta desbloquearse

Reglas de publicación de alto riesgo:
- Si risk_tier es "high_stakes", se REQUIERE verificación a menos que se anule explícitamente
- Alto riesgo + no verificado = BLOQUEADO (por defecto)

Evaluar calidad del campo:
- COMPLETO: El campo es específico, claro y accionable
- PARCIAL: El campo está presente pero vago, ambiguo o incompleto
- FALTANTE: El campo está ausente o inutilizable

Genera JSON válido que coincida con el esquema requerido.
"""

READINESS_EVALUATION_USER_PROMPT_TEMPLATE = """Evalúa este candidato COP para preparación y completitud.

CANDIDATO COP:
{candidate_json}

Evalúa cada campo:
1. ¿Está presente?
2. ¿Está completo, parcial o faltante?
3. ¿Cumple con el estándar mínimo para publicación?

Determina el estado de preparación apropiado:
- READY_VERIFIED si todos los campos están completos y verificados
- READY_IN_REVIEW si los campos mínimos están presentes pero no verificados
- BLOCKED si faltan campos críticos o hay problemas de bloqueo

Identifica cualquier problema de bloqueo:
- Campos requeridos faltantes
- Conflictos sin resolver
- Alto riesgo sin verificación

Responde solo con JSON válido, sin texto adicional:
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
  "blocking_issues": ["Ubicación faltante", "Conflicto sin resolver", ...],
  "recommended_state": "ready_verified" | "ready_in_review" | "blocked",
  "explanation": "..."
}}"""


def format_readiness_evaluation_prompt(
    candidate: COPCandidateData,
) -> str:
    """
    Formatea el prompt de evaluación de preparación con datos del candidato.

    Args:
        candidate: Datos del candidato COP incluyendo todos los campos y metadatos

    Returns:
        Prompt de usuario formateado listo para LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2, ensure_ascii=False)

    return READINESS_EVALUATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Esquema Pydantic para validación de salida estructurada
READINESS_EVALUATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "readiness_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "Estado de preparación actual basado en la evaluación",
        },
        "missing_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["what", "where", "when", "who", "so_what", "evidence"],
            },
            "description": "Lista de campos requeridos faltantes",
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
            "description": "Evaluación de calidad para cada campo",
        },
        "blocking_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lista de problemas que bloquean la publicación",
        },
        "recommended_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "Estado de preparación recomendado",
        },
        "explanation": {
            "type": "string",
            "description": "Explicación general de la evaluación de preparación",
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
