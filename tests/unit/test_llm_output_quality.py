"""Unit tests for LLM output quality evaluation with golden-set tests.

Tests:
- FR-COP-WORDING-001: Wording guidance (hedged vs direct phrasing)
- FR-COP-WORDING-002: High-stakes verification next steps
- FR-COPDRAFT-001: COP line item generation quality
"""

from datetime import datetime
from unittest.mock import MagicMock

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
    Verification,
    VerificationMethod,
)
from integritykit.services.draft import (
    DraftService,
    COPSection,
    WordingStyle,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candidate(
    what: str = "Test situation",
    where: str = "Test Location",
    when_desc: str = "Today",
    who: str = "",
    so_what: str = "",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
    verifications: list[Verification] = None,
    slack_permalinks: list[SlackPermalink] = None,
    external_sources: list[ExternalSource] = None,
) -> COPCandidate:
    """Create a test candidate with configurable fields."""
    return COPCandidate(
        id=ObjectId(),
        cluster_id=ObjectId(),
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        fields=COPFields(
            what=what,
            where=where,
            when=COPWhen(description=when_desc),
            who=who,
            so_what=so_what,
        ),
        evidence=Evidence(
            slack_permalinks=slack_permalinks or [],
            external_sources=external_sources or [],
        ),
        verifications=verifications or [],
        created_by=ObjectId(),
    )


# ============================================================================
# Golden Set Test Cases
# ============================================================================

# Golden set: Input candidates with expected output characteristics
GOLDEN_SET_VERIFIED = {
    "input": {
        "what": "Main Street Bridge is closed to all traffic",
        "where": "Downtown",
        "when_desc": "14:00 PST",
        "readiness_state": ReadinessState.VERIFIED,
        "risk_tier": RiskTier.ROUTINE,
    },
    "expected": {
        "status_label": "VERIFIED",
        "section": COPSection.VERIFIED,
        "wording_style": WordingStyle.DIRECT_FACTUAL,
        # Output should NOT contain hedging words
        "should_not_contain": ["Unconfirmed", "Reports indicate", "may be"],
        # Output SHOULD contain direct language
        "should_contain": ["closed to all traffic"],
    },
}

GOLDEN_SET_IN_REVIEW = {
    "input": {
        "what": "Highway 101 is flooded",
        "where": "Near Exit 45",
        "when_desc": "Morning",
        "readiness_state": ReadinessState.IN_REVIEW,
        "risk_tier": RiskTier.ROUTINE,
    },
    "expected": {
        "status_label": "IN REVIEW",
        "section": COPSection.IN_REVIEW,
        "wording_style": WordingStyle.HEDGED_UNCERTAIN,
        # Output SHOULD contain hedging language
        "should_contain": ["Unconfirmed"],
        # Should have risk-appropriate recheck time
        "recheck_time": "Within 4 hours",
    },
}

GOLDEN_SET_HIGH_STAKES = {
    "input": {
        "what": "Evacuation order issued for Zone A",
        "where": "Coastal District",
        "when_desc": "Immediately",
        "who": "",  # Missing source - should trigger specific next step
        "readiness_state": ReadinessState.IN_REVIEW,
        "risk_tier": RiskTier.HIGH_STAKES,
    },
    "expected": {
        "status_label": "IN REVIEW",
        "section": COPSection.IN_REVIEW,
        "wording_style": WordingStyle.HEDGED_UNCERTAIN,
        "recheck_time": "Within 30 minutes",
        # Should have URGENT next step since source is missing
        "next_step_contains": "URGENT",
    },
}

GOLDEN_SET_ELEVATED = {
    "input": {
        "what": "Road closure due to flooding",
        "where": "Main Street",
        "when_desc": "Ongoing",
        "readiness_state": ReadinessState.IN_REVIEW,
        "risk_tier": RiskTier.ELEVATED,
    },
    "expected": {
        "status_label": "IN REVIEW",
        "section": COPSection.IN_REVIEW,
        "wording_style": WordingStyle.HEDGED_UNCERTAIN,
        "recheck_time": "Within 2 hours",
    },
}


# ============================================================================
# Wording Quality Tests (FR-COP-WORDING-001)
# ============================================================================


@pytest.mark.unit
class TestWordingQualityVerified:
    """Test wording quality for VERIFIED items."""

    def test_verified_uses_direct_factual_style(self) -> None:
        """Verified items should use direct, factual wording."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_VERIFIED["input"])

        line_item = service._generate_rule_based(candidate)

        assert line_item.wording_style == WordingStyle.DIRECT_FACTUAL
        assert line_item.status_label == "VERIFIED"

    def test_verified_no_hedging_language(self) -> None:
        """Verified items should NOT contain hedging language."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_VERIFIED["input"])

        line_item = service._generate_rule_based(candidate)

        for phrase in GOLDEN_SET_VERIFIED["expected"]["should_not_contain"]:
            assert phrase.lower() not in line_item.line_item_text.lower(), (
                f"Verified text should not contain '{phrase}'"
            )

    def test_verified_preserves_factual_content(self) -> None:
        """Verified items should preserve the factual content."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_VERIFIED["input"])

        line_item = service._generate_rule_based(candidate)

        # Core fact should be preserved
        assert "closed" in line_item.line_item_text.lower()
        assert "traffic" in line_item.line_item_text.lower()


@pytest.mark.unit
class TestWordingQualityInReview:
    """Test wording quality for IN_REVIEW items."""

    def test_in_review_uses_hedged_style(self) -> None:
        """In-review items should use hedged, uncertain wording."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_IN_REVIEW["input"])

        line_item = service._generate_rule_based(candidate)

        assert line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN
        assert line_item.status_label == "IN REVIEW"

    def test_in_review_has_hedging_language(self) -> None:
        """In-review items SHOULD contain hedging language."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_IN_REVIEW["input"])

        line_item = service._generate_rule_based(candidate)

        has_hedging = any(
            phrase.lower() in line_item.line_item_text.lower()
            for phrase in GOLDEN_SET_IN_REVIEW["expected"]["should_contain"]
        )
        assert has_hedging, "In-review text should contain hedging language"

    def test_in_review_indicates_uncertainty(self) -> None:
        """In-review items should clearly indicate uncertainty."""
        service = DraftService()
        candidate = make_candidate(
            what="Bridge is closed",
            readiness_state=ReadinessState.IN_REVIEW,
        )

        line_item = service._generate_rule_based(candidate)

        # Should transform "is" to "may be" or add uncertainty marker
        text_lower = line_item.line_item_text.lower()
        has_uncertainty = (
            "unconfirmed" in text_lower
            or "may be" in text_lower
            or "reports indicate" in text_lower
        )
        assert has_uncertainty, f"Text should indicate uncertainty: {line_item.line_item_text}"


# ============================================================================
# Risk Tier Recheck Time Tests (FR-COP-WORDING-002)
# ============================================================================


@pytest.mark.unit
class TestRiskTierRecheckTimes:
    """Test recheck times are appropriate for risk tier."""

    def test_high_stakes_30_minute_recheck(self) -> None:
        """High-stakes items should have 30-minute recheck."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_HIGH_STAKES["input"])

        line_item = service._generate_rule_based(candidate)

        assert line_item.recheck_time == "Within 30 minutes"

    def test_elevated_2_hour_recheck(self) -> None:
        """Elevated items should have 2-hour recheck."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_ELEVATED["input"])

        line_item = service._generate_rule_based(candidate)

        assert line_item.recheck_time == "Within 2 hours"

    def test_routine_4_hour_recheck(self) -> None:
        """Routine items should have 4-hour recheck."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_IN_REVIEW["input"])

        line_item = service._generate_rule_based(candidate)

        assert line_item.recheck_time == "Within 4 hours"


# ============================================================================
# High-Stakes Next Step Tests (FR-COP-WORDING-002)
# ============================================================================


@pytest.mark.unit
class TestHighStakesNextSteps:
    """Test next verification step guidance for high-stakes items."""

    def test_high_stakes_no_source_urgent_step(self) -> None:
        """High-stakes without source should have URGENT identify step."""
        service = DraftService()
        candidate = make_candidate(
            what="Evacuation ordered",
            who="",  # Missing source
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        line_item = service._generate_rule_based(candidate)

        assert line_item.next_verification_step is not None
        assert "URGENT" in line_item.next_verification_step
        assert "source" in line_item.next_verification_step.lower()

    def test_high_stakes_no_verifications_assign_step(self) -> None:
        """High-stakes without verifications should assign verifier."""
        service = DraftService()
        candidate = make_candidate(
            what="Shelter closure",
            who="Red Cross",
            verifications=[],
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        line_item = service._generate_rule_based(candidate)

        assert line_item.next_verification_step is not None
        assert "URGENT" in line_item.next_verification_step
        assert "verif" in line_item.next_verification_step.lower()

    def test_high_stakes_has_source_and_verification(self) -> None:
        """High-stakes with source and verification should seek secondary confirmation."""
        service = DraftService()
        verification = Verification(
            verified_by=ObjectId(),
            verification_method=VerificationMethod.DIRECT_OBSERVATION,
        )
        candidate = make_candidate(
            what="Dam breach warning",
            who="County Emergency Management",
            verifications=[verification],
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        line_item = service._generate_rule_based(candidate)

        assert line_item.next_verification_step is not None
        # Should seek secondary confirmation
        assert "confirmation" in line_item.next_verification_step.lower() or \
               "secondary" in line_item.next_verification_step.lower()


# ============================================================================
# Citation Formatting Tests
# ============================================================================


@pytest.mark.unit
class TestCitationFormatting:
    """Test citation formatting in line items."""

    def test_citations_included_in_text(self) -> None:
        """Citations should be included in line item text."""
        service = DraftService()
        candidate = make_candidate(
            what="Road closed",
            slack_permalinks=[
                SlackPermalink(url="https://slack.com/archives/C123/p456"),
            ],
        )

        line_item = service._generate_rule_based(candidate)

        assert len(line_item.citations) == 1
        assert "[1]" in line_item.line_item_text

    def test_multiple_citations_numbered(self) -> None:
        """Multiple citations should be numbered."""
        service = DraftService()
        candidate = make_candidate(
            what="Road closed",
            slack_permalinks=[
                SlackPermalink(url="https://slack.com/archives/C123/p456"),
                SlackPermalink(url="https://slack.com/archives/C123/p789"),
            ],
            external_sources=[
                ExternalSource(url="https://news.example.com/article"),
            ],
        )

        line_item = service._generate_rule_based(candidate)

        assert len(line_item.citations) == 3
        assert "[1]" in line_item.line_item_text
        assert "[2]" in line_item.line_item_text
        assert "[3]" in line_item.line_item_text

    def test_no_citations_no_brackets(self) -> None:
        """Line items without citations should not have citation brackets."""
        service = DraftService()
        candidate = make_candidate(what="Road closed")

        line_item = service._generate_rule_based(candidate)

        assert len(line_item.citations) == 0
        assert "[" not in line_item.line_item_text


# ============================================================================
# Section Placement Tests
# ============================================================================


@pytest.mark.unit
class TestSectionPlacement:
    """Test correct section placement for line items."""

    def test_verified_in_verified_section(self) -> None:
        """Verified candidates go in verified section."""
        service = DraftService()
        candidate = make_candidate(readiness_state=ReadinessState.VERIFIED)

        line_item = service._generate_rule_based(candidate)

        assert line_item.section == COPSection.VERIFIED

    def test_in_review_in_in_review_section(self) -> None:
        """In-review candidates go in in-review section."""
        service = DraftService()
        candidate = make_candidate(readiness_state=ReadinessState.IN_REVIEW)

        line_item = service._generate_rule_based(candidate)

        assert line_item.section == COPSection.IN_REVIEW

    def test_blocked_in_open_questions_section(self) -> None:
        """Blocked candidates go in open questions section."""
        service = DraftService()
        candidate = make_candidate(readiness_state=ReadinessState.BLOCKED)

        line_item = service._generate_rule_based(candidate)

        assert line_item.section == COPSection.OPEN_QUESTIONS


# ============================================================================
# Location and Time Formatting Tests
# ============================================================================


@pytest.mark.unit
class TestLocationTimeFormatting:
    """Test location and time are properly formatted in output."""

    def test_location_and_time_included(self) -> None:
        """Location and time should be included when present."""
        service = DraftService()
        candidate = make_candidate(
            what="Road closed",
            where="Main Street",
            when_desc="14:00 PST",
            readiness_state=ReadinessState.VERIFIED,
        )

        line_item = service._generate_rule_based(candidate)

        assert "Main Street" in line_item.line_item_text
        assert "14:00 PST" in line_item.line_item_text

    def test_missing_location_graceful(self) -> None:
        """Missing location should not cause errors."""
        service = DraftService()
        candidate = make_candidate(
            what="Situation developing",
            where="",
            when_desc="Now",
        )

        line_item = service._generate_rule_based(candidate)

        assert "Now" in line_item.line_item_text
        assert line_item.line_item_text  # Should still generate text

    def test_missing_time_graceful(self) -> None:
        """Missing time should not cause errors."""
        service = DraftService()
        candidate = make_candidate(
            what="Situation developing",
            where="Downtown",
            when_desc="",
        )

        line_item = service._generate_rule_based(candidate)

        assert "Downtown" in line_item.line_item_text
        assert line_item.line_item_text


# ============================================================================
# Edge Cases Tests
# ============================================================================


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_what_field(self) -> None:
        """Empty what field should use default."""
        service = DraftService()
        candidate = make_candidate(what="")

        line_item = service._generate_rule_based(candidate)

        # Should use default "Situation developing"
        assert "developing" in line_item.line_item_text.lower()

    def test_very_long_content(self) -> None:
        """Very long content should be handled."""
        service = DraftService()
        long_text = "Situation " * 100
        candidate = make_candidate(what=long_text)

        line_item = service._generate_rule_based(candidate)

        assert line_item.line_item_text  # Should generate without error

    def test_special_characters_preserved(self) -> None:
        """Special characters should be preserved."""
        service = DraftService()
        candidate = make_candidate(
            what="Temperature is -5°F",
            readiness_state=ReadinessState.VERIFIED,
        )

        line_item = service._generate_rule_based(candidate)

        assert "-5" in line_item.line_item_text
        assert "°" in line_item.line_item_text or "F" in line_item.line_item_text

    def test_so_what_included_for_verified(self) -> None:
        """So-what (impact) should be included for verified items."""
        service = DraftService()
        candidate = make_candidate(
            what="Bridge closed",
            so_what="Use alternate route via Highway 99",
            readiness_state=ReadinessState.VERIFIED,
        )

        line_item = service._generate_rule_based(candidate)

        assert "Highway 99" in line_item.line_item_text

    def test_so_what_conditional_for_in_review(self) -> None:
        """So-what should have conditional wording for in-review items."""
        service = DraftService()
        candidate = make_candidate(
            what="Bridge closed",
            so_what="Use alternate route via Highway 99",
            readiness_state=ReadinessState.IN_REVIEW,
        )

        line_item = service._generate_rule_based(candidate)

        # Should include impact but with conditional wording
        text_lower = line_item.line_item_text.lower()
        assert "highway 99" in text_lower or "alternate" in text_lower
        # Should have conditional marker
        assert "if confirmed" in text_lower or "unconfirmed" in text_lower


# ============================================================================
# Golden Set Regression Tests
# ============================================================================


@pytest.mark.unit
class TestGoldenSetRegression:
    """Regression tests using golden set examples."""

    def test_golden_verified_example(self) -> None:
        """Test golden verified example produces expected output."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_VERIFIED["input"])

        line_item = service._generate_rule_based(candidate)

        expected = GOLDEN_SET_VERIFIED["expected"]
        assert line_item.status_label == expected["status_label"]
        assert line_item.section == expected["section"]
        assert line_item.wording_style == expected["wording_style"]

    def test_golden_in_review_example(self) -> None:
        """Test golden in-review example produces expected output."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_IN_REVIEW["input"])

        line_item = service._generate_rule_based(candidate)

        expected = GOLDEN_SET_IN_REVIEW["expected"]
        assert line_item.status_label == expected["status_label"]
        assert line_item.section == expected["section"]
        assert line_item.wording_style == expected["wording_style"]
        assert line_item.recheck_time == expected["recheck_time"]

    def test_golden_high_stakes_example(self) -> None:
        """Test golden high-stakes example produces expected output."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_HIGH_STAKES["input"])

        line_item = service._generate_rule_based(candidate)

        expected = GOLDEN_SET_HIGH_STAKES["expected"]
        assert line_item.status_label == expected["status_label"]
        assert line_item.section == expected["section"]
        assert line_item.wording_style == expected["wording_style"]
        assert line_item.recheck_time == expected["recheck_time"]
        assert expected["next_step_contains"] in line_item.next_verification_step

    def test_golden_elevated_example(self) -> None:
        """Test golden elevated example produces expected output."""
        service = DraftService()
        candidate = make_candidate(**GOLDEN_SET_ELEVATED["input"])

        line_item = service._generate_rule_based(candidate)

        expected = GOLDEN_SET_ELEVATED["expected"]
        assert line_item.status_label == expected["status_label"]
        assert line_item.section == expected["section"]
        assert line_item.wording_style == expected["wording_style"]
        assert line_item.recheck_time == expected["recheck_time"]
