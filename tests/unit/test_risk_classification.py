"""Unit tests for risk classification and publish gate services.

Tests:
- FR-COP-RISK-001: Risk-tier classification
- FR-COP-GATE-001: Publish gates for high-stakes content
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from integritykit.models.cop_candidate import (
    COPCandidate,
    COPFields,
    COPWhen,
    Evidence,
    ReadinessState,
    RiskTier,
)
from integritykit.models.user import User, UserRole
from integritykit.services.risk_classification import (
    HIGH_STAKES_KEYWORDS,
    ELEVATED_KEYWORDS,
    PublishGateService,
    RiskClassificationService,
    RiskSignal,
)


# ============================================================================
# Test Fixtures
# ============================================================================


def make_candidate(
    headline: str = "Test situation",
    summary: str = "",
    readiness_state: ReadinessState = ReadinessState.IN_REVIEW,
    risk_tier: RiskTier = RiskTier.ROUTINE,
) -> COPCandidate:
    """Create a test candidate."""
    return COPCandidate(
        id=ObjectId(),
        cluster_id=ObjectId(),
        readiness_state=readiness_state,
        risk_tier=risk_tier,
        fields=COPFields(
            what=headline,
            summary=summary,
            where="Test Location",
            when=COPWhen(description="Today"),
        ),
        evidence=Evidence(),
        created_by=ObjectId(),
    )


def make_user(roles: list[UserRole] = None) -> User:
    """Create a test user."""
    return User(
        id=ObjectId(),
        slack_user_id="U123",
        slack_team_id="T123",
        roles=roles or [UserRole.FACILITATOR],
    )


def make_mock_audit_service():
    """Create a mock audit service."""
    service = MagicMock()
    service.log_risk_override = AsyncMock()
    return service


# ============================================================================
# Risk Signal Detection Tests (FR-COP-RISK-001)
# ============================================================================


@pytest.mark.unit
class TestRiskSignalDetection:
    """Test risk signal detection from content."""

    def test_detect_evacuation_keywords(self) -> None:
        """Detect evacuation-related high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Mandatory evacuation ordered for downtown area"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "evacuation" for s in classification.signals)

    def test_detect_shelter_keywords(self) -> None:
        """Detect shelter-related high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Emergency shelter opening at the community center"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "shelter" for s in classification.signals)

    def test_detect_hazard_keywords(self) -> None:
        """Detect hazard-related high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Gas leak reported on Main Street, hazardous conditions"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "hazard" for s in classification.signals)

    def test_detect_medical_keywords(self) -> None:
        """Detect medical emergency high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Hospital overwhelmed with mass casualty event"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "medical" for s in classification.signals)

    def test_detect_donation_keywords(self) -> None:
        """Detect donation/scam risk high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Please donate to this GoFundMe for victims"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "donation" for s in classification.signals)

    def test_detect_infrastructure_keywords(self) -> None:
        """Detect infrastructure high-stakes keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Dam failure imminent, water contaminated downstream"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.HIGH_STAKES
        assert any(s.signal_type.value == "infrastructure" for s in classification.signals)

    def test_detect_elevated_weather(self) -> None:
        """Detect weather-related elevated keywords."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Storm warning issued for the area"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.ELEVATED
        assert any(s.signal_type.value == "weather" for s in classification.signals)

    def test_routine_content_no_signals(self) -> None:
        """Routine content should have no risk signals."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Community meeting scheduled for tomorrow"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.ROUTINE
        assert len(classification.signals) == 0


# ============================================================================
# Risk Tier Classification Tests (FR-COP-RISK-001)
# ============================================================================


@pytest.mark.unit
class TestRiskTierClassification:
    """Test overall risk tier determination."""

    def test_high_stakes_takes_precedence(self) -> None:
        """High-stakes signals override elevated signals."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Evacuation order due to flooding in area"
        )

        classification = service.classify_candidate(candidate)

        # Evacuation is HIGH_STAKES, flooding is ELEVATED
        # HIGH_STAKES should win
        assert classification.final_tier == RiskTier.HIGH_STAKES

    def test_elevated_when_no_high_stakes(self) -> None:
        """Elevated tier when only elevated signals present."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Storm warning in effect, conditions worsening"
        )

        classification = service.classify_candidate(candidate)

        # Just weather = ELEVATED
        assert classification.final_tier == RiskTier.ELEVATED

    def test_routine_when_no_signals(self) -> None:
        """Routine tier when no risk signals detected."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Local business reopening after renovations"
        )

        classification = service.classify_candidate(candidate)

        assert classification.final_tier == RiskTier.ROUTINE

    def test_classification_includes_explanation(self) -> None:
        """Classification should include human-readable explanation."""
        service = RiskClassificationService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Mandatory evacuation ordered for coastal areas"
        )

        classification = service.classify_candidate(candidate)

        assert classification.explanation is not None
        assert len(classification.explanation) > 0


