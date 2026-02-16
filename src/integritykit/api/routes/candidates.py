"""API routes for COP candidate management and readiness evaluation.

Implements:
- FR-COP-READ-001: Readiness computation endpoints
- FR-COP-READ-002: Missing fields checklist
- FR-COP-READ-003: Next action recommendations
"""

from typing import Annotated, Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from integritykit.api.dependencies import (
    CurrentUser,
    RequireSearch,
    RequireViewBacklog,
)
from integritykit.models.cop_candidate import (
    ActionType,
    BlockingIssue,
    COPCandidate,
    ReadinessState,
    RecommendedAction,
    RiskTier,
)
from integritykit.models.user import User
from integritykit.services.database import COPCandidateRepository, get_collection
from integritykit.services.readiness import (
    FieldEvaluation,
    FieldStatus,
    ReadinessEvaluation,
    ReadinessService,
)

router = APIRouter(prefix="/candidates", tags=["COP Candidates"])


# ============================================================================
# Response Models
# ============================================================================


class FieldEvaluationResponse(BaseModel):
    """Field evaluation in API response."""

    field: str
    status: str
    value: Optional[str] = None
    notes: str


class BlockingIssueResponse(BaseModel):
    """Blocking issue in API response."""

    issue_type: str
    description: str
    severity: str


class RecommendedActionResponse(BaseModel):
    """Recommended action in API response."""

    action_type: str
    reason: str
    alternatives: list[str] = []


class ReadinessEvaluationResponse(BaseModel):
    """Response model for readiness evaluation."""

    candidate_id: str
    readiness_state: str
    field_evaluations: list[FieldEvaluationResponse]
    missing_fields: list[str]
    blocking_issues: list[BlockingIssueResponse]
    recommended_action: Optional[RecommendedActionResponse] = None
    explanation: str
    evaluated_at: str
    evaluation_method: str


class CandidateResponse(BaseModel):
    """Response model for COP candidate."""

    id: str
    cluster_id: str
    readiness_state: str
    risk_tier: str
    fields: dict
    missing_fields: list[str]
    blocking_issues: list[BlockingIssueResponse]
    recommended_action: Optional[RecommendedActionResponse] = None
    verification_count: int
    has_unresolved_conflicts: bool
    created_at: str
    updated_at: str


class CandidateListResponse(BaseModel):
    """Response model for candidate list."""

    candidates: list[CandidateResponse]
    total: int
    limit: int
    offset: int


class MissingFieldsResponse(BaseModel):
    """Response model for missing fields checklist (FR-COP-READ-002)."""

    candidate_id: str
    fields: list[FieldEvaluationResponse]
    missing: list[str]
    partial: list[str]
    complete: list[str]
    overall_status: str


class NextActionResponse(BaseModel):
    """Response model for next action recommendation (FR-COP-READ-003)."""

    candidate_id: str
    primary_action: str
    reason: str
    alternatives: list[str]
    clarification_template: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================


def _candidate_to_response(candidate: COPCandidate) -> CandidateResponse:
    """Convert COPCandidate to API response."""
    blocking_issues = [
        BlockingIssueResponse(
            issue_type=bi.issue_type,
            description=bi.description,
            severity=bi.severity.value if hasattr(bi.severity, "value") else str(bi.severity),
        )
        for bi in candidate.blocking_issues
    ]

    recommended_action = None
    if candidate.recommended_action:
        recommended_action = RecommendedActionResponse(
            action_type=candidate.recommended_action.action_type.value
            if hasattr(candidate.recommended_action.action_type, "value")
            else str(candidate.recommended_action.action_type),
            reason=candidate.recommended_action.reason,
            alternatives=candidate.recommended_action.alternatives,
        )

    return CandidateResponse(
        id=str(candidate.id),
        cluster_id=str(candidate.cluster_id),
        readiness_state=candidate.readiness_state.value
        if hasattr(candidate.readiness_state, "value")
        else str(candidate.readiness_state),
        risk_tier=candidate.risk_tier.value
        if hasattr(candidate.risk_tier, "value")
        else str(candidate.risk_tier),
        fields={
            "what": candidate.fields.what,
            "where": candidate.fields.where,
            "when": candidate.fields.when.description or "",
            "who": candidate.fields.who,
            "so_what": candidate.fields.so_what,
        },
        missing_fields=candidate.missing_fields,
        blocking_issues=blocking_issues,
        recommended_action=recommended_action,
        verification_count=len(candidate.verifications),
        has_unresolved_conflicts=candidate.has_unresolved_conflicts,
        created_at=candidate.created_at.isoformat(),
        updated_at=candidate.updated_at.isoformat(),
    )


