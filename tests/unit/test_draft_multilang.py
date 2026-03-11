"""
Unit tests for multi-language COP draft generation (S8-4).

Tests:
- S8-4: Generate COP drafts in Spanish and French
- Multi-language wording guidance (hedged vs direct phrasing)
- Locale-specific date/time formatting
"""

from datetime import datetime, timezone

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ExternalSource,
    ReadinessState,
    RiskTier,
    SlackPermalink,
)
from integritykit.services.draft import (
    COPDraft,
    COPLineItem,
    COPSection,
    DraftService,
    WordingStyle,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candidate(
    *,
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    what: str = "Bridge closure on Main Street",
    where: str = "123 Main St, Springfield, IL",
    when_desc: str = "As of 2pm today",
    who: str = "City Public Works Department",
    so_what: str = "Traffic rerouted via Oak Avenue",
) -> COPCandidate:
    """Create a COPCandidate for testing."""
    slack_permalinks = [
        SlackPermalink(
            url="https://workspace.slack.com/archives/C123/p1000000",
            signal_id=ObjectId(),
            description="Source message",
        )
    ]

    evidence = Evidence(
        slack_permalinks=slack_permalinks,
        external_sources=[],
    )

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
                description=when_desc,
            ),
            who=who,
            so_what=so_what,
        ),
        evidence=evidence,
        verifications=[],
    )


# ============================================================================
# Multi-Language Draft Generation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_generate_draft_spanish():
    """Test draft generation in Spanish (S8-4)."""
    service = DraftService(use_llm=False, default_language="es")

    candidate = make_candidate(
        readiness_state=ReadinessState.VERIFIED,
        what="El puente de la Calle Principal está cerrado",
    )

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate],
        target_language="es",
    )

    # Verify Spanish language in metadata
    assert draft.metadata["language"] == "es"

    # Verify Spanish title
    assert "Actualización de PCO" in draft.title or "PCO" in draft.title

    # Verify status label is in Spanish
    assert len(draft.verified_items) == 1
    assert draft.verified_items[0].status_label == "VERIFICADO"


@pytest.mark.asyncio
async def test_generate_draft_french():
    """Test draft generation in French (S8-4)."""
    service = DraftService(use_llm=False, default_language="fr")

    candidate = make_candidate(
        readiness_state=ReadinessState.VERIFIED,
        what="Le pont de Main Street est fermé",
    )

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate],
        target_language="fr",
    )

    # Verify French language in metadata
    assert draft.metadata["language"] == "fr"

    # Verify French title
    assert "Mise à jour PCO" in draft.title or "PCO" in draft.title

    # Verify status label is in French
    assert len(draft.verified_items) == 1
    assert draft.verified_items[0].status_label == "VÉRIFIÉ"


@pytest.mark.asyncio
async def test_generate_draft_english_default():
    """Test draft generation defaults to English."""
    service = DraftService(use_llm=False)

    candidate = make_candidate(readiness_state=ReadinessState.VERIFIED)

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate],
    )

    # Verify English is default
    assert draft.metadata["language"] == "en"
    assert "COP Update" in draft.title
    assert draft.verified_items[0].status_label == "VERIFIED"


@pytest.mark.asyncio
async def test_spanish_hedged_wording():
    """Test Spanish hedged wording for in-review items."""
    service = DraftService(use_llm=False, default_language="es")

    candidate = make_candidate(
        readiness_state=ReadinessState.IN_REVIEW,
        what="El refugio está abierto",
    )

    line_item = await service.generate_line_item(candidate, target_language="es")

    # Should use hedged Spanish phrasing
    assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN
    assert line_item.status_label == "EN REVISIÓN"

    # Text should contain Spanish hedging phrases
    text_lower = line_item.line_item_text.lower()
    # Should contain one of the Spanish hedging indicators
    spanish_hedges = ["sin confirmar", "se reporta", "estaría", "serían"]
    assert any(hedge in text_lower for hedge in spanish_hedges)


@pytest.mark.asyncio
async def test_french_hedged_wording():
    """Test French hedged wording for in-review items."""
    service = DraftService(use_llm=False, default_language="fr")

    candidate = make_candidate(
        readiness_state=ReadinessState.IN_REVIEW,
        what="L'abri est ouvert",
    )

    line_item = await service.generate_line_item(candidate, target_language="fr")

    # Should use hedged French phrasing
    assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN
    assert line_item.status_label == "EN RÉVISION"

    # Text should contain French hedging phrases
    text_lower = line_item.line_item_text.lower()
    french_hedges = ["non confirmé", "il est rapporté", "serait", "seraient"]
    assert any(hedge in text_lower for hedge in french_hedges)


@pytest.mark.asyncio
async def test_spanish_high_stakes_next_step():
    """Test Spanish next steps for high-stakes items."""
    service = DraftService(use_llm=False, default_language="es")

    candidate = make_candidate(
        readiness_state=ReadinessState.IN_REVIEW,
        risk_tier=RiskTier.HIGH_STAKES,
        who="",  # Missing source triggers specific message
    )

    line_item = await service.generate_line_item(candidate, target_language="es")

    # Should have Spanish next step
    assert line_item.next_verification_step is not None
    assert "URGENTE" in line_item.next_verification_step

    # Should have Spanish recheck time
    assert line_item.recheck_time is not None
    assert "Dentro de" in line_item.recheck_time or "minutos" in line_item.recheck_time


