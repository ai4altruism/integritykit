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

        # Determine next verification step for high-stakes in-review items
        next_step = None
        recheck_time = None

        if (
            candidate.readiness_state == ReadinessState.IN_REVIEW
            and candidate.risk_tier == RiskTier.HIGH_STAKES
        ):
            if not candidate.fields.who:
                next_step = "Identify and contact primary source"
            elif not candidate.verifications:
                next_step = "Assign verification to available verifier"
            else:
                next_step = "Await secondary confirmation"

            recheck_time = "Within 1 hour"

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
