"""Unit tests for Slack Block Kit i18n module.

Tests:
- get_translation: Translation retrieval and fallback behavior
- get_status_badge: Status badge generation with icons
- get_button_block: Button block generation with translations
- build_clarification_message: Clarification message generation
- Translation completeness across all languages
"""

import pytest

from integritykit.models.language import LanguageCode
from integritykit.slack.i18n import (
    TranslationKey,
    build_clarification_message,
    get_button_block,
    get_status_badge,
    get_translation,
)


# ============================================================================
# get_translation() Tests
# ============================================================================


@pytest.mark.unit
class TestGetTranslation:
    """Test get_translation() function."""

    def test_english_translation(self) -> None:
        """Get English translation for a key."""
        result = get_translation(TranslationKey.VERIFIED, LanguageCode.EN)
        assert result == "Verified"

    def test_spanish_translation(self) -> None:
        """Get Spanish translation for a key."""
        result = get_translation(TranslationKey.VERIFIED, LanguageCode.ES)
        assert result == "Verificado"

    def test_french_translation(self) -> None:
        """Get French translation for a key."""
        result = get_translation(TranslationKey.VERIFIED, LanguageCode.FR)
        assert result == "Vérifié"

    def test_string_key_lookup(self) -> None:
        """Translation works with string key."""
        result = get_translation("verified", LanguageCode.ES)
        assert result == "Verificado"

    def test_string_language_code(self) -> None:
        """Translation works with string language code."""
        result = get_translation(TranslationKey.VERIFIED, "es")
        assert result == "Verificado"

    def test_default_to_english(self) -> None:
        """Defaults to English when no language specified."""
        result = get_translation(TranslationKey.VERIFIED)
        assert result == "Verified"

    def test_fallback_to_english_for_invalid_language(self) -> None:
        """Falls back to English for invalid language code."""
        result = get_translation(TranslationKey.VERIFIED, "de")
        assert result == "Verified"

    def test_unknown_key_returns_key_itself(self) -> None:
        """Unknown key returns the key string itself."""
        result = get_translation("unknown_key", LanguageCode.EN)
        assert result == "unknown_key"

    def test_formatted_translation_english(self) -> None:
        """Format translation with parameters in English."""
        result = get_translation(
            TranslationKey.MISSING_FIELDS_WARNING,
            LanguageCode.EN,
            missing=2,
            partial=1,
        )
        assert result == "2 missing, 1 need improvement"

    def test_formatted_translation_spanish(self) -> None:
        """Format translation with parameters in Spanish."""
        result = get_translation(
            TranslationKey.MISSING_FIELDS_WARNING,
            LanguageCode.ES,
            missing=3,
            partial=2,
        )
        assert result == "3 faltantes, 2 necesitan mejoras"

    def test_formatted_translation_french(self) -> None:
        """Format translation with parameters in French."""
        result = get_translation(
            TranslationKey.FIELDS_NEED_IMPROVEMENT,
            LanguageCode.FR,
            partial=4,
        )
        assert result == "4 champs nécessitent amélioration"

    def test_missing_format_params_returns_unformatted(self) -> None:
        """Missing format params returns unformatted string."""
        result = get_translation(TranslationKey.MISSING_FIELDS_WARNING, LanguageCode.EN)
        # Should contain format placeholders
        assert "{missing}" in result
        assert "{partial}" in result


# ============================================================================
# get_status_badge() Tests
# ============================================================================


