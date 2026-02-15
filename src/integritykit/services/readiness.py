"""Readiness computation service for COP candidates.

Implements:
- FR-COP-READ-001: Readiness states (Ready-Verified / Ready-In Review / Blocked)
- FR-COP-READ-002: Missing/weak fields identification
- FR-COP-READ-003: Best next action recommendation
- NFR-CONFLICT-001: Conflict blocking enforcement
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

import structlog
from openai import AsyncOpenAI

from integritykit.llm.prompts.next_action import (
    CLARIFICATION_TEMPLATES,
    NEXT_ACTION_OUTPUT_SCHEMA,
    NEXT_ACTION_SYSTEM_PROMPT,
    COPCandidateState,
    NextActionOutput,
    format_next_action_prompt,
)
from integritykit.llm.prompts.readiness_evaluation import (
    READINESS_EVALUATION_OUTPUT_SCHEMA,
    READINESS_EVALUATION_SYSTEM_PROMPT,
    COPCandidateData,
    FieldQuality,
    ReadinessOutput,
    format_readiness_evaluation_prompt,
)
from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    BlockingIssueSeverity,
    COPCandidate,
    ReadinessState,
    RecommendedAction,
    RiskTier,
)

logger = structlog.get_logger(__name__)


class FieldStatus(str, Enum):
    """Status of a COP candidate field."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    MISSING = "missing"


@dataclass
class FieldEvaluation:
    """Evaluation result for a single field."""

    field: str
    status: FieldStatus
    value: Optional[str]
    notes: str


@dataclass
class ReadinessEvaluation:
    """Complete readiness evaluation for a COP candidate."""

    candidate_id: str
    readiness_state: ReadinessState
    field_evaluations: list[FieldEvaluation]
    missing_fields: list[str]
    blocking_issues: list[BlockingIssue]
    recommended_action: Optional[RecommendedAction]
    explanation: str
    evaluated_at: datetime
    evaluation_method: Literal["rule_based", "llm"]


