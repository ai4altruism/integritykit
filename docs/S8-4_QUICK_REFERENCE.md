# S8-4 Multi-Language Support - Quick Reference

## Quick Start

### Generate Draft in Spanish
```python
from integritykit.services.draft import DraftService

service = DraftService(default_language="es")
draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="es",  # Spanish
)
```

### Generate Draft in French
```python
service = DraftService(default_language="fr")
draft = await service.generate_draft(
    workspace_id="W123",
    candidates=candidates,
    target_language="fr",  # French
)
```

### Export Markdown with Localized Headers
```python
# Spanish
markdown_es = draft.to_markdown(language="es")

# French
markdown_fr = draft.to_markdown(language="fr")
```

## Supported Languages

| Code | Language | Status Labels | Wording Style |
|------|----------|---------------|---------------|
| `en` | English | VERIFIED, IN REVIEW | Direct / Hedged |
| `es` | Spanish | VERIFICADO, EN REVISIÓN | Directo / Tentativo |
| `fr` | French | VÉRIFIÉ, EN RÉVISION | Direct / Nuancé |

## API Parameters

### DraftService
```python
DraftService(
    openai_client=client,
    model="gpt-4o",
    use_llm=True,
    default_language="en"  # NEW: Default language for all drafts
)
```

### generate_draft()
```python
await service.generate_draft(
    workspace_id="W123",
    candidates=[...],
    title="My COP",  # Optional
    include_open_questions=True,
    target_language="es"  # NEW: Override default language
)
```

### generate_line_item()
```python
await service.generate_line_item(
    candidate=candidate,
    use_llm=False,
    target_language="fr"  # NEW: Language for this item
)
```

### PublishService.create_draft_from_candidates()
```python
await publish_service.create_draft_from_candidates(
    workspace_id="W123",
    candidate_ids=[...],
    user=current_user,
    title="My COP",  # Optional
    target_language="es"  # NEW: Language for draft
)
```

## Status Label Translations

### Verified Items
- **English**: `VERIFIED`
- **Spanish**: `VERIFICADO`
- **French**: `VÉRIFIÉ`

### In Review Items
- **English**: `IN REVIEW`
- **Spanish**: `EN REVISIÓN`
- **French**: `EN RÉVISION`

### Blocked Items
- **English**: `BLOCKED`
- **Spanish**: `BLOQUEADO`
- **French**: `BLOQUÉ`

## Wording Examples

### English (Direct - Verified)
```
Bridge is closed to all traffic as of 14:00 PST. (Source: City DOT)
```

### English (Hedged - In Review)
```
Unconfirmed: Reports indicate bridge may be closed. Seeking confirmation from City DOT.
```

### Spanish (Directo - Verificado)
```
El puente está cerrado al tráfico desde las 14:00 hora del Pacífico. (Fuente: DOT Ciudad)
```

### Spanish (Tentativo - En Revisión)
```
Sin confirmar: Se reporta que el puente estaría cerrado. Se busca confirmación del DOT Ciudad.
```

### French (Direct - Vérifié)
```
Le pont est fermé à toute circulation à partir de 14h00 heure du Pacifique. (Source: DOT Ville)
```

### French (Nuancé - En Révision)
```
Non confirmé: Il est rapporté que le pont serait fermé. Confirmation recherchée auprès du DOT Ville.
```

## Markdown Headers

### English
```markdown
## Verified Updates
## In Review (Unconfirmed)
## Rumor Control / Corrections
## Open Questions / Gaps
```

### Spanish
```markdown
## Actualizaciones Verificadas
## En Revisión (Sin Confirmar)
## Control de Rumores / Correcciones
## Preguntas Abiertas / Brechas
```

### French
```markdown
## Mises à jour Vérifiées
## En Révision (Non Confirmé)
## Contrôle des Rumeurs / Corrections
## Questions Ouvertes / Lacunes
```

## Next Steps Text

### High-Stakes (Urgent)

**English**:
```
URGENT: Identify and contact primary source for direct confirmation
```

**Spanish**:
```
URGENTE: Identificar y contactar fuente primaria para confirmación directa
```

**French**:
```
URGENT : Identifier et contacter la source primaire pour confirmation directe
```

### Elevated

**English**:
```
Identify primary source for verification
```

**Spanish**:
```
Identificar fuente primaria para verificación
```

**French**:
```
Identifier la source primaire pour vérification
```

## Recheck Time Text

### 30 Minutes
- **English**: `Within 30 minutes`
- **Spanish**: `Dentro de 30 minutos`
- **French**: `Dans les 30 minutes`

### 2 Hours
- **English**: `Within 2 hours`
- **Spanish**: `Dentro de 2 horas`
- **French**: `Dans les 2 heures`

### 4 Hours
- **English**: `Within 4 hours`
- **Spanish**: `Dentro de 4 horas`
- **French**: `Dans les 4 heures`

## Testing

Run multi-language tests:
```bash
pytest tests/unit/test_draft_multilang.py -v
```

Test specific language:
```bash
pytest tests/unit/test_draft_multilang.py::test_generate_draft_spanish -v
```

## Troubleshooting

### Language Not Working?
- Check language code: `"en"`, `"es"`, `"fr"` (lowercase)
- Verify prompt registry has language loaded
- Check logs for fallback warnings

### Wrong Status Labels?
- Ensure `target_language` is passed to `generate_line_item()`
- Check that language is in supported list
- Verify language isn't falling back to English

### Headers Still in English?
- Pass `language` parameter to `to_markdown()`
- Or ensure draft metadata has correct language
- Check `draft.metadata.get('language')`

## Implementation Checklist

- [ ] Add `default_language` to `DraftService.__init__`
- [ ] Add `target_language` to `generate_line_item()`
- [ ] Add `target_language` to `generate_draft()`
- [ ] Update `_generate_rule_based()` with language support
- [ ] Update `_generate_with_llm()` with prompt registry
- [ ] Add localization helper methods
- [ ] Update `COPDraft.to_markdown()` with language support
- [ ] Update `PublishService` methods with language parameters
- [ ] Run tests: `pytest tests/unit/test_draft_multilang.py`
- [ ] Manual test with Spanish candidates
- [ ] Manual test with French candidates

## Resources

- **Full Implementation Guide**: `docs/S8-4_multilang_implementation.md`
- **Implementation Summary**: `docs/S8-4_IMPLEMENTATION_SUMMARY.md`
- **Test Suite**: `tests/unit/test_draft_multilang.py`
- **Prompt Registry**: `src/integritykit/llm/prompts/registry.py`
- **Spanish Prompts**: `src/integritykit/llm/prompts/spanish/`
- **French Prompts**: `src/integritykit/llm/prompts/french/`

## Key Principles

1. **Backwards Compatible**: Default is English, all new parameters optional
2. **Fail Gracefully**: Unsupported languages fall back to English
3. **Metadata Tracking**: Language stored in draft.metadata
4. **Consistent API**: Same pattern across all methods
5. **Prompt Registry**: Centralized management of all translations

---

**Quick Tip**: Start with Spanish tests to verify implementation, then add French support.
