"""Risk tier classification service for COP candidates.

Implements:
- FR-COP-RISK-001: Risk-tier classification with content signals and override
- FR-COP-GATE-001: High-stakes publish gates

Risk tiers:
- ROUTINE: Standard information updates
- ELEVATED: Time-sensitive or impactful but not life-safety
- HIGH_STAKES: Life-safety, evacuation, medical, shelter, hazards
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.cop_candidate import COPCandidate, RiskTier, RiskTierOverride
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service

logger = structlog.get_logger(__name__)


# ============================================================================
# High-Stakes Keywords (FR-COP-RISK-001)
# ============================================================================

# Keywords that trigger HIGH_STAKES classification
HIGH_STAKES_KEYWORDS = {
    # Evacuation
    "evacuation": ["evacuate", "evacuation", "evacuating", "mandatory evacuation",
                   "shelter in place", "leave immediately", "get out now"],

    # Shelter operations
    "shelter": ["shelter closed", "shelter closing", "shelter full", "shelter capacity",
                "shelter opening", "emergency shelter", "warming center", "cooling center"],

    # Hazards
    "hazard": ["hazardous", "hazmat", "gas leak", "chemical spill", "toxic",
               "explosion", "fire spreading", "structural collapse", "building collapse",
               "live wires", "downed power lines", "flood waters rising"],

    # Medical
    "medical": ["mass casualty", "fatality", "fatalities", "death", "deaths",
                "hospital overwhelmed", "medical emergency", "triage", "ems delayed",
                "ambulance unavailable", "critical condition"],

    # Donations/Resources (potential for fraud)
    "donation": ["donate", "donation", "gofundme", "venmo", "cashapp", "paypal",
                 "send money", "wire transfer", "financial assistance"],

    # Infrastructure critical
    "infrastructure": ["dam failure", "dam breach", "levee breach", "bridge collapse",
                       "road closed", "highway closed", "water contaminated",
                       "boil water", "power grid", "blackout"],
}

# Keywords that trigger ELEVATED classification
ELEVATED_KEYWORDS = {
    # Time-sensitive
    "time_sensitive": ["urgent", "immediately", "asap", "critical", "emergency",
                       "breaking", "just now", "happening now", "developing"],

    # Resource status
    "resources": ["running low", "almost out", "limited supply", "need volunteers",
                  "need supplies", "shortage", "rationing"],

    # Access changes
    "access": ["road blocked", "detour", "alternate route", "restricted access",
               "checkpoint", "curfew", "closed until"],

    # Weather escalation
    "weather": ["storm warning", "tornado watch", "flash flood", "severe weather",
                "conditions worsening", "expected to intensify"],
}


class RiskSignalType(str, Enum):
    """Types of risk signals detected in content."""

    EVACUATION = "evacuation"
    SHELTER = "shelter"
    HAZARD = "hazard"
    MEDICAL = "medical"
    DONATION = "donation"
    INFRASTRUCTURE = "infrastructure"
    TIME_SENSITIVE = "time_sensitive"
    RESOURCES = "resources"
    ACCESS = "access"
    WEATHER = "weather"


@dataclass
class RiskSignal:
    """A detected risk signal in content."""

    signal_type: RiskSignalType
    keyword_matched: str
    context: str  # Surrounding text
    severity: RiskTier


@dataclass
class RiskClassification:
    """Result of risk classification for a COP candidate."""

    candidate_id: str
    computed_tier: RiskTier
    final_tier: RiskTier  # After any override
    signals: list[RiskSignal]
    override: Optional[RiskTierOverride] = None
    explanation: str = ""
    classified_at: datetime = field(default_factory=datetime.utcnow)


class RiskClassificationService:
    """Service for classifying COP candidates by risk tier (FR-COP-RISK-001).

    Analyzes candidate content for high-stakes keywords and signals,
    supports facilitator override with audit logging.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
    ):
        """Initialize RiskClassificationService.

        Args:
            audit_service: Audit logging service
        """
        self.audit_service = audit_service or get_audit_service()

    def classify_candidate(self, candidate: COPCandidate) -> RiskClassification:
        """Classify a COP candidate's risk tier based on content.

        Args:
            candidate: COP candidate to classify

        Returns:
            RiskClassification with computed tier and detected signals
        """
        # Extract all text content from candidate
        text_content = self._extract_text_content(candidate)

        # Detect risk signals
        signals = self._detect_risk_signals(text_content)

        # Compute risk tier from signals
        computed_tier = self._compute_tier_from_signals(signals)

        # Check for existing override
        final_tier = computed_tier
        override = None
        if candidate.risk_tier_override:
            override = candidate.risk_tier_override
            final_tier = override.new_tier

        # Generate explanation
        explanation = self._generate_explanation(computed_tier, signals)

        logger.info(
            "Classified candidate risk tier",
            candidate_id=str(candidate.id),
            computed_tier=computed_tier.value,
            final_tier=final_tier.value,
            signal_count=len(signals),
            has_override=override is not None,
        )

        return RiskClassification(
            candidate_id=str(candidate.id),
            computed_tier=computed_tier,
            final_tier=final_tier,
            signals=signals,
            override=override,
            explanation=explanation,
        )

    def _extract_text_content(self, candidate: COPCandidate) -> str:
        """Extract all text content from candidate for analysis.

        Args:
            candidate: COP candidate

        Returns:
            Combined text content
        """
        parts = []

        # COP fields
        if candidate.fields:
            if candidate.fields.what:
                parts.append(candidate.fields.what)
            if candidate.fields.where:
                parts.append(candidate.fields.where)
            if candidate.fields.who:
                parts.append(candidate.fields.who)
            if candidate.fields.so_what:
                parts.append(candidate.fields.so_what)
            if candidate.fields.when and candidate.fields.when.description:
                parts.append(candidate.fields.when.description)

        # Draft wording if available
        if candidate.draft_wording:
            if candidate.draft_wording.headline:
                parts.append(candidate.draft_wording.headline)
            if candidate.draft_wording.body:
                parts.append(candidate.draft_wording.body)

        return " ".join(parts).lower()

    def _detect_risk_signals(self, text: str) -> list[RiskSignal]:
        """Detect risk signals in text content.

        Args:
            text: Text content to analyze

        Returns:
            List of detected risk signals
        """
        signals = []

        # Check high-stakes keywords
        for category, keywords in HIGH_STAKES_KEYWORDS.items():
            signal_type = RiskSignalType(category)
            for keyword in keywords:
                if self._keyword_match(keyword, text):
                    context = self._extract_context(keyword, text)
                    signals.append(RiskSignal(
                        signal_type=signal_type,
                        keyword_matched=keyword,
                        context=context,
                        severity=RiskTier.HIGH_STAKES,
                    ))

        # Check elevated keywords (only if no high-stakes found)
        if not any(s.severity == RiskTier.HIGH_STAKES for s in signals):
            for category, keywords in ELEVATED_KEYWORDS.items():
                signal_type = RiskSignalType(category)
                for keyword in keywords:
                    if self._keyword_match(keyword, text):
                        context = self._extract_context(keyword, text)
                        signals.append(RiskSignal(
                            signal_type=signal_type,
                            keyword_matched=keyword,
                            context=context,
                            severity=RiskTier.ELEVATED,
                        ))

        return signals

    def _keyword_match(self, keyword: str, text: str) -> bool:
        """Check if keyword matches in text (word boundary aware).

        Args:
            keyword: Keyword to search for
            text: Text to search in

        Returns:
            True if keyword found
        """
        # Use word boundaries for single words, substring for phrases
        if " " in keyword:
            return keyword.lower() in text.lower()
        else:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            return bool(re.search(pattern, text.lower()))

    def _extract_context(self, keyword: str, text: str, window: int = 50) -> str:
        """Extract surrounding context for a keyword match.

        Args:
            keyword: Matched keyword
            text: Full text
            window: Characters before/after to include

        Returns:
            Context string
        """
        idx = text.lower().find(keyword.lower())
        if idx == -1:
            return ""

        start = max(0, idx - window)
        end = min(len(text), idx + len(keyword) + window)

        context = text[start:end]
        if start > 0:
            context = "..." + context
        if end < len(text):
            context = context + "..."

        return context

    def _compute_tier_from_signals(self, signals: list[RiskSignal]) -> RiskTier:
        """Compute risk tier from detected signals.

        Args:
            signals: List of detected signals

        Returns:
            Computed risk tier
        """
        if not signals:
            return RiskTier.ROUTINE

        # If any high-stakes signal, return HIGH_STAKES
        if any(s.severity == RiskTier.HIGH_STAKES for s in signals):
            return RiskTier.HIGH_STAKES

        # If multiple elevated signals, escalate to HIGH_STAKES
        elevated_count = sum(1 for s in signals if s.severity == RiskTier.ELEVATED)
        if elevated_count >= 3:
            return RiskTier.HIGH_STAKES

        # If any elevated signal, return ELEVATED
        if any(s.severity == RiskTier.ELEVATED for s in signals):
            return RiskTier.ELEVATED

        return RiskTier.ROUTINE

    def _generate_explanation(
        self,
        tier: RiskTier,
        signals: list[RiskSignal],
    ) -> str:
        """Generate human-readable explanation for classification.

        Args:
            tier: Computed risk tier
            signals: Detected signals

        Returns:
            Explanation string
        """
        if tier == RiskTier.ROUTINE:
            return "No high-stakes or elevated risk signals detected."

        if tier == RiskTier.ELEVATED:
            signal_types = set(s.signal_type.value for s in signals)
            return f"Elevated risk due to: {', '.join(signal_types)}"

        if tier == RiskTier.HIGH_STAKES:
            high_signals = [s for s in signals if s.severity == RiskTier.HIGH_STAKES]
            if high_signals:
                keywords = [s.keyword_matched for s in high_signals[:3]]
                return f"HIGH STAKES: Contains life-safety keywords ({', '.join(keywords)})"
            else:
                return "HIGH STAKES: Multiple elevated risk indicators"

        return "Classification complete."

    async def override_risk_tier(
        self,
        candidate: COPCandidate,
        new_tier: RiskTier,
        user: User,
        justification: str,
    ) -> COPCandidate:
        """Override the risk tier classification for a candidate.

        Args:
            candidate: COP candidate to update
            new_tier: New risk tier
            user: User performing the override
            justification: Required written rationale

        Returns:
            Updated candidate with override recorded
        """
        if not justification or len(justification.strip()) < 10:
            raise ValueError("Override requires a justification (min 10 characters)")

        previous_tier = candidate.risk_tier

        # Record override
        override = RiskTierOverride(
            previous_tier=previous_tier,
            new_tier=new_tier,
            overridden_by=user.id,
            overridden_at=datetime.utcnow(),
            justification=justification.strip(),
        )

        candidate.risk_tier = new_tier
        candidate.risk_tier_override = override

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_CANDIDATE_UPDATE_RISK_TIER,
            target_type=AuditTargetType.COP_CANDIDATE,
            target_id=candidate.id,
            changes_before={"risk_tier": previous_tier.value},
            changes_after={"risk_tier": new_tier.value},
            justification=justification,
            system_context={
                "action": "risk_tier_override",
                "previous_tier": previous_tier.value,
                "new_tier": new_tier.value,
            },
        )

        logger.info(
            "Risk tier overridden",
            candidate_id=str(candidate.id),
            previous_tier=previous_tier.value,
            new_tier=new_tier.value,
            overridden_by=str(user.id),
        )

        return candidate


