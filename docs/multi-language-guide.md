# Multi-Language Support Guide - v1.0

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

## Overview

The Aid Arena Integrity Kit v1.0 supports multi-language COP (Common Operating Picture) draft generation in English, Spanish, and French. This guide explains how to configure and use the multi-language features.

## Supported Languages

| Language | Code | Status Labels | Wording Style |
|----------|------|---------------|---------------|
| English | `en` | VERIFIED, IN REVIEW, BLOCKED | Direct / Hedged |
| Spanish | `es` | VERIFICADO, EN REVISIÓN, BLOQUEADO | Directo / Tentativo |
| French | `fr` | VÉRIFIÉ, EN RÉVISION, BLOQUÉ | Direct / Nuancé |

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

For enhanced language detection using Google Cloud:

1. Create a Google Cloud project and enable the Translation API
2. Generate API credentials
3. Set environment variable:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/path/to/credentials.json
LANGUAGE_DETECTION_SERVICE=google
```

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

### Status Label Translations

Status labels are automatically translated based on the target language:

#### Verified Items

- **English**: `[VERIFIED]`
- **Spanish**: `[VERIFICADO]`
- **French**: `[VÉRIFIÉ]`

#### In Review Items

- **English**: `[IN REVIEW]`
- **Spanish**: `[EN REVISIÓN]`
- **French**: `[EN RÉVISION]`

#### Blocked Items

- **English**: `[BLOCKED]`
- **Spanish**: `[BLOQUEADO]`
- **French**: `[BLOQUÉ]`

### Section Header Translations

COP update sections are localized:

#### English

```
# Crisis Update #5

## Verified Updates

## In-Review Reports

## Open Questions
```

#### Spanish

```
# Actualización de Crisis #5

## Actualizaciones Verificadas

## Informes en Revisión

## Preguntas Abiertas
```

#### French

```
# Mise à Jour de Crise #5

## Mises à Jour Vérifiées

## Rapports en Révision

## Questions Ouvertes
```

### Wording Style

The LLM adapts wording style based on language and verification status:

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

## Slack Block Kit Integration

Block Kit templates support multi-language labels via the `i18n` module.

### Translation Keys

```python
from integritykit.slack.i18n import get_translation

# Get translated label
label = get_translation("en", "status.verified")  # "VERIFIED"
label = get_translation("es", "status.verified")  # "VERIFICADO"
label = get_translation("fr", "status.verified")  # "VÉRIFIÉ"
```

### Available Translation Keys

| Key | English | Spanish | French |
|-----|---------|---------|--------|
| `status.verified` | VERIFIED | VERIFICADO | VÉRIFIÉ |
| `status.in_review` | IN REVIEW | EN REVISIÓN | EN RÉVISION |
| `status.blocked` | BLOCKED | BLOQUEADO | BLOQUÉ |
| `section.verified` | Verified Updates | Actualizaciones Verificadas | Mises à Jour Vérifiées |
| `section.in_review` | In-Review Reports | Informes en Revisión | Rapports en Révision |
| `section.open_questions` | Open Questions | Preguntas Abiertas | Questions Ouvertes |

### Slack Block Kit Example

```python
from integritykit.slack.blocks import build_cop_update_blocks
from integritykit.slack.i18n import get_translation

blocks = build_cop_update_blocks(
    draft=draft,
    language="es"
)

# Or manually build with translations
blocks = [
    {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": get_translation("es", "section.verified")
        }
    }
]
```

## LLM Prompt Localization

### Prompt Registry

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

### Creating New Prompts

To add a new language:

1. Create language directory: `src/integritykit/llm/prompts/{language}/`
2. Copy prompt files from English directory
3. Translate system prompts and instructions
4. Update prompt registry in `registry.py`:

```python
PROMPT_REGISTRY = {
    "cop_draft_generation": {
        "en": english.cop_draft_generation,
        "es": spanish.cop_draft_generation,
        "fr": french.cop_draft_generation,
        "de": german.cop_draft_generation,  # New language
    }
}
```

5. Add language code to `SUPPORTED_LANGUAGES` environment variable

## Automatic Language Detection

When enabled, the system can automatically detect the language of incoming signals and suggest appropriate draft language.

### Configuration

```bash
LANGUAGE_DETECTION_ENABLED=true
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8
```

### Usage

```python
from integritykit.services.language_detection import LanguageDetectionService

