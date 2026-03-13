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

    def to_markdown(self, language: Optional[str] = None) -> str:
        """Convert draft to Markdown format with locale-specific headers.

        Args:
            language: Target language (en, es, fr). Defaults to metadata language or en.

        Returns:
            Markdown string with localized section headers
        """
        lang = language or self.metadata.get("language", "en")
        headers = self._get_section_headers(lang)

        lines = [f"# {self.title}", ""]
        lines.append(f"*{headers['generated']}: {self.generated_at.strftime('%Y-%m-%d %H:%M UTC')}*")
        lines.append("")

        if self.verified_items:
            lines.append(f"## {headers['verified']}")
            lines.append("")
            for item in self.verified_items:
                lines.append(f"- {item.line_item_text}")
            lines.append("")

        if self.in_review_items:
            lines.append(f"## {headers['in_review']}")
            lines.append("")
            for item in self.in_review_items:
                lines.append(f"- {item.line_item_text}")
                if item.next_verification_step:
                    lines.append(f"  - *{headers['next_step']}: {item.next_verification_step}*")
                if item.recheck_time:
                    lines.append(f"  - *{headers['recheck']}: {item.recheck_time}*")
            lines.append("")

        if self.disproven_items:
            lines.append(f"## {headers['disproven']}")
            lines.append("")
            for item in self.disproven_items:
                lines.append(f"- {item.line_item_text}")
            lines.append("")

        if self.open_questions:
            lines.append(f"## {headers['open_questions']}")
            lines.append("")
            for question in self.open_questions:
                lines.append(f"- {question}")
            lines.append("")

        return "\n".join(lines)

    def _get_section_headers(self, language: str) -> dict[str, str]:
        """Get localized section headers."""
        headers = {
            "en": {
                "generated": "Generated",
                "verified": "Verified Updates",
                "in_review": "In Review (Unconfirmed)",
                "disproven": "Rumor Control / Corrections",
                "open_questions": "Open Questions / Gaps",
                "next_step": "Next step",
                "recheck": "Recheck",
            },
            "es": {
                "generated": "Generado",
                "verified": "Actualizaciones Verificadas",
                "in_review": "En Revisión (Sin Confirmar)",
                "disproven": "Control de Rumores / Correcciones",
                "open_questions": "Preguntas Abiertas / Brechas",
                "next_step": "Siguiente paso",
                "recheck": "Reverificar",
            },
            "fr": {
                "generated": "Généré",
                "verified": "Mises à jour Vérifiées",
                "in_review": "En Révision (Non Confirmé)",
                "disproven": "Contrôle des Rumeurs / Corrections",
                "open_questions": "Questions Ouvertes / Lacunes",
                "next_step": "Prochaine étape",
                "recheck": "Revérifier",
            },
        }
        return headers.get(language, headers["en"])

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

    # Localized status labels
    STATUS_LABELS = {
        "en": {"verified": "VERIFIED", "in_review": "IN REVIEW", "blocked": "BLOCKED"},
        "es": {"verified": "VERIFICADO", "in_review": "EN REVISIÓN", "blocked": "BLOQUEADO"},
        "fr": {"verified": "VÉRIFIÉ", "in_review": "EN RÉVISION", "blocked": "BLOQUÉ"},
    }

    def __init__(
        self,
        openai_client: Optional[AsyncOpenAI] = None,
        model: str = "gpt-4o",  # Use more capable model for nuanced writing
        use_llm: bool = True,
        default_language: str = "en",
    ):
        """Initialize DraftService.

        Args:
            openai_client: OpenAI client for LLM-based generation
            model: Model to use for draft generation
            use_llm: Whether to use LLM for generation
            default_language: Default language for draft generation (en, es, fr)
        """
        self.client = openai_client
        self.model = model
        self.use_llm = use_llm and openai_client is not None
        self.default_language = default_language if default_language in ("en", "es", "fr") else "en"

    def _get_status_label(self, status_key: str, language: str) -> str:
        """Get localized status label."""
        labels = self.STATUS_LABELS.get(language, self.STATUS_LABELS["en"])
        return labels.get(status_key, self.STATUS_LABELS["en"][status_key])

    def _get_recheck_time_text(self, time_key: str, language: str) -> str:
        """Get localized recheck time text."""
        texts = {
            "en": {
                "30_minutes": "Within 30 minutes",
                "2_hours": "Within 2 hours",
                "4_hours": "Within 4 hours",
            },
            "es": {
                "30_minutes": "Dentro de 30 minutos",
                "2_hours": "Dentro de 2 horas",
                "4_hours": "Dentro de 4 horas",
            },
            "fr": {
                "30_minutes": "Dans les 30 minutes",
                "2_hours": "Dans les 2 heures",
                "4_hours": "Dans les 4 heures",
            },
        }
        lang_texts = texts.get(language, texts["en"])
        return lang_texts.get(time_key, texts["en"][time_key])

    def _get_hedging_prefix(self, language: str) -> str:
        """Get localized hedging prefix for uncertain items."""
        prefixes = {
            "en": "Unconfirmed:",
            "es": "Sin confirmar:",
            "fr": "Non confirmé:",
        }
        return prefixes.get(language, prefixes["en"])

    def _get_reports_indicate(self, language: str) -> str:
        """Get localized 'reports indicate' phrase."""
        phrases = {
            "en": "Reports indicate",
            "es": "Se reporta que",
            "fr": "Il est rapporté que",
        }
        return phrases.get(language, phrases["en"])

    def _get_language_connectors(self, language: str) -> dict[str, str]:
        """Get language-specific connectors and prepositions."""
        connectors = {
            "en": {"at": "at", "as_of": "as of", "source": "Source", "if_confirmed": "If confirmed"},
            "es": {"at": "en", "as_of": "desde", "source": "Fuente", "if_confirmed": "Si se confirma"},
            "fr": {"at": "à", "as_of": "à partir de", "source": "Source", "if_confirmed": "Si confirmé"},
        }
        return connectors.get(language, connectors["en"])

    def _get_default_title(self, timestamp: datetime, language: str) -> str:
        """Get default title in target language."""
        titles = {
            "en": f"COP Update - {timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "es": f"Actualización de PCO - {timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
            "fr": f"Mise à jour PCO - {timestamp.strftime('%Y-%m-%d %H:%M UTC')}",
        }
        return titles.get(language, titles["en"])

    def _get_no_items_text(self, language: str) -> str:
        """Get 'no items available' text in target language."""
        texts = {
            "en": "No COP items available for this period",
            "es": "No hay elementos de PCO disponibles para este período",
            "fr": "Aucun élément PCO disponible pour cette période",
        }
        return texts.get(language, texts["en"])

    def _apply_may_be_replacement(self, text: str, language: str) -> str:
        """Apply 'may be' hedging replacement for the given language."""
        replacements = {
            "en": [(" is ", " may be "), (" are ", " may be ")],
            "es": [(" está ", " estaría "), (" es ", " sería "), (" son ", " serían ")],
            "fr": [(" est ", " serait "), (" sont ", " seraient ")],
        }
        result = text
        for old, new in replacements.get(language, replacements["en"]):
            result = result.replace(old, new)
        return result

    async def generate_line_item(
        self,
        candidate: COPCandidate,
        use_llm: Optional[bool] = None,
        target_language: Optional[str] = None,
    ) -> COPLineItem:
        """Generate a COP line item from a candidate.

        Args:
            candidate: COP candidate to generate line item from
            use_llm: Override instance-level LLM setting
            target_language: Target language (en, es, fr). Defaults to instance default.

        Returns:
            COPLineItem ready for inclusion in draft
        """
        should_use_llm = use_llm if use_llm is not None else self.use_llm
        language = target_language or self.default_language

        if should_use_llm and self.client:
            try:
                return await self._generate_with_llm(candidate, language)
            except Exception as e:
                logger.warning(
                    "LLM generation failed, falling back to rule-based",
                    candidate_id=str(candidate.id),
                    error=str(e),
                )
                return self._generate_rule_based(candidate, language)
        else:
            return self._generate_rule_based(candidate, language)

    def _generate_rule_based(
        self, candidate: COPCandidate, language: str = "en"
    ) -> COPLineItem:
        """Rule-based line item generation.

        Args:
            candidate: COP candidate
            language: Target language (en, es, fr)

        Returns:
            Generated COPLineItem
        """
        # Determine section and status label
        if candidate.readiness_state == ReadinessState.VERIFIED:
            section = COPSection.VERIFIED
            status_label = self._get_status_label("verified", language)
            wording_style = WordingStyle.DIRECT_FACTUAL
        elif candidate.readiness_state == ReadinessState.IN_REVIEW:
            section = COPSection.IN_REVIEW
            status_label = self._get_status_label("in_review", language)
            wording_style = WordingStyle.HEDGED_UNCERTAIN
        else:
            section = COPSection.OPEN_QUESTIONS
            status_label = self._get_status_label("blocked", language)
            wording_style = WordingStyle.HEDGED_UNCERTAIN

        # Build the line item text with appropriate wording
        line_text = self._apply_wording_guidance(candidate, wording_style, language)

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
                next_step = self._determine_high_stakes_next_step(candidate, language)
                recheck_time = self._get_recheck_time_text("30_minutes", language)

            # Elevated items need near-term recheck
            elif candidate.risk_tier == RiskTier.ELEVATED:
                next_step = self._determine_elevated_next_step(candidate, language)
                recheck_time = self._get_recheck_time_text("2_hours", language)

            # Routine items may optionally have next steps
            elif candidate.risk_tier == RiskTier.ROUTINE:
                if not candidate.verifications:
                    next_step = self._get_routine_next_step(language)
                recheck_time = self._get_recheck_time_text("4_hours", language)

        logger.info(
            "Generated rule-based line item",
            candidate_id=str(candidate.id),
            section=section.value,
            wording_style=wording_style.value,
            language=language,
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

    def _get_routine_next_step(self, language: str) -> str:
        """Get localized routine next step text."""
        texts = {
            "en": "Await verification from any available verifier",
            "es": "Esperar verificación de cualquier verificador disponible",
            "fr": "Attendre la vérification d'un vérificateur disponible",
        }
        return texts.get(language, texts["en"])

    def _determine_high_stakes_next_step(
        self, candidate: COPCandidate, language: str = "en"
    ) -> str:
        """Determine next verification step for high-stakes items.

        Implements FR-COP-WORDING-002 for HIGH_STAKES risk tier.

        Args:
            candidate: COP candidate
            language: Target language (en, es, fr)

        Returns:
            Specific next verification step
        """
        urgent = {"en": "URGENT", "es": "URGENTE", "fr": "URGENT"}
        urgent_prefix = urgent.get(language, urgent["en"])

        # Priority 1: Need to identify source
        if not candidate.fields.who:
            texts = {
                "en": f"{urgent_prefix}: Identify and contact primary source for direct confirmation",
                "es": f"{urgent_prefix}: Identificar y contactar fuente principal para confirmación directa",
                "fr": f"{urgent_prefix}: Identifier et contacter la source principale pour confirmation directe",
            }
            return texts.get(language, texts["en"])

        # Priority 2: No verification attempts yet
        if not candidate.verifications:
            texts = {
                "en": f"{urgent_prefix}: Assign verification to available verifier immediately",
                "es": f"{urgent_prefix}: Asignar verificación a verificador disponible inmediatamente",
                "fr": f"{urgent_prefix}: Assigner la vérification à un vérificateur disponible immédiatement",
            }
            return texts.get(language, texts["en"])

        # Priority 3: Has verification attempts - check confidence levels
        low_confidence = [
            v for v in candidate.verifications
            if v.confidence_level.value == "low"
        ]

        if low_confidence:
            texts = {
                "en": f"{urgent_prefix}: Low-confidence verification - seek additional confirmation source",
                "es": f"{urgent_prefix}: Verificación de baja confianza - buscar fuente de confirmación adicional",
                "fr": f"{urgent_prefix}: Vérification à faible confiance - rechercher une source de confirmation supplémentaire",
            }
            return texts.get(language, texts["en"])

        # Priority 4: Has verifications but candidate still in review
        texts = {
            "en": f"{urgent_prefix}: Seek secondary independent confirmation before publishing",
            "es": f"{urgent_prefix}: Buscar confirmación secundaria independiente antes de publicar",
            "fr": f"{urgent_prefix}: Rechercher une confirmation secondaire indépendante avant publication",
        }
        return texts.get(language, texts["en"])

    def _determine_elevated_next_step(
        self, candidate: COPCandidate, language: str = "en"
    ) -> str:
        """Determine next verification step for elevated risk items.

        Implements FR-COP-WORDING-002 for ELEVATED risk tier.

        Args:
            candidate: COP candidate
            language: Target language (en, es, fr)

        Returns:
            Specific next verification step
        """
        # Check what's missing
        if not candidate.fields.who:
            texts = {
                "en": "Identify primary source for verification",
                "es": "Identificar fuente principal para verificación",
                "fr": "Identifier la source principale pour vérification",
            }
            return texts.get(language, texts["en"])

        if not candidate.fields.where:
            texts = {
                "en": "Confirm exact location details",
                "es": "Confirmar detalles exactos del emplacement",
                "fr": "Confirmer les détails exacts de l'emplacement",
            }
            return texts.get(language, texts["en"])

        if not candidate.fields.when or not candidate.fields.when.description:
            texts = {
                "en": "Confirm timing/recency of information",
                "es": "Confirmar cronología/actualidad de la información",
                "fr": "Confirmer le moment/la récence de l'information",
            }
            return texts.get(language, texts["en"])

        if not candidate.verifications:
            texts = {
                "en": "Request verification from available verifier",
                "es": "Solicitar verificación de verificador disponible",
                "fr": "Demander la vérification d'un vérificateur disponible",
            }
            return texts.get(language, texts["en"])

        # Has verification attempts - check if we need more confidence
        low_confidence = [
            v for v in candidate.verifications
            if v.confidence_level.value == "low"
        ]
        if low_confidence:
            texts = {
                "en": "Low-confidence verification - seek additional confirmation",
                "es": "Verificación de baja confianza - buscar confirmación adicional",
                "fr": "Vérification à faible confiance - rechercher une confirmation supplémentaire",
            }
            return texts.get(language, texts["en"])

        texts = {
            "en": "Seek additional confirmation if possible",
            "es": "Buscar confirmación adicional si es posible",
            "fr": "Rechercher une confirmation supplémentaire si possible",
        }
        return texts.get(language, texts["en"])

    def _apply_wording_guidance(
        self,
        candidate: COPCandidate,
        style: WordingStyle,
        language: str = "en",
    ) -> str:
        """Apply wording guidance based on verification status.

        Implements FR-COP-WORDING-001 and S8-4 (multi-language support).

        Args:
            candidate: COP candidate
            style: Wording style to apply
            language: Target language (en, es, fr)

        Returns:
            Formatted line item text with appropriate wording
        """
        # Get language-specific connectors
        connectors = self._get_language_connectors(language)

        # Build base statement from fields
        default_situation = {
            "en": "Situation developing",
            "es": "Situación en desarrollo",
            "fr": "Situation en développement",
        }
        what = candidate.fields.what or default_situation.get(language, default_situation["en"])
        where = candidate.fields.where or ""
        when = candidate.fields.when.description or ""
        who = candidate.fields.who or ""
        so_what = candidate.fields.so_what or ""

        # Build location/time clause
        location_time = ""
        if where and when:
            location_time = f" {connectors['at']} {where} {connectors['as_of']} {when}"
        elif where:
            location_time = f" {connectors['at']} {where}"
        elif when:
            location_time = f" {connectors['as_of']} {when}"

        if style == WordingStyle.DIRECT_FACTUAL:
            # Verified: Direct, factual phrasing
            # Example: "Main Street Bridge is closed to all traffic as of 14:00 PST."
            statement = f"{what}{location_time}."
            if so_what:
                statement = f"{statement} {so_what}"

        else:
            # In-Review: Hedged, uncertain phrasing
            # Example: "Unconfirmed: Reports indicate Main Street Bridge may be closed."
            hedging_prefix = self._get_hedging_prefix(language)
            reports_indicate = self._get_reports_indicate(language)

            # Add uncertainty markers to the statement
            what_hedged = self._apply_may_be_replacement(what, language)
            statement = f"{hedging_prefix} {reports_indicate} {what_hedged.lower()}{location_time}."

            if so_what:
                statement = f"{statement} {connectors['if_confirmed']}, {so_what.lower()}"

        # Add source attribution if available
        if who and style == WordingStyle.DIRECT_FACTUAL:
            statement = f"{statement} ({connectors['source']}: {who})"

        return statement

    async def _generate_with_llm(
        self, candidate: COPCandidate, language: str = "en"
    ) -> COPLineItem:
        """LLM-based line item generation.

        Args:
            candidate: COP candidate
            language: Target language (en, es, fr)

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
        target_language: Optional[str] = None,
    ) -> COPDraft:
        """Generate a complete COP draft from multiple candidates.

        Implements FR-COPDRAFT-002: Assemble draft grouped by section.
        Implements S8-4: Multi-language support.

        Args:
            workspace_id: Workspace ID
            candidates: List of COP candidates to include
            title: Optional title for the draft
            include_open_questions: Whether to include open questions section
            target_language: Target language (en, es, fr). Defaults to instance default.

        Returns:
            COPDraft organized by section
        """
        from bson import ObjectId

        draft_id = str(ObjectId())
        now = datetime.utcnow()
        language = target_language or self.default_language

        if not title:
            title = self._get_default_title(now, language)

        verified_items: list[COPLineItem] = []
        in_review_items: list[COPLineItem] = []
        disproven_items: list[COPLineItem] = []
        open_questions: list[str] = []

        # Get localized pending clarification text
        pending_texts = {
            "en": "Pending clarification",
            "es": "Pendiente de aclaración",
            "fr": "En attente de clarification",
        }
        pending_text = pending_texts.get(language, pending_texts["en"])

        unknown_texts = {
            "en": "Unknown topic",
            "es": "Tema desconocido",
            "fr": "Sujet inconnu",
        }
        unknown_text = unknown_texts.get(language, unknown_texts["en"])

        # Generate line items for each candidate
        for candidate in candidates:
            try:
                line_item = await self.generate_line_item(
                    candidate, target_language=language
                )

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
                            f"{pending_text}: {candidate.fields.what or unknown_text}"
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
                open_questions.append(self._get_no_items_text(language))

        logger.info(
            "Generated COP draft",
            draft_id=draft_id,
            workspace_id=workspace_id,
            verified_count=len(verified_items),
            in_review_count=len(in_review_items),
            disproven_count=len(disproven_items),
            open_questions_count=len(open_questions),
            language=language,
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
                "language": language,
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
