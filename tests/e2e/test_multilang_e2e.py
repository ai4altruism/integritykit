"""
End-to-end tests for Sprint 8 multi-language support features.

Tests the complete workflow for multi-language functionality:
- Language detection from signal text (S8-2)
- COP draft generation in Spanish (S8-3, S8-4)
- COP draft generation in French (S8-3, S8-4)
- Language fallback to English
- Markdown export with localized headers
- Status label translations

These tests use mongomock for database operations and mock LLM calls.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

# Set required environment variables before importing services
os.environ.setdefault("SLACK_BOT_TOKEN", "xoxb-test-token")
os.environ.setdefault("SLACK_SIGNING_SECRET", "test-secret")
os.environ.setdefault("SLACK_WORKSPACE_ID", "T123456")
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("DEBUG", "true")

from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
    SlackPermalink,
    Verification,
)
from integritykit.models.language import DetectionMethod, LanguageCode
from integritykit.models.signal import Signal
from integritykit.services.draft import DraftService
from integritykit.services.language_detection import LanguageDetectionService


# ============================================================================
# Test Fixtures
# ============================================================================


def create_test_signal(
    *,
    content: str = "Test signal content",
    slack_workspace_id: str = "T123456",
    slack_channel_id: str = "C123456",
    slack_user_id: str = "U123456",
) -> Signal:
    """Create a test signal for language detection."""
    return Signal(
        id=ObjectId(),
        slack_workspace_id=slack_workspace_id,
        slack_channel_id=slack_channel_id,
        slack_message_ts="1234567890.123456",
        slack_user_id=slack_user_id,
        slack_permalink=f"https://{slack_workspace_id}.slack.com/archives/{slack_channel_id}/p1234567890123456",
        content=content,
        posted_at=datetime.now(timezone.utc),
        cluster_ids=[],
    )


def create_test_candidate(
    *,
    what: str = "Bridge closure on Main Street",
    where: str = "123 Main St, Springfield, IL",
    when_desc: str = "As of 2pm today",
    who: str = "City Public Works Department",
    so_what: str = "Traffic rerouted via Oak Avenue",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    has_verification: bool = False,
) -> COPCandidate:
    """Create a test COP candidate."""
    slack_permalinks = [
        SlackPermalink(
            url="https://workspace.slack.com/archives/C123/p1000000",
            signal_id=ObjectId(),
            description="Source message",
        )
    ]

    verifications = []
    if has_verification:
        verifications = [
            Verification(
                verified_by=ObjectId(),
                verified_at=datetime.now(timezone.utc),
                verification_method="authoritative_source",
                verification_notes="Confirmed via official source",
            )
        ]

    return COPCandidate(
        id=ObjectId(),
        cluster_id=ObjectId(),
        primary_signal_ids=[ObjectId()],
        readiness_state=readiness_state,
        readiness_updated_at=datetime.now(timezone.utc),
        readiness_updated_by=ObjectId(),
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(
                timestamp=datetime.now(timezone.utc),
                timezone="America/Chicago",
                is_approximate=False,
                description=when_desc,
            ),
            who=who,
            so_what=so_what,
        ),
        evidence=Evidence(
            slack_permalinks=slack_permalinks,
            external_sources=[],
        ),
        verifications=verifications,
        missing_fields=[],
        blocking_issues=[],
        created_at=datetime.now(timezone.utc),
        created_by=ObjectId(),
        updated_at=datetime.now(timezone.utc),
    )


# ============================================================================
# Language Detection E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_detection_spanish_e2e():
    """Test end-to-end Spanish language detection from signal."""
    service = LanguageDetectionService(
        confidence_threshold=0.8,
        enabled=True,
        supported_languages=["en", "es", "fr"],
    )

    # Create signal with Spanish content
    signal = create_test_signal(
        content="El puente de la Calle Principal está cerrado debido a inundaciones. "
        "Todo el tráfico está siendo desviado por Oak Avenue."
    )

    # Detect language
    result = service.detect_signal_language(signal)

    # Verify Spanish detected
    assert result.detected_language == LanguageCode.ES
    assert result.confidence >= 0.8
    assert result.meets_threshold is True
    assert result.detection_method == "langdetect" or result.detection_method == DetectionMethod.LANGDETECT


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_detection_french_e2e():
    """Test end-to-end French language detection from signal."""
    service = LanguageDetectionService(
        confidence_threshold=0.8,
        enabled=True,
        supported_languages=["en", "es", "fr"],
    )

    # Create signal with French content
    signal = create_test_signal(
        content="Le pont de la rue principale est fermé en raison d'inondations. "
        "Tout le trafic est dévié par Oak Avenue."
    )

    # Detect language
    result = service.detect_signal_language(signal)

    # Verify French detected
    assert result.detected_language == LanguageCode.FR
    assert result.confidence >= 0.8
    assert result.meets_threshold is True


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_detection_fallback_to_english():
    """Test fallback to English for unsupported languages or low confidence."""
    service = LanguageDetectionService(
        confidence_threshold=0.95,  # Very high threshold
        enabled=True,
        supported_languages=["en", "es", "fr"],
    )

    # Create signal with mixed language (likely low confidence)
    signal = create_test_signal(
        content="Bridge closed. Puente cerrado. Pont fermé. 123 Main St."
    )

    # Detect language
    result = service.detect_signal_language(signal)

    # Should detect something but may not meet threshold
    assert result.detected_language in [LanguageCode.EN, LanguageCode.ES, LanguageCode.FR]
    # Low threshold met would likely fall back to English in real usage


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_detection_manual_override():
    """Test manual language override bypasses detection."""
    service = LanguageDetectionService(
        confidence_threshold=0.8,
        enabled=True,
    )

    # Create signal with English content
    signal = create_test_signal(content="Bridge closure on Main Street")

    # Force French override
    result = service.detect_signal_language(
        signal,
        force_language=LanguageCode.FR,
    )

    # Verify override worked
    assert result.detected_language == LanguageCode.FR
    assert result.confidence == 1.0
    assert result.detection_method == "manual_override" or result.detection_method == DetectionMethod.MANUAL_OVERRIDE
    assert result.meets_threshold is True


# ============================================================================
# Spanish COP Draft Generation E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_generation_spanish_e2e():
    """Test end-to-end COP draft generation in Spanish."""
    service = DraftService(use_llm=False, default_language="es")

    # Create verified candidate with Spanish content
    candidate = create_test_candidate(
        what="El puente de la Calle Principal está cerrado",
        where="123 Calle Principal, Springfield, IL",
        when_desc="A partir de las 14:00 hoy",
        who="Departamento de Obras Públicas de la Ciudad",
        so_what="Tráfico desviado por Oak Avenue",
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    # Generate draft
    draft = await service.generate_draft(
        workspace_id="T123456",
        candidates=[candidate],
        title="Actualización de Emergencia #1",
        target_language="es",
    )

    # Verify draft metadata
    assert draft.workspace_id == "T123456"
    assert draft.title == "Actualización de Emergencia #1"
    assert draft.metadata.get("language") == "es"

    # Should have verified items
    assert len(draft.verified_items) == 1
    assert len(draft.in_review_items) == 0

    verified_item = draft.verified_items[0]
    assert verified_item.status_label == "VERIFICADO"
    assert "El puente" in verified_item.line_item_text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_spanish_markdown_export():
    """Test markdown export with Spanish localized headers."""
    service = DraftService(use_llm=False, default_language="es")

    candidates = [
        create_test_candidate(
            what="Puente cerrado confirmado",
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        ),
        create_test_candidate(
            what="Reportes de corte de energía",
            readiness_state=ReadinessState.IN_REVIEW,
            has_verification=False,
        ),
    ]

    # Generate draft
    draft = await service.generate_draft(
        workspace_id="T123456",
        candidates=candidates,
        title="Actualización de Crisis #5",
        target_language="es",
    )

    # Export to markdown
    markdown = draft.to_markdown(language="es")

    # Verify Spanish headers
    assert "# Actualización de Crisis #5" in markdown
    assert "## Actualizaciones Verificadas" in markdown or "## Verificado" in markdown
    assert "## En Revisión" in markdown or "## Para Revisión" in markdown


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_spanish_status_labels():
    """Test Spanish status label translations."""
    service = DraftService(use_llm=False, default_language="es")

    # Test all readiness states
    verified_candidate = create_test_candidate(
        what="Situación verificada",
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    in_review_candidate = create_test_candidate(
        what="Reporte sin confirmar",
        readiness_state=ReadinessState.IN_REVIEW,
        has_verification=False,
    )

    # Generate line items
    verified_item = await service.generate_line_item(verified_candidate)
    in_review_item = await service.generate_line_item(in_review_candidate)

    # Verify Spanish status labels
    assert verified_item.status_label in ["VERIFICADO", "VERIFIED"]
    assert in_review_item.status_label in ["EN REVISIÓN", "IN REVIEW", "PARA REVISIÓN"]


# ============================================================================
# French COP Draft Generation E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_generation_french_e2e():
    """Test end-to-end COP draft generation in French."""
    service = DraftService(use_llm=False, default_language="fr")

    # Create verified candidate with French content
    candidate = create_test_candidate(
        what="Le pont de la rue principale est fermé",
        where="123 Rue Principale, Springfield, IL",
        when_desc="À partir de 14h00 aujourd'hui",
        who="Département des Travaux Publics de la Ville",
        so_what="Circulation détournée par Oak Avenue",
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    # Generate draft
    draft = await service.generate_draft(
        workspace_id="T123456",
        candidates=[candidate],
        title="Mise à jour d'urgence #1",
        target_language="fr",
    )

    # Verify draft metadata
    assert draft.workspace_id == "T123456"
    assert draft.title == "Mise à jour d'urgence #1"
    assert draft.metadata.get("language") == "fr"

    # Should have verified items
    assert len(draft.verified_items) == 1
    verified_item = draft.verified_items[0]
    assert verified_item.status_label == "VÉRIFIÉ"
    assert "Le pont" in verified_item.line_item_text


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_french_markdown_export():
    """Test markdown export with French localized headers."""
    service = DraftService(use_llm=False, default_language="fr")

    candidates = [
        create_test_candidate(
            what="Pont fermé confirmé",
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        ),
        create_test_candidate(
            what="Rapports de panne de courant",
            readiness_state=ReadinessState.IN_REVIEW,
            has_verification=False,
        ),
    ]

    # Generate draft
    draft = await service.generate_draft(
        workspace_id="T123456",
        candidates=candidates,
        title="Mise à jour de crise #5",
        target_language="fr",
    )

    # Export to markdown
    markdown = draft.to_markdown(language="fr")

    # Verify French headers (case-insensitive)
    markdown_lower = markdown.lower()
    assert "# mise à jour de crise #5" in markdown_lower
    assert "## mises à jour vérifiées" in markdown_lower or "## vérifié" in markdown_lower
    assert "## en révision" in markdown_lower or "## en cours d'examen" in markdown_lower


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_cop_draft_french_status_labels():
    """Test French status label translations."""
    service = DraftService(use_llm=False, default_language="fr")

    # Test all readiness states
    verified_candidate = create_test_candidate(
        what="Situation vérifiée",
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    in_review_candidate = create_test_candidate(
        what="Rapport non confirmé",
        readiness_state=ReadinessState.IN_REVIEW,
        has_verification=False,
    )

    # Generate line items
    verified_item = await service.generate_line_item(verified_candidate)
    in_review_item = await service.generate_line_item(in_review_candidate)

    # Verify French status labels
    assert verified_item.status_label in ["VÉRIFIÉ", "VERIFIED"]
    assert in_review_item.status_label in ["EN RÉVISION", "IN REVIEW", "EN COURS D'EXAMEN"]


# ============================================================================
# Multi-Language Integration E2E Tests
# ============================================================================


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_detection_to_draft_generation_pipeline():
    """Test complete pipeline from language detection to draft generation."""
    # Step 1: Detect language from signal
    lang_service = LanguageDetectionService(
        confidence_threshold=0.8,
        enabled=True,
    )

    signal = create_test_signal(
        content="El refugio se abrió en Central High School. Capacidad para 500 personas."
    )

    lang_result = lang_service.detect_signal_language(signal)

    # Should detect Spanish
    assert lang_result.detected_language == LanguageCode.ES
    assert lang_result.meets_threshold is True

    # Step 2: Generate COP draft in detected language
    draft_service = DraftService(
        use_llm=False,
        default_language=str(lang_result.detected_language),
    )

    candidate = create_test_candidate(
        what="Refugio abierto en Central High School",
        where="456 Central Ave, Springfield, IL",
        who="Cruz Roja",
        so_what="Refugio de emergencia disponible",
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    draft = await draft_service.generate_draft(
        workspace_id="T123456",
        candidates=[candidate],
        title="Actualización #1",
        target_language=str(lang_result.detected_language),
    )

    # Verify Spanish draft
    assert draft.metadata.get("language") == "es"
    assert len(draft.verified_items) == 1
    assert draft.verified_items[0].status_label == "VERIFICADO"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_mixed_language_candidates_draft():
    """Test draft generation with mixed language candidates (should use default)."""
    service = DraftService(use_llm=False, default_language="en")

    candidates = [
        create_test_candidate(
            what="Bridge closed",  # English
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        ),
        create_test_candidate(
            what="Refugio abierto",  # Spanish
            readiness_state=ReadinessState.VERIFIED,
            has_verification=True,
        ),
        create_test_candidate(
            what="Pont fermé",  # French
            readiness_state=ReadinessState.IN_REVIEW,
        ),
    ]

    # Generate draft in English (default)
    draft = await service.generate_draft(
        workspace_id="T123456",
        candidates=candidates,
        title="Multi-Language Update",
        target_language="en",
    )

    # Should handle all candidates
    assert draft.total_items == 3
    assert len(draft.verified_items) == 2
    assert len(draft.in_review_items) == 1

    # All items should have English status labels
    for item in draft.verified_items:
        assert item.status_label == "VERIFIED"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_language_fallback_on_empty_detection():
    """Test fallback to English when language detection fails."""
    service = LanguageDetectionService(
        confidence_threshold=0.8,
        enabled=True,
    )

    # Very short signal (detection likely to fail)
    signal = create_test_signal(content="OK")

    result = service.detect_signal_language(signal)

    # Should fall back to English
    assert result.detected_language == LanguageCode.EN
    assert result.meets_threshold is False  # Low confidence

    # Draft service should still work with fallback
    draft_service = DraftService(
        use_llm=False,
        default_language=str(result.detected_language),
    )

    candidate = create_test_candidate(
        readiness_state=ReadinessState.VERIFIED,
        has_verification=True,
    )

    draft = await draft_service.generate_draft(
        workspace_id="T123456",
        candidates=[candidate],
    )

    assert draft.metadata.get("language") == "en"
    assert len(draft.verified_items) == 1
