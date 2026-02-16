"""COP draft generation service with verification-aware wording.

Implements:
- FR-COPDRAFT-001: Generate COP line items with status labels and citations
- FR-COPDRAFT-002: Assemble drafts grouped by section
- FR-COP-WORDING-001: Wording guidance (hedged vs direct phrasing)
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

import structlog
from openai import AsyncOpenAI

from integritykit.llm.prompts.cop_draft_generation import (
    COP_DRAFT_GENERATION_OUTPUT_SCHEMA,
    COP_DRAFT_GENERATION_SYSTEM_PROMPT,
    COPCandidateFull,
    COPDraftOutput,
    EvidenceItem,
    format_cop_draft_generation_prompt,
)
from integritykit.models.cop_candidate import (
    COPCandidate,
    DraftWording,
    ReadinessState,
    RiskTier,
)

logger = structlog.get_logger(__name__)


class COPSection(str, Enum):
    """Sections in a COP update."""

    VERIFIED = "verified_updates"
    IN_REVIEW = "in_review_updates"
    DISPROVEN = "disproven_rumor_control"
    OPEN_QUESTIONS = "open_questions"


class WordingStyle(str, Enum):
    """Wording styles for COP line items."""

    DIRECT_FACTUAL = "direct_factual"
    HEDGED_UNCERTAIN = "hedged_uncertain"


@dataclass
class COPLineItem:
    """A single COP line item ready for publication."""

    candidate_id: str
    status_label: str  # VERIFIED, IN REVIEW, DISPROVEN
    line_item_text: str
    citations: list[str]
    wording_style: WordingStyle
    section: COPSection
    next_verification_step: Optional[str] = None
    recheck_time: Optional[str] = None
    generated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class COPDraft:
    """Complete COP update draft organized by section."""

    draft_id: str
    workspace_id: str
    title: str
    generated_at: datetime
    verified_items: list[COPLineItem]
    in_review_items: list[COPLineItem]
    disproven_items: list[COPLineItem]
    open_questions: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_items(self) -> int:
        """Total number of line items."""
        return (
            len(self.verified_items)
            + len(self.in_review_items)
            + len(self.disproven_items)
        )

    def to_markdown(self) -> str:
        """Convert draft to Markdown format."""
        lines = [f"# {self.title}", ""]
        lines.append(f"*Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*")
        lines.append("")

        if self.verified_items:
            lines.append("## Verified Updates")
            lines.append("")
            for item in self.verified_items:
                lines.append(f"- {item.line_item_text}")
            lines.append("")

        if self.in_review_items:
            lines.append("## In Review (Unconfirmed)")
            lines.append("")
            for item in self.in_review_items:
                lines.append(f"- {item.line_item_text}")
                if item.next_verification_step:
                    lines.append(f"  - *Next step: {item.next_verification_step}*")
                if item.recheck_time:
                    lines.append(f"  - *Recheck: {item.recheck_time}*")
            lines.append("")

        if self.disproven_items:
            lines.append("## Rumor Control / Corrections")
            lines.append("")
            for item in self.disproven_items:
                lines.append(f"- {item.line_item_text}")
            lines.append("")

        if self.open_questions:
            lines.append("## Open Questions / Gaps")
            lines.append("")
            for question in self.open_questions:
                lines.append(f"- {question}")
            lines.append("")

        return "\n".join(lines)

    def to_slack_blocks(self) -> list[dict[str, Any]]:
        """Convert draft to Slack Block Kit blocks."""
        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": self.title,
                "emoji": True,
            },
        })

        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f":clock3: Generated: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
                },
            ],
        })

        # Verified section
        if self.verified_items:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":white_check_mark: *Verified Updates*",
                },
            })
            for item in self.verified_items:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {item.line_item_text}",
                    },
                })

        # In Review section
        if self.in_review_items:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":hourglass: *In Review (Unconfirmed)*",
                },
            })
            for item in self.in_review_items:
                text = f"• {item.line_item_text}"
                if item.next_verification_step:
                    text += f"\n   _Next: {item.next_verification_step}_"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": text,
                    },
                })

        # Disproven section
        if self.disproven_items:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":no_entry: *Rumor Control / Corrections*",
                },
            })
            for item in self.disproven_items:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"• {item.line_item_text}",
                    },
                })

        # Open questions
        if self.open_questions:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":grey_question: *Open Questions / Gaps*",
                },
            })
            questions_text = "\n".join(f"• {q}" for q in self.open_questions)
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": questions_text,
                },
            })

        return blocks


class DraftService:
    """Service for generating COP drafts with verification-aware wording.

    Implements FR-COPDRAFT-001, FR-COPDRAFT-002, FR-COP-WORDING-001.
    """

    # Hedging phrases for In-Review items
    HEDGING_PREFIXES = [
        "Reports indicate",
        "Unconfirmed:",
        "Seeking confirmation of",
        "Initial reports suggest",
        "Unverified:",
    ]

    # Direct phrasing for Verified items
    DIRECT_VERBS = ["is", "has", "confirmed", "established", "verified"]

    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4o",  # Use more capable model for nuanced writing
        use_llm: bool = True,
    ):
        """Initialize DraftService.

        Args:
            openai_client: OpenAI client for LLM-based generation
            model: Model to use for draft generation
            use_llm: Whether to use LLM for generation
        """
        self.client = openai_client
        self.model = model
        self.use_llm = use_llm and openai_client is not None

    async def generate_line_item(
        self,
        candidate: COPCandidate,
        use_llm: Optional[bool] = None,
    ) -> COPLineItem:
        """Generate a COP line item from a candidate.

        Args:
            candidate: COP candidate to generate line item from
            use_llm: Override instance-level LLM setting

        Returns:
            COPLineItem ready for inclusion in draft
        """
        should_use_llm = use_llm if use_llm is not None else self.use_llm

        if should_use_llm and self.client:
            try:
                return await self._generate_with_llm(candidate)
            except Exception as e:
                logger.warning(
                    "LLM generation failed, falling back to rule-based",
                    candidate_id=str(candidate.id),
                    error=str(e),
                )
                return self._generate_rule_based(candidate)
        else:
            return self._generate_rule_based(candidate)

    def _generate_rule_based(self, candidate: COPCandidate) -> COPLineItem:
        """Rule-based line item generation.

        Args:
            candidate: COP candidate

        Returns:
            Generated COPLineItem
        """
        # Determine section and status label
        if candidate.readiness_state == ReadinessState.VERIFIED:
            section = COPSection.VERIFIED
            status_label = "VERIFIED"
            wording_style = WordingStyle.DIRECT_FACTUAL
        elif candidate.readiness_state == ReadinessState.IN_REVIEW:
            section = COPSection.IN_REVIEW
            status_label = "IN REVIEW"
            wording_style = WordingStyle.HEDGED_UNCERTAIN
        else:
            section = COPSection.OPEN_QUESTIONS
            status_label = "BLOCKED"
            wording_style = WordingStyle.HEDGED_UNCERTAIN

        # Build the line item text with appropriate wording
        line_text = self._apply_wording_guidance(candidate, wording_style)

        # Gather citations
        citations = []
        for permalink in candidate.evidence.slack_permalinks:
            citations.append(permalink.url)
        for source in candidate.evidence.external_sources:
            citations.append(source.url)

        # Add citations to line item
        if citations:
            citation_text = " ".join(f"[{i+1}]" for i in range(len(citations)))
            line_text = f"{line_text} {citation_text}"

        # Determine next verification step for in-review items (FR-COP-WORDING-002)
        # Applies to both HIGH_STAKES and ELEVATED risk tiers
        next_step = None
        recheck_time = None

        if candidate.readiness_state == ReadinessState.IN_REVIEW:
            # High-stakes items need urgent recheck and specific next steps
            if candidate.risk_tier == RiskTier.HIGH_STAKES:
                next_step = self._determine_high_stakes_next_step(candidate)
                recheck_time = "Within 30 minutes"

            # Elevated items need near-term recheck
            elif candidate.risk_tier == RiskTier.ELEVATED:
                next_step = self._determine_elevated_next_step(candidate)
                recheck_time = "Within 2 hours"

            # Routine items may optionally have next steps
            elif candidate.risk_tier == RiskTier.ROUTINE:
                if not candidate.verifications:
                    next_step = "Await verification from any available verifier"
                recheck_time = "Within 4 hours"

        logger.info(
            "Generated rule-based line item",
            candidate_id=str(candidate.id),
            section=section.value,
            wording_style=wording_style.value,
        )

        return COPLineItem(
            candidate_id=str(candidate.id),
            status_label=status_label,
            line_item_text=line_text,
            citations=citations,
            wording_style=wording_style,
            section=section,
            next_verification_step=next_step,
            recheck_time=recheck_time,
        )

    def _determine_high_stakes_next_step(self, candidate: COPCandidate) -> str:
        """Determine next verification step for high-stakes items.

        Implements FR-COP-WORDING-002 for HIGH_STAKES risk tier.

        Args:
            candidate: COP candidate

        Returns:
            Specific next verification step
        """
        # Priority 1: Need to identify source
        if not candidate.fields.who:
            return "URGENT: Identify and contact primary source for direct confirmation"

        # Priority 2: No verification attempts yet
        if not candidate.verifications:
            return "URGENT: Assign verification to available verifier immediately"

        # Priority 3: Has verification attempts - check confidence levels
        low_confidence = [
            v for v in candidate.verifications
            if v.confidence_level.value == "low"
        ]

        if low_confidence:
            return "URGENT: Low-confidence verification - seek additional confirmation source"

        # Priority 4: Has verifications but candidate still in review
        # (may need secondary confirmation or higher confidence)
        return "URGENT: Seek secondary independent confirmation before publishing"

    def _determine_elevated_next_step(self, candidate: COPCandidate) -> str:
        """Determine next verification step for elevated risk items.

        Implements FR-COP-WORDING-002 for ELEVATED risk tier.

        Args:
            candidate: COP candidate

        Returns:
            Specific next verification step
        """
        # Check what's missing
        if not candidate.fields.who:
            return "Identify primary source for verification"

        if not candidate.fields.where:
            return "Confirm exact location details"

        if not candidate.fields.when or not candidate.fields.when.description:
            return "Confirm timing/recency of information"

        if not candidate.verifications:
            return "Request verification from available verifier"

        # Has verification attempts - check if we need more confidence
        low_confidence = [
            v for v in candidate.verifications
            if v.confidence_level.value == "low"
        ]
        if low_confidence:
            return "Low-confidence verification - seek additional confirmation"

        return "Seek additional confirmation if possible"

    def _apply_wording_guidance(
        self,
        candidate: COPCandidate,
        style: WordingStyle,
    ) -> str:
        """Apply wording guidance based on verification status.

        Implements FR-COP-WORDING-001.

        Args:
            candidate: COP candidate
            style: Wording style to apply

        Returns:
            Formatted line item text with appropriate wording
        """
        # Build base statement from fields
        what = candidate.fields.what or "Situation developing"
        where = candidate.fields.where or ""
        when = candidate.fields.when.description or ""
        who = candidate.fields.who or ""
        so_what = candidate.fields.so_what or ""

        # Build location/time clause
        location_time = ""
        if where and when:
            location_time = f" at {where} as of {when}"
        elif where:
            location_time = f" at {where}"
        elif when:
            location_time = f" as of {when}"

        if style == WordingStyle.DIRECT_FACTUAL:
            # Verified: Direct, factual phrasing
            # Example: "Main Street Bridge is closed to all traffic as of 14:00 PST."
            statement = f"{what}{location_time}."
            if so_what:
                statement = f"{statement} {so_what}"

        else:
            # In-Review: Hedged, uncertain phrasing
            # Example: "Unconfirmed: Reports indicate Main Street Bridge may be closed."
            hedging_prefix = "Unconfirmed:"

            # Add uncertainty markers to the statement
            what_hedged = what.replace(" is ", " may be ").replace(" are ", " may be ")
            statement = f"{hedging_prefix} Reports indicate {what_hedged.lower()}{location_time}."

            if so_what:
                statement = f"{statement} If confirmed, {so_what.lower()}"

        # Add source attribution if available
        if who and style == WordingStyle.DIRECT_FACTUAL:
            statement = f"{statement} (Source: {who})"

        return statement

    async def _generate_with_llm(self, candidate: COPCandidate) -> COPLineItem:
        """LLM-based line item generation.

        Args:
            candidate: COP candidate

        Returns:
            Generated COPLineItem
        """
        # Prepare evidence pack
        evidence_pack: list[EvidenceItem] = []
        for permalink in candidate.evidence.slack_permalinks:
            evidence_pack.append({
                "source_type": "slack_permalink",
                "url": permalink.url,
                "description": permalink.description,
                "timestamp": None,
            })
        for source in candidate.evidence.external_sources:
            evidence_pack.append({
                "source_type": "external_url",
                "url": source.url,
                "description": source.description,
                "timestamp": source.retrieved_at.isoformat() if source.retrieved_at else None,
            })

        # Determine verification status
        if candidate.readiness_state == ReadinessState.VERIFIED:
            verification_status = "verified"
        elif candidate.readiness_state == ReadinessState.IN_REVIEW:
            verification_status = "in_review"
        else:
            verification_status = "in_review"  # Blocked items treated as in_review for wording

        # Prepare candidate data
        candidate_data: COPCandidateFull = {
            "candidate_id": str(candidate.id),
            "what": candidate.fields.what or "",
            "where": candidate.fields.where or "",
            "when": candidate.fields.when.description or "",
            "who": candidate.fields.who or "",
            "so_what": candidate.fields.so_what or "",
            "evidence_pack": evidence_pack,
            "verification_status": verification_status,
            "risk_tier": candidate.risk_tier.value,
            "conflicts_resolved": not candidate.has_unresolved_conflicts,
            "recheck_time": None,
        }

        user_prompt = format_cop_draft_generation_prompt(candidate_data)

        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0.3,
            messages=[
                {"role": "system", "content": COP_DRAFT_GENERATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        result: COPDraftOutput = json.loads(content)

        # Map section placement
        section_map = {
            "verified_updates": COPSection.VERIFIED,
            "in_review_updates": COPSection.IN_REVIEW,
            "disproven_rumor_control": COPSection.DISPROVEN,
            "open_questions": COPSection.OPEN_QUESTIONS,
        }
        section = section_map.get(result["section_placement"], COPSection.IN_REVIEW)

        # Map wording style
        style_map = {
            "direct_factual": WordingStyle.DIRECT_FACTUAL,
            "hedged_uncertain": WordingStyle.HEDGED_UNCERTAIN,
        }
        wording_style = style_map.get(result["wording_style"], WordingStyle.HEDGED_UNCERTAIN)

        logger.info(
            "Generated LLM line item",
            candidate_id=str(candidate.id),
            section=section.value,
            wording_style=wording_style.value,
            model=self.model,
        )

        return COPLineItem(
            candidate_id=str(candidate.id),
            status_label=result["status_label"],
            line_item_text=result["line_item_text"],
            citations=result["citations"],
            wording_style=wording_style,
            section=section,
            next_verification_step=result.get("next_verification_step"),
            recheck_time=result.get("recheck_time"),
        )

    async def generate_draft(
        self,
        workspace_id: str,
        candidates: list[COPCandidate],
        title: Optional[str] = None,
        include_open_questions: bool = True,
    ) -> COPDraft:
        """Generate a complete COP draft from multiple candidates.

        Implements FR-COPDRAFT-002: Assemble draft grouped by section.

        Args:
            workspace_id: Workspace ID
            candidates: List of COP candidates to include
            title: Optional title for the draft
            include_open_questions: Whether to include open questions section

        Returns:
            COPDraft organized by section
        """
        from bson import ObjectId

        draft_id = str(ObjectId())
        now = datetime.utcnow()

        if not title:
            title = f"COP Update - {now.strftime('%Y-%m-%d %H:%M UTC')}"

        verified_items: list[COPLineItem] = []
        in_review_items: list[COPLineItem] = []
        disproven_items: list[COPLineItem] = []
        open_questions: list[str] = []

        # Generate line items for each candidate
        for candidate in candidates:
            try:
                line_item = await self.generate_line_item(candidate)

                if line_item.section == COPSection.VERIFIED:
                    verified_items.append(line_item)
                elif line_item.section == COPSection.IN_REVIEW:
                    in_review_items.append(line_item)
                elif line_item.section == COPSection.DISPROVEN:
                    disproven_items.append(line_item)
                else:
                    # Blocked items go to open questions
                    if include_open_questions:
                        open_questions.append(
                            f"Pending clarification: {candidate.fields.what or 'Unknown topic'}"
                        )

            except Exception as e:
                logger.error(
                    "Failed to generate line item for candidate",
                    candidate_id=str(candidate.id),
                    error=str(e),
                )

        # Add standard open questions if enabled
        if include_open_questions:
            # Check for common gaps
            total_items = len(verified_items) + len(in_review_items)
            if total_items == 0:
                open_questions.append("No COP items available for this period")

        logger.info(
            "Generated COP draft",
            draft_id=draft_id,
            workspace_id=workspace_id,
            verified_count=len(verified_items),
            in_review_count=len(in_review_items),
            disproven_count=len(disproven_items),
            open_questions_count=len(open_questions),
        )

        return COPDraft(
            draft_id=draft_id,
            workspace_id=workspace_id,
            title=title,
            generated_at=now,
            verified_items=verified_items,
            in_review_items=in_review_items,
            disproven_items=disproven_items,
            open_questions=open_questions,
            metadata={
                "candidate_count": len(candidates),
                "generator_model": self.model if self.use_llm else "rule_based",
            },
        )

    def save_draft_wording(
        self,
        candidate: COPCandidate,
        line_item: COPLineItem,
    ) -> COPCandidate:
        """Save generated draft wording to candidate.

        Args:
            candidate: COP candidate to update
            line_item: Generated line item

        Returns:
            Updated candidate with draft wording
        """
        candidate.draft_wording = DraftWording(
            headline=candidate.fields.what or "",
            body=line_item.line_item_text,
            hedging_applied=line_item.wording_style == WordingStyle.HEDGED_UNCERTAIN,
            recheck_time=datetime.fromisoformat(line_item.recheck_time)
            if line_item.recheck_time and ":" in line_item.recheck_time
            else None,
            next_verification_step=line_item.next_verification_step,
        )
        candidate.updated_at = datetime.utcnow()

        return candidate


# ============================================================================
# Delta Summary (FR-COPDRAFT-003)
# ============================================================================


class ChangeType(str, Enum):
    """Types of changes between COP drafts."""

    NEW = "new"
    REMOVED = "removed"
    STATUS_CHANGE = "status_change"
    CONTENT_UPDATE = "content_update"
    SECTION_MOVE = "section_move"


@dataclass
class DeltaChange:
    """A single change between COP drafts."""

    change_type: ChangeType
    candidate_id: str
    headline: str
    previous_status: Optional[str] = None
    new_status: Optional[str] = None
    previous_section: Optional[str] = None
    new_section: Optional[str] = None
    description: str = ""


@dataclass
class COPDeltaSummary:
    """Summary of what changed since the last COP draft (FR-COPDRAFT-003)."""

    current_draft_id: str
    previous_draft_id: Optional[str]
    generated_at: datetime
    changes: list[DeltaChange]
    summary_text: str

    @property
    def new_items_count(self) -> int:
        """Count of newly added items."""
        return sum(1 for c in self.changes if c.change_type == ChangeType.NEW)

    @property
    def removed_items_count(self) -> int:
        """Count of removed items."""
        return sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)

    @property
    def status_changes_count(self) -> int:
        """Count of status changes."""
        return sum(1 for c in self.changes if c.change_type == ChangeType.STATUS_CHANGE)

    @property
    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return len(self.changes) > 0

    def to_markdown(self) -> str:
        """Convert delta summary to Markdown format."""
        lines = ["## What's Changed Since Last COP", ""]

        if not self.has_changes:
            lines.append("*No changes since the previous COP draft.*")
            return "\n".join(lines)

        lines.append(self.summary_text)
        lines.append("")

        # Group changes by type
        new_items = [c for c in self.changes if c.change_type == ChangeType.NEW]
        removed = [c for c in self.changes if c.change_type == ChangeType.REMOVED]
        status_changes = [c for c in self.changes if c.change_type == ChangeType.STATUS_CHANGE]
        section_moves = [c for c in self.changes if c.change_type == ChangeType.SECTION_MOVE]
        content_updates = [c for c in self.changes if c.change_type == ChangeType.CONTENT_UPDATE]

        if new_items:
            lines.append("### New Items")
            for c in new_items:
                lines.append(f"- **{c.headline}** ({c.new_section})")
            lines.append("")

        if status_changes:
            lines.append("### Status Changes")
            for c in status_changes:
                lines.append(
                    f"- **{c.headline}**: {c.previous_status} → {c.new_status}"
                )
            lines.append("")

        if section_moves:
            lines.append("### Section Moves")
            for c in section_moves:
                lines.append(
                    f"- **{c.headline}**: moved from {c.previous_section} to {c.new_section}"
                )
            lines.append("")

        if removed:
            lines.append("### Removed Items")
            for c in removed:
                lines.append(f"- ~~{c.headline}~~ (was in {c.previous_section})")
            lines.append("")

        if content_updates:
            lines.append("### Content Updates")
            for c in content_updates:
                lines.append(f"- **{c.headline}**: {c.description}")
            lines.append("")

        return "\n".join(lines)


class DeltaSummaryService:
    """Service for generating delta summaries between COP drafts.

    Implements FR-COPDRAFT-003: "What changed since last COP" delta summary.
    """

    def __init__(self, llm_client: Optional[AsyncOpenAI] = None):
        """Initialize delta summary service.

        Args:
            llm_client: Optional LLM client for generating natural language summaries
        """
        self.llm_client = llm_client

    def compare_drafts(
        self,
        current_draft: COPDraft,
        previous_draft: Optional[COPDraft],
    ) -> COPDeltaSummary:
        """Compare two COP drafts and generate a delta summary.

        Args:
            current_draft: The current/new COP draft
            previous_draft: The previous COP draft (None for first draft)

        Returns:
            Delta summary with all changes
        """
        changes: list[DeltaChange] = []

        if previous_draft is None:
            # First draft - all items are new
            for item in current_draft.verified_items:
                changes.append(
                    DeltaChange(
                        change_type=ChangeType.NEW,
                        candidate_id=item.candidate_id,
                        headline=self._extract_headline(item.line_item_text),
                        new_status="VERIFIED",
                        new_section=COPSection.VERIFIED.value,
                        description="New verified item",
                    )
                )
            for item in current_draft.in_review_items:
                changes.append(
                    DeltaChange(
                        change_type=ChangeType.NEW,
                        candidate_id=item.candidate_id,
                        headline=self._extract_headline(item.line_item_text),
                        new_status="IN_REVIEW",
                        new_section=COPSection.IN_REVIEW.value,
                        description="New in-review item",
                    )
                )
            for item in current_draft.disproven_items:
                changes.append(
                    DeltaChange(
                        change_type=ChangeType.NEW,
                        candidate_id=item.candidate_id,
                        headline=self._extract_headline(item.line_item_text),
                        new_status="DISPROVEN",
                        new_section=COPSection.DISPROVEN.value,
                        description="New disproven item",
                    )
                )

            summary_text = self._generate_summary_text(changes, is_first_draft=True)

            return COPDeltaSummary(
                current_draft_id=current_draft.draft_id,
                previous_draft_id=None,
                generated_at=datetime.utcnow(),
                changes=changes,
                summary_text=summary_text,
            )

        # Build maps of items by candidate_id
        prev_items = self._build_item_map(previous_draft)
        curr_items = self._build_item_map(current_draft)

        # Find new items (in current but not in previous)
        for cid, (item, section) in curr_items.items():
            if cid not in prev_items:
                changes.append(
                    DeltaChange(
                        change_type=ChangeType.NEW,
                        candidate_id=cid,
                        headline=self._extract_headline(item.line_item_text),
                        new_status=item.status_label,
                        new_section=section,
                        description="Newly added to draft",
                    )
                )

        # Find removed items (in previous but not in current)
        for cid, (item, section) in prev_items.items():
            if cid not in curr_items:
                changes.append(
                    DeltaChange(
                        change_type=ChangeType.REMOVED,
                        candidate_id=cid,
                        headline=self._extract_headline(item.line_item_text),
                        previous_status=item.status_label,
                        previous_section=section,
                        description="Removed from draft",
                    )
                )

        # Find status/section changes
        for cid, (curr_item, curr_section) in curr_items.items():
            if cid in prev_items:
                prev_item, prev_section = prev_items[cid]

                # Check for section move
                if curr_section != prev_section:
                    changes.append(
                        DeltaChange(
                            change_type=ChangeType.SECTION_MOVE,
                            candidate_id=cid,
                            headline=self._extract_headline(curr_item.line_item_text),
                            previous_status=prev_item.status_label,
                            new_status=curr_item.status_label,
                            previous_section=prev_section,
                            new_section=curr_section,
                            description=f"Moved from {prev_section} to {curr_section}",
                        )
                    )
                # Check for status change within same section
                elif curr_item.status_label != prev_item.status_label:
                    changes.append(
                        DeltaChange(
                            change_type=ChangeType.STATUS_CHANGE,
                            candidate_id=cid,
                            headline=self._extract_headline(curr_item.line_item_text),
                            previous_status=prev_item.status_label,
                            new_status=curr_item.status_label,
                            description=f"Status changed from {prev_item.status_label} to {curr_item.status_label}",
                        )
                    )
                # Check for content updates
                elif curr_item.line_item_text != prev_item.line_item_text:
                    changes.append(
                        DeltaChange(
                            change_type=ChangeType.CONTENT_UPDATE,
                            candidate_id=cid,
                            headline=self._extract_headline(curr_item.line_item_text),
                            new_section=curr_section,
                            description="Content updated",
                        )
                    )

        summary_text = self._generate_summary_text(changes)

        return COPDeltaSummary(
            current_draft_id=current_draft.draft_id,
            previous_draft_id=previous_draft.draft_id,
            generated_at=datetime.utcnow(),
            changes=changes,
            summary_text=summary_text,
        )

    def _build_item_map(
        self, draft: COPDraft
    ) -> dict[str, tuple[COPLineItem, str]]:
        """Build a map of candidate_id to (item, section)."""
        items: dict[str, tuple[COPLineItem, str]] = {}

        for item in draft.verified_items:
            items[item.candidate_id] = (item, COPSection.VERIFIED.value)
        for item in draft.in_review_items:
            items[item.candidate_id] = (item, COPSection.IN_REVIEW.value)
        for item in draft.disproven_items:
            items[item.candidate_id] = (item, COPSection.DISPROVEN.value)

        return items

    def _extract_headline(self, line_item_text: str) -> str:
        """Extract a short headline from the line item text."""
        # Take first sentence or first 100 chars
        text = line_item_text.strip()
        if "." in text:
            text = text.split(".")[0] + "."
        if len(text) > 100:
            text = text[:97] + "..."
        return text

    def _generate_summary_text(
        self,
        changes: list[DeltaChange],
        is_first_draft: bool = False,
    ) -> str:
        """Generate a natural language summary of changes."""
        if is_first_draft:
            verified = sum(1 for c in changes if c.new_section == COPSection.VERIFIED.value)
            in_review = sum(1 for c in changes if c.new_section == COPSection.IN_REVIEW.value)
            disproven = sum(1 for c in changes if c.new_section == COPSection.DISPROVEN.value)

            parts = []
            if verified:
                parts.append(f"{verified} verified item{'s' if verified != 1 else ''}")
            if in_review:
                parts.append(f"{in_review} in-review item{'s' if in_review != 1 else ''}")
            if disproven:
                parts.append(f"{disproven} rumor control item{'s' if disproven != 1 else ''}")

            if parts:
                return "Initial COP draft with " + ", ".join(parts) + "."
            return "Initial COP draft with no items."

        if not changes:
            return "No changes since the previous COP draft."

        parts = []

        new_count = sum(1 for c in changes if c.change_type == ChangeType.NEW)
        removed_count = sum(1 for c in changes if c.change_type == ChangeType.REMOVED)
        status_count = sum(1 for c in changes if c.change_type == ChangeType.STATUS_CHANGE)
        section_count = sum(1 for c in changes if c.change_type == ChangeType.SECTION_MOVE)
        update_count = sum(1 for c in changes if c.change_type == ChangeType.CONTENT_UPDATE)

        if new_count:
            parts.append(f"{new_count} new item{'s' if new_count != 1 else ''}")
        if removed_count:
            parts.append(f"{removed_count} item{'s' if removed_count != 1 else ''} removed")
        if status_count:
            parts.append(f"{status_count} status change{'s' if status_count != 1 else ''}")
        if section_count:
            parts.append(f"{section_count} item{'s' if section_count != 1 else ''} moved between sections")
        if update_count:
            parts.append(f"{update_count} content update{'s' if update_count != 1 else ''}")

        return "Since the last COP: " + ", ".join(parts) + "."