detector = LanguageDetectionService()

# Detect language from text
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

## Export Formats

### CAP 1.2 XML

CAP exports support multi-language via separate `<info>` blocks:

```xml
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>cop-update-12345</identifier>
  <sent>2026-03-13T14:30:00Z</sent>

  <!-- English -->
  <info>
    <language>en-US</language>
    <headline>Shelter Alpha Closure</headline>
    <description>Shelter Alpha has closed...</description>
  </info>

  <!-- Spanish -->
  <info>
    <language>es-ES</language>
    <headline>Cierre del Refugio Alpha</headline>
    <description>El refugio Alpha ha cerrado...</description>
  </info>
</alert>
```

### EDXL-DE

EDXL-DE exports embed multi-language content as separate content objects.

### GeoJSON

GeoJSON exports include language metadata:

```json
{
  "type": "Feature",
  "properties": {
    "language": "es",
    "headline": "Cierre del Refugio Alpha",
    "description": "El refugio Alpha ha cerrado..."
  }
}
```

## Best Practices

### 1. Consistent Language Per Workspace

Choose a primary language for each workspace based on your team:

```python
# Configure workspace default
DraftService(default_language="es")
```

### 2. Language Detection for Mixed Workspaces

Enable auto-detection in multilingual environments:

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

### 4. Localize Custom Templates

When creating custom Slack templates, use the `i18n` module:

```python
from integritykit.slack.i18n import get_translation

heading = get_translation(language, "custom.my_heading")
```

### 5. Test Exports in Target Language

Verify CAP/EDXL-DE exports render correctly in target systems:

```bash
curl -H "Accept: application/xml" \
  "https://api.integritykit.aidarena.org/api/v1/exports/cap/update-123?language=es"
```

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

**Issue:** Auto-detection returns low confidence scores.

**Solutions:**
1. Lower `LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD` (not recommended below 0.6)
2. Switch to Google Cloud Translation API for better accuracy:
   ```bash
   LANGUAGE_DETECTION_SERVICE=google
   ```
3. Manually specify language in API requests

### Translations Not Appearing in Slack

**Issue:** Block Kit messages show English labels instead of Spanish/French.

**Solutions:**
1. Verify `language` parameter passed to `build_cop_update_blocks()`
2. Check `i18n.py` includes all required translation keys
3. Clear Slack message cache (re-post the message)

### LLM Generating Wrong Language

**Issue:** LLM generates English text despite `target_language="es"`.

**Solutions:**
1. Verify Spanish prompts exist in `src/integritykit/llm/prompts/spanish/`
2. Check prompt registry includes Spanish mappings
3. Ensure `get_prompt()` is called with correct language parameter
4. Review LLM system prompt for language instructions

## Performance Considerations

### LLM Prompt Caching

Multi-language prompts benefit from LLM prompt caching:

```bash
# Enable prompt caching
PROMPT_CACHING_ENABLED=true
PROMPT_CACHE_TTL_HOURS=24
```

This reduces latency and costs for repeated draft generation in the same language.

### Translation API Rate Limits

Google Cloud Translation API has rate limits:

- Free tier: 500,000 characters/month
- Paid tier: Higher limits

For high-volume deployments, use local `langdetect` service:

```bash
LANGUAGE_DETECTION_SERVICE=langdetect
```

## Migration from v0.x

Existing COP drafts and updates remain in English. To migrate:

1. Update environment variables with language configuration
2. Restart the service
3. New drafts will use configured language
4. Optionally regenerate existing drafts in target language

No database migration required - language is stored at draft generation time.

## API Reference

### DraftService

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

### LanguageDetectionService

```python
class LanguageDetectionService:
    async def detect_language(
        self,
        text: str,
        confidence_threshold: float = 0.8
    ) -> LanguageDetectionResult:
        ...
```

### Translation Helper

```python
def get_translation(
    language: str,
    key: str,
    default: Optional[str] = None
) -> str:
    """Get translation for a key in the specified language."""
```

## See Also

- [API Guide](api_guide.md)
- [Webhook System Guide](webhooks-guide.md)
- [CAP Export Documentation](integration-architecture-v1.0.md#cap-12-export)
- [LLM Prompt Engineering Guide](prompts.md)

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8
