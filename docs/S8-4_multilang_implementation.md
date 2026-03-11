# S8-4: Multi-Language COP Draft Generation Implementation

## Overview

This document describes the implementation of multi-language support (Spanish and French) for COP draft generation.

## Changes Required

### 1. Update `src/integritykit/services/draft.py`

#### 1.1 Update imports

```python
# Replace the cop_draft_generation imports with registry import
from integritykit.llm.prompts.registry import get_prompts
```

#### 1.2 Update `DraftService.__init__`

Add `default_language` parameter:

```python
def __init__(
    self,
    openai_client: Optional[AsyncOpenAI] = None,
    model: str = "gpt-4o",
    use_llm: bool = True,
    default_language: str = "en",  # NEW
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
    self.default_language = default_language  # NEW
```

#### 1.3 Update `generate_line_item` method

Add `target_language` parameter:

```python
async def generate_line_item(
    self,
    candidate: COPCandidate,
    use_llm: Optional[bool] = None,
    target_language: Optional[str] = None,  # NEW
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
    language = target_language or self.default_language  # NEW

    if should_use_llm and self.client:
        try:
            return await self._generate_with_llm(candidate, language)  # UPDATED
        except Exception as e:
            logger.warning(
                "LLM generation failed, falling back to rule-based",
                candidate_id=str(candidate.id),
                error=str(e),
            )
            return self._generate_rule_based(candidate, language)  # UPDATED
    else:
        return self._generate_rule_based(candidate, language)  # UPDATED
```

#### 1.4 Update `_generate_rule_based` method

Add language parameter and use prompt registry:

```python
def _generate_rule_based(self, candidate: COPCandidate, language: str = "en") -> COPLineItem:
    """Rule-based line item generation.

    Args:
        candidate: COP candidate
        language: Target language (en, es, fr)

    Returns:
        Generated COPLineItem
    """
    # Load language-specific prompts and wording guidance
    prompts = get_prompts(language)
    wording_guidance = prompts.wording_guidance

    # Define status labels by language
    status_labels = {
        "en": {"verified": "VERIFIED", "in_review": "IN REVIEW", "blocked": "BLOCKED"},
        "es": {"verified": "VERIFICADO", "in_review": "EN REVISIÓN", "blocked": "BLOQUEADO"},
        "fr": {"verified": "VÉRIFIÉ", "in_review": "EN RÉVISION", "blocked": "BLOQUÉ"},
    }

    language_labels = status_labels.get(language, status_labels["en"])

    # Rest of the method...
    # Update status_label assignments to use language_labels
    # Update next_step and recheck_time calls to pass language parameter
```

#### 1.5 Add helper methods

Add these new methods to `DraftService`:

```python
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
    return texts.get(language, texts["en"]).get(time_key, texts["en"][time_key])

def _get_routine_next_step(self, language: str) -> str:
    """Get localized routine next step text."""
    texts = {
        "en": "Await verification from any available verifier",
        "es": "Esperar verificación de cualquier verificador disponible",
        "fr": "Attendre la vérification d'un vérificateur disponible",
    }
    return texts.get(language, texts["en"])

def _get_default_text(self, key: str, language: str) -> str:
    """Get default text in target language."""
    texts = {
        "en": {"situation_developing": "Situation developing"},
        "es": {"situation_developing": "Situación en desarrollo"},
        "fr": {"situation_developing": "Situation en développement"},
    }
    return texts.get(language, texts["en"]).get(key, texts["en"][key])

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
```

#### 1.6 Update `_determine_high_stakes_next_step` and `_determine_elevated_next_step`

Add language parameter and localized messages (see test file for examples).

#### 1.7 Update `_apply_wording_guidance` method

Add language-specific wording using the wording guidance from prompt registry.

#### 1.8 Update `_generate_with_llm` method

Use language-specific prompts from registry:

```python
async def _generate_with_llm(self, candidate: COPCandidate, language: str = "en") -> COPLineItem:
    """LLM-based line item generation.

    Args:
        candidate: COP candidate
        language: Target language (en, es, fr)

    Returns:
        Generated COPLineItem
    """
    # Load language-specific prompts
    prompts = get_prompts(language)
    cop_prompts = prompts.cop_draft_generation

    # Use language-specific prompts in API call
    response = await self.client.chat.completions.create(
        model=self.model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": cop_prompts.COP_DRAFT_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": cop_prompts.format_cop_draft_generation_prompt(candidate_data)},
        ],
        response_format={"type": "json_object"},
    )
    # ... rest of method
```

#### 1.9 Update `generate_draft` method

Add `target_language` parameter and use it throughout:

```python
async def generate_draft(
    self,
    workspace_id: str,
    candidates: list[COPCandidate],
    title: Optional[str] = None,
    include_open_questions: bool = True,
    target_language: Optional[str] = None,  # NEW
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
    language = target_language or self.default_language

    # Use language-specific title if not provided
    if not title:
        title = self._get_default_title(now, language)

    # Pass language to generate_line_item calls
    for candidate in candidates:
        line_item = await self.generate_line_item(candidate, target_language=language)
        # ... rest of loop

    # Use language-specific no items text
    if total_items == 0:
        no_items_text = self._get_no_items_text(language)
        open_questions.append(no_items_text)

    # Add language to metadata
    return COPDraft(
        # ... other fields
        metadata={
            "candidate_count": len(candidates),
            "generator_model": self.model if self.use_llm else "rule_based",
            "language": language,  # NEW
        },
    )
```

