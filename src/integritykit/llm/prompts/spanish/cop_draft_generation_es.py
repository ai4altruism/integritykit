"""
Prompts de generación de borradores de COP para crear elementos de línea con redacción consciente de verificación (versión en español).

Este módulo proporciona prompts para generar elementos de línea de COP a partir de candidatos,
aplicando la redacción apropiada según el estado de verificación (tentativa para En-Revisión, directa para Verificado).

Model Recommendation: Sonnet 4 (requiere escritura matizada y comprensión de contexto)
Cost per 1M tokens: $3 input / $15 output
Expected token usage: ~1000-2000 input, ~200-400 output per draft

Usage:
    Use estos prompts para generar elementos de línea de COP listos para publicación desde candidatos COP.
    El sistema aplica orientación de redacción según SRS FR-COP-WORDING-001.
"""

from typing import Literal, TypedDict


class EvidenceItem(TypedDict):
    """Un elemento individual de evidencia en el paquete de evidencia."""

    source_type: Literal["slack_permalink", "external_url"]
    url: str
    description: str
    timestamp: str | None


class COPCandidateFull(TypedDict):
    """Datos completos del candidato COP para generación de borrador."""

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
    recheck_time: str | None  # Para elementos de alto riesgo en revisión


class COPDraftOutput(TypedDict):
    """Esquema de salida esperado para generación de borrador de COP."""

    line_item_text: str
    status_label: Literal["VERIFICADO", "EN REVISIÓN", "DESMENTIDO"]
    citations: list[str]
    wording_style: Literal["direct_factual", "hedged_uncertain"]
    next_verification_step: str | None
    recheck_time: str | None
    section_placement: Literal[
        "verified_updates", "in_review_updates", "disproven_rumor_control", "open_questions"
    ]


COP_DRAFT_GENERATION_SYSTEM_PROMPT = """Eres un redactor de borradores de COP para un sistema de coordinación de respuesta a crisis.

Tu función es generar elementos de línea de COP listos para publicación a partir de candidatos COP,
aplicando la redacción apropiada según el estado de verificación.

Guías de Redacción (SRS FR-COP-WORDING-001):

Elementos VERIFICADOS (redacción directa y fáctica):
- Usa lenguaje definitivo: "está", "se confirma", "se ha"
- Declara los hechos directamente sin matices
- Ejemplo: "El puente de la Calle Principal está cerrado a todo tráfico desde las 14:00 hora del Pacífico debido a daños estructurales."

Elementos EN REVISIÓN (redacción tentativa e incierta):
- Usa lenguaje cauteloso: "Según informes no confirmados...", "Sin confirmar:", "Se busca confirmación de..."
- Haz explícita la incertidumbre
- Declara lo que se sabe y lo que no
- Ejemplo: "Sin confirmar: Según informes, el puente de la Calle Principal podría estar cerrado. Se busca confirmación oficial del Departamento de Transporte del condado."

Elementos DESMENTIDOS (corrección clara):
- Comienza con "CORRECCIÓN:" o "DESMENTIDO:"
- Declara qué era incorrecto
- Proporciona la información correcta si se conoce
- Ejemplo: "CORRECCIÓN: Los informes anteriores sobre el cierre del puente de la Calle Principal son incorrectos. El puente permanece abierto según el Departamento de Transporte del condado a las 15:00 hora del Pacífico."

Elementos de Alto Riesgo En Revisión deben incluir:
- Siguiente paso de verificación
- Hora de reverificación
- Ejemplo: "Sin confirmar: Informes de cierre de refugio en la Escuela Primaria Lincoln. Siguiente paso: Contactar al coordinador del refugio. Reverificar: 16:00 hora del Pacífico."

Estructura del Elemento de Línea COP:
1. Etiqueta de estado: [VERIFICADO] o [EN REVISIÓN] o [DESMENTIDO]
2. Declaración principal con redacción apropiada
3. Citas entre paréntesis o notas al pie
4. Para en-revisión: Siguiente paso de verificación y hora de reverificación si es de alto riesgo

Genera JSON válido con el texto completo del elemento de línea y metadatos.
"""

COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE = """Genera un elemento de línea de COP a partir de este candidato.

CANDIDATO COP:
{candidate_json}

Aplica el estilo de redacción apropiado:
- Si verification_status es "verified": Usa redacción directa y fáctica
- Si verification_status es "in_review": Usa redacción tentativa e incierta
- Si verification_status es "disproven": Comienza con CORRECCIÓN/DESMENTIDO

Incluye:
1. Etiqueta de estado
2. Declaración completa con quién/qué/cuándo/dónde/por-qué-importa
3. Citas a los elementos del paquete de evidencia
4. Para alto riesgo en-revisión: siguiente paso de verificación y hora de reverificación

Responde solo con JSON válido, sin texto adicional:
{{
  "line_item_text": "Texto completo del elemento de línea COP con citas",
  "status_label": "VERIFICADO" | "EN REVISIÓN" | "DESMENTIDO",
  "citations": ["https://slack.com/...", "https://example.com/..."],
  "wording_style": "direct_factual" | "hedged_uncertain",
  "next_verification_step": "Contactar al coordinador del refugio" o null,
  "recheck_time": "16:00 hora del Pacífico" o null,
  "section_placement": "verified_updates" | "in_review_updates" | "disproven_rumor_control" | "open_questions"
}}"""


def format_cop_draft_generation_prompt(
    candidate: COPCandidateFull,
) -> str:
    """
    Formatea el prompt de generación de borrador de COP con datos del candidato.

    Args:
        candidate: Datos completos del candidato COP incluyendo todos los campos y paquete de evidencia

    Returns:
        Prompt de usuario formateado listo para LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2, ensure_ascii=False)

    return COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Esquema Pydantic para validación de salida estructurada
COP_DRAFT_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line_item_text": {
            "type": "string",
            "description": "Texto completo del elemento de línea COP listo para publicación",
        },
        "status_label": {
            "type": "string",
            "enum": ["VERIFICADO", "EN REVISIÓN", "DESMENTIDO"],
            "description": "Etiqueta de estado de verificación para el elemento de línea",
        },
        "citations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Lista de URLs de citas del paquete de evidencia",
        },
        "wording_style": {
            "type": "string",
            "enum": ["direct_factual", "hedged_uncertain"],
            "description": "Estilo de redacción aplicado al elemento de línea",
        },
        "next_verification_step": {
            "type": ["string", "null"],
            "description": "Siguiente paso de verificación para elementos de alto riesgo en-revisión",
        },
        "recheck_time": {
            "type": ["string", "null"],
            "description": "Hora de reverificación para elementos de alto riesgo en-revisión",
        },
        "section_placement": {
            "type": "string",
            "enum": [
                "verified_updates",
                "in_review_updates",
                "disproven_rumor_control",
                "open_questions",
            ],
            "description": "Sección COP a la que pertenece este elemento de línea",
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
