"""
Directives de rédaction pour phrases nuancées vs directes en français.

Ce module fournit des directives sur comment rédiger les mises à jour COP en français
selon l'état de vérification, incluant des phrases nuancées culturellement appropriées
pour les éléments en révision et un langage direct pour les éléments vérifiés.

Usage:
    Utilisez ces directives lors de la génération de brouillons COP pour assurer une rédaction
    culturellement appropriée qui transmet correctement la certitude ou l'incertitude.
"""

from typing import Literal


# Phrases nuancées courantes en français pour information non vérifiée
HEDGED_PHRASES_FRENCH = [
    "Selon des rapports non confirmés",
    "Non confirmé",
    "Il est rapporté que",
    "Présumément",
    "En cours de vérification",
    "En attente de confirmation",
    "Selon des rapports préliminaires",
    "Les rapports initiaux suggèrent",
    "Confirmation recherchée de",
    "Nécessite vérification",
    "Information préliminaire indique",
    "Pas encore confirmé",
]

# Phrases directes pour information vérifiée
DIRECT_PHRASES_FRENCH = [
    "Il est confirmé",
    "Confirmé",
    "Vérifié",
    "Officiellement",
    "Selon des sources officielles",
    "Il a été confirmé",
    "Il est confirmé que",
    "De manière officielle",
]

# Phrases de correction pour information démentie
CORRECTION_PHRASES_FRENCH = [
    "CORRECTION",
    "DÉMENTI",
    "RECTIFICATION",
    "Les rapports antérieurs de... sont incorrects",
    "Contrairement aux rapports précédents",
    "L'information antérieure est corrigée",
]

# Verbes conjugués pour états de vérification
VERIFICATION_VERBS = {
    "verified": {
        "to_be": "est",  # Main Street est fermée
        "to_have": "a",  # Le refuge a ouvert
        "to_confirm": "se confirme",  # La fermeture se confirme
        "to_report": "rapporte",  # Le DOT rapporte
    },
    "in_review": {
        "to_be": "serait",  # Main Street serait fermée (conditionnel)
        "to_have": "aurait",  # Le refuge aurait ouvert
        "to_confirm": "recherche confirmation",  # Confirmation recherchée
        "to_report": "est rapporté",  # Il est rapporté (non officiel)
    },
    "disproven": {
        "to_be": "n'est pas",  # Main Street n'est pas fermée
        "to_have": "n'a pas",  # Le refuge n'a pas fermé
        "to_confirm": "est démenti",  # La fermeture est démentie
        "to_report": "est corrigé",  # Le rapport est corrigé
    },
}


def get_wording_guidance(
    verification_status: Literal["verified", "in_review", "disproven"],
    risk_tier: Literal["routine", "elevated", "high_stakes"],
) -> dict[str, str | list[str]]:
    """
    Obtient les directives de rédaction basées sur l'état de vérification et le niveau de risque.

    Args:
        verification_status: État de vérification de l'élément
        risk_tier: Niveau de risque de l'élément

    Returns:
        Dictionnaire avec directives de rédaction incluant phrases recommandées,
        verbes et notes de style
    """
    if verification_status == "verified":
        return {
            "style": "direct_factual",
            "recommended_phrases": DIRECT_PHRASES_FRENCH,
            "verbs": VERIFICATION_VERBS["verified"],
            "example": "Le pont de Main Street est fermé à toute circulation depuis 14h00 heure du Pacifique en raison de dommages structurels.",
            "notes": "Utilisez un langage définitif et le présent de l'indicatif. Énoncez les faits directement sans nuances.",
        }
    elif verification_status == "in_review":
        guidance = {
            "style": "hedged_uncertain",
            "recommended_phrases": HEDGED_PHRASES_FRENCH,
            "verbs": VERIFICATION_VERBS["in_review"],
            "example": "Non confirmé : Selon des rapports, le pont de Main Street pourrait être fermé. Confirmation recherchée auprès du Département des Transports du comté.",
            "notes": "Utilisez un langage prudent et le conditionnel. Rendez l'incertitude explicite. Énoncez ce qui est connu et ce qui ne l'est pas.",
        }
        if risk_tier == "high_stakes":
            guidance["additional_requirements"] = [
                "Incluez la prochaine étape de vérification",
                "Spécifiez l'heure de revérification",
                "Indiquez la source qui est contactée",
            ]
        return guidance
    else:  # disproven
        return {
            "style": "correction",
            "recommended_phrases": CORRECTION_PHRASES_FRENCH,
            "verbs": VERIFICATION_VERBS["disproven"],
            "example": "CORRECTION : Les rapports antérieurs de fermeture du pont de Main Street sont incorrects. Le pont reste ouvert selon le Département des Transports du comté à 15h00 heure du Pacifique.",
            "notes": "Commencez par CORRECTION ou DÉMENTI en majuscules. Énoncez clairement ce qui était incorrect. Fournissez les informations correctes.",
        }


