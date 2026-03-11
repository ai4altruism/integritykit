"""Unit tests for Slack Block Kit builders with i18n support.

Tests:
- build_fields_checklist_blocks with language parameter
- build_readiness_summary_blocks with language parameter
- build_next_action_blocks with language parameter
- build_candidate_detail_blocks with language parameter
- build_candidate_list_item_blocks with language parameter
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    BlockingIssueSeverity,
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RecommendedAction,
    RiskTier,
    Verification,
    VerificationMethod,
)
from integritykit.models.language import LanguageCode
from integritykit.services.readiness import (
    FieldEvaluation,
    FieldStatus,
    ReadinessEvaluation,
)
from integritykit.slack.blocks import (
    build_candidate_detail_blocks,
    build_candidate_list_item_blocks,
    build_fields_checklist_blocks,
    build_next_action_blocks,
    build_readiness_summary_blocks,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_cop_candidate(
    *,
    candidate_id: ObjectId | None = None,
    what: str = "Test event",
    where: str = "Test location",
    when_description: str = "Today",
    who: str = "Test people",
    so_what: str = "Test impact",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    verifications: list[Verification] | None = None,
    blocking_issues: list[BlockingIssue] | None = None,
) -> COPCandidate:
    """Create a test COP candidate."""
    candidate = COPCandidate(
        id=candidate_id or ObjectId(),
        cluster_id=ObjectId(),
        created_by=ObjectId(),
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(description=when_description),
            who=who,
            so_what=so_what,
        ),
        evidence=Evidence(),
        verifications=verifications or [],
        blocking_issues=blocking_issues or [],
    )
    return candidate


def make_field_evaluation(
    field: str,
    status: FieldStatus,
    value: str | None = None,
    notes: str = "",
) -> FieldEvaluation:
    """Create a test field evaluation."""
    return FieldEvaluation(
        field=field,
        status=status,
        value=value,
        notes=notes,
    )


def make_readiness_evaluation(
    candidate: COPCandidate,
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    field_evaluations: list[FieldEvaluation] | None = None,
    missing_fields: list[str] | None = None,
    blocking_issues: list[BlockingIssue] | None = None,
    recommended_action: RecommendedAction | None = None,
    explanation: str = "Test evaluation",
) -> ReadinessEvaluation:
    """Create a test readiness evaluation."""
    return ReadinessEvaluation(
        candidate_id=str(candidate.id),
        readiness_state=readiness_state,
        field_evaluations=field_evaluations or [],
        missing_fields=missing_fields or [],
        blocking_issues=blocking_issues or [],
        recommended_action=recommended_action,
        explanation=explanation,
        evaluated_at=datetime.now(timezone.utc),
        evaluation_method="rule_based",
    )


# ============================================================================
# build_fields_checklist_blocks() i18n Tests
# ============================================================================


@pytest.mark.unit
class TestFieldsChecklistBlocksI18n:
    """Test build_fields_checklist_blocks() with different languages."""

    def test_header_in_spanish(self) -> None:
        """Checklist header is translated to Spanish."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.ES)

        assert blocks[0]["type"] == "header"
        assert "Lista de Verificación de Campos" in blocks[0]["text"]["text"]

    def test_header_in_french(self) -> None:
        """Checklist header is translated to French."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.FR)

        assert blocks[0]["type"] == "header"
        assert "Liste de Vérification des Champs" in blocks[0]["text"]["text"]

    def test_all_fields_complete_spanish(self) -> None:
        """All fields complete message in Spanish."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
            make_field_evaluation("where", FieldStatus.COMPLETE, "Test location"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.ES)

        summary_text = blocks[1]["text"]["text"]
        assert "¡Todos los campos están completos!" in summary_text

    def test_missing_fields_warning_french(self) -> None:
        """Missing fields warning in French."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test event"),
            make_field_evaluation("where", FieldStatus.MISSING, None),
            make_field_evaluation("when", FieldStatus.PARTIAL, "Partial"),
        ]

        blocks = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.FR)

        summary_text = blocks[1]["text"]["text"]
        assert "1 manquants" in summary_text
        assert "1 nécessitent amélioration" in summary_text

    def test_field_labels_translated(self) -> None:
        """Field labels are translated correctly."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test"),
            make_field_evaluation("where", FieldStatus.COMPLETE, "Test"),
            make_field_evaluation("who", FieldStatus.COMPLETE, "Test"),
        ]

        # Spanish
        blocks_es = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.ES)
        blocks_text_es = str(blocks_es)
        assert "Qué" in blocks_text_es
        assert "Dónde" in blocks_text_es
        assert "Quién" in blocks_text_es

        # French
        blocks_fr = build_fields_checklist_blocks(candidate, field_evaluations, LanguageCode.FR)
        blocks_text_fr = str(blocks_fr)
        assert "Quoi" in blocks_text_fr
        assert "Où" in blocks_text_fr
        assert "Qui" in blocks_text_fr


