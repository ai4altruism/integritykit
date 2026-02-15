# LLM Prompt Design Documentation

**Aid Arena Integrity Kit — Prompt Engineering Guide**

Version: 0.4
Date: 2026-02-15

---

## Table of Contents

1. [Overview](#overview)
2. [Model Selection Strategy](#model-selection-strategy)
3. [Prompt Templates](#prompt-templates)
4. [Design Rationale](#design-rationale)
5. [Cost Optimization](#cost-optimization)
6. [Usage Patterns](#usage-patterns)
7. [Testing and Evaluation](#testing-and-evaluation)

---

## Overview

The Integrity Kit uses LLM capabilities to assist facilitators in producing accurate, complete COP updates from Slack messages. All LLM outputs are suggestions/drafts that require human review and approval.

### Core LLM Operations

| Operation | Purpose | Model | Frequency |
|-----------|---------|-------|-----------|
| **Clustering** | Assign new signals to topic/incident clusters | Haiku 3.5 | Per message (high volume) |
| **Conflict Detection** | Identify contradictory claims | Haiku/Sonnet | Per cluster update |
| **Readiness Evaluation** | Assess COP candidate completeness | Haiku 3.5 | Per candidate state change |
| **COP Draft Generation** | Generate publication-ready line items | Sonnet 4 | Per COP publish cycle |
| **Next Action Recommendation** | Suggest best facilitator action | Haiku 3.5 | Per candidate view |

### Design Principles

1. **Humans remain accountable**: All LLM outputs are labeled as drafts/suggestions
2. **Cost efficiency**: Use the cheapest model that achieves required quality
3. **Structured outputs**: All prompts use JSON schemas for validation
4. **Explainability**: LLMs must provide reasoning for decisions
5. **Verification-aware**: Prompts adapt to verification status (verified vs in-review)

---

## Model Selection Strategy

### Anthropic Claude Model Tiers

| Model | Cost (per 1M tokens) | Speed | Best For |
|-------|----------------------|-------|----------|
| **Haiku 3.5** | $0.80 in / $4 out | Fastest | Classification, extraction, structured evaluation |
| **Sonnet 4** | $3 in / $15 out | Fast | Writing, analysis, complex reasoning |
| **Opus 4** | $15 in / $75 out | Slower | Advanced reasoning (not used in MVP) |

### Model Assignment Rationale

#### Clustering → Haiku 3.5

**Why Haiku:**
- Simple classification task (existing cluster vs new cluster)
- High volume (per message ingestion)
- Cost-critical (can process thousands of messages per incident)
- Fast response needed for real-time clustering

**Expected token usage:**
- Input: 500-1000 tokens (signal + cluster summaries)
- Output: 50-100 tokens (structured classification)
- Cost per call: ~$0.0005 - $0.001

#### Conflict Detection → Haiku 3.5 / Sonnet 4

**Why Haiku (default):**
- Most conflicts are straightforward contradictions
- Structured comparison task
- Medium volume (per cluster with multiple signals)

**Why Sonnet (escalation):**
- Nuanced conflicts requiring interpretation
- Temporal reasoning (sequence of events)
- Ambiguous phrasing requiring context understanding

**Routing logic:**
- Use Haiku for initial detection
- Escalate to Sonnet if conflict_type is "temporal_inconsistency" or confidence is "low"

**Expected token usage (Haiku):**
- Input: 800-2000 tokens (2-5 signals)
- Output: 100-200 tokens (conflict analysis)
- Cost per call: ~$0.001 - $0.002

#### Readiness Evaluation → Haiku 3.5

**Why Haiku:**
- Structured checklist evaluation
- Well-defined criteria (SRS FR-COP-READ-001)
- High volume (per candidate state change)
- No creative writing required

**Expected token usage:**
- Input: 600-1200 tokens (candidate fields)
- Output: 150-300 tokens (field quality scores + reasoning)
- Cost per call: ~$0.001 - $0.0015

#### COP Draft Generation → Sonnet 4

**Why Sonnet:**
- Requires nuanced writing
- Must apply verification-aware wording (hedged vs direct)
- Context-sensitive phrasing (high-stakes vs routine)
- Publication quality required (human edit load reduced)
- Lower volume (per COP publish cycle, not per message)

**Expected token usage:**
- Input: 1000-2000 tokens (candidate + evidence pack)
- Output: 200-400 tokens (complete line item)
- Cost per call: ~$0.006 - $0.012

#### Next Action Recommendation → Haiku 3.5

**Why Haiku:**
- Decision tree-style recommendation
- Well-defined priority logic
- High volume (per candidate view in facilitator UI)
- Cost-sensitive (displayed frequently)

**Expected token usage:**
- Input: 500-1000 tokens (candidate state)
- Output: 100-150 tokens (action + reasoning)
- Cost per call: ~$0.0005 - $0.001

---

## Prompt Templates

All prompt templates are located in `/src/integritykit/llm/prompts/`.

### 1. Clustering (`clustering.py`)

**Purpose:** Classify whether a new signal belongs to an existing cluster or creates a new cluster.

**System Prompt Key Points:**
- Cluster by TOPIC and INCIDENT, not channel or author
- Prefer existing clusters when topically related
- Create new clusters only for genuinely new topics
- Time proximity alone does not define clusters

**User Prompt Structure:**
```
NEW SIGNAL:
  Author, channel, timestamp, content, thread context

EXISTING CLUSTERS:
  List of cluster summaries with topic and key details

OUTPUT:
  JSON with assignment, cluster_id/topic, confidence, reasoning
```

**Output Schema:**
```json
{
  "assignment": "existing_cluster" | "new_cluster",
  "cluster_id": "string or null",
  "new_cluster_topic": "string or null",
  "confidence": "high" | "medium" | "low",
  "reasoning": "explanation"
}
```

**Typical Use Case:**
```python
from integritykit.llm.prompts.clustering import format_clustering_prompt

prompt = format_clustering_prompt(
    signal_author="@user123",
    signal_channel="#operations",
    signal_timestamp="2026-02-15T14:30:00Z",
    signal_content="Bridge on Main St is now closed",
    signal_thread_context="Reply to: Traffic updates thread",
    existing_clusters=[
        {
            "cluster_id": "cluster-001",
            "topic": "Main Street Bridge damage",
            "key_details": "Bridge damage reported, closure pending",
            "signal_count": 5,
            "latest_timestamp": "2026-02-15T14:00:00Z"
        }
    ]
)
```

### 2. Conflict Detection (`conflict_detection.py`)

**Purpose:** Identify contradictory claims between signals in the same cluster.

**System Prompt Key Points:**
- Detect direct contradictions (open vs closed, location mismatches, count discrepancies)
- Distinguish conflicts from supplemental details
- Recognize updates that supersede earlier info
- Assess severity (high for safety-critical conflicts)

**User Prompt Structure:**
```
CLUSTER TOPIC: [topic name]

SIGNALS TO COMPARE:
  List of signals with author, timestamp, content, source type

OUTPUT:
  JSON with conflict detection, type, severity, fields, resolution suggestion
```

**Output Schema:**
```json
{
  "conflict_detected": true | false,
  "conflict_type": "direct_contradiction" | "temporal_inconsistency" | "location_mismatch" | "count_discrepancy" | "no_conflict",
  "severity": "high" | "medium" | "low" | "none",
  "conflicting_fields": [
    {
      "field": "location" | "time" | "count" | "status" | "attribution" | "other",
      "signal_1_value": "...",
      "signal_2_value": "...",
      "description": "..."
    }
  ],
  "conflicting_signal_ids": ["id1", "id2"],
  "resolution_suggestion": "request_clarification | verify_sources | merge_as_uncertain | mark_one_disproven",
  "explanation": "..."
}
```

**Severity Logic:**
- HIGH: Safety, evacuation, medical guidance conflicts
- MEDIUM: Resource allocation, access, operational impact
- LOW: Minor inconsistencies, easily resolved

### 3. Readiness Evaluation (`readiness_evaluation.py`)

**Purpose:** Assess COP candidate completeness and compute readiness state.

**System Prompt Key Points:**
- Evaluate against minimum fields: what/where/when/who/so-what/evidence
- Apply readiness logic (Ready-Verified / Ready-In-Review / Blocked)
- High-stakes items require verification
- Identify blocking issues (missing fields, conflicts)

**User Prompt Structure:**
```
COP CANDIDATE:
  Full candidate data including all fields, verification status, risk tier

OUTPUT:
  JSON with readiness state, missing fields, quality scores, blocking issues
```

**Output Schema:**
```json
{
  "readiness_state": "ready_verified" | "ready_in_review" | "blocked",
  "missing_fields": ["what", "where", ...],
  "field_quality_scores": [
    {
      "field": "what" | "where" | "when" | "who" | "so_what" | "evidence",
      "present": true | false,
      "quality": "complete" | "partial" | "missing",
      "notes": "..."
    }
  ],
  "blocking_issues": ["Missing location", ...],
  "recommended_state": "ready_verified" | "ready_in_review" | "blocked",
  "explanation": "..."
}
```

**Readiness Decision Tree:**
```
1. Are all minimum fields present?
   NO → BLOCKED
   YES → Continue

2. Is verification_status "verified"?
   YES → READY_VERIFIED
   NO → Continue

3. Are minimum fields sufficient to avoid misleading readers?
   NO → BLOCKED
   YES → Continue

4. Is risk_tier "high_stakes" AND verification_status not "verified"?
   YES → BLOCKED (unless override)
   NO → READY_IN_REVIEW
```

### 4. COP Draft Generation (`cop_draft_generation.py`)

**Purpose:** Generate publication-ready COP line items with verification-aware wording.

**System Prompt Key Points:**
- Apply wording based on verification status
- VERIFIED: Direct, factual phrasing ("is", "has", "confirmed")
- IN-REVIEW: Hedged phrasing ("Reports indicate", "Unconfirmed:", "Seeking confirmation")
- DISPROVEN: Lead with "CORRECTION:" or "DISPROVEN:"
- High-stakes in-review must include next verification step and recheck time

**User Prompt Structure:**
```
COP CANDIDATE:
  Full candidate with what/where/when/who/so-what, evidence pack, verification status

OUTPUT:
  JSON with line item text, status label, citations, wording style, section placement
```

**Output Schema:**
```json
{
  "line_item_text": "Complete COP line item with citations",
  "status_label": "VERIFIED" | "IN REVIEW" | "DISPROVEN",
  "citations": ["url1", "url2"],
  "wording_style": "direct_factual" | "hedged_uncertain",
  "next_verification_step": "string or null",
  "recheck_time": "string or null",
  "section_placement": "verified_updates" | "in_review_updates" | "disproven_rumor_control" | "open_questions"
}
```

**Wording Examples:**

**Verified:**
> [VERIFIED] Main Street Bridge is closed to all traffic as of 14:00 PST due to structural damage. County DOT estimates reopening Monday. ([Slack](https://slack.com/...), [DOT Update](https://county.gov/...))

**In-Review:**
> [IN REVIEW] Unconfirmed: Reports indicate Main Street Bridge may be closed due to structural concerns. Seeking official confirmation from county DOT. Next step: Contact DOT public info. Recheck: 16:00 PST. ([Slack](https://slack.com/...))

**Disproven:**
> [DISPROVEN] CORRECTION: Earlier reports of Main Street Bridge closure are incorrect. Bridge remains open per county DOT as of 15:00 PST. ([DOT Twitter](https://twitter.com/...))

### 5. Next Action Recommendation (`next_action.py`)

**Purpose:** Recommend the best next action for a facilitator to improve COP candidate readiness.

**System Prompt Key Points:**
- Recommend single primary action plus 1-3 alternatives
- Priority logic based on risk and readiness
- Provide urgency level (immediate / soon / when possible)
- For clarifications, provide suggested message template

**User Prompt Structure:**
```
COP CANDIDATE STATE:
  Readiness state, missing fields, conflicts, verification status, risk tier

OUTPUT:
  JSON with primary action, alternatives, target, urgency, reasoning
```

**Output Schema:**
```json
{
  "primary_action": "request_clarification" | "assign_verification" | "merge_duplicate" | "resolve_conflict" | "publish_as_in_review" | "publish_as_verified" | "defer",
  "alternative_actions": ["action1", "action2"],
  "action_target": "Specific target (field, person, candidates)",
  "urgency": "immediate" | "soon" | "when_possible",
  "reasoning": "Why this is best action",
  "suggested_message": "Template message or null"
}
```

**Priority Logic:**
1. High-stakes unverified → ASSIGN_VERIFICATION (immediate)
2. Unresolved high-severity conflict → RESOLVE_CONFLICT (immediate)
3. Missing critical field → REQUEST_CLARIFICATION (soon)
4. Potential duplicate → MERGE_DUPLICATE (when possible)
5. Ready verified → PUBLISH_AS_VERIFIED (soon)
6. Ready in-review (not high-stakes) → PUBLISH_AS_IN_REVIEW (soon)
7. Incomplete, low-risk → REQUEST_CLARIFICATION or DEFER (when possible)

**Clarification Message Templates:**

Included in `next_action.py` as `CLARIFICATION_TEMPLATES`:
- `location`: Request exact location
- `time`: Request timestamp and timezone
- `location_and_time`: Request both
- `source`: Request source attribution
- `conflict`: Request conflict resolution

---

## Design Rationale

### Why Structured JSON Outputs?

1. **Validation**: Pydantic schemas catch malformed outputs before they reach application logic
2. **Consistency**: Guarantees downstream code can rely on field presence and types
3. **Explainability**: `reasoning` and `explanation` fields provide audit trail
4. **Testing**: Easy to unit test with expected output schemas

### Why Separate System and User Prompts?

1. **Prompt Caching**: System prompts are static and can be cached (50% cost reduction on repeated calls)
2. **Role Clarity**: System prompt defines the role, user prompt provides specific data
3. **Maintainability**: Update instructions without changing data formatting

### Why Include Confidence/Quality Scores?

1. **Human-in-the-loop**: Low confidence signals can be flagged for human review
2. **Metrics**: Track LLM classification quality over time
3. **Routing**: Escalate low-confidence tasks to stronger models

### Verification-Aware Wording Design

The COP draft generation prompts implement SRS FR-COP-WORDING-001 by explicitly instructing the LLM to:

1. **Detect verification status** from candidate metadata
2. **Apply appropriate wording style**:
   - Verified → Direct, factual
   - In-review → Hedged, uncertain
   - Disproven → Correction-leading
3. **Include verification metadata** (next step, recheck time) for high-stakes in-review

**Why this matters:**
- Reduces cognitive load on facilitators (don't have to manually rephrase each line)
- Ensures consistency in COP wording across updates
- Makes uncertainty explicit (prevents false certainty)
- Aligns with quality target QT-3 (uncertainty is explicit)

---

## Cost Optimization

### Estimated Costs Per Incident

Assume a 24-hour incident with:
- 500 Slack messages
- 50 clusters formed
- 20 COP candidates promoted
- 3 COP updates published (8 line items each)

| Operation | Calls | Model | Cost per Call | Total Cost |
|-----------|-------|-------|---------------|------------|
| Clustering | 500 | Haiku | $0.0008 | $0.40 |
| Conflict Detection | 50 | Haiku | $0.0015 | $0.08 |
| Readiness Evaluation | 60 | Haiku | $0.0012 | $0.07 |
| Next Action | 100 | Haiku | $0.0008 | $0.08 |
| COP Draft Generation | 24 | Sonnet | $0.009 | $0.22 |
| **TOTAL** | | | | **$0.85** |

**Per-incident cost: ~$1** (well within budget for crisis response)

### Cost Reduction Strategies

1. **Prompt Caching**
   - Cache static system prompts
   - 50% reduction on input token costs for repeated calls
   - Implemented in all prompt modules

2. **Batch Processing**
   - Use Message Batches API for clustering (50% cost reduction)
   - Batch conflict detection for clusters with many signals

3. **Intelligent Model Routing**
   - Default to Haiku for conflict detection
   - Escalate to Sonnet only when confidence is low
   - Saves ~60% on conflict detection costs

4. **Token Efficiency**
   - Minimize cluster summaries (topic + key details only)
   - Truncate thread context to last 3 messages
   - Use short field names in JSON

---

## Usage Patterns

### Pattern 1: Real-time Signal Ingestion

```python
from integritykit.llm.prompts.clustering import (
    format_clustering_prompt,
    CLUSTERING_SYSTEM_PROMPT,
    CLUSTERING_OUTPUT_SCHEMA
)
import anthropic

client = anthropic.Anthropic()

# On new Slack message
prompt = format_clustering_prompt(
    signal_author=message.user,
    signal_channel=message.channel,
    signal_timestamp=message.timestamp,
    signal_content=message.text,
    signal_thread_context=get_thread_context(message),
    existing_clusters=fetch_recent_clusters()
)

response = client.messages.create(
    model="claude-haiku-3-5-20241022",
    max_tokens=150,
    system=[{
        "type": "text",
        "text": CLUSTERING_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}  # Cache system prompt
    }],
    messages=[{"role": "user", "content": prompt}]
)

# Validate output
output = json.loads(response.content[0].text)
validate_against_schema(output, CLUSTERING_OUTPUT_SCHEMA)

# Route to cluster
if output["assignment"] == "existing_cluster":
    add_signal_to_cluster(message, output["cluster_id"])
else:
    create_new_cluster(message, output["new_cluster_topic"])
```

### Pattern 2: Facilitator Backlog Review

```python
from integritykit.llm.prompts.next_action import (
    format_next_action_prompt,
    NEXT_ACTION_SYSTEM_PROMPT
)

# When facilitator views candidate
candidate_state = {
    "candidate_id": candidate.id,
    "readiness_state": candidate.readiness,
    "missing_fields": candidate.missing_fields,
    "has_unresolved_conflicts": candidate.has_conflicts,
    "conflict_severity": candidate.conflict_severity,
    "verification_status": candidate.verification_status,
    "risk_tier": candidate.risk_tier,
    "has_potential_duplicates": len(candidate.duplicates) > 0,
    "evidence_pack_size": len(candidate.evidence_pack)
}

prompt = format_next_action_prompt(candidate_state)

response = client.messages.create(
    model="claude-haiku-3-5-20241022",
    max_tokens=200,
    system=[{
        "type": "text",
        "text": NEXT_ACTION_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}
    }],
    messages=[{"role": "user", "content": prompt}]
)

output = json.loads(response.content[0].text)

# Display recommendation in UI
display_recommended_action(
    action=output["primary_action"],
    target=output["action_target"],
    urgency=output["urgency"],
    reasoning=output["reasoning"],
    message_template=output.get("suggested_message")
)
```

### Pattern 3: COP Publishing Workflow

```python
from integritykit.llm.prompts.cop_draft_generation import (
    format_cop_draft_generation_prompt,
    COP_DRAFT_GENERATION_SYSTEM_PROMPT
)

# When facilitator triggers COP publish
verified_candidates = get_candidates_by_state("ready_verified")
in_review_candidates = get_candidates_by_state("ready_in_review")

cop_sections = {
    "verified_updates": [],
    "in_review_updates": [],
    "disproven_rumor_control": []
}

# Generate line items for each candidate (use Sonnet for quality)
for candidate in verified_candidates + in_review_candidates:
    prompt = format_cop_draft_generation_prompt(candidate)

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        system=[{
            "type": "text",
            "text": COP_DRAFT_GENERATION_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{"role": "user", "content": prompt}]
    )

    output = json.loads(response.content[0].text)

    # Add to appropriate section
    cop_sections[output["section_placement"]].append({
        "text": output["line_item_text"],
        "citations": output["citations"],
        "label": output["status_label"]
    })

# Assemble final COP draft for facilitator review
cop_draft = assemble_cop_update(cop_sections)
present_for_facilitator_approval(cop_draft)
```

### Pattern 4: Batch Conflict Detection

```python
from integritykit.llm.prompts.conflict_detection import (
    format_conflict_detection_prompt,
    CONFLICT_DETECTION_SYSTEM_PROMPT
)

# When cluster receives multiple new signals
for cluster in get_clusters_with_new_signals():
    signals = get_cluster_signals(cluster)

    if len(signals) < 2:
        continue  # No conflicts possible

    prompt = format_conflict_detection_prompt(
        cluster_topic=cluster.topic,
        signals=signals
    )

    response = client.messages.create(
        model="claude-haiku-3-5-20241022",
        max_tokens=300,
        system=[{
            "type": "text",
            "text": CONFLICT_DETECTION_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{"role": "user", "content": prompt}]
    )

    output = json.loads(response.content[0].text)

    if output["conflict_detected"] and output["severity"] in ["high", "medium"]:
        # Flag cluster for facilitator review
        flag_cluster_conflict(
            cluster=cluster,
            conflict_type=output["conflict_type"],
            severity=output["severity"],
            conflicting_signals=output["conflicting_signal_ids"],
            resolution_suggestion=output["resolution_suggestion"]
        )
```

---

## Testing and Evaluation

### Unit Testing Prompts

Each prompt module should have associated tests:

```python
# tests/llm/prompts/test_clustering.py
def test_format_clustering_prompt():
    """Test that clustering prompt formats correctly."""
    prompt = format_clustering_prompt(
        signal_author="@alice",
        signal_channel="#ops",
        signal_timestamp="2026-02-15T14:00:00Z",
        signal_content="Bridge closure update",
        signal_thread_context="",
        existing_clusters=[
            {
                "cluster_id": "c1",
                "topic": "Bridge damage",
                "key_details": "Main St bridge",
                "signal_count": 3,
                "latest_timestamp": "2026-02-15T13:00:00Z"
            }
        ]
    )

    assert "@alice" in prompt
    assert "Bridge closure update" in prompt
    assert "Bridge damage" in prompt

def test_clustering_output_schema():
    """Test that valid outputs pass schema validation."""
    valid_output = {
        "assignment": "existing_cluster",
        "cluster_id": "c1",
        "new_cluster_topic": None,
        "confidence": "high",
        "reasoning": "Same incident"
    }
    validate_against_schema(valid_output, CLUSTERING_OUTPUT_SCHEMA)
```

### Integration Testing with LLM

```python
# tests/integration/test_clustering_llm.py
@pytest.mark.integration
def test_clustering_with_haiku(anthropic_client):
    """Test actual clustering with Haiku model."""
    prompt = format_clustering_prompt(
        signal_author="@user",
        signal_channel="#ops",
        signal_timestamp="2026-02-15T14:00:00Z",
        signal_content="Main St bridge is now fully closed",
        signal_thread_context="",
        existing_clusters=[
            {
                "cluster_id": "bridge-damage-001",
                "topic": "Main Street bridge structural damage",
                "key_details": "Damage reported, closure pending",
                "signal_count": 3,
                "latest_timestamp": "2026-02-15T13:00:00Z"
            }
        ]
    )

    response = anthropic_client.messages.create(
        model="claude-haiku-3-5-20241022",
        max_tokens=150,
        system=CLUSTERING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    output = json.loads(response.content[0].text)

    # Should assign to existing cluster
    assert output["assignment"] == "existing_cluster"
    assert output["cluster_id"] == "bridge-damage-001"
    assert output["confidence"] in ["high", "medium", "low"]
```

### Evaluation Metrics

Track these metrics in production:

1. **Classification Accuracy** (Clustering)
   - Sample 100 cluster assignments
   - Human facilitator labels ground truth
   - Measure: % agreement with facilitator

2. **Conflict Detection Precision/Recall**
   - Precision: % of detected conflicts that are real
   - Recall: % of real conflicts that were detected
   - Target: >90% precision, >80% recall

3. **Readiness Agreement** (Readiness Evaluation)
   - % agreement with facilitator final readiness decision
   - Target: >85% agreement

4. **Draft Quality** (COP Draft Generation)
   - Facilitator edit rate (characters changed / total characters)
   - Wording style correctness (verified vs in-review)
   - Target: <30% edit rate, >95% wording style correctness

5. **Next Action Usefulness**
   - % of recommendations that facilitator follows
   - Target: >70% follow rate

### Synthetic Dataset Creation

Create test fixtures with known ground truth:

```python
# tests/fixtures/test_signals.py
BRIDGE_CLOSURE_SIGNALS = [
    {
        "id": "sig-001",
        "content": "Main St bridge has structural damage, inspecting now",
        "timestamp": "2026-02-15T10:00:00Z",
        "author": "@inspector",
        "expected_cluster": "bridge-damage"
    },
    {
        "id": "sig-002",
        "content": "Bridge closure starts at 2pm today",
        "timestamp": "2026-02-15T13:00:00Z",
        "author": "@dot_official",
        "expected_cluster": "bridge-damage"
    },
    {
        "id": "sig-003",
        "content": "Oak Ave shelter opening at 3pm for storm",
        "timestamp": "2026-02-15T13:30:00Z",
        "author": "@shelter_coord",
        "expected_cluster": "new_cluster"  # Different topic
    }
]

CONFLICT_SIGNALS = [
    {
        "id": "sig-010",
        "content": "Bridge closed as of 2pm",
        "timestamp": "2026-02-15T14:00:00Z",
        "expected_conflict": False
    },
    {
        "id": "sig-011",
        "content": "Bridge is still open, DOT says no closure",
        "timestamp": "2026-02-15T14:15:00Z",
        "expected_conflict": True,
        "expected_severity": "high"
    }
]
```

---

## Appendix: Prompt Evolution and Versioning

As the system is deployed and we gather real-world feedback, prompts will evolve. Track changes:

```python
# src/integritykit/llm/prompts/clustering.py

# Version history:
# v0.4.0 (2026-02-15): Initial clustering prompts with topic-based logic
# v0.4.1 (TBD): Add temporal clustering hints for evolving incidents
# v0.5.0 (TBD): Multi-lingual support for Spanish/French crisis contexts
```

---

## Related Documentation

- [SRS (System Requirements Specification)](/docs/Aid_Arena_Integrity_Kit_SRS_Ambient_v0_4.md)
- [CDD (Capability Description Document)](/docs/Aid_Arena_Integrity_Kit_CDD_Ambient_v0_4.md)
- LLM Prompt Patterns Skill: `~/.claude/skills/llm-prompt-patterns/SKILL.md`

---

**Document Status:** Draft v0.4
**Last Updated:** 2026-02-15
**Author:** Claude Code with Aid Arena team guidance
