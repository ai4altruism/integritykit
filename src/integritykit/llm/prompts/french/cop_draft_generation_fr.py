"""
Prompts de génération de brouillons COP pour créer des éléments de ligne avec rédaction consciente de la vérification (version française).

Ce module fournit des prompts pour générer des éléments de ligne COP à partir de candidats,
en appliquant la rédaction appropriée selon l'état de vérification (nuancée pour En-Révision, directe pour Vérifié).

Model Recommendation: Sonnet 4 (nécessite une rédaction nuancée et compréhension du contexte)
Cost per 1M tokens: $3 input / $15 output
Expected token usage: ~1000-2000 input, ~200-400 output per draft

Usage:
    Utilisez ces prompts pour générer des éléments de ligne COP prêts pour publication à partir de candidats COP.
    Le système applique les directives de rédaction selon SRS FR-COP-WORDING-001.
"""

from typing import Literal, TypedDict


class EvidenceItem(TypedDict):
    """Un élément individuel de preuve dans le paquet de preuves."""

    source_type: Literal["slack_permalink", "external_url"]
    url: str
    description: str
    timestamp: str | None


class COPCandidateFull(TypedDict):
    """Données complètes du candidat COP pour génération de brouillon."""

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
    recheck_time: str | None  # Pour éléments à haut risque en révision


class COPDraftOutput(TypedDict):
    """Schéma de sortie attendu pour génération de brouillon COP."""

    line_item_text: str
    status_label: Literal["VÉRIFIÉ", "EN RÉVISION", "DÉMENTI"]
    citations: list[str]
    wording_style: Literal["direct_factual", "hedged_uncertain"]
    next_verification_step: str | None
    recheck_time: str | None
    section_placement: Literal[
        "verified_updates", "in_review_updates", "disproven_rumor_control", "open_questions"
    ]


COP_DRAFT_GENERATION_SYSTEM_PROMPT = """Vous êtes un rédacteur de brouillons COP pour un système de coordination de réponse aux crises.

Votre rôle est de générer des éléments de ligne COP prêts pour publication à partir de candidats COP,
en appliquant la rédaction appropriée selon l'état de vérification.

Directives de Rédaction (SRS FR-COP-WORDING-001) :

Éléments VÉRIFIÉS (rédaction directe et factuelle) :
- Utilisez un langage définitif : "est", "se confirme", "a été"
- Énoncez les faits directement sans nuances
- Exemple : "Le pont de Main Street est fermé à toute circulation depuis 14h00 heure du Pacifique en raison de dommages structurels."

Éléments EN RÉVISION (rédaction nuancée et incertaine) :
- Utilisez un langage prudent : "Selon des rapports non confirmés...", "Non confirmé :", "Confirmation recherchée de..."
- Rendez l'incertitude explicite
- Énoncez ce qui est connu et ce qui ne l'est pas
- Exemple : "Non confirmé : Selon des rapports, le pont de Main Street pourrait être fermé. Confirmation recherchée auprès du Département des Transports du comté."

Éléments DÉMENTIS (correction claire) :
- Commencez par "CORRECTION :" ou "DÉMENTI :"
- Énoncez ce qui était incorrect
- Fournissez les informations correctes si connues
- Exemple : "CORRECTION : Les rapports antérieurs de fermeture du pont de Main Street sont incorrects. Le pont reste ouvert selon le Département des Transports du comté à 15h00 heure du Pacifique."

Éléments à Haut Risque En Révision doivent inclure :
- Prochaine étape de vérification
- Heure de revérification
- Exemple : "Non confirmé : Rapports de fermeture d'abri à l'École Primaire Lincoln. Prochaine étape : Contacter le coordinateur d'abri. Revérification : 16h00 heure du Pacifique."

Structure de l'Élément de Ligne COP :
1. Étiquette de statut : [VÉRIFIÉ] ou [EN RÉVISION] ou [DÉMENTI]
2. Déclaration principale avec rédaction appropriée
3. Citations entre parenthèses ou notes de bas de page
4. Pour en-révision : Prochaine étape de vérification et heure de revérification si à haut risque

Générez du JSON valide avec le texte complet de l'élément de ligne et les métadonnées.
"""

COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE = """Générez un élément de ligne COP à partir de ce candidat.

CANDIDAT COP :
{candidate_json}

Appliquez le style de rédaction approprié :
- Si verification_status est "verified" : Utilisez une rédaction directe et factuelle
- Si verification_status est "in_review" : Utilisez une rédaction nuancée et incertaine
- Si verification_status est "disproven" : Commencez par CORRECTION/DÉMENTI

Incluez :
1. Étiquette de statut
2. Déclaration complète avec qui/quoi/quand/où/pourquoi-important
3. Citations aux éléments du paquet de preuves
4. Pour haut risque en-révision : prochaine étape de vérification et heure de revérification

Répondez uniquement avec du JSON valide, sans texte supplémentaire :
{{
  "line_item_text": "Texte complet de l'élément de ligne COP avec citations",
  "status_label": "VÉRIFIÉ" | "EN RÉVISION" | "DÉMENTI",
  "citations": ["https://slack.com/...", "https://example.com/..."],
  "wording_style": "direct_factual" | "hedged_uncertain",
  "next_verification_step": "Contacter le coordinateur d'abri" ou null,
  "recheck_time": "16h00 heure du Pacifique" ou null,
  "section_placement": "verified_updates" | "in_review_updates" | "disproven_rumor_control" | "open_questions"
}}"""


def format_cop_draft_generation_prompt(
    candidate: COPCandidateFull,
) -> str:
    """
    Formate le prompt de génération de brouillon COP avec les données du candidat.

    Args:
        candidate: Données complètes du candidat COP incluant tous les champs et paquet de preuves

    Returns:
        Prompt utilisateur formaté prêt pour LLM
    """
    import json

    candidate_json = json.dumps(candidate, indent=2, ensure_ascii=False)

    return COP_DRAFT_GENERATION_USER_PROMPT_TEMPLATE.format(
        candidate_json=candidate_json,
    )


# Schéma Pydantic pour validation de sortie structurée
COP_DRAFT_GENERATION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line_item_text": {
            "type": "string",
            "description": "Texte complet de l'élément de ligne COP prêt pour publication",
        },
        "status_label": {
            "type": "string",
            "enum": ["VÉRIFIÉ", "EN RÉVISION", "DÉMENTI"],
            "description": "Étiquette de statut de vérification pour l'élément de ligne",
        },
        "citations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Liste des URLs de citations du paquet de preuves",
        },
        "wording_style": {
            "type": "string",
            "enum": ["direct_factual", "hedged_uncertain"],
            "description": "Style de rédaction appliqué à l'élément de ligne",
        },
        "next_verification_step": {
            "type": ["string", "null"],
            "description": "Prochaine étape de vérification pour éléments à haut risque en-révision",
        },
        "recheck_time": {
            "type": ["string", "null"],
            "description": "Heure de revérification pour éléments à haut risque en-révision",
        },
        "section_placement": {
            "type": "string",
            "enum": [
                "verified_updates",
                "in_review_updates",
                "disproven_rumor_control",
                "open_questions",
            ],
            "description": "Section COP à laquelle appartient cet élément de ligne",
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