# ============================================================================
# Publish Gate Enforcement (FR-COP-GATE-001)
# ============================================================================


@dataclass
class PublishGateResult:
    """Result of publish gate check."""

    allowed: bool
    requires_override: bool
    override_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class HighStakesOverride:
    """Override record for high-stakes publish gate."""

    candidate_id: ObjectId
    override_type: str  # "high_stakes_unverified"
    justification: str
    overridden_by: ObjectId
    overridden_at: datetime
    unconfirmed_label_applied: bool = True


class PublishGateService:
    """Service for enforcing publish gates on high-stakes content (FR-COP-GATE-001).

    High-stakes candidates require VERIFIED status unless explicitly overridden
    with a written rationale and UNCONFIRMED labeling.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
    ):
        """Initialize PublishGateService.

        Args:
            audit_service: Audit logging service
        """
        self.audit_service = audit_service or get_audit_service()

    def check_publish_gate(
        self,
        candidate: COPCandidate,
        classification: Optional[RiskClassification] = None,
    ) -> PublishGateResult:
        """Check if a candidate passes publish gates.

        Args:
            candidate: COP candidate to check
            classification: Optional pre-computed classification

        Returns:
            PublishGateResult with gate status
        """
        from integritykit.models.cop_candidate import ReadinessState

        warnings = []

        # Get effective risk tier
        risk_tier = candidate.risk_tier
        if classification:
            risk_tier = classification.final_tier

        # Routine and Elevated pass without special gates
        if risk_tier in [RiskTier.ROUTINE, RiskTier.ELEVATED]:
            if risk_tier == RiskTier.ELEVATED:
                warnings.append("Elevated risk content - extra review recommended")
            return PublishGateResult(
                allowed=True,
                requires_override=False,
                warnings=warnings,
            )

        # HIGH_STAKES requires VERIFIED status
        if risk_tier == RiskTier.HIGH_STAKES:
            if candidate.readiness_state == ReadinessState.VERIFIED:
                return PublishGateResult(
                    allowed=True,
                    requires_override=False,
                    warnings=["High-stakes content - verification confirmed"],
                )
            else:
                return PublishGateResult(
                    allowed=False,
                    requires_override=True,
                    override_reason=(
                        "High-stakes content requires VERIFIED status or explicit override. "
                        "Override will add UNCONFIRMED label to published content."
                    ),
                    warnings=[
                        "HIGH STAKES: This content involves life-safety information",
                        "Verification is required before publishing",
                        "Override available with written justification",
                    ],
                )

        return PublishGateResult(allowed=True, requires_override=False)

    async def apply_high_stakes_override(
        self,
        candidate: COPCandidate,
        user: User,
        justification: str,
    ) -> HighStakesOverride:
        """Apply an override for high-stakes unverified content.

        Args:
            candidate: COP candidate being overridden
            user: User applying override
            justification: Required written rationale

        Returns:
            HighStakesOverride record
        """
        if not justification or len(justification.strip()) < 20:
            raise ValueError(
                "High-stakes override requires detailed justification (min 20 characters)"
            )

        override = HighStakesOverride(
            candidate_id=candidate.id,
            override_type="high_stakes_unverified",
            justification=justification.strip(),
            overridden_by=user.id,
            overridden_at=datetime.utcnow(),
            unconfirmed_label_applied=True,
        )

        # Log to audit
        await self.audit_service.log_action(
            actor=user,
            action_type=AuditActionType.COP_UPDATE_OVERRIDE,
            target_type=AuditTargetType.COP_CANDIDATE,
            target_id=candidate.id,
            changes_before={"publish_gate": "blocked"},
            changes_after={
                "publish_gate": "override_applied",
                "unconfirmed_label": True,
            },
            justification=justification,
            system_context={
                "action": "high_stakes_override",
                "risk_tier": candidate.risk_tier.value,
                "readiness_state": candidate.readiness_state.value,
            },
        )

        logger.warning(
            "High-stakes publish gate overridden",
            candidate_id=str(candidate.id),
            overridden_by=str(user.id),
            justification_length=len(justification),
        )

        return override

    def apply_unconfirmed_label(self, text: str) -> str:
        """Apply UNCONFIRMED label to text for high-stakes override.

        Args:
            text: Original text

        Returns:
            Text with UNCONFIRMED label prepended
        """
        return f"⚠️ UNCONFIRMED: {text}"


def get_risk_classification_service() -> RiskClassificationService:
    """Get a RiskClassificationService instance."""
    return RiskClassificationService()


def get_publish_gate_service() -> PublishGateService:
    """Get a PublishGateService instance."""
    return PublishGateService()
