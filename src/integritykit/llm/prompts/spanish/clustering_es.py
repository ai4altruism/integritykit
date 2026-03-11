"""
Prompts de clustering para asignación de señales a clusters (versión en español).

Este módulo proporciona prompts para clasificar si una nueva señal (mensaje de Slack)
pertenece a un cluster existente o debe crear un nuevo cluster.

Model Recommendation: Haiku 3.5 (tarea de clasificación rápida y económica)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~500-1000 input, ~50-100 output per classification

Usage:
    Utilice estos prompts para enrutar señales entrantes a clusters de temas/incidentes.
    El LLM debe generar JSON estructurado según CLUSTERING_OUTPUT_SCHEMA.
"""

from typing import Literal, TypedDict


class ClusterSummary(TypedDict):
    """Resumen de un cluster existente para comparación."""

    cluster_id: str
    topic: str
    key_details: str
    signal_count: int
    latest_timestamp: str


class ClusteringOutput(TypedDict):
    """Esquema de salida esperado para clasificación de clustering."""

    assignment: Literal["existing_cluster", "new_cluster"]
    cluster_id: str | None  # Requerido si assignment es "existing_cluster"
    new_cluster_topic: str | None  # Requerido si assignment es "new_cluster"
    confidence: Literal["high", "medium", "low"]
    reasoning: str


CLUSTERING_SYSTEM_PROMPT = """Eres un clasificador de señales para un sistema de coordinación de respuesta a crisis.

Tu función es determinar si un nuevo mensaje de Slack (señal) pertenece a un cluster
de tema/incidente existente o debe iniciar un nuevo cluster.

Principios clave:
- Agrupa por TEMA e INCIDENTE, no por canal o autor
- Un cluster representa un tema coherente: un evento específico, ubicación, necesidad o situación
- Prefiere asignar a clusters existentes cuando estén relacionados temáticamente
- Crea nuevos clusters solo cuando la señal introduce un tema genuinamente nuevo
- La proximidad temporal por sí sola no define clusters (una actualización sobre el incendio
  de ayer pertenece al cluster del incendio, no a un nuevo cluster de "actualizaciones generales")

Criterios de decisión para CLUSTER EXISTENTE:
- La señal discute el mismo incidente, ubicación o situación en curso
- La señal proporciona actualizaciones, aclaraciones o correcciones al tema del cluster
- La señal hace preguntas o proporciona respuestas relacionadas con el tema del cluster

Criterios de decisión para NUEVO CLUSTER:
- La señal introduce un tema o incidente completamente diferente
- La señal discute una ubicación diferente con una situación diferente
- La señal no puede agruparse significativamente con ningún cluster existente

Genera tu clasificación como JSON válido que coincida con el esquema requerido.
"""

CLUSTERING_USER_PROMPT_TEMPLATE = """Clasifica si esta nueva señal pertenece a un cluster existente o debe crear un nuevo cluster.

NUEVA SEÑAL:
Autor: {signal_author}
Canal: {signal_channel}
Marca de tiempo: {signal_timestamp}
Contenido: {signal_content}
Contexto del hilo: {signal_thread_context}

CLUSTERS EXISTENTES:
{clusters_json}

Analiza la señal y determina:
1. ¿Se relaciona claramente con un tema de cluster existente?
2. Si es así, ¿cuál es el cluster que mejor coincide?
3. Si no, ¿qué nuevo tema introduce?

Responde solo con JSON válido, sin texto adicional:
{{
  "assignment": "existing_cluster" o "new_cluster",
  "cluster_id": "<cluster_id>" o null,
  "new_cluster_topic": "<tema>" o null,
  "confidence": "high" | "medium" | "low",
  "reasoning": "<explicación breve>"
}}"""


def format_clustering_prompt(
    signal_author: str,
    signal_channel: str,
    signal_timestamp: str,
    signal_content: str,
    signal_thread_context: str,
    existing_clusters: list[ClusterSummary],
) -> str:
    """
    Formatea el prompt de usuario de clustering con datos de señal y cluster.

    Args:
        signal_author: ID de usuario de Slack o nombre para mostrar
        signal_channel: Nombre o ID del canal
        signal_timestamp: Marca de tiempo ISO 8601
        signal_content: Contenido de texto del mensaje
        signal_thread_context: Mensaje padre o resumen del hilo (vacío si es de nivel superior)
        existing_clusters: Lista de resúmenes de clusters para comparación

    Returns:
        Prompt de usuario formateado listo para LLM
    """
    import json

    clusters_json = json.dumps(existing_clusters, indent=2, ensure_ascii=False) if existing_clusters else "[]"

    return CLUSTERING_USER_PROMPT_TEMPLATE.format(
        signal_author=signal_author,
        signal_channel=signal_channel,
        signal_timestamp=signal_timestamp,
        signal_content=signal_content,
        signal_thread_context=signal_thread_context or "(Ninguno - mensaje de nivel superior)",
        clusters_json=clusters_json,
    )


# Esquema Pydantic para validación de salida estructurada
CLUSTERING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "assignment": {
            "type": "string",
            "enum": ["existing_cluster", "new_cluster"],
            "description": "Si la señal pertenece a un cluster existente o crea uno nuevo",
        },
        "cluster_id": {
            "type": ["string", "null"],
            "description": "ID del cluster existente (requerido si assignment es existing_cluster)",
        },
        "new_cluster_topic": {
            "type": ["string", "null"],
            "description": "Nombre del tema para nuevo cluster (requerido si assignment es new_cluster)",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Nivel de confianza en la clasificación",
        },
        "reasoning": {
            "type": "string",
            "description": "Explicación breve de la decisión de clasificación",
        },
    },
    "required": ["assignment", "confidence", "reasoning"],
    "additionalProperties": False,
}