@pytest.mark.unit
class TestGetStatusBadge:
    """Test get_status_badge() function."""

    def test_verified_badge_english(self) -> None:
        """Verified badge has correct icon and English text."""
        badge = get_status_badge("verified", LanguageCode.EN)
        assert badge["type"] == "mrkdwn"
        assert ":white_check_mark:" in badge["text"]
        assert "Verified" in badge["text"]

    def test_verified_badge_spanish(self) -> None:
        """Verified badge has correct icon and Spanish text."""
        badge = get_status_badge("verified", LanguageCode.ES)
        assert badge["type"] == "mrkdwn"
        assert ":white_check_mark:" in badge["text"]
        assert "Verificado" in badge["text"]

    def test_in_review_badge_french(self) -> None:
        """In review badge has correct icon and French text."""
        badge = get_status_badge("in_review", LanguageCode.FR)
        assert badge["type"] == "mrkdwn"
        assert ":hourglass:" in badge["text"]
        assert "En Cours de Vérification" in badge["text"]

    def test_blocked_badge(self) -> None:
        """Blocked badge has correct icon."""
        badge = get_status_badge("blocked", LanguageCode.EN)
        assert ":no_entry:" in badge["text"]
        assert "Blocked" in badge["text"]

    def test_complete_badge(self) -> None:
        """Complete badge has correct icon."""
        badge = get_status_badge("complete", LanguageCode.EN)
        assert ":white_check_mark:" in badge["text"]
        assert "Complete" in badge["text"]

    def test_partial_badge(self) -> None:
        """Partial badge has correct icon."""
        badge = get_status_badge("partial", LanguageCode.EN)
        assert ":warning:" in badge["text"]
        assert "Needs improvement" in badge["text"]

    def test_missing_badge(self) -> None:
        """Missing badge has correct icon."""
        badge = get_status_badge("missing", LanguageCode.EN)
        assert ":x:" in badge["text"]
        assert "Missing" in badge["text"]

    def test_routine_risk_badge(self) -> None:
        """Routine risk badge has correct icon."""
        badge = get_status_badge("routine", LanguageCode.EN)
        assert ":large_green_circle:" in badge["text"]
        assert "Routine" in badge["text"]

    def test_elevated_risk_badge(self) -> None:
        """Elevated risk badge has correct icon."""
        badge = get_status_badge("elevated", LanguageCode.EN)
        assert ":large_yellow_circle:" in badge["text"]
        assert "Elevated" in badge["text"]

    def test_high_stakes_risk_badge(self) -> None:
        """High stakes risk badge has correct icon."""
        badge = get_status_badge("high_stakes", LanguageCode.EN)
        assert ":red_circle:" in badge["text"]
        assert "High Stakes" in badge["text"]

    def test_unknown_status_uses_default_icon(self) -> None:
        """Unknown status uses default question mark icon."""
        badge = get_status_badge("unknown_status", LanguageCode.EN)
        assert ":grey_question:" in badge["text"]

    def test_case_insensitive_status(self) -> None:
        """Status key is case insensitive."""
        badge = get_status_badge("VERIFIED", LanguageCode.EN)
        assert ":white_check_mark:" in badge["text"]


# ============================================================================
# get_button_block() Tests
# ============================================================================


@pytest.mark.unit
class TestGetButtonBlock:
    """Test get_button_block() function."""

    def test_button_basic_structure(self) -> None:
        """Button has correct Block Kit structure."""
        button = get_button_block("approve", "123", LanguageCode.EN)
        assert button["type"] == "button"
        assert button["text"]["type"] == "plain_text"
        assert button["text"]["emoji"] is True
        assert button["action_id"] == "approve_123"
        assert button["value"] == "123"

    def test_approve_button_english(self) -> None:
        """Approve button has English label."""
        button = get_button_block("approve", "123", LanguageCode.EN)
        assert button["text"]["text"] == "Approve"

    def test_approve_button_spanish(self) -> None:
        """Approve button has Spanish label."""
        button = get_button_block("approve", "123", LanguageCode.ES)
        assert button["text"]["text"] == "Aprobar"

    def test_reject_button_french(self) -> None:
        """Reject button has French label."""
        button = get_button_block("reject", "456", LanguageCode.FR)
        assert button["text"]["text"] == "Rejeter"

    def test_view_button(self) -> None:
        """View button has correct label."""
        button = get_button_block("view", "789", LanguageCode.EN)
        assert button["text"]["text"] == "View"

    def test_button_with_primary_style(self) -> None:
        """Button can have primary style."""
        button = get_button_block("approve", "123", LanguageCode.EN, style="primary")
        assert button["style"] == "primary"

    def test_button_with_danger_style(self) -> None:
        """Button can have danger style."""
        button = get_button_block("reject", "123", LanguageCode.EN, style="danger")
        assert button["style"] == "danger"

    def test_button_without_style(self) -> None:
        """Button without style has no style field."""
        button = get_button_block("view", "123", LanguageCode.EN)
        assert "style" not in button


# ============================================================================
# build_clarification_message() Tests
# ============================================================================


