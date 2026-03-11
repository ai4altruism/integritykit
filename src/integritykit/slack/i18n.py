"""Internationalization (i18n) for Slack Block Kit UI components.

This module provides translation utilities for Block Kit elements including:
- Status labels (Verified, In Review, Blocked)
- Button labels (Approve, Reject, Promote, Edit)
- Section headers (Backlog, Candidates, COP Updates)
- Clarification template messages
- Error messages

Supported Languages:
- English (en) - Default
- Spanish (es)
- French (fr)

Usage:
    from integritykit.slack.i18n import get_translation, get_status_badge

    # Get translated string
    label = get_translation("verified", "es")  # "Verificado"

    # Get status badge with icon
    badge = get_status_badge("verified", "fr")  # Block Kit badge
"""

from enum import Enum
from typing import Any

from integritykit.models.language import LanguageCode


class TranslationKey(str, Enum):
    """Translation keys for UI elements."""

    # Readiness states
    VERIFIED = "verified"
    IN_REVIEW = "in_review"
    BLOCKED = "blocked"
    READY_VERIFIED = "ready_verified"
    READY_IN_REVIEW = "ready_in_review"

    # Field statuses
    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"
    NEEDS_IMPROVEMENT = "needs_improvement"

    # Risk tiers
    ROUTINE = "routine"
    ELEVATED = "elevated"
    HIGH_STAKES = "high_stakes"

    # Button labels
    APPROVE = "approve"
    REJECT = "reject"
    PROMOTE = "promote"
    EDIT = "edit"
    VIEW = "view"
    VIEW_FULL_DETAILS = "view_full_details"
    REEVALUATE = "reevaluate"
    ASSIGN_VERIFIER = "assign_verifier"
    VIEW_CONFLICTS = "view_conflicts"
    REQUEST_INFO = "request_info"
    PUBLISH = "publish"
    VIEW_DUPLICATES = "view_duplicates"

    # Section headers
    BACKLOG = "backlog"
    CANDIDATES = "candidates"
    COP_UPDATES = "cop_updates"
    FIELD_COMPLETENESS_CHECKLIST = "field_completeness_checklist"
    COP_CANDIDATE_DETAILS = "cop_candidate_details"
    RECOMMENDED_NEXT_ACTION = "recommended_next_action"
    COP_INFORMATION = "cop_information"
    READINESS_STATUS = "readiness_status"
    RISK_TIER = "risk_tier"
    BLOCKING_ISSUES = "blocking_issues"

    # Field labels
    WHAT = "what"
    WHERE = "where"
    WHEN = "when"
    WHO = "who"
    SO_WHAT = "so_what"
    EVIDENCE = "evidence"

    # Action types
    ASSIGN_VERIFICATION = "assign_verification"
    RESOLVE_CONFLICT = "resolve_conflict"
    ADD_EVIDENCE = "add_evidence"
    READY_TO_PUBLISH = "ready_to_publish"
    MERGE_CANDIDATES = "merge_candidates"

    # Messages
    ALL_FIELDS_COMPLETE = "all_fields_complete"
    MISSING_FIELDS_WARNING = "missing_fields_warning"
    FIELDS_NEED_IMPROVEMENT = "fields_need_improvement"
    NO_ACTION_REQUIRED = "no_action_required"
    VERIFICATIONS = "verifications"
    BLOCKING_ISSUE_COUNT = "blocking_issue_count"
    NOT_SPECIFIED = "not_specified"
    UNTITLED = "untitled"
    SUGGESTED_MESSAGE = "suggested_message"
    COPY_MESSAGE_HINT = "copy_message_hint"
    ALTERNATIVES = "alternatives"

    # Clarification templates
    CLARIFICATION_INTRO = "clarification_intro"
    CLARIFICATION_MISSING_FIELD = "clarification_missing_field"
    CLARIFICATION_WEAK_FIELD = "clarification_weak_field"
    CLARIFICATION_EVIDENCE_REQUEST = "clarification_evidence_request"
    CLARIFICATION_CLOSING = "clarification_closing"

    # Error messages
    ERROR_GENERIC = "error_generic"
    ERROR_NOT_FOUND = "error_not_found"
    ERROR_PERMISSION_DENIED = "error_permission_denied"
    ERROR_VALIDATION_FAILED = "error_validation_failed"