# ============================================================================
# build_readiness_summary_blocks() i18n Tests
# ============================================================================


@pytest.mark.unit
class TestReadinessSummaryBlocksI18n:
    """Test build_readiness_summary_blocks() with different languages."""

    def test_verified_state_spanish(self) -> None:
        """Verified state displays in Spanish."""
        candidate = make_cop_candidate(readiness_state=ReadinessState.VERIFIED)
        evaluation = make_readiness_evaluation(candidate, readiness_state=ReadinessState.VERIFIED)

        blocks = build_readiness_summary_blocks(candidate, evaluation, LanguageCode.ES)

        state_text = blocks[0]["text"]["text"]
        assert "Estado de Preparación" in state_text
        assert "Listo - Verificado" in state_text

    def test_risk_tier_french(self) -> None:
        """Risk tier displays in French."""
        candidate = make_cop_candidate(risk_tier=RiskTier.HIGH_STAKES)
        evaluation = make_readiness_evaluation(candidate)

        blocks = build_readiness_summary_blocks(candidate, evaluation, LanguageCode.FR)

        risk_text = blocks[1]["text"]["text"]
        assert "Niveau de Risque" in risk_text
        assert "Haut Risque" in risk_text

    def test_blocking_issues_spanish(self) -> None:
        """Blocking issues header in Spanish."""
        candidate = make_cop_candidate()
        blocking_issues = [
            BlockingIssue(
                issue_type="missing_field",
                description="Missing critical information",
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            ),
        ]
        evaluation = make_readiness_evaluation(candidate, blocking_issues=blocking_issues)

        blocks = build_readiness_summary_blocks(candidate, evaluation, LanguageCode.ES)

        blocks_text = str(blocks)
        assert "Problemas Bloqueantes" in blocks_text


# ============================================================================
# build_next_action_blocks() i18n Tests
# ============================================================================


@pytest.mark.unit
class TestNextActionBlocksI18n:
    """Test build_next_action_blocks() with different languages."""

    def test_no_action_required_spanish(self) -> None:
        """No action required message in Spanish."""
        candidate = make_cop_candidate()

        blocks = build_next_action_blocks(candidate, None, None, LanguageCode.ES)

        assert "No se requiere acción en este momento" in blocks[0]["text"]["text"]

    def test_recommended_action_header_french(self) -> None:
        """Recommended action header in French."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ASSIGN_VERIFICATION,
            reason="Needs verification",
        )

        blocks = build_next_action_blocks(candidate, action, None, LanguageCode.FR)

        assert blocks[0]["type"] == "header"
        assert "Prochaine Action Recommandée" in blocks[0]["text"]["text"]

    def test_button_labels_translated(self) -> None:
        """Button labels are translated."""
        candidate = make_cop_candidate()

        # Test different action types
        actions = [
            (ActionType.ASSIGN_VERIFICATION, "Asignar Verificador", "Assigner Vérificateur"),
            (ActionType.RESOLVE_CONFLICT, "Ver Conflictos", "Voir Conflits"),
            (ActionType.ADD_EVIDENCE, "Solicitar Info", "Demander Info"),
            (ActionType.READY_TO_PUBLISH, "Publicar", "Publier"),
        ]

        for action_type, spanish_label, french_label in actions:
            action = RecommendedAction(action_type=action_type, reason="Test")

            # Spanish
            blocks_es = build_next_action_blocks(candidate, action, None, LanguageCode.ES)
            button_es = blocks_es[2]["elements"][0]
            assert button_es["text"]["text"] == spanish_label

            # French
            blocks_fr = build_next_action_blocks(candidate, action, None, LanguageCode.FR)
            button_fr = blocks_fr[2]["elements"][0]
            assert button_fr["text"]["text"] == french_label

    def test_suggested_message_spanish(self) -> None:
        """Suggested message label in Spanish."""
        candidate = make_cop_candidate()
        action = RecommendedAction(
            action_type=ActionType.ADD_EVIDENCE,
            reason="Need more info",
        )
        template = "Test template"

        blocks = build_next_action_blocks(candidate, action, template, LanguageCode.ES)

        blocks_text = str(blocks)
        assert "Mensaje Sugerido:" in blocks_text


# ============================================================================
# build_candidate_detail_blocks() i18n Tests
# ============================================================================


@pytest.mark.unit
class TestCandidateDetailBlocksI18n:
    """Test build_candidate_detail_blocks() with different languages."""

    def test_header_spanish(self) -> None:
        """Candidate detail header in Spanish."""
        candidate = make_cop_candidate()
        field_evaluations = []
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation, LanguageCode.ES
        )

        assert blocks[0]["type"] == "header"
        assert "Detalles del Candidato COP" in blocks[0]["text"]["text"]

    def test_cop_information_section_french(self) -> None:
        """COP Information section in French."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test"),
        ]
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation, LanguageCode.FR
        )

        blocks_text = str(blocks)
        assert "Information COP" in blocks_text
        assert "Quoi:" in blocks_text
        assert "Où:" in blocks_text
        assert "Quand:" in blocks_text
        assert "Qui:" in blocks_text

    def test_not_specified_spanish(self) -> None:
        """Not specified text in Spanish."""
        candidate = make_cop_candidate(what="", where="")
        field_evaluations = []
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation, LanguageCode.ES
        )

        blocks_text = str(blocks)
        assert "No especificado" in blocks_text

    def test_action_buttons_french(self) -> None:
        """Action buttons translated to French."""
        candidate = make_cop_candidate()
        field_evaluations = []
        evaluation = make_readiness_evaluation(candidate, field_evaluations=field_evaluations)

        blocks = build_candidate_detail_blocks(
            candidate, field_evaluations, evaluation, LanguageCode.FR
        )

        # Find the last actions block
        actions_blocks = [b for b in blocks if b["type"] == "actions"]
        final_actions = actions_blocks[-1]
        buttons = final_actions["elements"]

        assert any("Voir Tous les Détails" in str(b) for b in buttons)
        assert any("Réévaluer" in str(b) for b in buttons)