@pytest.mark.asyncio
async def test_french_elevated_next_step():
    """Test French next steps for elevated risk items."""
    service = DraftService(use_llm=False, default_language="fr")

    candidate = make_candidate(
        readiness_state=ReadinessState.IN_REVIEW,
        risk_tier=RiskTier.ELEVATED,
        where="",  # Missing location triggers specific message
    )

    line_item = await service.generate_line_item(candidate, target_language="fr")

    # Should have French next step
    assert line_item.next_verification_step is not None
    assert "Confirmer" in line_item.next_verification_step or "emplacement" in line_item.next_verification_step

    # Should have French recheck time
    assert line_item.recheck_time is not None
    assert "Dans les" in line_item.recheck_time or "heures" in line_item.recheck_time


# ============================================================================
# Markdown Localization Tests
# ============================================================================


@pytest.mark.asyncio
async def test_markdown_spanish_headers():
    """Test Spanish section headers in markdown output."""
    service = DraftService(use_llm=False, default_language="es")

    candidate_verified = make_candidate(readiness_state=ReadinessState.VERIFIED)
    candidate_review = make_candidate(readiness_state=ReadinessState.IN_REVIEW)

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate_verified, candidate_review],
        target_language="es",
    )

    markdown = draft.to_markdown(language="es")

    # Check for Spanish section headers
    assert "Actualizaciones Verificadas" in markdown
    assert "En Revisión (Sin Confirmar)" in markdown
    assert "Generado:" in markdown


@pytest.mark.asyncio
async def test_markdown_french_headers():
    """Test French section headers in markdown output."""
    service = DraftService(use_llm=False, default_language="fr")

    candidate_verified = make_candidate(readiness_state=ReadinessState.VERIFIED)
    candidate_review = make_candidate(readiness_state=ReadinessState.IN_REVIEW)

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate_verified, candidate_review],
        target_language="fr",
    )

    markdown = draft.to_markdown(language="fr")

    # Check for French section headers
    assert "Mises à jour Vérifiées" in markdown
    assert "En Révision (Non Confirmé)" in markdown
    assert "Généré:" in markdown


@pytest.mark.asyncio
async def test_markdown_auto_detect_language():
    """Test markdown automatically detects language from metadata."""
    service = DraftService(use_llm=False, default_language="es")

    candidate = make_candidate(readiness_state=ReadinessState.VERIFIED)

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate],
        target_language="es",
    )

    # Don't pass language explicitly - should use metadata
    markdown = draft.to_markdown()

    # Should use Spanish headers from metadata
    assert "Actualizaciones Verificadas" in markdown or "Generado:" in markdown


# ============================================================================
# Language Fallback Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unsupported_language_fallback():
    """Test that unsupported languages fall back to English."""
    service = DraftService(use_llm=False, default_language="de")  # German not supported

    candidate = make_candidate(readiness_state=ReadinessState.VERIFIED)

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate],
        target_language="de",
    )

    # Should fall back to English
    assert draft.metadata["language"] == "de"  # Preserves requested language
    assert "COP Update" in draft.title or draft.verified_items[0].status_label == "VERIFIED"


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.asyncio
async def test_multilang_no_items_message():
    """Test that 'no items' message is localized."""
    service_es = DraftService(use_llm=False, default_language="es")
    service_fr = DraftService(use_llm=False, default_language="fr")

    # Spanish
    draft_es = await service_es.generate_draft(
        workspace_id="W123",
        candidates=[],
        target_language="es",
    )
    assert len(draft_es.open_questions) == 1
    assert "No hay elementos" in draft_es.open_questions[0] or "PCO" in draft_es.open_questions[0]

    # French
    draft_fr = await service_fr.generate_draft(
        workspace_id="W123",
        candidates=[],
        target_language="fr",
    )
    assert len(draft_fr.open_questions) == 1
    assert "Aucun élément" in draft_fr.open_questions[0] or "PCO" in draft_fr.open_questions[0]


@pytest.mark.asyncio
async def test_mixed_language_candidates():
    """Test that service handles candidates with mixed content languages."""
    service = DraftService(use_llm=False, default_language="es")

    # Create candidates with different content languages
    candidate_spanish = make_candidate(
        readiness_state=ReadinessState.VERIFIED,
        what="El puente está cerrado",
    )
    candidate_english = make_candidate(
        readiness_state=ReadinessState.VERIFIED,
        what="The shelter is open",
    )

    draft = await service.generate_draft(
        workspace_id="W123",
        candidates=[candidate_spanish, candidate_english],
        target_language="es",
    )

    # All status labels and headers should be in Spanish
    assert all(item.status_label == "VERIFICADO" for item in draft.verified_items)
    assert draft.metadata["language"] == "es"

    # Content should preserve original text
    texts = [item.line_item_text for item in draft.verified_items]
    assert any("puente" in text.lower() for text in texts)
    assert any("shelter" in text.lower() for text in texts)