# Translation dictionaries for each supported language
TRANSLATIONS = {
    LanguageCode.EN: {
        # Readiness states
        TranslationKey.VERIFIED: "Verified",
        TranslationKey.IN_REVIEW: "In Review",
        TranslationKey.BLOCKED: "Blocked",
        TranslationKey.READY_VERIFIED: "Ready - Verified",
        TranslationKey.READY_IN_REVIEW: "Ready - In Review",

        # Field statuses
        TranslationKey.COMPLETE: "Complete",
        TranslationKey.PARTIAL: "Needs improvement",
        TranslationKey.MISSING: "Missing",
        TranslationKey.NEEDS_IMPROVEMENT: "Needs improvement",

        # Risk tiers
        TranslationKey.ROUTINE: "Routine",
        TranslationKey.ELEVATED: "Elevated",
        TranslationKey.HIGH_STAKES: "High Stakes",

        # Button labels
        TranslationKey.APPROVE: "Approve",
        TranslationKey.REJECT: "Reject",
        TranslationKey.PROMOTE: "Promote",
        TranslationKey.EDIT: "Edit",
        TranslationKey.VIEW: "View",
        TranslationKey.VIEW_FULL_DETAILS: "View Full Details",
        TranslationKey.REEVALUATE: "Re-evaluate",
        TranslationKey.ASSIGN_VERIFIER: "Assign Verifier",
        TranslationKey.VIEW_CONFLICTS: "View Conflicts",
        TranslationKey.REQUEST_INFO: "Request Info",
        TranslationKey.PUBLISH: "Publish",
        TranslationKey.VIEW_DUPLICATES: "View Duplicates",

        # Section headers
        TranslationKey.BACKLOG: "Backlog",
        TranslationKey.CANDIDATES: "Candidates",
        TranslationKey.COP_UPDATES: "COP Updates",
        TranslationKey.FIELD_COMPLETENESS_CHECKLIST: "Field Completeness Checklist",
        TranslationKey.COP_CANDIDATE_DETAILS: "COP Candidate Details",
        TranslationKey.RECOMMENDED_NEXT_ACTION: "Recommended Next Action",
        TranslationKey.COP_INFORMATION: "COP Information",
        TranslationKey.READINESS_STATUS: "Readiness Status",
        TranslationKey.RISK_TIER: "Risk Tier",
        TranslationKey.BLOCKING_ISSUES: "Blocking Issues",

        # Field labels
        TranslationKey.WHAT: "What",
        TranslationKey.WHERE: "Where",
        TranslationKey.WHEN: "When",
        TranslationKey.WHO: "Who",
        TranslationKey.SO_WHAT: "So What",
        TranslationKey.EVIDENCE: "Evidence",

        # Action types
        TranslationKey.ASSIGN_VERIFICATION: "Assign Verification",
        TranslationKey.RESOLVE_CONFLICT: "Resolve Conflict",
        TranslationKey.ADD_EVIDENCE: "Add Evidence",
        TranslationKey.READY_TO_PUBLISH: "Ready To Publish",
        TranslationKey.MERGE_CANDIDATES: "Merge Candidates",

        # Messages
        TranslationKey.ALL_FIELDS_COMPLETE: "All fields are complete!",
        TranslationKey.MISSING_FIELDS_WARNING: "{missing} missing, {partial} need improvement",
        TranslationKey.FIELDS_NEED_IMPROVEMENT: "{partial} fields need improvement",
        TranslationKey.NO_ACTION_REQUIRED: "No action required at this time.",
        TranslationKey.VERIFICATIONS: "verifications",
        TranslationKey.BLOCKING_ISSUE_COUNT: "blocking issue(s)",
        TranslationKey.NOT_SPECIFIED: "Not specified",
        TranslationKey.UNTITLED: "Untitled",
        TranslationKey.SUGGESTED_MESSAGE: "Suggested Message:",
        TranslationKey.COPY_MESSAGE_HINT: "Copy this message to request clarification from the source.",
        TranslationKey.ALTERNATIVES: "Alternatives:",

        # Clarification templates
        TranslationKey.CLARIFICATION_INTRO: "Hi, I need some clarification on the following information:",
        TranslationKey.CLARIFICATION_MISSING_FIELD: "Missing information: {field}",
        TranslationKey.CLARIFICATION_WEAK_FIELD: "{field} needs more detail: {reason}",
        TranslationKey.CLARIFICATION_EVIDENCE_REQUEST: "Can you provide additional evidence or sources?",
        TranslationKey.CLARIFICATION_CLOSING: "Thank you for your help!",

        # Error messages
        TranslationKey.ERROR_GENERIC: "An error occurred. Please try again.",
        TranslationKey.ERROR_NOT_FOUND: "Item not found.",
        TranslationKey.ERROR_PERMISSION_DENIED: "Permission denied.",
        TranslationKey.ERROR_VALIDATION_FAILED: "Validation failed. Please check your input.",
    },
    LanguageCode.ES: {
        # Readiness states
        TranslationKey.VERIFIED: "Verificado",
        TranslationKey.IN_REVIEW: "En Revisión",
        TranslationKey.BLOCKED: "Bloqueado",
        TranslationKey.READY_VERIFIED: "Listo - Verificado",
        TranslationKey.READY_IN_REVIEW: "Listo - En Revisión",

        # Field statuses
        TranslationKey.COMPLETE: "Completo",
        TranslationKey.PARTIAL: "Necesita mejoras",
        TranslationKey.MISSING: "Faltante",
        TranslationKey.NEEDS_IMPROVEMENT: "Necesita mejoras",

        # Risk tiers
        TranslationKey.ROUTINE: "Rutina",
        TranslationKey.ELEVATED: "Elevado",
        TranslationKey.HIGH_STAKES: "Alto Riesgo",

        # Button labels
        TranslationKey.APPROVE: "Aprobar",
        TranslationKey.REJECT: "Rechazar",
        TranslationKey.PROMOTE: "Promover",
        TranslationKey.EDIT: "Editar",
        TranslationKey.VIEW: "Ver",
        TranslationKey.VIEW_FULL_DETAILS: "Ver Detalles Completos",
        TranslationKey.REEVALUATE: "Re-evaluar",
        TranslationKey.ASSIGN_VERIFIER: "Asignar Verificador",
        TranslationKey.VIEW_CONFLICTS: "Ver Conflictos",
        TranslationKey.REQUEST_INFO: "Solicitar Info",
        TranslationKey.PUBLISH: "Publicar",
        TranslationKey.VIEW_DUPLICATES: "Ver Duplicados",

        # Section headers
        TranslationKey.BACKLOG: "Pendientes",
        TranslationKey.CANDIDATES: "Candidatos",
        TranslationKey.COP_UPDATES: "Actualizaciones COP",
        TranslationKey.FIELD_COMPLETENESS_CHECKLIST: "Lista de Verificación de Campos",
        TranslationKey.COP_CANDIDATE_DETAILS: "Detalles del Candidato COP",
        TranslationKey.RECOMMENDED_NEXT_ACTION: "Próxima Acción Recomendada",
        TranslationKey.COP_INFORMATION: "Información COP",
        TranslationKey.READINESS_STATUS: "Estado de Preparación",
        TranslationKey.RISK_TIER: "Nivel de Riesgo",
        TranslationKey.BLOCKING_ISSUES: "Problemas Bloqueantes",

        # Field labels
        TranslationKey.WHAT: "Qué",
        TranslationKey.WHERE: "Dónde",
        TranslationKey.WHEN: "Cuándo",
        TranslationKey.WHO: "Quién",
        TranslationKey.SO_WHAT: "Por Qué Importa",
        TranslationKey.EVIDENCE: "Evidencia",

        # Action types
        TranslationKey.ASSIGN_VERIFICATION: "Asignar Verificación",
        TranslationKey.RESOLVE_CONFLICT: "Resolver Conflicto",
        TranslationKey.ADD_EVIDENCE: "Agregar Evidencia",
        TranslationKey.READY_TO_PUBLISH: "Listo para Publicar",
        TranslationKey.MERGE_CANDIDATES: "Fusionar Candidatos",

        # Messages
        TranslationKey.ALL_FIELDS_COMPLETE: "¡Todos los campos están completos!",
        TranslationKey.MISSING_FIELDS_WARNING: "{missing} faltantes, {partial} necesitan mejoras",
        TranslationKey.FIELDS_NEED_IMPROVEMENT: "{partial} campos necesitan mejoras",
        TranslationKey.NO_ACTION_REQUIRED: "No se requiere acción en este momento.",
        TranslationKey.VERIFICATIONS: "verificaciones",
        TranslationKey.BLOCKING_ISSUE_COUNT: "problema(s) bloqueante(s)",
        TranslationKey.NOT_SPECIFIED: "No especificado",
        TranslationKey.UNTITLED: "Sin título",
        TranslationKey.SUGGESTED_MESSAGE: "Mensaje Sugerido:",
        TranslationKey.COPY_MESSAGE_HINT: "Copie este mensaje para solicitar aclaración de la fuente.",
        TranslationKey.ALTERNATIVES: "Alternativas:",

        # Clarification templates
        TranslationKey.CLARIFICATION_INTRO: "Hola, necesito aclaración sobre la siguiente información:",
        TranslationKey.CLARIFICATION_MISSING_FIELD: "Información faltante: {field}",
        TranslationKey.CLARIFICATION_WEAK_FIELD: "{field} necesita más detalle: {reason}",
        TranslationKey.CLARIFICATION_EVIDENCE_REQUEST: "¿Puede proporcionar evidencia o fuentes adicionales?",
        TranslationKey.CLARIFICATION_CLOSING: "¡Gracias por su ayuda!",

        # Error messages
        TranslationKey.ERROR_GENERIC: "Ocurrió un error. Por favor, intente de nuevo.",
        TranslationKey.ERROR_NOT_FOUND: "Elemento no encontrado.",
        TranslationKey.ERROR_PERMISSION_DENIED: "Permiso denegado.",
        TranslationKey.ERROR_VALIDATION_FAILED: "La validación falló. Por favor, verifique su entrada.",
    },
    LanguageCode.FR: {
        # Readiness states
        TranslationKey.VERIFIED: "Vérifié",
        TranslationKey.IN_REVIEW: "En Cours de Vérification",
        TranslationKey.BLOCKED: "Bloqué",
        TranslationKey.READY_VERIFIED: "Prêt - Vérifié",
        TranslationKey.READY_IN_REVIEW: "Prêt - En Cours de Vérification",

        # Field statuses
        TranslationKey.COMPLETE: "Complet",
        TranslationKey.PARTIAL: "Nécessite amélioration",
        TranslationKey.MISSING: "Manquant",
        TranslationKey.NEEDS_IMPROVEMENT: "Nécessite amélioration",

        # Risk tiers
        TranslationKey.ROUTINE: "Routine",
        TranslationKey.ELEVATED: "Élevé",
        TranslationKey.HIGH_STAKES: "Haut Risque",

        # Button labels
        TranslationKey.APPROVE: "Approuver",
        TranslationKey.REJECT: "Rejeter",
        TranslationKey.PROMOTE: "Promouvoir",
        TranslationKey.EDIT: "Modifier",
        TranslationKey.VIEW: "Voir",
        TranslationKey.VIEW_FULL_DETAILS: "Voir Tous les Détails",
        TranslationKey.REEVALUATE: "Réévaluer",
        TranslationKey.ASSIGN_VERIFIER: "Assigner Vérificateur",
        TranslationKey.VIEW_CONFLICTS: "Voir Conflits",
        TranslationKey.REQUEST_INFO: "Demander Info",
        TranslationKey.PUBLISH: "Publier",
        TranslationKey.VIEW_DUPLICATES: "Voir Doublons",

        # Section headers
        TranslationKey.BACKLOG: "En Attente",
        TranslationKey.CANDIDATES: "Candidats",
        TranslationKey.COP_UPDATES: "Mises à Jour COP",
        TranslationKey.FIELD_COMPLETENESS_CHECKLIST: "Liste de Vérification des Champs",
        TranslationKey.COP_CANDIDATE_DETAILS: "Détails du Candidat COP",
        TranslationKey.RECOMMENDED_NEXT_ACTION: "Prochaine Action Recommandée",
        TranslationKey.COP_INFORMATION: "Information COP",
        TranslationKey.READINESS_STATUS: "État de Préparation",
        TranslationKey.RISK_TIER: "Niveau de Risque",
        TranslationKey.BLOCKING_ISSUES: "Problèmes Bloquants",

        # Field labels
        TranslationKey.WHAT: "Quoi",
        TranslationKey.WHERE: "Où",
        TranslationKey.WHEN: "Quand",
        TranslationKey.WHO: "Qui",
        TranslationKey.SO_WHAT: "Pourquoi Important",
        TranslationKey.EVIDENCE: "Preuve",

        # Action types
        TranslationKey.ASSIGN_VERIFICATION: "Assigner Vérification",
        TranslationKey.RESOLVE_CONFLICT: "Résoudre Conflit",
        TranslationKey.ADD_EVIDENCE: "Ajouter Preuve",
        TranslationKey.READY_TO_PUBLISH: "Prêt à Publier",
        TranslationKey.MERGE_CANDIDATES: "Fusionner Candidats",

        # Messages
        TranslationKey.ALL_FIELDS_COMPLETE: "Tous les champs sont complets !",
        TranslationKey.MISSING_FIELDS_WARNING: "{missing} manquants, {partial} nécessitent amélioration",
        TranslationKey.FIELDS_NEED_IMPROVEMENT: "{partial} champs nécessitent amélioration",
        TranslationKey.NO_ACTION_REQUIRED: "Aucune action requise pour le moment.",
        TranslationKey.VERIFICATIONS: "vérifications",
        TranslationKey.BLOCKING_ISSUE_COUNT: "problème(s) bloquant(s)",
        TranslationKey.NOT_SPECIFIED: "Non spécifié",
        TranslationKey.UNTITLED: "Sans titre",
        TranslationKey.SUGGESTED_MESSAGE: "Message Suggéré :",
        TranslationKey.COPY_MESSAGE_HINT: "Copiez ce message pour demander des éclaircissements à la source.",
        TranslationKey.ALTERNATIVES: "Alternatives :",

        # Clarification templates
        TranslationKey.CLARIFICATION_INTRO: "Bonjour, j'ai besoin de clarification sur les informations suivantes :",
        TranslationKey.CLARIFICATION_MISSING_FIELD: "Information manquante : {field}",
        TranslationKey.CLARIFICATION_WEAK_FIELD: "{field} nécessite plus de détails : {reason}",
        TranslationKey.CLARIFICATION_EVIDENCE_REQUEST: "Pouvez-vous fournir des preuves ou des sources supplémentaires ?",
        TranslationKey.CLARIFICATION_CLOSING: "Merci pour votre aide !",

        # Error messages
        TranslationKey.ERROR_GENERIC: "Une erreur s'est produite. Veuillez réessayer.",
        TranslationKey.ERROR_NOT_FOUND: "Élément non trouvé.",
        TranslationKey.ERROR_PERMISSION_DENIED: "Permission refusée.",
        TranslationKey.ERROR_VALIDATION_FAILED: "La validation a échoué. Veuillez vérifier votre saisie.",
    },
}