class ReadinessService:
    """Service for evaluating COP candidate readiness (FR-COP-READ-001).

    Provides both rule-based (fast) and LLM-based (nuanced) evaluation of
    COP candidates to determine their readiness state.
    """

    # Minimum required fields for publication
    REQUIRED_FIELDS = ["what", "where", "when", "who", "so_what"]

    # Fields that absolutely block publication if missing
    CRITICAL_FIELDS = ["what", "where", "when"]

    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4o-mini",
        use_llm: bool = True,
    ):
        """Initialize ReadinessService.

        Args:
            openai_client: OpenAI client for LLM-based evaluation
            model: Model to use for LLM evaluation
            use_llm: Whether to use LLM for evaluation (fallback to rules if False)
        """
        self.client = openai_client
        self.model = model
        self.use_llm = use_llm and openai_client is not None

    async def evaluate_readiness(
        self,
        candidate: COPCandidate,
        use_llm: Optional[bool] = None,
    ) -> ReadinessEvaluation:
        """Evaluate readiness state for a COP candidate.

        Args:
            candidate: COP candidate to evaluate
            use_llm: Override instance-level LLM setting

        Returns:
            ReadinessEvaluation with state, missing fields, and blocking issues
        """
        should_use_llm = use_llm if use_llm is not None else self.use_llm

        if should_use_llm and self.client:
            try:
                return await self._evaluate_with_llm(candidate)
            except Exception as e:
                logger.warning(
                    "LLM evaluation failed, falling back to rule-based",
                    candidate_id=str(candidate.id),
                    error=str(e),
                )
                return self._evaluate_rule_based(candidate)
        else:
            return self._evaluate_rule_based(candidate)

    def _evaluate_rule_based(self, candidate: COPCandidate) -> ReadinessEvaluation:
        """Rule-based readiness evaluation (fast, deterministic).

        Args:
            candidate: COP candidate to evaluate

        Returns:
            ReadinessEvaluation based on field completeness rules
        """
        field_evaluations = self._evaluate_fields(candidate)
        missing_fields = [
            fe.field for fe in field_evaluations if fe.status == FieldStatus.MISSING
        ]
        partial_fields = [
            fe.field for fe in field_evaluations if fe.status == FieldStatus.PARTIAL
        ]

        blocking_issues: list[BlockingIssue] = []

        # Check for missing critical fields
        for field in self.CRITICAL_FIELDS:
            if field in missing_fields:
                blocking_issues.append(
                    BlockingIssue(
                        issue_type="missing_field",
                        description=f"Critical field '{field}' is missing",
                        severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
                    )
                )

        # Check for unresolved conflicts (NFR-CONFLICT-001)
        if candidate.has_unresolved_conflicts:
            blocking_issues.append(
                BlockingIssue(
                    issue_type="unresolved_conflict",
                    description="Candidate has unresolved conflicts that must be resolved before verification",
                    severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
                )
            )

        # Check high-stakes verification requirement
        has_verification = len(candidate.verifications) > 0
        if candidate.risk_tier == RiskTier.HIGH_STAKES and not has_verification:
            blocking_issues.append(
                BlockingIssue(
                    issue_type="verification_required",
                    description="High-stakes item requires verification before publishing",
                    severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
                )
            )

        # Check evidence requirement
        has_evidence = (
            len(candidate.evidence.slack_permalinks) > 0
            or len(candidate.evidence.external_sources) > 0
        )
        if not has_evidence:
            blocking_issues.append(
                BlockingIssue(
                    issue_type="missing_evidence",
                    description="No evidence (Slack permalinks or external sources) provided",
                    severity=BlockingIssueSeverity.REQUIRES_ATTENTION,
                )
            )

        # Partial fields as warnings
        for field in partial_fields:
            blocking_issues.append(
                BlockingIssue(
                    issue_type="partial_field",
                    description=f"Field '{field}' is incomplete or vague",
                    severity=BlockingIssueSeverity.WARNING,
                )
            )

        # Determine readiness state
        has_blocking_issues = any(
            bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING
            for bi in blocking_issues
        )

        if has_blocking_issues:
            readiness_state = ReadinessState.BLOCKED
            explanation = "Candidate is blocked due to: " + "; ".join(
                bi.description
                for bi in blocking_issues
                if bi.severity == BlockingIssueSeverity.BLOCKS_PUBLISHING
            )
        elif has_verification and not missing_fields:
            readiness_state = ReadinessState.VERIFIED
            explanation = "All required fields present and verified"
        else:
            readiness_state = ReadinessState.IN_REVIEW
            if missing_fields:
                explanation = f"Minimum fields present but missing: {', '.join(missing_fields)}"
            else:
                explanation = "Minimum fields present, awaiting verification"

        # Generate recommended action
        recommended_action = self._generate_rule_based_recommendation(
            candidate, readiness_state, missing_fields, blocking_issues
        )

        logger.info(
            "Rule-based readiness evaluation completed",
            candidate_id=str(candidate.id),
            readiness_state=readiness_state.value,
            missing_fields=missing_fields,
            blocking_issue_count=len(blocking_issues),
        )

        return ReadinessEvaluation(
            candidate_id=str(candidate.id),
            readiness_state=readiness_state,
            field_evaluations=field_evaluations,
            missing_fields=missing_fields,
            blocking_issues=blocking_issues,
            recommended_action=recommended_action,
            explanation=explanation,
            evaluated_at=datetime.utcnow(),
            evaluation_method="rule_based",
        )

    def _evaluate_fields(self, candidate: COPCandidate) -> list[FieldEvaluation]:
        """Evaluate individual fields of a candidate.

        Args:
            candidate: COP candidate to evaluate

        Returns:
            List of field evaluations
        """
        evaluations = []

        # What field
        what_value = candidate.fields.what
        evaluations.append(
            FieldEvaluation(
                field="what",
                status=self._assess_field_status(what_value),
                value=what_value,
                notes=self._get_field_notes("what", what_value),
            )
        )

        # Where field
        where_value = candidate.fields.where
        evaluations.append(
            FieldEvaluation(
                field="where",
                status=self._assess_field_status(where_value),
                value=where_value,
                notes=self._get_field_notes("where", where_value),
            )
        )

        # When field
        when_value = candidate.fields.when.description or (
            candidate.fields.when.timestamp.isoformat()
            if candidate.fields.when.timestamp
            else ""
        )
        evaluations.append(
            FieldEvaluation(
                field="when",
                status=self._assess_field_status(when_value),
                value=when_value,
                notes=self._get_field_notes("when", when_value),
            )
        )

        # Who field
        who_value = candidate.fields.who
        evaluations.append(
            FieldEvaluation(
                field="who",
                status=self._assess_field_status(who_value, required=False),
                value=who_value,
                notes=self._get_field_notes("who", who_value),
            )
        )

        # So what field
        so_what_value = candidate.fields.so_what
        evaluations.append(
            FieldEvaluation(
                field="so_what",
                status=self._assess_field_status(so_what_value),
                value=so_what_value,
                notes=self._get_field_notes("so_what", so_what_value),
            )
        )

        # Evidence
        evidence_count = (
            len(candidate.evidence.slack_permalinks)
            + len(candidate.evidence.external_sources)
        )
        evaluations.append(
            FieldEvaluation(
                field="evidence",
                status=(
                    FieldStatus.COMPLETE
                    if evidence_count >= 2
                    else FieldStatus.PARTIAL
                    if evidence_count == 1
                    else FieldStatus.MISSING
                ),
                value=f"{evidence_count} sources",
                notes=f"Has {evidence_count} evidence source(s)",
            )
        )

        return evaluations

    def _assess_field_status(
        self, value: Optional[str], required: bool = True
    ) -> FieldStatus:
        """Assess the status of a field value.

        Args:
            value: Field value to assess
            required: Whether the field is required

        Returns:
            FieldStatus indicating completeness
        """
        if not value or not value.strip():
            return FieldStatus.MISSING

        # Check for vague indicators
        vague_indicators = [
            "unknown",
            "tbd",
            "to be determined",
            "unclear",
            "unspecified",
            "?",
            "n/a",
        ]
        value_lower = value.lower().strip()

        if value_lower in vague_indicators or len(value.strip()) < 5:
            return FieldStatus.PARTIAL

        return FieldStatus.COMPLETE

    def _get_field_notes(self, field: str, value: Optional[str]) -> str:
        """Generate notes for a field evaluation.

        Args:
            field: Field name
            value: Field value

        Returns:
            Descriptive notes about the field status
        """
        if not value or not value.strip():
            return f"'{field}' is empty or not provided"
        if len(value.strip()) < 5:
            return f"'{field}' value is too short to be meaningful"
        return f"'{field}' appears adequately specified"

    def _generate_rule_based_recommendation(
        self,
        candidate: COPCandidate,
        readiness_state: ReadinessState,
        missing_fields: list[str],
        blocking_issues: list[BlockingIssue],
    ) -> Optional[RecommendedAction]:
        """Generate next action recommendation using rules.

        Args:
            candidate: COP candidate
            readiness_state: Current readiness state
            missing_fields: List of missing fields
            blocking_issues: List of blocking issues

        Returns:
            Recommended next action
        """
        # Priority 1: High-stakes unverified
        if (
            candidate.risk_tier == RiskTier.HIGH_STAKES
            and len(candidate.verifications) == 0
        ):
            return RecommendedAction(
                action_type=ActionType.ASSIGN_VERIFICATION,
                reason="High-stakes item requires verification before publishing",
                alternatives=["resolve_conflict", "add_evidence"],
            )

        # Priority 2: Unresolved conflicts
        if candidate.has_unresolved_conflicts:
            return RecommendedAction(
                action_type=ActionType.RESOLVE_CONFLICT,
                reason="Unresolved conflicts must be addressed before proceeding",
                alternatives=["assign_verification"],
            )

        # Priority 3: Missing critical fields
        critical_missing = [f for f in missing_fields if f in self.CRITICAL_FIELDS]
        if critical_missing:
            return RecommendedAction(
                action_type=ActionType.ADD_EVIDENCE,
                reason=f"Missing critical fields: {', '.join(critical_missing)}",
                alternatives=["merge_candidates"],
            )

        # Priority 4: Ready for verification
        if (
            readiness_state == ReadinessState.IN_REVIEW
            and len(candidate.verifications) == 0
        ):
            return RecommendedAction(
                action_type=ActionType.ASSIGN_VERIFICATION,
                reason="Minimum fields present, ready for verification",
                alternatives=["add_evidence"],
            )

        # Priority 5: Verified and ready
        if readiness_state == ReadinessState.VERIFIED:
            return RecommendedAction(
                action_type=ActionType.READY_TO_PUBLISH,
                reason="All fields complete and verified, ready to publish",
                alternatives=[],
            )

        return None

    async def _evaluate_with_llm(
        self, candidate: COPCandidate
    ) -> ReadinessEvaluation:
        """LLM-based readiness evaluation (nuanced, context-aware).

        Args:
            candidate: COP candidate to evaluate

        Returns:
            ReadinessEvaluation based on LLM analysis
        """
        # Prepare candidate data for prompt
        candidate_data: COPCandidateData = {
            "candidate_id": str(candidate.id),
            "what": candidate.fields.what or None,
            "where": candidate.fields.where or None,
            "when": candidate.fields.when.description
            or (
                candidate.fields.when.timestamp.isoformat()
                if candidate.fields.when.timestamp
                else None
            ),
            "who": candidate.fields.who or None,
            "so_what": candidate.fields.so_what or None,
            "evidence_pack_size": len(candidate.evidence.slack_permalinks)
            + len(candidate.evidence.external_sources),
            "verification_status": (
                "verified"
                if len(candidate.verifications) > 0
                else "in_review"
            ),
            "has_unresolved_conflicts": candidate.has_unresolved_conflicts,
            "risk_tier": candidate.risk_tier.value,
        }

        user_prompt = format_readiness_evaluation_prompt(candidate_data)

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": READINESS_EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result: ReadinessOutput = json.loads(content)

        # Convert LLM output to internal types
        state_map = {
            "ready_verified": ReadinessState.VERIFIED,
            "ready_in_review": ReadinessState.IN_REVIEW,
            "blocked": ReadinessState.BLOCKED,
        }
        readiness_state = state_map.get(
            result["readiness_state"], ReadinessState.IN_REVIEW
        )

        # Convert field quality scores to evaluations
        field_evaluations = []
        for fq in result.get("field_quality_scores", []):
            status_map = {
                "complete": FieldStatus.COMPLETE,
                "partial": FieldStatus.PARTIAL,
                "missing": FieldStatus.MISSING,
            }
            field_evaluations.append(
                FieldEvaluation(
                    field=fq["field"],
                    status=status_map.get(fq["quality"], FieldStatus.MISSING),
                    value=None,  # LLM doesn't return values
                    notes=fq.get("notes", ""),
                )
            )

        # Convert blocking issues
        blocking_issues = [
            BlockingIssue(
                issue_type="llm_identified",
                description=issue,
                severity=BlockingIssueSeverity.BLOCKS_PUBLISHING,
            )
            for issue in result.get("blocking_issues", [])
        ]

        # Get recommended action via separate LLM call
        recommended_action = await self._get_llm_recommendation(
            candidate, readiness_state, result.get("missing_fields", [])
        )

        logger.info(
            "LLM readiness evaluation completed",
            candidate_id=str(candidate.id),
            readiness_state=readiness_state.value,
            missing_fields=result.get("missing_fields", []),
            blocking_issue_count=len(blocking_issues),
            model=self.model,
        )

        return ReadinessEvaluation(
            candidate_id=str(candidate.id),
            readiness_state=readiness_state,
            field_evaluations=field_evaluations,
            missing_fields=result.get("missing_fields", []),
            blocking_issues=blocking_issues,
            recommended_action=recommended_action,
            explanation=result.get("explanation", ""),
            evaluated_at=datetime.utcnow(),
            evaluation_method="llm",
        )

    async def _get_llm_recommendation(
        self,
        candidate: COPCandidate,
        readiness_state: ReadinessState,
        missing_fields: list[str],
    ) -> Optional[RecommendedAction]:
        """Get next action recommendation from LLM.

        Args:
            candidate: COP candidate
            readiness_state: Current readiness state
            missing_fields: List of missing fields

        Returns:
            Recommended action from LLM
        """
        if not self.client:
            return None

        # Prepare state for prompt
        conflict_severity = "none"
        if candidate.has_unresolved_conflicts:
            conflict_severity = "high"  # Simplified; could analyze actual severity

        candidate_state: COPCandidateState = {
            "candidate_id": str(candidate.id),
            "readiness_state": (
                "ready_verified"
                if readiness_state == ReadinessState.VERIFIED
                else "ready_in_review"
                if readiness_state == ReadinessState.IN_REVIEW
                else "blocked"
            ),
            "missing_fields": missing_fields,
            "has_unresolved_conflicts": candidate.has_unresolved_conflicts,
            "conflict_severity": conflict_severity,
            "verification_status": (
                "verified" if len(candidate.verifications) > 0 else "in_review"
            ),
            "risk_tier": candidate.risk_tier.value,
            "has_potential_duplicates": False,  # Would need duplicate detection
            "evidence_pack_size": len(candidate.evidence.slack_permalinks)
            + len(candidate.evidence.external_sources),
        }

        user_prompt = format_next_action_prompt(candidate_state)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": NEXT_ACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content
            result: NextActionOutput = json.loads(content)

            # Map LLM action to internal ActionType
            action_map = {
                "request_clarification": ActionType.ADD_EVIDENCE,
                "assign_verification": ActionType.ASSIGN_VERIFICATION,
                "merge_duplicate": ActionType.MERGE_CANDIDATES,
                "resolve_conflict": ActionType.RESOLVE_CONFLICT,
                "publish_as_in_review": ActionType.READY_TO_PUBLISH,
                "publish_as_verified": ActionType.READY_TO_PUBLISH,
                "defer": ActionType.ADD_EVIDENCE,
            }

            action_type = action_map.get(
                result["primary_action"], ActionType.ADD_EVIDENCE
            )

            return RecommendedAction(
                action_type=action_type,
                reason=result.get("reasoning", ""),
                alternatives=result.get("alternative_actions", []),
            )

        except Exception as e:
            logger.warning(
                "Failed to get LLM recommendation",
                candidate_id=str(candidate.id),
                error=str(e),
            )
            return None

    async def apply_evaluation(
        self,
        candidate: COPCandidate,
        evaluation: ReadinessEvaluation,
    ) -> COPCandidate:
        """Apply evaluation results to a COP candidate.

        Args:
            candidate: COP candidate to update
            evaluation: Evaluation results to apply

        Returns:
            Updated COP candidate
        """
        candidate.readiness_state = evaluation.readiness_state
        candidate.readiness_updated_at = evaluation.evaluated_at
        candidate.missing_fields = evaluation.missing_fields
        candidate.blocking_issues = evaluation.blocking_issues
        candidate.recommended_action = evaluation.recommended_action
        candidate.updated_at = datetime.utcnow()

        logger.info(
            "Applied readiness evaluation to candidate",
            candidate_id=str(candidate.id),
            readiness_state=evaluation.readiness_state.value,
            method=evaluation.evaluation_method,
        )

        return candidate

    def get_clarification_template(self, field: str) -> str:
        """Get a clarification message template for a field.

        Args:
            field: Field name to get template for

        Returns:
            Template message for requesting clarification
        """
        templates = {
            "where": CLARIFICATION_TEMPLATES["location"],
            "when": CLARIFICATION_TEMPLATES["time"],
            "who": CLARIFICATION_TEMPLATES["source"],
        }
        return templates.get(
            field,
            f"Can you provide more details about the {field.replace('_', ' ')}?",
        )
