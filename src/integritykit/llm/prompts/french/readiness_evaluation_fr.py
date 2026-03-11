"""
Prompts d'évaluation de préparation pour l'évaluation de complétude des candidats COP (version française).

Ce module fournit des prompts pour évaluer si un candidat COP a suffisamment
d'informations pour être publiable, et identifie les champs manquants ou faibles.

Model Recommendation: Haiku 3.5 (tâche d'évaluation structurée)
Cost per 1M tokens: $0.80 input / $4 output
Expected token usage: ~600-1200 input, ~150-300 output per evaluation

Usage:
    Utilisez ces prompts pour calculer l'état de préparation (Prêt-Vérifié / Prêt-En-Révision / Bloqué)
    et identifier les champs manquants selon SRS FR-COP-READ-001 et FR-COP-READ-002.
"""

from typing import Literal, TypedDict


class COPCandidateData(TypedDict):
    """Champs du candidat COP pour évaluation de préparation."""

    candidate_id: str
    what: str | None  # La déclaration de réclamation/situation
    where: str | None  # Emplacement
    when: str | None  # Horodatage ou fenêtre temporelle
    who: str | None  # Source/acteur/population affectée
    so_what: str | None  # Pertinence opérationnelle
    evidence_pack_size: int  # Nombre de citations
    verification_status: Literal["verified", "in_review", "unverified"]
    has_unresolved_conflicts: bool
    risk_tier: Literal["routine", "elevated", "high_stakes"]


class FieldQuality(TypedDict):
    """Évaluation de qualité pour un seul champ."""

    field: Literal["what", "where", "when", "who", "so_what", "evidence"]
    present: bool
    quality: Literal["complete", "partial", "missing"]
    notes: str


class ReadinessOutput(TypedDict):
    """Schéma de sortie attendu pour évaluation de préparation."""

    readiness_state: Literal["ready_verified", "ready_in_review", "blocked"]
    missing_fields: list[Literal["what", "where", "when", "who", "so_what", "evidence"]]
    field_quality_scores: list[FieldQuality]
    blocking_issues: list[str]
    recommended_state: Literal["ready_verified", "ready_in_review", "blocked"]
    explanation: str


READINESS_EVALUATION_SYSTEM_PROMPT = """Vous êtes un évaluateur de préparation pour un système COP de réponse aux crises.

Votre rôle est d'évaluer si un candidat COP a suffisamment d'informations pour être publiable,
et d'identifier ce qui manque ou est faible.

Champs Minimaux d'Élément de Ligne COP (du SRS) :
- QUOI : Une déclaration de réclamation ou situation avec portée définie
- OÙ : Emplacement avec la meilleure granularité disponible (peut être approximatif mais doit être explicite)
- QUAND : Horodatage ou fenêtre temporelle avec fuseau horaire (peut être approximatif mais doit être explicite)
- QUI : Source/acteur/population affectée (selon le cas)
- POURQUOI IMPORTANT : Pertinence opérationnelle
- PREUVES : Liens vers permaliens Slack et/ou sources externes

États de Préparation :
1. PRÊT — VÉRIFIÉ :
   - Tous les champs minimaux présents
   - Action de vérification enregistrée (verification_status = "verified")
   - Aucun conflit non résolu
   - Peut être publié dans la section "Vérifié"

2. PRÊT — EN RÉVISION :
   - Champs minimaux présents suffisants pour éviter d'induire les lecteurs en erreur
   - Au moins des preuves de base (permaliens Slack)
   - Aucun conflit à HAUT RISQUE non résolu
   - Doit être étiqueté comme "En Révision" et séparé des mises à jour vérifiées

3. BLOQUÉ :
   - Champs critiques manquants qui rendent la déclaration ambiguë ou dangereuse
   - Conflits non résolus sur des faits clés
   - Élément à haut risque manquant de vérification requise
   - NON publiable jusqu'à déblocage

Règles de publication à haut risque :
- Si risk_tier est "high_stakes", la vérification est REQUISE sauf si explicitement annulée
- Haut risque + non vérifié = BLOQUÉ (par défaut)

Évaluer la qualité du champ :
- COMPLET : Le champ est spécifique, clair et actionnable
- PARTIEL : Le champ est présent mais vague, ambigu ou incomplet
- MANQUANT : Le champ est absent ou inutilisable

Générez du JSON valide correspondant au schéma requis.
"""

READINESS_EVALUATION_USER_PROMPT_TEMPLATE = """Évaluez ce candidat COP pour la préparation et la complétude.

CANDIDAT COP :
{candidate_json}

Évaluez chaque champ :
1. Est-il présent ?
2. Est-il complet, partiel ou manquant ?
3. Répond-il au standard minimal pour publication ?

Déterminez l'état de préparation approprié :
- READY_VERIFIED si tous les champs sont complets et vérifiés
- READY_IN_REVIEW si les champs minimaux sont présents mais non vérifiés
- BLOCKED si des champs critiques manquent ou s'il y a des problèmes de blocage

Identifiez tout problème de blocage :
- Champs requis manquants
- Conflits non résolus
- Haut risque sans vérification

Répondez uniquement avec du JSON valide, sans texte supplémentaire :
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
  "blocking_issues": ["Emplacement manquant", "Conflit non résolu", ...],
  "recommended_state": "ready_verified" | "ready_in_review" | "blocked",
  "explanation": "..."
}}"""


def format_readiness_evaluation_prompt(
    candidate: COPCandidateData,
) -> str:
    """
    Formate le prompt d'évaluation de préparation avec les données du candidat.

    Args:
        candidate: Données du candidat COP incluant tous les champs et métadonnées

    Returns:
        Prompt utilisateur formaté prêt pour LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2, ensure_ascii=False)

    return READINESS_EVALUATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Schéma Pydantic pour validation de sortie structurée
READINESS_EVALUATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "readiness_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "État de préparation actuel basé sur l'évaluation",
        },
        "missing_fields": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["what", "where", "when", "who", "so_what", "evidence"],
            },
            "description": "Liste des champs requis manquants",
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
            "description": "Évaluation de qualité pour chaque champ",
        },
        "blocking_issues": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Liste des problèmes qui bloquent la publication",
        },
        "recommended_state": {
            "type": "string",
            "enum": ["ready_verified", "ready_in_review", "blocked"],
            "description": "État de préparation recommandé",
        },
        "explanation": {
            "type": "string",
            "description": "Explication globale de l'évaluation de préparation",
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