def get_translation(
    key: str | TranslationKey,
    language: str | LanguageCode = LanguageCode.EN,
    **format_params: Any,
) -> str:
    """Get translated string for a given key.

    Args:
        key: Translation key (string or TranslationKey enum)
        language: Language code (defaults to English)
        **format_params: Optional parameters for string formatting

    Returns:
        Translated string. Falls back to English if translation not found.

    Examples:
        >>> get_translation("verified", "es")
        'Verificado'

        >>> get_translation(TranslationKey.MISSING_FIELDS_WARNING, "fr", missing=2, partial=1)
        '2 manquants, 1 nécessitent amélioration'

        >>> get_translation("unknown_key", "es")
        'unknown_key'  # Falls back to key itself
    """
    # Normalize language code
    if isinstance(language, str):
        try:
            language = LanguageCode(language.lower())
        except ValueError:
            language = LanguageCode.EN

    # Normalize translation key
    if isinstance(key, str):
        try:
            key = TranslationKey(key)
        except ValueError:
            # If key is not a valid TranslationKey, return it as-is
            return key

    # Get translation dictionary for language
    translations = TRANSLATIONS.get(language, TRANSLATIONS[LanguageCode.EN])

    # Get translated string
    translated = translations.get(key, TRANSLATIONS[LanguageCode.EN].get(key, str(key)))

    # Apply formatting if parameters provided
    if format_params:
        try:
            translated = translated.format(**format_params)
        except (KeyError, ValueError):
            # If formatting fails, return unformatted string
            pass

    return translated