#### 1.10 Update `COPDraft.to_markdown` method

Add language parameter and localized headers:

```python
def to_markdown(self, language: Optional[str] = None) -> str:
    """Convert draft to Markdown format with locale-specific headers.

    Args:
        language: Target language (en, es, fr). Defaults to metadata language or en.

    Returns:
        Markdown string with localized section headers
    """
    lang = language or self.metadata.get("language", "en")
    headers = self._get_section_headers(lang)

    # Use localized headers throughout
    lines = [f"# {self.title}", ""]
    timestamp_text = self._format_timestamp(self.generated_at, lang, headers["generated"])
    lines.append(f"*{timestamp_text}*")
    # ... rest of method using headers dict

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
```

### 2. Update `src/integritykit/services/publish.py`

#### 2.1 Update `create_draft_from_candidates` method

Add `target_language` parameter:

```python
async def create_draft_from_candidates(
    self,
    workspace_id: str,
    candidate_ids: list[ObjectId],
    user: User,
    title: Optional[str] = None,
    target_language: Optional[str] = None,  # NEW
) -> COPUpdate:
    """Create a COP update draft from selected candidates.

    Args:
        workspace_id: Slack workspace ID
        candidate_ids: List of candidate IDs to include
        user: User creating the draft
        title: Optional custom title
        target_language: Target language (en, es, fr). Defaults to service default.

    Returns:
        Created COPUpdate in DRAFT status
    """
    # Pass target_language to generate_draft
    draft = await self.draft_service.generate_draft(
        workspace_id=workspace_id,
        candidates=candidates,
        title=title,
        include_open_questions=True,
        target_language=target_language,  # NEW
    )
    # ... rest of method
```

#### 2.2 Update `create_new_version` method

Add `target_language` parameter with inheritance:

```python
async def create_new_version(
    self,
    previous_update: COPUpdate,
    candidate_ids: list[ObjectId],
    user: User,
    title: Optional[str] = None,
    target_language: Optional[str] = None,  # NEW
) -> COPUpdate:
    """Create a new version of a COP update (S7-2).

    Args:
        previous_update: Previous update to base new version on
        candidate_ids: Candidate IDs for the new version
        user: User creating the new version
        title: Optional new title
        target_language: Target language (en, es, fr). Inherits from previous if not specified.

    Returns:
        New COPUpdate with version tracking
    """
    # Inherit language from previous update if not specified
    if not target_language and hasattr(previous_update, 'metadata'):
        target_language = previous_update.metadata.get('language')

    # Pass target_language to generate_draft
    draft = await self.draft_service.generate_draft(
        workspace_id=previous_update.workspace_id,
        candidates=candidates,
        title=title or previous_update.title,
        include_open_questions=True,
        target_language=target_language,  # NEW
    )
    # ... rest of method
```

## Testing

Unit tests are provided in `/home/theo/work/integritykit/tests/unit/test_draft_multilang.py`:

- Test Spanish draft generation
- Test French draft generation
- Test English default behavior
- Test language-specific hedging phrases
- Test localized next steps for high-stakes/elevated items
- Test markdown localization
- Test language fallback
- Test no-items message localization

Run tests:
```bash
pytest tests/unit/test_draft_multilang.py -v
```

## Usage Examples

### Generate Spanish draft

```python
from integritykit.services.draft import DraftService

service = DraftService(use_llm=False, default_language="es")

draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="es",
)

# Draft will have Spanish status labels, headers, and wording
print(draft.to_markdown(language="es"))
```

### Generate French draft via publish service

```python
from integritykit.services.publish import PublishService

publish_service = PublishService()

cop_update = await publish_service.create_draft_from_candidates(
    workspace_id="W123",
    candidate_ids=[...],
    user=user,
    target_language="fr",
)
```

### Override language on markdown export

```python
# Draft created in English
draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="en",
)

# Export with French headers
markdown_fr = draft.to_markdown(language="fr")
```

## API Integration

If exposing via API, add language parameter:

```python
@router.post("/cop/drafts")
async def create_cop_draft(
    workspace_id: str,
    candidate_ids: list[str],
    title: Optional[str] = None,
    language: str = "en",  # NEW: Accept language parameter
    current_user: User = Depends(get_current_user),
):
    """Create COP draft in specified language."""
    draft_service = DraftService(default_language=language)
    # ... rest of endpoint
```

## Prompt Registry Integration

The implementation uses `integritykit.llm.prompts.registry.get_prompts(language)` to load:

- `cop_draft_generation`: Language-specific COP draft prompts
- `wording_guidance`: Hedged/direct phrases and verb conjugations

Supported languages in registry:
- `"en"` - English (default)
- `"es"` - Spanish (Español)
- `"fr"` - French (Français)

Unsupported languages fall back to English with a warning.

## Backwards Compatibility

- Default language is `"en"` - existing code continues to work
- `target_language` parameter is optional everywhere
- If not specified, uses instance `default_language`
- Metadata preserves language for draft history

## Future Enhancements

Potential future improvements:
1. Add more languages (German, Portuguese, etc.)
2. Date/time formatting per locale (strftime patterns)
3. Number formatting (thousands separators)
4. Right-to-left language support
5. Language auto-detection from candidate content
6. User language preferences in database