def _evaluation_to_response(evaluation: ReadinessEvaluation) -> ReadinessEvaluationResponse:
    """Convert ReadinessEvaluation to API response."""
    field_evals = [
        FieldEvaluationResponse(
            field=fe.field,
            status=fe.status.value if hasattr(fe.status, "value") else str(fe.status),
            value=fe.value,
            notes=fe.notes,
        )
        for fe in evaluation.field_evaluations
    ]

    blocking_issues = [
        BlockingIssueResponse(
            issue_type=bi.issue_type,
            description=bi.description,
            severity=bi.severity.value if hasattr(bi.severity, "value") else str(bi.severity),
        )
        for bi in evaluation.blocking_issues
    ]

    recommended_action = None
    if evaluation.recommended_action:
        recommended_action = RecommendedActionResponse(
            action_type=evaluation.recommended_action.action_type.value
            if hasattr(evaluation.recommended_action.action_type, "value")
            else str(evaluation.recommended_action.action_type),
            reason=evaluation.recommended_action.reason,
            alternatives=evaluation.recommended_action.alternatives,
        )

    return ReadinessEvaluationResponse(
        candidate_id=evaluation.candidate_id,
        readiness_state=evaluation.readiness_state.value
        if hasattr(evaluation.readiness_state, "value")
        else str(evaluation.readiness_state),
        field_evaluations=field_evals,
        missing_fields=evaluation.missing_fields,
        blocking_issues=blocking_issues,
        recommended_action=recommended_action,
        explanation=evaluation.explanation,
        evaluated_at=evaluation.evaluated_at.isoformat(),
        evaluation_method=evaluation.evaluation_method,
    )


# ============================================================================
# Endpoints
# ============================================================================