def get_status_badge(
    status: str,
    language: str | LanguageCode = LanguageCode.EN,
) -> dict[str, Any]:
    """Get a Slack Block Kit formatted status badge.

    Args:
        status: Status key (verified, in_review, blocked, etc.)
        language: Language code (defaults to English)

    Returns:
        Dict containing Block Kit elements for status badge with icon

    Example:
        >>> badge = get_status_badge("verified", "es")
        >>> # Returns: {"type": "mrkdwn", "text": ":white_check_mark: Verificado"}
    """
    # Icon mapping
    status_icons = {
        "verified": ":white_check_mark:",
        "in_review": ":hourglass:",
        "blocked": ":no_entry:",
        "complete": ":white_check_mark:",
        "partial": ":warning:",
        "missing": ":x:",
        "routine": ":large_green_circle:",
        "elevated": ":large_yellow_circle:",
        "high_stakes": ":red_circle:",
    }

    icon = status_icons.get(status.lower(), ":grey_question:")
    text = get_translation(status, language)

    return {
        "type": "mrkdwn",
        "text": f"{icon} {text}",
    }


def get_button_block(
    action: str,
    value: str,
    language: str | LanguageCode = LanguageCode.EN,
    style: str | None = None,
) -> dict[str, Any]:
    """Get a Slack Block Kit button with translated label.

    Args:
        action: Action key (approve, reject, view, etc.)
        value: Button value (usually ID)
        language: Language code (defaults to English)
        style: Optional button style (primary, danger)

    Returns:
        Dict containing Block Kit button element

    Example:
        >>> button = get_button_block("approve", "candidate_123", "fr", "primary")
        >>> # Returns button with "Approuver" label
    """
    button_text = get_translation(action, language)

    button = {
        "type": "button",
        "text": {
            "type": "plain_text",
            "text": button_text,
            "emoji": True,
        },
        "action_id": f"{action}_{value}",
        "value": value,
    }

    if style:
        button["style"] = style

    return button