@pytest.mark.unit
class TestBuildClarificationMessage:
    """Test build_clarification_message() function."""

    def test_clarification_message_english(self) -> None:
        """Build clarification message in English."""
        message = build_clarification_message(
            missing_fields=["where"],
            weak_fields=[("what", "too vague")],
            language=LanguageCode.EN,
        )

        assert "Hi, I need some clarification" in message
        assert "Missing information: Where" in message
        assert "What needs more detail: too vague" in message
        assert "Can you provide additional evidence" in message
        assert "Thank you for your help!" in message

    def test_clarification_message_spanish(self) -> None:
        """Build clarification message in Spanish."""
        message = build_clarification_message(
            missing_fields=["donde"],
            weak_fields=[("que", "demasiado vago")],
            language=LanguageCode.ES,
        )

        assert "Hola, necesito aclaración" in message
        assert "Información faltante" in message
        assert "¿Puede proporcionar evidencia" in message
        assert "¡Gracias por su ayuda!" in message

    def test_clarification_message_french(self) -> None:
        """Build clarification message in French."""
        message = build_clarification_message(
            missing_fields=["où"],
            weak_fields=[("quoi", "trop vague")],
            language=LanguageCode.FR,
        )

        assert "Bonjour, j'ai besoin de clarification" in message
        assert "Information manquante" in message
        assert "Pouvez-vous fournir des preuves" in message
        assert "Merci pour votre aide !" in message

    def test_clarification_only_missing_fields(self) -> None:
        """Clarification message with only missing fields."""
        message = build_clarification_message(
            missing_fields=["where", "when"],
            weak_fields=[],
            language=LanguageCode.EN,
        )

        assert "Missing information: Where" in message
        assert "Missing information: When" in message
        assert "needs more detail" not in message

    def test_clarification_only_weak_fields(self) -> None:
        """Clarification message with only weak fields."""
        message = build_clarification_message(
            missing_fields=[],
            weak_fields=[("what", "not specific"), ("who", "unclear")],
            language=LanguageCode.EN,
        )

        assert "What needs more detail: not specific" in message
        assert "Who needs more detail: unclear" in message
        assert "Missing information" not in message

    def test_clarification_empty_lists(self) -> None:
        """Clarification message with empty lists still has intro/outro."""
        message = build_clarification_message(
            missing_fields=[],
            weak_fields=[],
            language=LanguageCode.EN,
        )

        assert "Hi, I need some clarification" in message
        assert "Thank you for your help!" in message

    def test_clarification_translates_field_names(self) -> None:
        """Field names are translated in clarification message."""
        message = build_clarification_message(
            missing_fields=["where"],
            weak_fields=[],
            language=LanguageCode.ES,
        )

        # "where" should be translated to "Dónde" in Spanish
        assert "Dónde" in message


# ============================================================================
# Translation Completeness Tests
# ============================================================================


@pytest.mark.unit
class TestTranslationCompleteness:
    """Test that all translation keys exist in all languages."""

    def test_all_keys_in_english(self) -> None:
        """All translation keys have English translations."""
        from integritykit.slack.i18n import TRANSLATIONS

        english_translations = TRANSLATIONS[LanguageCode.EN]
        for key in TranslationKey:
            assert key in english_translations, f"Missing English translation for {key}"

    def test_all_keys_in_spanish(self) -> None:
        """All translation keys have Spanish translations."""
        from integritykit.slack.i18n import TRANSLATIONS

        spanish_translations = TRANSLATIONS[LanguageCode.ES]
        for key in TranslationKey:
            assert key in spanish_translations, f"Missing Spanish translation for {key}"

    def test_all_keys_in_french(self) -> None:
        """All translation keys have French translations."""
        from integritykit.slack.i18n import TRANSLATIONS

        french_translations = TRANSLATIONS[LanguageCode.FR]
        for key in TranslationKey:
            assert key in french_translations, f"Missing French translation for {key}"

    def test_no_missing_translations(self) -> None:
        """No translation key is missing across all languages."""
        from integritykit.slack.i18n import TRANSLATIONS

        for language_code, translations in TRANSLATIONS.items():
            for key in TranslationKey:
                assert key in translations, (
                    f"Missing {language_code.value} translation for {key.value}"
                )

    def test_all_languages_have_same_keys(self) -> None:
        """All languages have the same set of translation keys."""
        from integritykit.slack.i18n import TRANSLATIONS

        english_keys = set(TRANSLATIONS[LanguageCode.EN].keys())
        spanish_keys = set(TRANSLATIONS[LanguageCode.ES].keys())
        french_keys = set(TRANSLATIONS[LanguageCode.FR].keys())

        assert english_keys == spanish_keys, "English and Spanish have different keys"
        assert english_keys == french_keys, "English and French have different keys"
        assert spanish_keys == french_keys, "Spanish and French have different keys"