@router.get("", response_model=CandidateListResponse)
async def list_candidates(
    user: CurrentUser,
    _: None = RequireViewBacklog,
    readiness_state: Optional[str] = Query(
        None, description="Filter by readiness state"
    ),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CandidateListResponse:
    """List COP candidates for the user's workspace.

    Requires VIEW_BACKLOG permission.
    """
    workspace_id = user.slack_team_id

    candidate_repo = COPCandidateRepository()

    # Get cluster IDs for workspace
    cluster_collection = get_collection("clusters")
    cluster_ids = []
    async for doc in cluster_collection.find(
        {"workspace_id": workspace_id},
        {"_id": 1},
    ):
        cluster_ids.append(doc["_id"])

    if not cluster_ids:
        return CandidateListResponse(
            candidates=[],
            total=0,
            limit=limit,
            offset=offset,
        )

    candidates = await candidate_repo.list_by_workspace(
        cluster_ids=cluster_ids,
        readiness_state=readiness_state,
        limit=limit,
        offset=offset,
    )

    # Get total count
    query = {"cluster_id": {"$in": cluster_ids}}
    if readiness_state:
        query["readiness_state"] = readiness_state
    total = await candidate_repo.collection.count_documents(query)

    return CandidateListResponse(
        candidates=[_candidate_to_response(c) for c in candidates],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{candidate_id}", response_model=CandidateResponse)
async def get_candidate(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> CandidateResponse:
    """Get a specific COP candidate by ID.

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    return _candidate_to_response(candidate)


@router.post("/{candidate_id}/evaluate", response_model=ReadinessEvaluationResponse)
async def evaluate_candidate_readiness(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
    use_llm: bool = Query(False, description="Use LLM for evaluation"),
) -> ReadinessEvaluationResponse:
    """Evaluate readiness state for a COP candidate (FR-COP-READ-001).

    Computes the readiness state (Ready-Verified, Ready-In Review, Blocked)
    based on field completeness, verification status, and conflicts.

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # Create readiness service (without LLM client for now)
    readiness_service = ReadinessService(use_llm=False)

    # Evaluate readiness
    evaluation = await readiness_service.evaluate_readiness(
        candidate, use_llm=use_llm
    )

    # Save evaluation results to database
    blocking_issues_dicts = [
        {
            "issue_type": bi.issue_type,
            "description": bi.description,
            "severity": bi.severity.value if hasattr(bi.severity, "value") else str(bi.severity),
        }
        for bi in evaluation.blocking_issues
    ]

    recommended_action_dict = None
    if evaluation.recommended_action:
        recommended_action_dict = {
            "action_type": evaluation.recommended_action.action_type.value
            if hasattr(evaluation.recommended_action.action_type, "value")
            else str(evaluation.recommended_action.action_type),
            "reason": evaluation.recommended_action.reason,
            "alternatives": evaluation.recommended_action.alternatives,
        }

    await candidate_repo.update_readiness_evaluation(
        candidate_id=obj_id,
        readiness_state=evaluation.readiness_state.value
        if hasattr(evaluation.readiness_state, "value")
        else str(evaluation.readiness_state),
        missing_fields=evaluation.missing_fields,
        blocking_issues=blocking_issues_dicts,
        recommended_action=recommended_action_dict,
        updated_by=user.id,
    )

    return _evaluation_to_response(evaluation)


@router.get("/{candidate_id}/fields", response_model=MissingFieldsResponse)
async def get_missing_fields(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> MissingFieldsResponse:
    """Get missing/weak fields checklist for a candidate (FR-COP-READ-002).

    Returns field-by-field assessment showing which fields are complete,
    partial, or missing.

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    readiness_service = ReadinessService(use_llm=False)
    field_evaluations = readiness_service._evaluate_fields(candidate)

    missing = [fe.field for fe in field_evaluations if fe.status == FieldStatus.MISSING]
    partial = [fe.field for fe in field_evaluations if fe.status == FieldStatus.PARTIAL]
    complete = [fe.field for fe in field_evaluations if fe.status == FieldStatus.COMPLETE]

    # Determine overall status
    if missing:
        overall_status = "incomplete"
    elif partial:
        overall_status = "needs_improvement"
    else:
        overall_status = "complete"

    return MissingFieldsResponse(
        candidate_id=candidate_id,
        fields=[
            FieldEvaluationResponse(
                field=fe.field,
                status=fe.status.value if hasattr(fe.status, "value") else str(fe.status),
                value=fe.value,
                notes=fe.notes,
            )
            for fe in field_evaluations
        ],
        missing=missing,
        partial=partial,
        complete=complete,
        overall_status=overall_status,
    )


@router.get("/{candidate_id}/next-action", response_model=NextActionResponse)
async def get_next_action(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> NextActionResponse:
    """Get recommended next action for a candidate (FR-COP-READ-003).

    Returns the best next action for the facilitator to take on this
    candidate, with alternatives and a clarification template if applicable.

    Requires VIEW_BACKLOG permission.
    """
    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    readiness_service = ReadinessService(use_llm=False)

    # Get evaluation to determine recommended action
    evaluation = await readiness_service.evaluate_readiness(candidate, use_llm=False)

    if not evaluation.recommended_action:
        return NextActionResponse(
            candidate_id=candidate_id,
            primary_action="none",
            reason="No action required at this time",
            alternatives=[],
            clarification_template=None,
        )

    # Get clarification template if action is to add evidence/clarification
    clarification_template = None
    if evaluation.recommended_action.action_type == ActionType.ADD_EVIDENCE:
        # Find the first missing critical field
        for field in evaluation.missing_fields:
            if field in ["where", "when", "who"]:
                clarification_template = readiness_service.get_clarification_template(field)
                break

    return NextActionResponse(
        candidate_id=candidate_id,
        primary_action=evaluation.recommended_action.action_type.value
        if hasattr(evaluation.recommended_action.action_type, "value")
        else str(evaluation.recommended_action.action_type),
        reason=evaluation.recommended_action.reason,
        alternatives=evaluation.recommended_action.alternatives,
        clarification_template=clarification_template,
    )


@router.get("/by-state/{state}", response_model=CandidateListResponse)
async def list_candidates_by_state(
    state: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> CandidateListResponse:
    """List COP candidates filtered by readiness state.

    Valid states: in_review, verified, blocked

    Requires VIEW_BACKLOG permission.
    """
    valid_states = ["in_review", "verified", "blocked"]
    if state not in valid_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid state. Must be one of: {', '.join(valid_states)}",
        )

    workspace_id = user.slack_team_id
    candidate_repo = COPCandidateRepository()

    candidates = await candidate_repo.list_by_readiness_state(
        workspace_id=workspace_id,
        readiness_state=state,
        limit=limit,
        offset=offset,
    )

    # Get total count for this state
    cluster_collection = get_collection("clusters")
    cluster_ids = []
    async for doc in cluster_collection.find(
        {"workspace_id": workspace_id},
        {"_id": 1},
    ):
        cluster_ids.append(doc["_id"])

    total = 0
    if cluster_ids:
        total = await candidate_repo.count_by_state(cluster_ids, state)

    return CandidateListResponse(
        candidates=[_candidate_to_response(c) for c in candidates],
        total=total,
        limit=limit,
        offset=offset,
    )


# ============================================================================
# Risk Tier Classification (FR-COP-RISK-001)
# ============================================================================


class RiskSignalResponse(BaseModel):
    """Risk signal in API response."""

    signal_type: str
    keyword_matched: str
    context: str
    severity: str


class RiskClassificationResponse(BaseModel):
    """Response model for risk classification."""

    candidate_id: str
    computed_tier: str
    final_tier: str
    signals: list[RiskSignalResponse]
    has_override: bool
    override_justification: Optional[str] = None
    explanation: str
    classified_at: str


class RiskTierOverrideRequest(BaseModel):
    """Request to override risk tier."""

    new_tier: str = Field(..., description="New risk tier (routine, elevated, high_stakes)")
    justification: str = Field(
        ...,
        min_length=10,
        description="Required justification for override",
    )


class PublishGateResponse(BaseModel):
    """Response for publish gate check."""

    allowed: bool
    requires_override: bool
    override_reason: Optional[str] = None
    warnings: list[str]


class HighStakesOverrideRequest(BaseModel):
    """Request to apply high-stakes override."""

    justification: str = Field(
        ...,
        min_length=20,
        description="Detailed justification for publishing unverified high-stakes content",
    )


class HighStakesOverrideResponse(BaseModel):
    """Response for high-stakes override."""

    candidate_id: str
    override_type: str
    unconfirmed_label_applied: bool
    overridden_at: str


@router.get("/{candidate_id}/risk", response_model=RiskClassificationResponse)
async def get_risk_classification(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> RiskClassificationResponse:
    """Get risk classification for a candidate (FR-COP-RISK-001).

    Analyzes candidate content for high-stakes keywords and returns
    the computed risk tier with detected signals.

    Requires VIEW_BACKLOG permission.
    """
    from integritykit.services.risk_classification import RiskClassificationService

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    risk_service = RiskClassificationService()
    classification = risk_service.classify_candidate(candidate)

    signals = [
        RiskSignalResponse(
            signal_type=s.signal_type.value,
            keyword_matched=s.keyword_matched,
            context=s.context,
            severity=s.severity.value,
        )
        for s in classification.signals
    ]

    return RiskClassificationResponse(
        candidate_id=classification.candidate_id,
        computed_tier=classification.computed_tier.value,
        final_tier=classification.final_tier.value,
        signals=signals,
        has_override=classification.override is not None,
        override_justification=(
            classification.override.justification if classification.override else None
        ),
        explanation=classification.explanation,
        classified_at=classification.classified_at.isoformat(),
    )


@router.post("/{candidate_id}/risk/override", response_model=RiskClassificationResponse)
async def override_risk_tier(
    candidate_id: str,
    request: RiskTierOverrideRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> RiskClassificationResponse:
    """Override the risk tier for a candidate (FR-COP-RISK-001).

    Allows facilitators to adjust the computed risk tier with
    a required justification. All overrides are audit logged.

    Requires VIEW_BACKLOG permission.
    """
    from integritykit.services.risk_classification import RiskClassificationService

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    # Validate tier value
    valid_tiers = ["routine", "elevated", "high_stakes"]
    if request.new_tier not in valid_tiers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid risk tier. Must be one of: {', '.join(valid_tiers)}",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    risk_service = RiskClassificationService()

    try:
        new_tier = RiskTier(request.new_tier)
        candidate = await risk_service.override_risk_tier(
            candidate=candidate,
            new_tier=new_tier,
            user=user,
            justification=request.justification,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Save updated candidate
    await candidate_repo.update(
        obj_id,
        {
            "risk_tier": candidate.risk_tier.value,
            "risk_tier_override": candidate.risk_tier_override.model_dump()
            if candidate.risk_tier_override
            else None,
        },
    )

    # Return updated classification
    classification = risk_service.classify_candidate(candidate)

    signals = [
        RiskSignalResponse(
            signal_type=s.signal_type.value,
            keyword_matched=s.keyword_matched,
            context=s.context,
            severity=s.severity.value,
        )
        for s in classification.signals
    ]

    return RiskClassificationResponse(
        candidate_id=classification.candidate_id,
        computed_tier=classification.computed_tier.value,
        final_tier=classification.final_tier.value,
        signals=signals,
        has_override=True,
        override_justification=request.justification,
        explanation=classification.explanation,
        classified_at=classification.classified_at.isoformat(),
    )


# ============================================================================
# Publish Gates (FR-COP-GATE-001)
# ============================================================================


@router.get("/{candidate_id}/publish-gate", response_model=PublishGateResponse)
async def check_publish_gate(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> PublishGateResponse:
    """Check if a candidate passes publish gates (FR-COP-GATE-001).

    High-stakes candidates require VERIFIED status or explicit override.

    Requires VIEW_BACKLOG permission.
    """
    from integritykit.services.risk_classification import (
        PublishGateService,
        RiskClassificationService,
    )

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    # Get classification and check gate
    risk_service = RiskClassificationService()
    gate_service = PublishGateService()

    classification = risk_service.classify_candidate(candidate)
    result = gate_service.check_publish_gate(candidate, classification)

    return PublishGateResponse(
        allowed=result.allowed,
        requires_override=result.requires_override,
        override_reason=result.override_reason,
        warnings=result.warnings,
    )


@router.post("/{candidate_id}/publish-gate/override", response_model=HighStakesOverrideResponse)
async def apply_high_stakes_override(
    candidate_id: str,
    request: HighStakesOverrideRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> HighStakesOverrideResponse:
    """Apply override for high-stakes unverified content (FR-COP-GATE-001).

    Allows publishing high-stakes content that isn't verified, with
    required justification and automatic UNCONFIRMED labeling.

    Requires VIEW_BACKLOG permission.
    """
    from integritykit.services.risk_classification import PublishGateService

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    gate_service = PublishGateService()

    try:
        override = await gate_service.apply_high_stakes_override(
            candidate=candidate,
            user=user,
            justification=request.justification,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return HighStakesOverrideResponse(
        candidate_id=str(override.candidate_id),
        override_type=override.override_type,
        unconfirmed_label_applied=override.unconfirmed_label_applied,
        overridden_at=override.overridden_at.isoformat(),
    )


# ============================================================================
# Duplicate Merge Endpoints (FR-BACKLOG-003)
# ============================================================================


class DuplicateSuggestionResponse(BaseModel):
    """Response model for a duplicate candidate suggestion."""

    candidate_id: str
    headline: str
    similarity_score: float
    readiness_state: str


class DuplicateSuggestionsResponse(BaseModel):
    """Response model for duplicate suggestions list."""

    candidate_id: str
    suggestions: list[DuplicateSuggestionResponse]


class MergeRequest(BaseModel):
    """Request model for merging candidates."""

    secondary_candidate_ids: list[str] = Field(
        ...,
        description="IDs of candidates to merge into the primary",
        min_length=1,
    )
    merge_reason: Optional[str] = Field(
        None,
        description="Reason for merging these candidates",
    )


class MergeResultResponse(BaseModel):
    """Response model for merge operation result."""

    primary_candidate_id: str
    merged_candidate_ids: list[str]
    signals_added: int
    message: str


@router.get("/{candidate_id}/duplicates", response_model=DuplicateSuggestionsResponse)
async def get_duplicate_suggestions(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
    limit: int = Query(5, ge=1, le=20),
) -> DuplicateSuggestionsResponse:
    """Get suggested duplicate candidates for a candidate (FR-BACKLOG-003).

    Uses semantic similarity to find candidates that may describe
    the same incident or event.

    Requires VIEW_BACKLOG permission.
    """
    from integritykit.services.candidate_merge import CandidateMergeService

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(obj_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found",
        )

    merge_service = CandidateMergeService(candidate_repository=candidate_repo)
    suggestions = await merge_service.suggest_duplicates(candidate, limit=limit)

    return DuplicateSuggestionsResponse(
        candidate_id=candidate_id,
        suggestions=[
            DuplicateSuggestionResponse(
                candidate_id=str(s.candidate_id),
                headline=s.headline,
                similarity_score=s.similarity_score,
                readiness_state=s.readiness_state,
            )
            for s in suggestions
        ],
    )


@router.post("/{candidate_id}/merge", response_model=MergeResultResponse)
async def merge_candidates(
    candidate_id: str,
    request: MergeRequest,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> MergeResultResponse:
    """Merge duplicate candidates into a primary candidate (FR-BACKLOG-003).

    The primary candidate absorbs all signals from secondary candidates.
    Secondary candidates are archived with merge metadata.

    Requires VIEW_BACKLOG permission and MERGE_CANDIDATES permission.
    """
    from integritykit.services.candidate_merge import CandidateMergeService
    from integritykit.services.rbac import AccessDeniedError, RBACService
    from integritykit.models.user import Permission

    # Check MERGE_CANDIDATES permission
    rbac = RBACService()
    if not user.has_permission(Permission.MERGE_CANDIDATES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: merge_candidates required",
        )

    try:
        primary_id = ObjectId(candidate_id)
        secondary_ids = [ObjectId(sid) for sid in request.secondary_candidate_ids]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    candidate = await candidate_repo.get_by_id(primary_id)

    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Primary candidate not found",
        )

    merge_service = CandidateMergeService(candidate_repository=candidate_repo)

    try:
        result = await merge_service.merge_candidates(
            primary_candidate_id=primary_id,
            secondary_candidate_ids=secondary_ids,
            user=user,
            merge_reason=request.merge_reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return MergeResultResponse(
        primary_candidate_id=str(result.primary_candidate.id),
        merged_candidate_ids=[str(mid) for mid in result.merged_candidate_ids],
        signals_added=result.signals_added,
        message=f"Successfully merged {len(result.merged_candidate_ids)} candidate(s)",
    )


@router.post("/{candidate_id}/unmerge", response_model=CandidateResponse)
async def unmerge_candidate(
    candidate_id: str,
    user: CurrentUser,
    _: None = RequireViewBacklog,
) -> CandidateResponse:
    """Restore a previously merged candidate (FR-BACKLOG-003).

    Restores the candidate to IN_REVIEW state and removes merge metadata.

    Requires VIEW_BACKLOG permission and MERGE_CANDIDATES permission.
    """
    from integritykit.services.candidate_merge import CandidateMergeService
    from integritykit.models.user import Permission

    # Check MERGE_CANDIDATES permission
    if not user.has_permission(Permission.MERGE_CANDIDATES):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied: merge_candidates required",
        )

    try:
        obj_id = ObjectId(candidate_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid candidate ID format",
        )

    candidate_repo = COPCandidateRepository()
    merge_service = CandidateMergeService(candidate_repository=candidate_repo)

    try:
        restored = await merge_service.unmerge_candidate(obj_id, user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return _candidate_to_response(restored)