def build_clarification_message(
    missing_fields: list[str],
    weak_fields: list[tuple[str, str]],
    language: str | LanguageCode = LanguageCode.EN,
) -> str:
    """Build a clarification request message in the specified language.

    Args:
        missing_fields: List of missing field names
        weak_fields: List of (field_name, reason) tuples for weak fields
        language: Language code (defaults to English)

    Returns:
        Formatted clarification message

    Example:
        >>> msg = build_clarification_message(
        ...     missing_fields=["where"],
        ...     weak_fields=[("what", "too vague")],
        ...     language="es"
        ... )
    """
    parts = [get_translation(TranslationKey.CLARIFICATION_INTRO, language)]
    parts.append("")

    # Add missing fields
    if missing_fields:
        for field in missing_fields:
            field_label = get_translation(field, language)
            parts.append(f"- {get_translation(TranslationKey.CLARIFICATION_MISSING_FIELD, language, field=field_label)}")

    # Add weak fields
    if weak_fields:
        for field, reason in weak_fields:
            field_label = get_translation(field, language)
            parts.append(f"- {get_translation(TranslationKey.CLARIFICATION_WEAK_FIELD, language, field=field_label, reason=reason)}")

    parts.append("")
    parts.append(get_translation(TranslationKey.CLARIFICATION_EVIDENCE_REQUEST, language))
    parts.append("")
    parts.append(get_translation(TranslationKey.CLARIFICATION_CLOSING, language))

    return "\n".join(parts)