# ============================================================================
# build_candidate_list_item_blocks() i18n Tests
# ============================================================================


@pytest.mark.unit
class TestCandidateListItemBlocksI18n:
    """Test build_candidate_list_item_blocks() with different languages."""

    def test_view_button_spanish(self) -> None:
        """View button in Spanish."""
        candidate = make_cop_candidate()

        blocks = build_candidate_list_item_blocks(candidate, LanguageCode.ES)

        button = blocks[0]["accessory"]
        assert button["text"]["text"] == "Ver"

    def test_risk_tier_french(self) -> None:
        """Risk tier in French."""
        candidate = make_cop_candidate(risk_tier=RiskTier.ELEVATED)

        blocks = build_candidate_list_item_blocks(candidate, LanguageCode.FR)

        section_text = blocks[0]["text"]["text"]
        assert "Élevé" in section_text

    def test_verifications_count_spanish(self) -> None:
        """Verifications count in Spanish."""
        verifications = [
            Verification(
                verified_by=ObjectId(),
                verification_method=VerificationMethod.AUTHORITATIVE_SOURCE,
            ),
        ]
        candidate = make_cop_candidate(verifications=verifications)

        blocks = build_candidate_list_item_blocks(candidate, LanguageCode.ES)

        section_text = blocks[0]["text"]["text"]
        assert "verificaciones" in section_text

    def test_untitled_french(self) -> None:
        """Untitled in French."""
        candidate = make_cop_candidate(what="")

        blocks = build_candidate_list_item_blocks(candidate, LanguageCode.FR)

        section_text = blocks[0]["text"]["text"]
        assert "Sans titre" in section_text

    def test_blocking_issues_spanish(self) -> None:
        """Blocking issues indicator in Spanish."""
        blocking_issues = [
            BlockingIssue(
                issue_type="conflict",
                description="Data conflict",
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            ),
        ]
        candidate = make_cop_candidate(blocking_issues=blocking_issues)

        blocks = build_candidate_list_item_blocks(candidate, LanguageCode.ES)

        assert len(blocks) == 2
        context_text = blocks[1]["elements"][0]["text"]
        assert "problema(s) bloqueante(s)" in context_text


# ============================================================================
# Language Fallback Tests
# ============================================================================


@pytest.mark.unit
class TestLanguageFallback:
    """Test language fallback behavior."""

    def test_invalid_language_falls_back_to_english(self) -> None:
        """Invalid language code falls back to English."""
        candidate = make_cop_candidate()
        field_evaluations = []

        # Use an invalid language code
        blocks = build_fields_checklist_blocks(candidate, field_evaluations, "de")

        # Should fall back to English
        assert blocks[0]["type"] == "header"
        assert "Field Completeness Checklist" in blocks[0]["text"]["text"]

    def test_backwards_compatibility_no_language_param(self) -> None:
        """Functions work without language parameter (default to English)."""
        candidate = make_cop_candidate()
        field_evaluations = [
            make_field_evaluation("what", FieldStatus.COMPLETE, "Test"),
        ]

        # Call without language parameter
        blocks = build_fields_checklist_blocks(candidate, field_evaluations)

        # Should default to English
        assert blocks[0]["type"] == "header"
        assert "Field Completeness Checklist" in blocks[0]["text"]["text"]