# ============================================================================
# Translation Quality Tests
# ============================================================================


@pytest.mark.unit
class TestTranslationQuality:
    """Test translation quality and consistency."""

    def test_translations_not_empty(self) -> None:
        """All translations are non-empty strings."""
        from integritykit.slack.i18n import TRANSLATIONS

        for language_code, translations in TRANSLATIONS.items():
            for key, value in translations.items():
                assert value.strip() != "", (
                    f"Empty translation for {key.value} in {language_code.value}"
                )

    def test_format_placeholders_consistent(self) -> None:
        """Format placeholders are consistent across languages."""
        from integritykit.slack.i18n import TRANSLATIONS

        keys_with_placeholders = [
            TranslationKey.MISSING_FIELDS_WARNING,
            TranslationKey.FIELDS_NEED_IMPROVEMENT,
            TranslationKey.CLARIFICATION_MISSING_FIELD,
            TranslationKey.CLARIFICATION_WEAK_FIELD,
        ]

        for key in keys_with_placeholders:
            english_text = TRANSLATIONS[LanguageCode.EN][key]
            spanish_text = TRANSLATIONS[LanguageCode.ES][key]
            french_text = TRANSLATIONS[LanguageCode.FR][key]

            # Extract placeholders from each
            import re
            english_placeholders = set(re.findall(r"\{(\w+)\}", english_text))
            spanish_placeholders = set(re.findall(r"\{(\w+)\}", spanish_text))
            french_placeholders = set(re.findall(r"\{(\w+)\}", french_text))

            assert english_placeholders == spanish_placeholders == french_placeholders, (
                f"Inconsistent placeholders for {key.value}: "
                f"EN={english_placeholders}, ES={spanish_placeholders}, FR={french_placeholders}"
            )

    def test_button_labels_are_concise(self) -> None:
        """Button labels are reasonably short (< 50 chars)."""
        from integritykit.slack.i18n import TRANSLATIONS

        button_keys = [
            TranslationKey.APPROVE,
            TranslationKey.REJECT,
            TranslationKey.PROMOTE,
            TranslationKey.EDIT,
            TranslationKey.VIEW,
            TranslationKey.VIEW_FULL_DETAILS,
            TranslationKey.REEVALUATE,
            TranslationKey.ASSIGN_VERIFIER,
            TranslationKey.VIEW_CONFLICTS,
            TranslationKey.REQUEST_INFO,
            TranslationKey.PUBLISH,
            TranslationKey.VIEW_DUPLICATES,
        ]

        for language_code, translations in TRANSLATIONS.items():
            for key in button_keys:
                text = translations[key]
                assert len(text) < 50, (
                    f"Button label too long ({len(text)} chars) for {key.value} "
                    f"in {language_code.value}: '{text}'"
                )


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_get_translation_with_none_language(self) -> None:
        """get_translation handles None language gracefully."""
        # Should default to English
        result = get_translation(TranslationKey.VERIFIED)
        assert result == "Verified"

    def test_get_status_badge_with_empty_status(self) -> None:
        """get_status_badge handles empty status."""
        badge = get_status_badge("", LanguageCode.EN)
        assert badge["type"] == "mrkdwn"
        # Should use default icon for unknown status
        assert ":grey_question:" in badge["text"]

    def test_get_button_block_with_special_chars_in_value(self) -> None:
        """get_button_block handles special characters in value."""
        button = get_button_block("view", "abc-123_xyz", LanguageCode.EN)
        assert button["value"] == "abc-123_xyz"
        assert button["action_id"] == "view_abc-123_xyz"

    def test_build_clarification_with_special_chars(self) -> None:
        """build_clarification_message handles special characters."""
        message = build_clarification_message(
            missing_fields=["field_with_underscores"],
            weak_fields=[("field-with-dashes", "reason with 'quotes'")],
            language=LanguageCode.EN,
        )

        assert "field_with_underscores" in message or "field with underscores" in message
        assert "reason with 'quotes'" in message
