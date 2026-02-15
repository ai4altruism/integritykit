# LLM Prompts Module

This module contains all LLM prompt templates for the Aid Arena Integrity Kit.

## Quick Reference

| Module | Purpose | Model | Cost/Call |
|--------|---------|-------|-----------|
| `clustering.py` | Signal-to-cluster assignment | Haiku 3.5 | ~$0.0008 |
| `conflict_detection.py` | Identify contradictions | Haiku/Sonnet | ~$0.0015 |
| `readiness_evaluation.py` | Assess COP completeness | Haiku 3.5 | ~$0.0012 |
| `cop_draft_generation.py` | Generate line items | Sonnet 4 | ~$0.009 |
| `next_action.py` | Recommend facilitator action | Haiku 3.5 | ~$0.0008 |

## Usage Example

```python
from integritykit.llm.prompts.clustering import (
    format_clustering_prompt,
    CLUSTERING_SYSTEM_PROMPT,
    CLUSTERING_OUTPUT_SCHEMA
)

# Format prompt with data
prompt = format_clustering_prompt(
    signal_author="@user",
    signal_channel="#ops",
    signal_timestamp="2026-02-15T14:00:00Z",
    signal_content="Update on bridge closure",
    signal_thread_context="",
    existing_clusters=clusters
)

# Call LLM (Anthropic Claude)
response = client.messages.create(
    model="claude-haiku-3-5-20241022",
    max_tokens=150,
    system=[{
        "type": "text",
        "text": CLUSTERING_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }],
    messages=[{"role": "user", "content": prompt}]
)

# Parse and validate output
output = json.loads(response.content[0].text)
# Validate against CLUSTERING_OUTPUT_SCHEMA
```

## Design Principles

1. **Structured Outputs**: All prompts return JSON with defined schemas
2. **Cost Efficiency**: Use cheapest model that achieves quality
3. **Prompt Caching**: System prompts are cache-enabled
4. **Explainability**: All outputs include reasoning/explanation
5. **Verification-Aware**: Prompts adapt to verification status

## Documentation

See `/docs/prompts.md` for comprehensive documentation including:
- Model selection rationale
- Prompt design decisions
- Cost optimization strategies
- Usage patterns and examples
- Testing and evaluation guidance