# ============================================================================
# Publish Gate Tests (FR-COP-GATE-001)
# ============================================================================


@pytest.mark.unit
class TestPublishGate:
    """Test publish gate enforcement for high-stakes content."""

    def test_verified_high_stakes_can_publish(self) -> None:
        """Verified high-stakes candidates can publish."""
        service = PublishGateService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Evacuation order",
            readiness_state=ReadinessState.VERIFIED,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        risk_service = RiskClassificationService(audit_service=make_mock_audit_service())
        classification = risk_service.classify_candidate(candidate)
        result = service.check_publish_gate(candidate, classification)

        assert result.allowed is True
        assert result.requires_override is False

    def test_unverified_high_stakes_blocked(self) -> None:
        """Unverified high-stakes candidates are blocked."""
        service = PublishGateService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Evacuation order",
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.HIGH_STAKES,
        )

        risk_service = RiskClassificationService(audit_service=make_mock_audit_service())
        classification = risk_service.classify_candidate(candidate)
        result = service.check_publish_gate(candidate, classification)

        assert result.allowed is False
        assert result.requires_override is True

    def test_routine_can_always_publish(self) -> None:
        """Routine candidates can publish regardless of verification."""
        service = PublishGateService(audit_service=make_mock_audit_service())
        candidate = make_candidate(
            headline="Community meeting",
            readiness_state=ReadinessState.IN_REVIEW,
            risk_tier=RiskTier.ROUTINE,
        )

        risk_service = RiskClassificationService(audit_service=make_mock_audit_service())
        classification = risk_service.classify_candidate(candidate)
        result = service.check_publish_gate(candidate, classification)

        assert result.allowed is True
        assert result.requires_override is False


# ============================================================================
# UNCONFIRMED Label Tests
# ============================================================================


@pytest.mark.unit
class TestUnconfirmedLabel:
    """Test UNCONFIRMED label application."""

    def test_unconfirmed_label_format(self) -> None:
        """Test UNCONFIRMED label format."""
        service = PublishGateService(audit_service=make_mock_audit_service())

        labeled = service.apply_unconfirmed_label("Bridge is closed")

        assert "UNCONFIRMED" in labeled
        assert "Bridge is closed" in labeled


# ============================================================================
# High-Stakes Keywords Tests
# ============================================================================


@pytest.mark.unit
class TestHighStakesKeywords:
    """Test that all expected keyword categories are defined."""

    def test_evacuation_keywords_defined(self) -> None:
        """Evacuation keywords should be defined."""
        assert "evacuation" in HIGH_STAKES_KEYWORDS
        assert "evacuate" in HIGH_STAKES_KEYWORDS["evacuation"]

    def test_shelter_keywords_defined(self) -> None:
        """Shelter keywords should be defined."""
        assert "shelter" in HIGH_STAKES_KEYWORDS
        assert "shelter closed" in HIGH_STAKES_KEYWORDS["shelter"]

    def test_hazard_keywords_defined(self) -> None:
        """Hazard keywords should be defined."""
        assert "hazard" in HIGH_STAKES_KEYWORDS
        assert "gas leak" in HIGH_STAKES_KEYWORDS["hazard"]

    def test_medical_keywords_defined(self) -> None:
        """Medical keywords should be defined."""
        assert "medical" in HIGH_STAKES_KEYWORDS
        assert "mass casualty" in HIGH_STAKES_KEYWORDS["medical"]

    def test_donation_keywords_defined(self) -> None:
        """Donation keywords should be defined."""
        assert "donation" in HIGH_STAKES_KEYWORDS
        assert "gofundme" in HIGH_STAKES_KEYWORDS["donation"]

    def test_infrastructure_keywords_defined(self) -> None:
        """Infrastructure keywords should be defined."""
        assert "infrastructure" in HIGH_STAKES_KEYWORDS
        assert "dam failure" in HIGH_STAKES_KEYWORDS["infrastructure"]


# ============================================================================
# Elevated Keywords Tests
# ============================================================================


@pytest.mark.unit
class TestElevatedKeywords:
    """Test that elevated keyword categories are defined."""

    def test_weather_keywords_defined(self) -> None:
        """Weather keywords should be defined."""
        assert "weather" in ELEVATED_KEYWORDS
        assert "storm warning" in ELEVATED_KEYWORDS["weather"]

    def test_resources_keywords_defined(self) -> None:
        """Resources keywords should be defined."""
        assert "resources" in ELEVATED_KEYWORDS
