#!/usr/bin/env python3
"""
Quick test script to verify multi-language prompt registry works correctly.

This script tests:
1. Loading prompts for all supported languages (en, es, fr)
2. Verifying prompt structure and content
3. Testing fallback to English for unsupported languages
4. Verifying caching functionality
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from integritykit.llm.prompts.registry import (
    clear_prompt_cache,
    get_prompts,
    get_supported_languages,
    is_language_supported,
)


def test_supported_languages():
    """Test getting list of supported languages."""
    print("\n=== Testing Supported Languages ===")
    languages = get_supported_languages()
    print(f"Supported languages: {languages}")
    assert len(languages) == 3, "Should have 3 supported languages"
    assert any(lang["code"] == "en" for lang in languages), "Should include English"
    assert any(lang["code"] == "es" for lang in languages), "Should include Spanish"
    assert any(lang["code"] == "fr" for lang in languages), "Should include French"
    print("✓ Supported languages test passed")


def test_language_support_check():
    """Test checking if languages are supported."""
    print("\n=== Testing Language Support Check ===")
    assert is_language_supported("en"), "English should be supported"
    assert is_language_supported("es"), "Spanish should be supported"
    assert is_language_supported("fr"), "French should be supported"
    assert is_language_supported("spanish"), "Extended code 'spanish' should work"
    assert not is_language_supported("de"), "German should not be supported"
    print("✓ Language support check passed")


def test_english_prompts():
    """Test loading English prompts."""
    print("\n=== Testing English Prompts ===")
    prompts = get_prompts("en")

    assert prompts.language_code == "en"
    assert prompts.language_name == "English"

    # Test clustering prompts
    assert "signal classifier" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT
    assert "CLUSTER" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT.upper()
    print(f"Clustering system prompt length: {len(prompts.clustering.CLUSTERING_SYSTEM_PROMPT)} chars")

    # Test COP draft generation prompts
    assert "COP draft" in prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT
    assert "VERIFIED" in prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT.upper()
    print(f"COP draft system prompt length: {len(prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT)} chars")

    # Test readiness evaluation prompts
    assert "readiness" in prompts.readiness_evaluation.READINESS_EVALUATION_SYSTEM_PROMPT.lower()
    print(f"Readiness system prompt length: {len(prompts.readiness_evaluation.READINESS_EVALUATION_SYSTEM_PROMPT)} chars")

    # Test wording guidance
    assert len(prompts.wording_guidance.HEDGED_PHRASES) > 0
    assert len(prompts.wording_guidance.DIRECT_PHRASES) > 0
    print(f"Hedged phrases: {prompts.wording_guidance.HEDGED_PHRASES[:2]}")
    print(f"Direct phrases: {prompts.wording_guidance.DIRECT_PHRASES[:2]}")

    print("✓ English prompts test passed")


def test_spanish_prompts():
    """Test loading Spanish prompts."""
    print("\n=== Testing Spanish Prompts ===")
    prompts = get_prompts("es")

    assert prompts.language_code == "es"
    assert prompts.language_name == "Español"

    # Test clustering prompts (should be in Spanish)
    assert "clasificador" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT.lower()
    assert "cluster" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT.lower()
    print(f"Clustering system prompt (Spanish) length: {len(prompts.clustering.CLUSTERING_SYSTEM_PROMPT)} chars")

    # Test COP draft generation prompts (should be in Spanish)
    assert "verificado" in prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT.lower()
    print(f"COP draft system prompt (Spanish) length: {len(prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT)} chars")

    # Test Spanish-specific wording guidance
    assert "Sin confirmar" in prompts.wording_guidance.HEDGED_PHRASES
    assert "Según informes no confirmados" in prompts.wording_guidance.HEDGED_PHRASES
    assert "Confirmado" in prompts.wording_guidance.DIRECT_PHRASES
    print(f"Spanish hedged phrases: {prompts.wording_guidance.HEDGED_PHRASES[:3]}")

    # Test Spanish verification verbs
    verbs = prompts.wording_guidance.VERIFICATION_VERBS
    assert verbs["verified"]["to_be"] == "está"
    assert verbs["in_review"]["to_be"] == "estaría"
    print(f"Spanish verb conjugations: {verbs['verified']}")

    print("✓ Spanish prompts test passed")


def test_french_prompts():
    """Test loading French prompts."""
    print("\n=== Testing French Prompts ===")
    prompts = get_prompts("fr")

    assert prompts.language_code == "fr"
    assert prompts.language_name == "Français"

    # Test clustering prompts (should be in French)
    assert "classificateur" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT.lower()
    assert "cluster" in prompts.clustering.CLUSTERING_SYSTEM_PROMPT.lower()
    print(f"Clustering system prompt (French) length: {len(prompts.clustering.CLUSTERING_SYSTEM_PROMPT)} chars")

    # Test COP draft generation prompts (should be in French)
    assert "vérifié" in prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT.lower()
    print(f"COP draft system prompt (French) length: {len(prompts.cop_draft_generation.COP_DRAFT_GENERATION_SYSTEM_PROMPT)} chars")

    # Test French-specific wording guidance
    assert "Non confirmé" in prompts.wording_guidance.HEDGED_PHRASES
    assert "Selon des rapports non confirmés" in prompts.wording_guidance.HEDGED_PHRASES
    assert "Confirmé" in prompts.wording_guidance.DIRECT_PHRASES
    print(f"French hedged phrases: {prompts.wording_guidance.HEDGED_PHRASES[:3]}")

    # Test French verification verbs
    verbs = prompts.wording_guidance.VERIFICATION_VERBS
    assert verbs["verified"]["to_be"] == "est"
    assert verbs["in_review"]["to_be"] == "serait"
    print(f"French verb conjugations: {verbs['verified']}")

    print("✓ French prompts test passed")


def test_fallback_to_english():
    """Test fallback to English for unsupported languages."""
    print("\n=== Testing Fallback to English ===")
    prompts = get_prompts("de")  # German not supported

    assert prompts.language_code == "en", "Should fallback to English"
    assert prompts.language_name == "English"
    print("✓ Fallback test passed")


def test_caching():
    """Test that prompt caching works."""
    print("\n=== Testing Prompt Caching ===")

    # Clear cache first
    clear_prompt_cache()

    # Load Spanish prompts twice
    prompts1 = get_prompts("es")
    prompts2 = get_prompts("es")

    # Should be the same object (cached)
    assert prompts1 is prompts2, "Should return cached object"
    print("✓ Caching test passed")


def test_prompt_formatting():
    """Test prompt formatting functions."""
    print("\n=== Testing Prompt Formatting ===")

    # Test English clustering prompt formatting
    en_prompts = get_prompts("en")
    formatted = en_prompts.clustering.format_clustering_prompt(
        signal_author="user123",
        signal_channel="crisis-response",
        signal_timestamp="2026-03-10T14:00:00Z",
        signal_content="Bridge is closed due to damage",
        signal_thread_context="",
        existing_clusters=[],
    )
    assert "user123" in formatted
    assert "Bridge is closed" in formatted
    print(f"English formatted prompt length: {len(formatted)} chars")

    # Test Spanish clustering prompt formatting
    es_prompts = get_prompts("es")
    formatted_es = es_prompts.clustering.format_clustering_prompt(
        signal_author="user123",
        signal_channel="respuesta-crisis",
        signal_timestamp="2026-03-10T14:00:00Z",
        signal_content="El puente está cerrado debido a daños",
        signal_thread_context="",
        existing_clusters=[],
    )
    assert "user123" in formatted_es
    assert "El puente" in formatted_es
    print(f"Spanish formatted prompt length: {len(formatted_es)} chars")

    print("✓ Prompt formatting test passed")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Multi-Language Prompt Registry")
    print("=" * 60)

    try:
        test_supported_languages()
        test_language_support_check()
        test_english_prompts()
        test_spanish_prompts()
        test_french_prompts()
        test_fallback_to_english()
        test_caching()
        test_prompt_formatting()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
