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
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

import structlog
from bson import ObjectId

from integritykit.models.audit import AuditActionType, AuditTargetType
from integritykit.models.cop_candidate import (
    COPCandidate,
    RiskTier,
    RiskTierOverride,
    TwoPersonApproval,
    TwoPersonApprovalStatus,
)
from integritykit.models.user import User
from integritykit.services.audit import AuditService, get_audit_service

logger = structlog.get_logger(__name__)


def _get_abuse_detection_service():
    """Lazy import of abuse detection service to avoid circular imports."""
    from integritykit.services.abuse_detection import get_abuse_detection_service
    return get_abuse_detection_service()


def _get_settings():
    """Lazy import of settings to avoid validation errors in tests."""
    from integritykit.config import settings
    return settings


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
    requires_two_person_approval: bool = False
    override_reason: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    pending_approval: Optional["TwoPersonApproval"] = None


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

    When two-person rule is enabled (FR-COP-GATE-002), high-stakes overrides
    also require approval from a second facilitator.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        two_person_service: Optional["TwoPersonApprovalService"] = None,
    ):
        """Initialize PublishGateService.

        Args:
            audit_service: Audit logging service
            two_person_service: Two-person approval service (optional)
        """
        self.audit_service = audit_service or get_audit_service()
        self._two_person_service = two_person_service

    @property
    def two_person_service(self) -> "TwoPersonApprovalService":
        """Get two-person approval service (lazy initialization)."""
        if self._two_person_service is None:
            self._two_person_service = TwoPersonApprovalService(
                audit_service=self.audit_service
            )
        return self._two_person_service

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
                requires_two_person_approval=False,
                warnings=warnings,
            )

        # HIGH_STAKES requires VERIFIED status
        if risk_tier == RiskTier.HIGH_STAKES:
            if candidate.readiness_state == ReadinessState.VERIFIED:
                return PublishGateResult(
                    allowed=True,
                    requires_override=False,
                    requires_two_person_approval=False,
                    warnings=["High-stakes content - verification confirmed"],
                )
            else:
                # Check if two-person approval is required
                two_person_required = self.two_person_service.requires_two_person_approval(
                    candidate, "high_stakes_publish"
                )

                # Check for existing pending approval
                pending = self.two_person_service.get_pending_approval(
                    candidate.id, "high_stakes_publish"
                )

                override_reason = (
                    "High-stakes content requires VERIFIED status or explicit override. "
                    "Override will add UNCONFIRMED label to published content."
                )
                if two_person_required:
                    override_reason += (
                        " Two-person approval is required: a second facilitator "
                        "must approve the override before publishing."
                    )

                return PublishGateResult(
                    allowed=False,
                    requires_override=True,
                    requires_two_person_approval=two_person_required,
                    override_reason=override_reason,
                    warnings=[
                        "HIGH STAKES: This content involves life-safety information",
                        "Verification is required before publishing",
                        "Override available with written justification",
                    ] + (
                        ["Two-person approval required for override"]
                        if two_person_required else []
                    ),
                    pending_approval=pending,
                )

        return PublishGateResult(
            allowed=True,
            requires_override=False,
            requires_two_person_approval=False,
        )

    async def apply_high_stakes_override(
        self,
        candidate: COPCandidate,
        user: User,
        justification: str,
        two_person_approval: Optional[TwoPersonApproval] = None,
    ) -> HighStakesOverride:
        """Apply an override for high-stakes unverified content.

        When two-person rule is enabled, this method requires a completed
        TwoPersonApproval before proceeding.

        Args:
            candidate: COP candidate being overridden
            user: User applying override
            justification: Required written rationale
            two_person_approval: Completed two-person approval (required if enabled)

        Returns:
            HighStakesOverride record

        Raises:
            ValueError: If justification insufficient or two-person approval required
        """
        if not justification or len(justification.strip()) < 20:
            raise ValueError(
                "High-stakes override requires detailed justification (min 20 characters)"
            )

        # Check if two-person approval is required
        requires_two_person = self.two_person_service.requires_two_person_approval(
            candidate, "high_stakes_publish"
        )

        if requires_two_person:
            if two_person_approval is None:
                raise ValueError(
                    "Two-person approval is required for high-stakes overrides. "
                    "Request approval from a second facilitator first."
                )

            if two_person_approval.status != TwoPersonApprovalStatus.APPROVED:
                raise ValueError(
                    f"Two-person approval is not complete. "
                    f"Status: {two_person_approval.status.value}"
                )

            if two_person_approval.candidate_id != candidate.id:
                raise ValueError(
                    "Two-person approval is for a different candidate"
                )

        override = HighStakesOverride(
            candidate_id=candidate.id,
            override_type="high_stakes_unverified",
            justification=justification.strip(),
            overridden_by=user.id,
            overridden_at=datetime.utcnow(),
            unconfirmed_label_applied=True,
        )

        # Build audit context
        audit_context: dict[str, Any] = {
            "action": "high_stakes_override",
            "risk_tier": candidate.risk_tier if isinstance(candidate.risk_tier, str) else candidate.risk_tier.value,
            "readiness_state": candidate.readiness_state if isinstance(candidate.readiness_state, str) else candidate.readiness_state.value,
        }

        if two_person_approval:
            audit_context["two_person_approval"] = {
                "requested_by": str(two_person_approval.requested_by),
                "approved_by": str(two_person_approval.second_approver_id),
                "approved_at": two_person_approval.second_approval_at.isoformat()
                if two_person_approval.second_approval_at else None,
            }

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
                "two_person_approved": two_person_approval is not None,
            },
            justification=justification,
            system_context=audit_context,
        )

        logger.warning(
            "High-stakes publish gate overridden",
            candidate_id=str(candidate.id),
            overridden_by=str(user.id),
            justification_length=len(justification),
            two_person_approved=two_person_approval is not None,
        )

        # Record override for abuse detection (S7-3)
        try:
            abuse_service = _get_abuse_detection_service()
            alert = await abuse_service.record_override(
                user=user,
                action_type="high_stakes_override",
                target_id=candidate.id,
            )
            if alert:
                logger.warning(
                    "Abuse alert triggered for user",
                    user_id=str(user.id),
                    alert_type=alert.alert_type,
                    override_count=alert.override_count,
                )
        except Exception as e:
            # Don't fail the override if abuse detection fails
            logger.error(
                "Failed to record override for abuse detection",
                error=str(e),
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


class TwoPersonApprovalService:
    """Service for managing two-person approval workflow (FR-COP-GATE-002).

    When enabled, high-stakes overrides require approval from a second
    facilitator before taking effect. This provides an additional safety
    check for life-safety information.
    """

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
    ):
        """Initialize TwoPersonApprovalService.

        Args:
            audit_service: Audit logging service
        """
        self.audit_service = audit_service or get_audit_service()
        self._pending_approvals: dict[str, TwoPersonApproval] = {}

    def is_enabled(self) -> bool:
        """Check if two-person rule is enabled.

        Returns:
            True if two-person rule is enabled in settings
        """
        return _get_settings().two_person_rule_enabled

    def requires_two_person_approval(
        self,
        candidate: COPCandidate,
        override_type: str,
    ) -> bool:
        """Check if an action requires two-person approval.

        Args:
            candidate: COP candidate being acted upon
            override_type: Type of override being requested

        Returns:
            True if two-person approval is required
        """
        if not self.is_enabled():
            return False

        # Two-person rule applies to high-stakes overrides
        return (
            candidate.risk_tier == RiskTier.HIGH_STAKES
            and override_type in ["high_stakes_publish", "risk_tier_override"]
        )

    async def request_approval(
        self,
        candidate: COPCandidate,
        override_type: str,
        requester: User,
        justification: str,
        override_context: Optional[dict] = None,
    ) -> TwoPersonApproval:
        """Request two-person approval for a high-stakes override.

        Args:
            candidate: COP candidate requiring approval
            override_type: Type of override (high_stakes_publish, risk_tier_override)
            requester: Facilitator requesting the override
            justification: Required justification for the override
            override_context: Additional context about the override

        Returns:
            TwoPersonApproval pending record
        """
        if not justification or len(justification.strip()) < 20:
            raise ValueError(
                "Two-person approval requires detailed justification (min 20 characters)"
            )

        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(
            hours=_get_settings().two_person_rule_timeout_hours
        )

        approval = TwoPersonApproval(
            candidate_id=candidate.id,
            override_type=override_type,
            requested_by=requester.id,
            requested_at=datetime.utcnow(),
            request_justification=justification.strip(),
            status=TwoPersonApprovalStatus.PENDING,
            expires_at=expires_at,
            override_context=override_context or {
                "candidate_risk_tier": candidate.risk_tier if isinstance(candidate.risk_tier, str) else candidate.risk_tier.value,
                "candidate_readiness_state": candidate.readiness_state if isinstance(candidate.readiness_state, str) else candidate.readiness_state.value,
            },
        )

        # Store pending approval (in production, persist to MongoDB)
        approval_key = f"{candidate.id}:{override_type}"
        self._pending_approvals[approval_key] = approval

        # Log to audit
        await self.audit_service.log_action(
            actor=requester,
            action_type=AuditActionType.TWO_PERSON_APPROVAL_REQUESTED,
            target_type=AuditTargetType.COP_CANDIDATE,
            target_id=candidate.id,
            changes_after={
                "override_type": override_type,
                "status": "pending",
                "expires_at": expires_at.isoformat(),
            },
            justification=justification,
            system_context={
                "action": "two_person_approval_requested",
                "risk_tier": candidate.risk_tier if isinstance(candidate.risk_tier, str) else candidate.risk_tier.value,
            },
        )

        logger.info(
            "Two-person approval requested",
            candidate_id=str(candidate.id),
            override_type=override_type,
            requested_by=str(requester.id),
            expires_at=expires_at.isoformat(),
        )

        return approval

    async def grant_approval(
        self,
        candidate_id: ObjectId,
        override_type: str,
        approver: User,
        notes: Optional[str] = None,
    ) -> TwoPersonApproval:
        """Grant second approval for a pending request.

        Args:
            candidate_id: COP candidate ID
            override_type: Type of override being approved
            approver: Second facilitator granting approval
            notes: Optional notes from second approver

        Returns:
            Updated TwoPersonApproval with approved status

        Raises:
            ValueError: If no pending approval, already complete, or same user
        """
        approval_key = f"{candidate_id}:{override_type}"
        approval = self._pending_approvals.get(approval_key)

        if not approval:
            raise ValueError("No pending two-person approval found")

        if approval.is_expired:
            approval.status = TwoPersonApprovalStatus.EXPIRED
            raise ValueError("Two-person approval has expired")

        if approval.is_complete:
            raise ValueError("Two-person approval already completed")

        if approval.requested_by == approver.id:
            raise ValueError(
                "Second approver must be different from the requester"
            )

        # Grant approval
        now = datetime.utcnow()
        approval.second_approver_id = approver.id
        approval.second_approval_at = now
        approval.second_approver_notes = notes
        approval.status = TwoPersonApprovalStatus.APPROVED
        approval.updated_at = now

        # Log to audit
        await self.audit_service.log_action(
            actor=approver,
            action_type=AuditActionType.TWO_PERSON_APPROVAL_GRANTED,
            target_type=AuditTargetType.COP_CANDIDATE,
            target_id=candidate_id,
            changes_before={"status": "pending"},
            changes_after={
                "status": "approved",
                "second_approver_id": str(approver.id),
            },
            justification=notes,
            system_context={
                "action": "two_person_approval_granted",
                "original_requester": str(approval.requested_by),
                "override_type": override_type,
            },
        )

        logger.info(
            "Two-person approval granted",
            candidate_id=str(candidate_id),
            override_type=override_type,
            approved_by=str(approver.id),
            original_requester=str(approval.requested_by),
        )

        return approval

    async def deny_approval(
        self,
        candidate_id: ObjectId,
        override_type: str,
        denier: User,
        reason: str,
    ) -> TwoPersonApproval:
        """Deny a pending two-person approval request.

        Args:
            candidate_id: COP candidate ID
            override_type: Type of override being denied
            denier: Facilitator denying the approval
            reason: Required reason for denial

        Returns:
            Updated TwoPersonApproval with denied status
        """
        if not reason or len(reason.strip()) < 10:
            raise ValueError("Denial requires a reason (min 10 characters)")

        approval_key = f"{candidate_id}:{override_type}"
        approval = self._pending_approvals.get(approval_key)

        if not approval:
            raise ValueError("No pending two-person approval found")

        if approval.is_complete:
            raise ValueError("Two-person approval already completed")

        # Deny approval
        now = datetime.utcnow()
        approval.second_approver_id = denier.id
        approval.second_approval_at = now
        approval.status = TwoPersonApprovalStatus.DENIED
        approval.denial_reason = reason.strip()
        approval.updated_at = now

        # Log to audit
        await self.audit_service.log_action(
            actor=denier,
            action_type=AuditActionType.TWO_PERSON_APPROVAL_DENIED,
            target_type=AuditTargetType.COP_CANDIDATE,
            target_id=candidate_id,
            changes_before={"status": "pending"},
            changes_after={
                "status": "denied",
                "denier_id": str(denier.id),
                "denial_reason": reason,
            },
            justification=reason,
            system_context={
                "action": "two_person_approval_denied",
                "original_requester": str(approval.requested_by),
                "override_type": override_type,
            },
        )

        logger.warning(
            "Two-person approval denied",
            candidate_id=str(candidate_id),
            override_type=override_type,
            denied_by=str(denier.id),
            reason=reason,
        )

        return approval

    def get_pending_approval(
        self,
        candidate_id: ObjectId,
        override_type: str,
    ) -> Optional[TwoPersonApproval]:
        """Get pending approval for a candidate if one exists.

        Args:
            candidate_id: COP candidate ID
            override_type: Type of override

        Returns:
            TwoPersonApproval if pending, None otherwise
        """
        approval_key = f"{candidate_id}:{override_type}"
        approval = self._pending_approvals.get(approval_key)

        if approval and approval.is_pending:
            return approval
        return None

    def get_all_pending_approvals(self) -> list[TwoPersonApproval]:
        """Get all pending approval requests.

        Returns:
            List of pending TwoPersonApproval records
        """
        return [
            approval for approval in self._pending_approvals.values()
            if approval.is_pending
        ]

    async def expire_pending_approvals(self) -> list[TwoPersonApproval]:
        """Expire all overdue pending approvals.

        This should be called periodically to clean up expired requests.

        Returns:
            List of expired TwoPersonApproval records
        """
        expired = []
        for _key, approval in list(self._pending_approvals.items()):
            if approval.status == TwoPersonApprovalStatus.PENDING and approval.is_expired:
                approval.status = TwoPersonApprovalStatus.EXPIRED
                approval.updated_at = datetime.utcnow()
                expired.append(approval)

                # Log expiration (use system actor)
                logger.warning(
                    "Two-person approval expired",
                    candidate_id=str(approval.candidate_id),
                    override_type=approval.override_type,
                    requested_by=str(approval.requested_by),
                    expired_at=approval.expires_at.isoformat(),
                )

        return expired


def get_risk_classification_service() -> RiskClassificationService:
    """Get a RiskClassificationService instance."""
    return RiskClassificationService()


def get_publish_gate_service() -> PublishGateService:
    """Get a PublishGateService instance."""
    return PublishGateService()


def get_two_person_approval_service() -> TwoPersonApprovalService:
    """Get a TwoPersonApprovalService instance."""
    return TwoPersonApprovalService()