def format_timestamp_french(timestamp: str, timezone: str = "heure du Pacifique") -> str:
    """
    Formate un horodatage pour utilisation dans COP en français.

    Args:
        timestamp: Horodatage au format ISO ou similaire
        timezone: Fuseau horaire à afficher

    Returns:
        Horodatage formaté approprié pour COP en français
    """
    # Exemple : "14h00 heure du Pacifique" ou "14 mars, 15h30 heure de l'Est"
    # Ceci est une fonction auxiliaire pour formatage cohérent
    return f"{timestamp} {timezone}"


def get_date_format_french() -> str:
    """
    Retourne le format de date recommandé pour COP en français.

    Returns:
        Modèle de format de date (e.g., "14 mars 2026, 15h30 heure du Pacifique")
    """
    return "%d %B %Y, %Hh%M"


# Exemples d'éléments de ligne complets pour référence
EXAMPLE_LINE_ITEMS_FRENCH = {
    "verified": """[VÉRIFIÉ] L'abri à l'École Primaire Lincoln est opérationnel et accueille des familles depuis 14h00 heure du Pacifique. Capacité : 200 personnes. Contact : coordinateur@abri.org. (Source : Coordinateur d'Abri Sarah Martinez, message Slack 2026-03-10 14h15)""",
    "in_review": """[EN RÉVISION] Non confirmé : Selon des rapports, l'abri à l'École Primaire Lincoln accueillerait des familles. Confirmation recherchée du coordinateur d'abri. Prochaine étape : Contacter Sarah Martinez. Revérification : 16h00 heure du Pacifique. (Source : message communautaire, en attente de vérification)""",
    "in_review_high_stakes": """[EN RÉVISION - HAUT RISQUE] Non confirmé : Les rapports préliminaires suggèrent une possible contamination de l'approvisionnement en eau dans le secteur est. NÉCESSITE VÉRIFICATION URGENTE. Prochaine étape : Contacter immédiatement le Département de Santé Publique. Revérification : 15h30 heure du Pacifique. NE PAS distribuer publiquement avant confirmation. (Source : rapport de résident, non confirmé)""",
    "disproven": """[DÉMENTI] CORRECTION : Les rapports antérieurs de fermeture de l'abri à l'École Primaire Lincoln sont incorrects. L'abri reste ouvert et opérationnel selon confirmation du coordinateur Sarah Martinez à 15h00 heure du Pacifique. (Source : Vérification directe avec coordinateur d'abri)""",
}


# Directives pour facilitateurs sur quand utiliser chaque style
FACILITATOR_GUIDANCE_FRENCH = """
Directives de Rédaction pour Facilitateurs - COP en Français

1. INFORMATION VÉRIFIÉE (Style Direct) :
   - Utilisez lorsque vous avez confirmation d'une source autorisée
   - Employez le présent de l'indicatif
   - Soyez spécifique et définitif
   - Exemple : "Le pont est fermé" (pas "serait fermé")

2. INFORMATION EN RÉVISION (Style Nuancé) :
   - Utilisez lorsque l'information n'est pas confirmée
   - Employez des phrases comme "Non confirmé", "Selon des rapports"
   - Utilisez le conditionnel lorsque approprié
   - Exemple : "Le pont pourrait être fermé" ou "Le pont serait fermé"
   - Énoncez explicitement ce qui est en cours de vérification

3. INFORMATION À HAUT RISQUE EN RÉVISION :
   - Incluez toujours la prochaine étape de vérification
   - Spécifiez l'heure exacte de revérification
   - Considérez ne pas publier avant vérification si le risque est critique
   - Soyez explicite sur l'incertitude

4. CORRECTIONS ET DÉMENTIS :
   - Commencez par "CORRECTION :" ou "DÉMENTI :" en majuscules
   - Énoncez clairement ce qui était incorrect
   - Fournissez les informations correctes
   - Incluez quand la correction a été confirmée

5. FORMATAGE DES DATES ET HEURES :
   - Utilisez le format 24 heures : 14h00, pas 2:00 PM
   - Incluez toujours le fuseau horaire : "14h00 heure du Pacifique"
   - Dates : "14 mars 2026" (jour en premier)

6. CONSIDÉRATIONS CULTURELLES :
   - Le français permet des structures de phrases formelles
   - Utilisez la voix active lorsque possible
   - "Il est confirmé" est approprié pour voix passive formelle
   - Évitez les anglicismes inutiles
   - Utilisez "h" pour les heures : "14h00" pas "14:00"
"""
