"""
Prompts de clustering pour l'affectation de signaux aux clusters (version française).

Ce module fournit des prompts pour classifier si un nouveau signal (message Slack)
appartient à un cluster existant ou doit créer un nouveau cluster.

Model Recommendation: Haiku 3.5 (tâche de classification rapide et économique)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~500-1000 input, ~50-100 output per classification

Usage:
    Utilisez ces prompts pour router les signaux entrants vers des clusters de sujets/incidents.
    Le LLM doit générer du JSON structuré selon CLUSTERING_OUTPUT_SCHEMA.
"""

from typing import Literal, TypedDict


class ClusterSummary(TypedDict):
    """Résumé d'un cluster existant pour comparaison."""

    cluster_id: str
    topic: str
    key_details: str
    signal_count: int
    latest_timestamp: str


class ClusteringOutput(TypedDict):
    """Schéma de sortie attendu pour la classification de clustering."""

    assignment: Literal["existing_cluster", "new_cluster"]
    cluster_id: str | None  # Requis si assignment est "existing_cluster"
    new_cluster_topic: str | None  # Requis si assignment est "new_cluster"
    confidence: Literal["high", "medium", "low"]
    reasoning: str


CLUSTERING_SYSTEM_PROMPT = """Vous êtes un classificateur de signaux pour un système de coordination de réponse aux crises.

Votre rôle est de déterminer si un nouveau message Slack (signal) appartient à un cluster
de sujet/incident existant ou doit initier un nouveau cluster.

Principes clés :
- Regrouper par SUJET et INCIDENT, pas par canal ou auteur
- Un cluster représente un thème cohérent : un événement spécifique, un lieu, un besoin ou une situation
- Préférez l'affectation à des clusters existants lorsqu'ils sont liés thématiquement
- Créez de nouveaux clusters uniquement lorsque le signal introduit un sujet véritablement nouveau
- La proximité temporelle seule ne définit pas les clusters (une mise à jour sur l'incendie
  d'hier appartient au cluster de l'incendie, pas à un nouveau cluster de "mises à jour générales")

Critères de décision pour CLUSTER EXISTANT :
- Le signal discute du même incident, lieu ou situation en cours
- Le signal fournit des mises à jour, des clarifications ou des corrections au sujet du cluster
- Le signal pose des questions ou fournit des réponses liées au sujet du cluster

Critères de décision pour NOUVEAU CLUSTER :
- Le signal introduit un sujet ou incident complètement différent
- Le signal discute d'un lieu différent avec une situation différente
- Le signal ne peut pas être regroupé de manière significative avec un cluster existant

Générez votre classification sous forme de JSON valide correspondant au schéma requis.
"""

CLUSTERING_USER_PROMPT_TEMPLATE = """Classifiez si ce nouveau signal appartient à un cluster existant ou doit créer un nouveau cluster.

NOUVEAU SIGNAL :
Auteur : {signal_author}
Canal : {signal_channel}
Horodatage : {signal_timestamp}
Contenu : {signal_content}
Contexte du fil : {signal_thread_context}

CLUSTERS EXISTANTS :
{clusters_json}

Analysez le signal et déterminez :
1. Est-il clairement lié à un sujet de cluster existant ?
2. Si oui, quel cluster correspond le mieux ?
3. Si non, quel nouveau sujet introduit-il ?

Répondez uniquement avec du JSON valide, sans texte supplémentaire :
{{
  "assignment": "existing_cluster" ou "new_cluster",
  "cluster_id": "<cluster_id>" ou null,
  "new_cluster_topic": "<sujet>" ou null,
  "confidence": "high" | "medium" | "low",
  "reasoning": "<explication brève>"
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
    Formate le prompt utilisateur de clustering avec les données du signal et du cluster.

    Args:
        signal_author: ID utilisateur Slack ou nom d'affichage
        signal_channel: Nom ou ID du canal
        signal_timestamp: Horodatage ISO 8601
        signal_content: Contenu texte du message
        signal_thread_context: Message parent ou résumé du fil (vide si de niveau supérieur)
        existing_clusters: Liste des résumés de clusters pour comparaison

    Returns:
        Prompt utilisateur formaté prêt pour LLM
    """
    import json

    clusters_json = json.dumps(existing_clusters, indent=2, ensure_ascii=False) if existing_clusters else "[]"

    return CLUSTERING_USER_PROMPT_TEMPLATE.format(
        signal_author=signal_author,
        signal_channel=signal_channel,
        signal_timestamp=signal_timestamp,
        signal_content=signal_content,
        signal_thread_context=signal_thread_context or "(Aucun - message de niveau supérieur)",
        clusters_json=clusters_json,
    )


# Schéma Pydantic pour validation de sortie structurée
CLUSTERING_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "assignment": {
            "type": "string",
            "enum": ["existing_cluster", "new_cluster"],
            "description": "Si le signal appartient à un cluster existant ou en crée un nouveau",
        },
        "cluster_id": {
            "type": ["string", "null"],
            "description": "ID du cluster existant (requis si assignment est existing_cluster)",
        },
        "new_cluster_topic": {
            "type": ["string", "null"],
            "description": "Nom du sujet pour nouveau cluster (requis si assignment est new_cluster)",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": "Niveau de confiance dans la classification",
        },
        "reasoning": {
            "type": "string",
            "description": "Explication brève de la décision de classification",
        },
    },
    "required": ["assignment", "confidence", "reasoning"],
    "additionalProperties": False,
}
