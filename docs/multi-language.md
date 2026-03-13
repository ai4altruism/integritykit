# Multi-Language Support Guide

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

This document consolidates all multi-language documentation for the Aid Arena Integrity Kit v1.0.

---

## Table of Contents

1. [Overview](#overview)
2. [Supported Languages](#supported-languages)
3. [Configuration](#configuration)
4. [Usage](#usage)
5. [Language Detection API](#language-detection-api)
6. [Draft Generation](#draft-generation)
7. [Quick Reference](#quick-reference)

---

## Overview

The Aid Arena Integrity Kit v1.0 supports multi-language COP (Common Operating Picture) draft generation in English, Spanish, and French. This enables crisis response communities to operate in their preferred language with culturally appropriate wording.

### Key Features

- **Automatic language detection** for ingested messages
- **Spanish and French** COP draft generation with language-aware wording
- **Mixed-language workspace** support (multilingual signal processing)
- **Translation of system messages** and Slack Block Kit templates
- **Language-specific hedging** (verified vs in-review)

---

## Supported Languages

| Language | Code | Status Labels | Wording Style |
|----------|------|---------------|---------------|
| English | `en` | VERIFIED, IN REVIEW, BLOCKED | Direct / Hedged |
| Spanish | `es` | VERIFICADO, EN REVISIÓN, BLOQUEADO | Directo / Tentativo |
| French | `fr` | VÉRIFIÉ, EN RÉVISION, BLOQUÉ | Direct / Nuancé |

### Status Label Translations

**Verified Items:**
- **English**: `[VERIFIED]`
- **Spanish**: `[VERIFICADO]`
- **French**: `[VÉRIFIÉ]`

**In Review Items:**
- **English**: `[IN REVIEW]`
- **Spanish**: `[EN REVISIÓN]`
- **French**: `[EN RÉVISION]`

**Blocked Items:**
- **English**: `[BLOCKED]`
- **Spanish**: `[BLOQUEADO]`
- **French**: `[BLOQUÉ]`

---

## Configuration

### Environment Variables

Add these variables to your `.env` file:

```bash
# Multi-Language Configuration
SUPPORTED_LANGUAGES=en,es,fr
DEFAULT_LANGUAGE=en

# Language Detection (optional)
LANGUAGE_DETECTION_ENABLED=true
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8
LANGUAGE_DETECTION_SERVICE=google  # or 'langdetect' for offline
```

### Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SUPPORTED_LANGUAGES` | No | `en` | Comma-separated list of language codes |
| `DEFAULT_LANGUAGE` | No | `en` | Default language for COP drafts |
| `LANGUAGE_DETECTION_ENABLED` | No | `false` | Enable automatic language detection |
| `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD` | No | `0.8` | Minimum confidence for auto-detection (0.0-1.0) |
| `LANGUAGE_DETECTION_SERVICE` | No | `langdetect` | Language detection service (`langdetect` or `google`) |

### Google Cloud Translation API (Optional)

For enhanced language detection:

1. Create a Google Cloud project and enable the Translation API
2. Generate API credentials
3. Set environment variable:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
LANGUAGE_DETECTION_SERVICE=google
```

---

## Usage

### API Endpoints

All COP draft endpoints support an optional `language` parameter.

#### Create Draft with Language

```bash
POST /api/v1/publish/drafts
Content-Type: application/json

{
  "candidate_ids": ["candidate-123", "candidate-456"],
  "title": "Actualización de Crisis #5",
  "language": "es"
}
```

#### Generate Draft (DraftService)

```python
from integritykit.services.draft import DraftService

service = DraftService(
    openai_client=openai_client,
    default_language="es"
)

draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    title="Actualización de Crisis #5",
    target_language="es"  # Override default
)
```

### Section Header Translations

COP update sections are localized:

**English:**
```markdown
# Crisis Update #5

## Verified Updates
## In-Review Reports
## Open Questions
```

**Spanish:**
```markdown
# Actualización de Crisis #5

## Actualizaciones Verificadas
## Informes en Revisión
## Preguntas Abiertas
```

**French:**
```markdown
# Mise à Jour de Crise #5

## Mises à Jour Vérifiées
## Rapports en Révision
## Questions Ouvertes
```

### Wording Style Examples

#### English - Verified
```
[VERIFIED] Shelter Alpha at 123 Main St has closed due to capacity.
Residents are being redirected to Shelter Bravo (456 Oak Ave).
```

#### English - In Review
```
[IN REVIEW] Unconfirmed reports indicate Shelter Alpha may be at capacity.
Verification in progress with shelter management.
```

#### Spanish - Verificado
```
[VERIFICADO] El refugio Alpha en 123 Main St ha cerrado debido a la capacidad.
Los residentes están siendo redirigidos al refugio Bravo (456 Oak Ave).
```

#### Spanish - En Revisión
```
[EN REVISIÓN] Informes no confirmados indican que el refugio Alpha puede estar
a capacidad máxima. Verificación en curso con la administración del refugio.
```

#### French - Vérifié
```
[VÉRIFIÉ] Le refuge Alpha au 123 Main St a fermé en raison de la capacité.
Les résidents sont redirigés vers le refuge Bravo (456 Oak Ave).
```

#### French - En Révision
```
[EN RÉVISION] Des rapports non confirmés indiquent que le refuge Alpha pourrait
être à pleine capacité. Vérification en cours avec la direction du refuge.
```

---

## Language Detection API

### Automatic Language Detection

When enabled, the system can automatically detect the language of incoming signals.

**Configuration:**
```bash
LANGUAGE_DETECTION_ENABLED=true
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8
```

**Usage:**
```python
from integritykit.services.language_detection import LanguageDetectionService

detector = LanguageDetectionService()

result = await detector.detect_language(
    "El refugio está cerrado debido a la capacidad"
)

# result.language: "es"
# result.confidence: 0.95
# result.is_confident: True (>= threshold)
```

### Auto-Detection Workflow

1. Signals are analyzed for language
2. If confidence exceeds threshold, language is stored with signal
3. When creating COP draft from cluster, predominant language is suggested
4. Facilitator can override suggested language

---

## Draft Generation

### DraftService API

```python
class DraftService:
    def __init__(
        self,
        openai_client: OpenAI,
        model: str = "gpt-4o",
        use_llm: bool = True,
        default_language: str = "en"
    ):
        ...

    async def generate_draft(
        self,
        workspace_id: str,
        candidates: List[COPCandidate],
        title: Optional[str] = None,
        include_open_questions: bool = True,
        target_language: str = "en"
    ) -> COPDraft:
        ...
```

### LLM Prompt Localization

LLM prompts are localized in the prompt registry:

```python
from integritykit.llm.prompts.registry import get_prompt

# English prompt
prompt = get_prompt("cop_draft_generation", language="en")

# Spanish prompt
prompt = get_prompt("cop_draft_generation", language="es")

# French prompt
prompt = get_prompt("cop_draft_generation", language="fr")
```

### Prompt File Structure

```
src/integritykit/llm/prompts/
├── english/
│   ├── cop_draft_generation.py
│   ├── readiness_evaluation.py
│   └── conflict_detection.py
├── spanish/
│   ├── cop_draft_generation.py
│   ├── readiness_evaluation.py
│   └── conflict_detection.py
└── french/
    ├── cop_draft_generation.py
    ├── readiness_evaluation.py
    └── conflict_detection.py
```

---

## Quick Reference

### Generate Draft in Spanish

```python
from integritykit.services.draft import DraftService

service = DraftService(default_language="es")
draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="es",
)
```

### Generate Draft in French

```python
service = DraftService(default_language="fr")
draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="fr",
)
```

### Export Markdown with Localized Headers

```python
# Spanish
markdown_es = draft.to_markdown(language="es")

# French
markdown_fr = draft.to_markdown(language="fr")
```

### API Parameters

**DraftService:**
```python
DraftService(
    openai_client=client,
    model="gpt-4o",
    use_llm=True,
    default_language="en"  # Default language for all drafts
)
```

**generate_draft():**
```python
await service.generate_draft(
    workspace_id="W123",
    candidates=[...],
    title="My COP",
    target_language="es"  # Override default language
)
```

**PublishService.create_draft_from_candidates():**
```python
await publish_service.create_draft_from_candidates(
    workspace_id="W123",
    candidate_ids=[...],
    user=current_user,
    target_language="es"  # Language for draft
)
```

### Wording Examples Quick Reference

| Context | English | Spanish | French |
|---------|---------|---------|--------|
| **Direct (Verified)** | Bridge is closed | El puente está cerrado | Le pont est fermé |
| **Hedged (In Review)** | Reports indicate bridge may be closed | Se reporta que el puente estaría cerrado | Il est rapporté que le pont serait fermé |
| **High-Stakes Next Step** | URGENT: Identify and contact primary source | URGENTE: Identificar y contactar fuente primaria | URGENT : Identifier et contacter la source primaire |
| **Recheck Time (30 min)** | Within 30 minutes | Dentro de 30 minutos | Dans les 30 minutes |
| **Recheck Time (2 hours)** | Within 2 hours | Dentro de 2 horas | Dans les 2 heures |

### Markdown Headers

| Section | English | Spanish | French |
|---------|---------|---------|--------|
| **Verified** | Verified Updates | Actualizaciones Verificadas | Mises à jour Vérifiées |
| **In Review** | In Review (Unconfirmed) | En Revisión (Sin Confirmar) | En Révision (Non Confirmé) |
| **Rumor Control** | Rumor Control / Corrections | Control de Rumores / Correcciones | Contrôle des Rumeurs / Corrections |
| **Open Questions** | Open Questions / Gaps | Preguntas Abiertas / Brechas | Questions Ouvertes / Lacunes |

---

## Export Formats

### CAP 1.2 XML

CAP exports support multi-language via separate `<info>` blocks:

```xml
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>cop-update-12345</identifier>

  <!-- English -->
  <info>
    <language>en-US</language>
    <headline>Shelter Alpha Closure</headline>
  </info>

  <!-- Spanish -->
  <info>
    <language>es-ES</language>
    <headline>Cierre del Refugio Alpha</headline>
  </info>
</alert>
```

### GeoJSON

GeoJSON exports include language metadata:

```json
{
  "type": "Feature",
  "properties": {
    "language": "es",
    "headline": "Cierre del Refugio Alpha"
  }
}
```

---

## Best Practices

### 1. Consistent Language Per Workspace

Choose a primary language for each workspace based on your team:

```python
DraftService(default_language="es")
```

### 2. Enable Language Detection for Mixed Workspaces

```bash
LANGUAGE_DETECTION_ENABLED=true
```

### 3. Override When Needed

Always allow facilitators to override auto-detected language:

```python
draft = await service.generate_draft(
    candidates=candidates,
    target_language="fr"  # Override detected language
)
```

### 4. Test Exports in Target Language

Verify CAP/EDXL-DE exports render correctly:

```bash
curl -H "Accept: application/xml" \
  "https://api.integritykit.aidarena.org/api/v1/exports/cap/update-123?language=es"
```

---

## Troubleshooting

### Language Not Supported

**Error:**
```json
{
  "error": "Unsupported language: de"
}
```

**Solution:**
1. Check `SUPPORTED_LANGUAGES` includes the language code
2. Verify prompt files exist for that language
3. Restart the service after configuration changes

### Language Detection Low Confidence

**Solutions:**
1. Lower `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD` (not recommended below 0.6)
2. Switch to Google Cloud Translation API:
   ```bash
   LANGUAGE_DETECTION_SERVICE=google
   ```
3. Manually specify language in API requests

### LLM Generating Wrong Language

**Solutions:**
1. Verify language prompts exist in `src/integritykit/llm/prompts/{language}/`
2. Check prompt registry includes language mappings
3. Ensure `get_prompt()` is called with correct language parameter

---

## Migration from v0.x

Existing COP drafts and updates remain in English. To migrate:

1. Update environment variables with language configuration
2. Restart the service
3. New drafts will use configured language
4. Optionally regenerate existing drafts in target language

No database migration required - language is stored at draft generation time.

---

## See Also

- [API Guide](api_guide.md) - Full API reference
- [External Integrations Guide](external-integrations.md) - CAP export documentation
- [Analytics Guide](analytics.md) - Analytics and reporting
- [LLM Prompt Engineering Guide](prompts.md) - Prompt customization

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8

**Sources Consolidated:**
- `multi-language-guide.md`
- `S8-4_QUICK_REFERENCE.md`
