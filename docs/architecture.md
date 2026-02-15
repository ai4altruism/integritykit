# Aid Arena Integrity Kit — Architecture Documentation

**Version**: 1.0
**Date**: 2026-02-15
**Status**: Draft

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Design Philosophy](#design-philosophy)
3. [Architecture Layers](#architecture-layers)
4. [Core Components](#core-components)
5. [Data Flow](#data-flow)
6. [Database Design](#database-design)
7. [LLM Integration Architecture](#llm-integration-architecture)
8. [Security Model](#security-model)
9. [Deployment Architecture](#deployment-architecture)
10. [Performance and Scalability](#performance-and-scalability)
11. [Monitoring and Observability](#monitoring-and-observability)

---

## System Overview

The Aid Arena Integrity Kit is a FastAPI-based backend system that operates in **ambient mode**: it continuously processes Slack messages in the background without requiring general participants to change their behavior. A small team of facilitators uses private tooling to transform raw Slack signals into accurate, provenance-backed Common Operating Picture (COP) updates.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SYSTEMS                              │
│                                                                         │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐              │
│  │    Slack     │   │    OpenAI    │   │  External    │              │
│  │   Workspace  │   │   API (LLM)  │   │   Sources    │              │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘              │
└─────────┼──────────────────┼──────────────────┼────────────────────────┘
          │                  │                  │
          │ Events API       │ Completions      │ Web Search
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      APPLICATION LAYER (FastAPI)                        │
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  API Routes                                                       │ │
│  │  /backlog  /candidates  /cop  /search  /metrics  /audit  /users  │ │
│  └───────────────────────────┬───────────────────────────────────────┘ │
│                              │                                         │
│  ┌───────────────────────────┼───────────────────────────────────────┐ │
│  │  Middleware & Auth        │                                       │ │
│  │  RBAC Enforcement • Audit Logging • Rate Limiting                 │ │
│  └───────────────────────────┼───────────────────────────────────────┘ │
│                              │                                         │
│  ┌───────────────────────────┼───────────────────────────────────────┐ │
│  │  Service Layer            │                                       │ │
│  │  ┌────────────┐ ┌────────┴────┐ ┌─────────────┐ ┌──────────────┐ │ │
│  │  │  Signal    │ │  Cluster    │ │  Candidate  │ │  Publishing  │ │ │
│  │  │  Ingestor  │ │  Manager    │ │  Manager    │ │  Service     │ │ │
│  │  └─────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬───────┘ │ │
│  └────────┼───────────────┼───────────────┼───────────────┼─────────┘ │
│           │               │               │               │           │
│  ┌────────┼───────────────┼───────────────┼───────────────┼─────────┐ │
│  │  LLM Service Layer     │               │               │         │ │
│  │  ┌──────────┐ ┌────────┴──┐ ┌─────────┴──┐ ┌──────────┴───────┐ │ │
│  │  │Clustering│ │ Conflict  │ │ Readiness  │ │  COP Drafting    │ │ │
│  │  │  (Haiku) │ │Detection  │ │ Evaluation │ │    (Sonnet)      │ │ │
│  │  │          │ │(Haiku/Son)│ │  (Haiku)   │ │                  │ │ │
│  │  └──────────┘ └───────────┘ └────────────┘ └──────────────────┘ │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                                                                         │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        PERSISTENCE LAYER                                │
│                                                                         │
│  ┌──────────────────────┐   ┌──────────────────────┐                  │
│  │      MongoDB         │   │      ChromaDB        │                  │
│  │  ┌────────────────┐  │   │  ┌────────────────┐  │                  │
│  │  │ signals        │  │   │  │ Vector Index   │  │                  │
│  │  │ clusters       │  │   │  │ (Embeddings)   │  │                  │
│  │  │ cop_candidates │  │   │  │                │  │                  │
│  │  │ cop_updates    │  │   │  └────────────────┘  │                  │
│  │  │ audit_log      │  │   │                      │                  │
│  │  │ users          │  │   │                      │                  │
│  │  └────────────────┘  │   │                      │                  │
│  └──────────────────────┘   └──────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Design Philosophy

### Core Principles

1. **Ambient Operation**
   - General participants use Slack normally
   - No mandatory forms, slash commands, or bot conversations
   - Background processing operates transparently

2. **Human Accountability**
   - All AI outputs labeled as suggestions/drafts
   - Humans make all verification and publishing decisions
   - Full audit trail of human actions

3. **Provenance-First**
   - Every published claim links to source evidence
   - Slack permalinks preserved for full traceability
   - Verification actions logged with identities

4. **Explicit Uncertainty**
   - Clear separation of verified vs in-review content
   - Hedged wording for unconfirmed information
   - Conflicts surfaced before publication

5. **Fail-Safe Gates**
   - High-stakes information requires verification
   - Conflicts block publishing until resolved
   - Override justifications logged

### Technology Choices

| Component | Technology | Rationale |
|-----------|-----------|-----------|
| **API Framework** | FastAPI | Async support, automatic OpenAPI docs, type safety with Pydantic |
| **Database** | MongoDB | Flexible schema for rapid iteration, document model matches Slack data, rich querying |
| **Vector Store** | ChromaDB | Semantic search for duplicate detection, lightweight, Python-native |
| **LLM Provider** | Anthropic Claude | Strong reasoning, structured outputs, cost-effective tiers (Haiku/Sonnet) |
| **Message Queue** | N/A (direct processing) | Real-time requirements, small scale doesn't justify queue complexity (MVP) |
| **Auth** | Slack OAuth | Native Slack integration, leverages existing workspace identity |

---

## Architecture Layers

### 1. External Integration Layer

Handles communication with external systems:

- **Slack Integration**: Events API listener, message posting, App Home UI
- **LLM Integration**: OpenAI API client with model routing and prompt management
- **Web Search**: External source verification (future)

### 2. API Layer (FastAPI)

RESTful API for facilitator tooling:

- **Routes**: Backlog, candidates, COP publishing, search, metrics, audit, user management
- **Middleware**: RBAC enforcement, request validation, error handling
- **WebSocket** (future): Real-time updates for facilitator UI

### 3. Service Layer

Business logic orchestration:

- **Signal Ingestor**: Ingests Slack messages, triggers clustering
- **Cluster Manager**: Maintains clusters, detects conflicts
- **Candidate Manager**: Promotes clusters, tracks readiness state
- **Publishing Service**: Assembles COP drafts, enforces publish gates
- **Search Service**: Full-text and semantic search across signals/clusters

### 4. LLM Service Layer

AI operations with model routing:

- **Clustering Service**: Assigns signals to clusters (Haiku)
- **Conflict Detection**: Flags contradictions (Haiku, escalates to Sonnet)
- **Readiness Evaluation**: Checks completeness (Haiku)
- **COP Drafting**: Generates publication text (Sonnet)
- **Next Action Recommendation**: Suggests facilitator actions (Haiku)

### 5. Persistence Layer

Data storage and retrieval:

- **MongoDB**: Primary data store (signals, clusters, candidates, COP updates, audit log, users)
- **ChromaDB**: Vector embeddings for semantic search and duplicate detection

---

## Core Components

### Signal Pipeline

**Purpose**: Continuous ingestion and structuring of Slack messages.

**Flow**:
```
Slack Message → Validate → Store MongoDB → Embed Text → Index ChromaDB → Assign Cluster
```

**Key Classes**:
- `SlackEventListener`: Receives Slack events via Socket Mode
- `SignalRepository`: MongoDB CRUD operations for signals
- `EmbeddingService`: Generates text embeddings via OpenAI
- `ClusteringService`: LLM-based cluster assignment

**Sequence Diagram**:
```
┌────────┐   ┌───────────┐   ┌─────────────┐   ┌──────────┐   ┌───────────┐
│ Slack  │   │  Listener │   │  Repository │   │Embedding │   │Clustering │
└───┬────┘   └─────┬─────┘   └──────┬──────┘   └────┬─────┘   └─────┬─────┘
    │              │                │               │               │
    │─message──────▶                │               │               │
    │              │─validate────────│               │               │
    │              │                │               │               │
    │              │──save_signal───▶               │               │
    │              │                │◀──signal_id───│               │
    │              │                │               │               │
    │              │───get_embedding────────────────▶               │
    │              │                │               │◀─embedding────│
    │              │                │               │               │
    │              │────assign_to_cluster──────────────────────────▶
    │              │                │               │               │◀─LLM
    │              │                │               │               │  call
    │              │◀────cluster_assignment────────────────────────│
    │              │                │               │               │
    │              │─update_cluster_membership──▶   │               │
    │              │                │               │               │
```

**Configuration**:
- Monitored channels configured via environment variables
- Embedding model: `text-embedding-3-small` (OpenAI)
- Clustering model: `claude-haiku-3-5` (Anthropic)

### Readiness Engine

**Purpose**: Evaluate COP candidate completeness and compute readiness state.

**Readiness States**:
- **Ready — Verified**: Complete fields + verification + no conflicts → Publishable in Verified section
- **Ready — In Review**: Complete fields + labeled uncertainty → Publishable in In-Review section
- **Blocked**: Missing critical fields OR unresolved conflicts → Not publishable

**Decision Logic**:
```python
def compute_readiness(candidate):
    # Check minimum fields
    required_fields = ["what", "where", "when", "so_what"]
    missing = [f for f in required_fields if not candidate.fields.get(f)]

    if missing:
        return "blocked", f"Missing: {', '.join(missing)}"

    # Check evidence pack
    if not candidate.evidence.slack_permalinks:
        return "blocked", "No evidence links"

    # Check conflicts
    if candidate.has_unresolved_conflicts and candidate.conflict_severity == "high":
        return "blocked", "Unresolved high-severity conflict"

    # Check verification for high-stakes
    if candidate.risk_tier == "high_stakes":
        if candidate.verifications:
            return "ready_verified", "Verified and complete"
        else:
            return "blocked", "High-stakes item requires verification"

    # Standard readiness
    if candidate.verifications:
        return "ready_verified", "Verified and complete"
    else:
        return "ready_in_review", "Complete but unverified"
```

**Integration**:
- Called on candidate creation, field updates, and verification actions
- Updates `readiness_state` field in MongoDB
- Triggers UI badge update for facilitators

### COP Drafting Engine

**Purpose**: Generate publication-ready COP line items with verification-aware wording.

**Wording Patterns**:

| Status | Wording Style | Example |
|--------|---------------|---------|
| **Verified** | Direct, factual | "Shelter Alpha (123 Main St) is closed as of 18:00 PST due to power outage." |
| **In-Review** | Hedged, uncertain | "Reports indicate Shelter Alpha may be closing due to power issues. Seeking confirmation from shelter director." |
| **Disproven** | Correction-leading | "CORRECTION: Earlier reports of Shelter Alpha closure are incorrect. Shelter remains open per director as of 18:30 PST." |

**LLM Prompt Structure**:
```
SYSTEM PROMPT:
You are drafting a Common Operating Picture (COP) line item for crisis coordinators.

VERIFICATION-AWARE WORDING:
- If verification_status is "verified": Use direct, factual phrasing
- If verification_status is "in_review": Use hedged phrasing (e.g., "Reports indicate...", "Unconfirmed:")
- If verification_status is "disproven": Lead with "CORRECTION:" or "DISPROVEN:"

USER PROMPT:
COP CANDIDATE:
  what: "Shelter Alpha closure"
  where: "123 Main St, Springfield"
  when: "18:00 PST, Feb 15, 2026"
  who: "Approximately 45 residents"
  so_what: "Residents relocating to Shelter Beta; no capacity lost"
  verification_status: "verified"
  evidence:
    - Slack: https://workspace.slack.com/archives/.../p123456
    - Official: https://county.gov/emergency-notices/shelter-alpha

OUTPUT (JSON):
{
  "line_item_text": "[VERIFIED] Shelter Alpha (123 Main St) is closed as of 18:00 PST today due to a power outage. Approximately 45 residents have been relocated to Shelter Beta (456 Oak Ave). No reduction in overall shelter capacity; this is a temporary operational change only. (Sources: [Slack](https://...), [County DOT](https://))",
  "status_label": "VERIFIED",
  "citations": ["https://...", "https://..."],
  "wording_style": "direct_factual"
}
```

**Model Selection**: Claude Sonnet 4 (higher quality writing, nuanced hedging)

### Publish Workflow

**Purpose**: Enforce publish gates and assemble final COP update.

**Publish Gates**:

```python
def validate_publish_gates(candidates):
    blocking_issues = []

    for candidate in candidates:
        # Gate 1: High-stakes must be verified
        if candidate.risk_tier == "high_stakes" and candidate.readiness_state != "verified":
            if not has_override_justification(candidate):
                blocking_issues.append({
                    "candidate_id": candidate.id,
                    "issue": "high_stakes_unverified",
                    "message": "High-stakes item requires verification or override justification"
                })

        # Gate 2: Conflicts must be resolved
        if candidate.has_unresolved_conflicts and candidate.conflict_severity in ["high", "medium"]:
            blocking_issues.append({
                "candidate_id": candidate.id,
                "issue": "unresolved_conflict",
                "message": "Conflict must be resolved before publishing"
            })

        # Gate 3: Evidence pack must exist
        if not candidate.evidence.slack_permalinks and not candidate.evidence.external_sources:
            blocking_issues.append({
                "candidate_id": candidate.id,
                "issue": "missing_evidence",
                "message": "No citations available for this claim"
            })

    return blocking_issues
```

**COP Assembly**:
```
1. Fetch all Ready-Verified and Ready-In-Review candidates
2. Validate publish gates → return errors if blocked
3. Group candidates by section:
   - verified_updates
   - in_review_updates
   - disproven_rumor_control
   - open_questions_gaps
4. Generate line items via COP Drafting Engine (Sonnet)
5. Assemble final structure:
   - Header (timestamp, disclaimer)
   - Sections (verified, in-review, disproven, gaps)
   - Footer (change summary, next update time, contact)
6. Create immutable snapshot:
   - Candidates at publish time
   - Evidence packs
   - Verification records
7. Store as versioned cop_update document
8. Post to Slack channel
9. Log publish action to audit trail
```

**Two-Person Rule** (v1.0 feature):
- High-stakes overrides require second approver
- First facilitator drafts and justifies override
- Second facilitator reviews and approves
- Both identities logged in audit trail

---

## Data Flow

### End-to-End Flow: Slack Message → Published COP

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. SIGNAL INGESTION                                                     │
│                                                                         │
│ Slack Message                                                           │
│   └─▶ Validate & Store (MongoDB: signals collection)                   │
│        └─▶ Generate Embedding (OpenAI: text-embedding-3-small)         │
│             └─▶ Index in ChromaDB                                      │
│                  └─▶ Cluster Assignment (LLM: Claude Haiku)            │
│                       └─▶ Update Cluster (MongoDB: clusters collection)│
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 2. CONFLICT DETECTION (Triggered on cluster update)                    │
│                                                                         │
│ Fetch cluster signals → LLM Conflict Detection (Haiku)                 │
│   └─▶ If conflict: Flag cluster, update conflict_details               │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 3. BACKLOG PRIORITIZATION (Facilitator view)                           │
│                                                                         │
│ Fetch unpromoted clusters, sort by priority_score                      │
│   └─▶ Display in facilitator UI with conflict badges                   │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 4. PROMOTION TO CANDIDATE (Facilitator action)                         │
│                                                                         │
│ Facilitator selects cluster → Promote to COP Candidate                 │
│   └─▶ Create cop_candidate document                                    │
│        └─▶ Extract key signals as primary_signal_ids                   │
│             └─▶ Compute initial readiness (Haiku: Readiness Eval)      │
│                  └─▶ Log promotion action (audit_log)                  │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 5. VERIFICATION WORKFLOW (Facilitator/Verifier action)                 │
│                                                                         │
│ IF readiness = "blocked" due to missing fields:                        │
│   └─▶ Facilitator requests clarification (Slack thread reply)          │
│        └─▶ New signal ingested → Updates cluster → Re-evaluate ready   │
│                                                                         │
│ IF readiness = "ready_in_review" AND risk = "high_stakes":             │
│   └─▶ Verifier performs verification (contacts authoritative source)   │
│        └─▶ Records verification action (cop_candidates.verifications)  │
│             └─▶ Adds external source to evidence pack                  │
│                  └─▶ Readiness re-computed → "ready_verified"          │
│                       └─▶ Log verification action (audit_log)          │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 6. COP DRAFT GENERATION (Facilitator action)                           │
│                                                                         │
│ Facilitator triggers "Draft COP Update"                                │
│   └─▶ Fetch all ready_verified + ready_in_review candidates            │
│        └─▶ Validate publish gates                                      │
│             └─▶ For each candidate: Generate line item (Sonnet)        │
│                  └─▶ Group by section (verified, in_review, etc.)      │
│                       └─▶ Assemble draft with header/footer            │
│                            └─▶ Present for facilitator review          │
└─────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 7. HUMAN APPROVAL & PUBLICATION (Facilitator action)                   │
│                                                                         │
│ Facilitator reviews draft                                              │
│   └─▶ Edits wording for clarity (optional)                             │
│        └─▶ Approves publication                                        │
│             └─▶ Create versioned cop_update document                   │
│                  └─▶ Snapshot candidates + evidence packs              │
│                       └─▶ Post to Slack #cop-updates channel           │
│                            └─▶ Log publish action (audit_log)          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Database Design

See [mongodb_schema.md](mongodb_schema.md) for complete schema documentation.

### Key Collections

#### 1. `signals`
- Stores all ingested Slack messages
- Indexed by channel, timestamp, cluster membership
- TTL expiration per retention policy
- Links to ChromaDB embedding via `embedding_id`

#### 2. `clusters`
- Groups related signals by topic/incident
- Maintains priority scores for backlog sorting
- Tracks conflicts and duplicates
- Links to promoted COP candidate via `promoted_to_candidate_id`

#### 3. `cop_candidates`
- Tracks facilitator-managed items through workflow
- Stores structured COP fields (what/where/when/who/so-what)
- Maintains evidence pack (Slack permalinks + external sources)
- Records verification history
- Computes readiness state

#### 4. `cop_updates`
- Immutable versioned COP publications
- Embeds full candidate snapshots (point-in-time provenance)
- Stores publish gate overrides with justifications
- Tracks metrics (provenance coverage, time-to-publish)

#### 5. `audit_log`
- Append-only log of all system actions
- Records actor, timestamp, entity, before/after state
- Supports abuse detection and compliance review

#### 6. `users`
- User records with role assignments
- Role history for accountability
- Suspension status tracking
- Activity stats for abuse detection

### Relationship Diagram

```
┌──────────┐       ┌──────────┐       ┌──────────────┐       ┌─────────────┐
│ signals  │──────▶│ clusters │──────▶│cop_candidates│──────▶│ cop_updates │
│          │  n:1  │          │  1:1  │              │  n:m  │             │
│          │       │          │       │              │       │             │
│ cluster_ │       │ promoted_│       │ published_in_│       │ candidates_ │
│ ids[]    │       │ to_      │       │ cop_update_  │       │ snapshot[]  │
│          │       │ candidate│       │ ids[]        │       │             │
└──────────┘       └──────────┘       └──────────────┘       └─────────────┘
      │                                       │                      │
      │                                       │                      │
      └───────────────────────────────────────┴──────────────────────┘
                                              │
                                              ▼
                                       ┌─────────────┐
                                       │  audit_log  │
                                       │             │
                                       │ Records all │
                                       │ actions on  │
                                       │ entities    │
                                       └─────────────┘

┌──────────┐
│  users   │
│          │───────────────────────────────────────────────────────────┐
│ roles[]  │                                                           │
│          │                                                           │
└──────────┘                                                           │
      │                                                                │
      └──────▶ Linked via actor_id in audit_log, created_by, etc.     │
                                                                       ▼
                                                              (All user actions)
```

---

## LLM Integration Architecture

### Model Selection Strategy

| Task | Model | Rationale | Cost per Call |
|------|-------|-----------|---------------|
| **Clustering** | Claude Haiku 3.5 | Simple classification, high volume | $0.0008 |
| **Conflict Detection** | Claude Haiku 3.5 (default) | Structured comparison | $0.0015 |
| **Conflict Detection (escalated)** | Claude Sonnet 4 | Nuanced conflicts | $0.008 |
| **Readiness Evaluation** | Claude Haiku 3.5 | Checklist evaluation | $0.0012 |
| **Next Action Recommendation** | Claude Haiku 3.5 | Decision tree logic | $0.0008 |
| **COP Draft Generation** | Claude Sonnet 4 | Publication-quality writing | $0.009 |

**Estimated cost per incident** (500 messages, 20 candidates, 3 COP updates): **~$1.00**

### Prompt Architecture

All prompts follow a consistent structure:

1. **System Prompt** (static, cacheable):
   - Role definition
   - Task instructions
   - Constraints and guardrails
   - Output format specification

2. **User Prompt** (dynamic):
   - Input data (candidate, signals, cluster)
   - Specific task parameters
   - Output schema reminder

3. **Output Schema** (JSON):
   - Pydantic models for validation
   - Required fields enforce completeness
   - Reasoning/explanation fields for audit trail

See [docs/prompts.md](docs/prompts.md) for detailed prompt templates.

### Prompt Caching

System prompts are marked with cache control to reduce costs:

```python
response = client.messages.create(
    model="claude-haiku-3-5-20241022",
    max_tokens=150,
    system=[{
        "type": "text",
        "text": CLUSTERING_SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"}  # Cache for 5 minutes
    }],
    messages=[{"role": "user", "content": user_prompt}]
)
```

**Cost reduction**: ~50% on repeated calls (system prompt tokens free after cache hit)

### Error Handling

LLM calls include retry logic and fallback strategies:

```python
@retry(max_attempts=3, backoff_factor=2, exceptions=[APIError, RateLimitError])
async def call_llm(prompt, model="claude-haiku-3-5"):
    try:
        response = await anthropic_client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        return parse_json_response(response.content[0].text)
    except JSONDecodeError:
        logger.error("LLM returned invalid JSON", extra={"response": response})
        raise ValidationError("Invalid LLM response")
    except RateLimitError:
        logger.warning("Rate limit hit, retrying with backoff")
        raise  # Retry decorator handles this
```

---

## Security Model

### Authentication

**Slack OAuth 2.0** used for all authentication:
- Users authenticate via Slack workspace SSO
- App receives user token and workspace context
- Session stored in secure HTTP-only cookies
- Token refresh handled automatically

### Authorization (RBAC)

Four role levels:

| Role | Permissions |
|------|-------------|
| **general_participant** | Read published COPs only |
| **facilitator** | Backlog access, promote candidates, edit/publish COPs, search |
| **verifier** | Record verification actions, add evidence to candidates |
| **workspace_admin** | User/role management, system configuration, suspend users |

**Enforcement**:
```python
@require_roles(["facilitator", "workspace_admin"])
async def promote_cluster_to_candidate(cluster_id: str, current_user: User):
    # Only facilitators and admins can promote
    ...
```

**Role assignment audit**:
- All role changes logged to `audit_log`
- Includes old roles, new roles, actor, justification
- Workspace admins can view full role history

### Audit Logging

**All sensitive actions logged**:
- Cluster promotion
- Candidate state changes
- Risk tier overrides
- Verification actions
- COP publishing
- Role assignments
- User suspensions
- Access denials

**Audit log fields**:
- `timestamp`, `actor_id`, `actor_role`
- `action_type`, `target_entity_type`, `target_entity_id`
- `changes` (before/after state)
- `justification` (for overrides)
- `is_flagged` (abuse detection)

**Immutability**:
- Audit log documents cannot be edited after creation
- MongoDB collection-level write-once enforcement
- Backup retention separate from signal retention

### Abuse Detection

System flags suspicious patterns:

1. **Bulk high-stakes overrides**: Facilitator publishes >5 high-stakes unverified items in <1 hour
2. **Rapid role escalation**: User granted facilitator/admin role and immediately performs sensitive actions
3. **Verification bypass**: Verifier marks item verified without adding external source
4. **Publish rate abuse**: Facilitator publishes >10 COP updates in <1 hour

**Response**:
- Alert sent to workspace admin
- Flagged actions visible in audit log UI
- Admin can suspend user's publish permissions

### Data Privacy

**Sensitive Information Redaction** (NFR-PRIVACY-002):
- Configurable redaction rules (PII, exact addresses, phone numbers)
- LLM-assisted detection of sensitive content
- Facilitator override with justification
- Redacted fields logged in `signals.redaction`

**Data Retention** (NFR-PRIVACY-003):
- Configurable TTL per workspace (default 90 days)
- Signals marked `is_archived: true` exempt from deletion
- Archived signals: referenced in published COPs, high-stakes verified
- Purge events logged to audit trail

---

## Deployment Architecture

### Container Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       Docker Compose Stack                      │
│                                                                 │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────┐ │
│  │   integritykit   │  │    MongoDB       │  │   ChromaDB   │ │
│  │   (FastAPI app)  │  │    (7.0)         │  │              │ │
│  │                  │  │                  │  │              │ │
│  │  Port: 8080      │  │  Port: 27017     │  │  Port: 8000  │ │
│  │  Env: .env       │  │  Volume: mongo_  │  │  Volume:     │ │
│  │                  │  │         data     │  │  chroma_data │ │
│  └──────────────────┘  └──────────────────┘  └──────────────┘ │
│           │                     │                    │         │
│           └─────────────────────┴────────────────────┘         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ External connections
                              ▼
                    ┌─────────────────────┐
                    │  Slack Workspace    │
                    │  OpenAI API         │
                    └─────────────────────┘
```

### Production Deployment (AWS Example)

```
┌─────────────────────────────────────────────────────────────────────┐
│                           AWS VPC                                   │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Application Load Balancer (ALB)                              │ │
│  │  HTTPS (ACM Certificate)                                      │ │
│  └─────────────────────────────┬─────────────────────────────────┘ │
│                                │                                   │
│  ┌─────────────────────────────┴─────────────────────────────────┐ │
│  │  ECS Fargate Service (integritykit)                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │ │
│  │  │   Task 1     │  │   Task 2     │  │   Task 3     │        │ │
│  │  │  (FastAPI)   │  │  (FastAPI)   │  │  (FastAPI)   │        │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │ │
│  │         │                 │                 │                 │ │
│  │         └─────────────────┴─────────────────┘                 │ │
│  └─────────────────────────────┬─────────────────────────────────┘ │
│                                │                                   │
│  ┌─────────────────────────────┴─────────────────────────────────┐ │
│  │  DocumentDB (MongoDB-compatible)                              │ │
│  │  Multi-AZ, Encrypted at Rest                                  │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  EC2 Instance (ChromaDB Server)                               │ │
│  │  EBS Volume, Auto Scaling Group                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  Secrets Manager                                              │ │
│  │  (SLACK_BOT_TOKEN, OPENAI_API_KEY, DB credentials)           │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  CloudWatch Logs & Metrics                                    │ │
│  │  (Application logs, performance metrics, alarms)              │ │
│  └───────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Environment-Specific Configuration

| Environment | Instance Type | DB | Scaling | Monitoring |
|-------------|---------------|-----|---------|------------|
| **Development** | Local Docker | Local MongoDB | Single instance | Logs only |
| **Staging** | Fargate 2 vCPU | DocumentDB (t3.medium) | 2 tasks | CloudWatch |
| **Production** | Fargate 4 vCPU | DocumentDB (r5.large, Multi-AZ) | 3-10 tasks (auto-scale) | CloudWatch + Datadog |

---

## Performance and Scalability

### Performance Targets

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Signal ingestion latency** | <100ms p95 | Real-time clustering needed |
| **Facilitator search response** | <500ms p95 | Interactive UI requirement |
| **Backlog load time** | <200ms p95 | Frequent facilitator access |
| **COP draft generation** | <5s p95 | User tolerance for AI operations |

### Scalability Bottlenecks & Mitigation

#### 1. LLM API Rate Limits

**Issue**: OpenAI/Anthropic have rate limits (requests per minute, tokens per minute)

**Mitigation**:
- Use Message Batches API for clustering (50% cost reduction, higher throughput)
- Queue non-urgent LLM calls (conflict detection, next action recommendations)
- Implement exponential backoff retry logic
- Cache cluster summaries to reduce repeat clustering calls

#### 2. MongoDB Write Load (Signal Ingestion)

**Issue**: High-volume incident (1000+ messages/hour) may overwhelm single MongoDB instance

**Mitigation**:
- Use MongoDB replica set for read scaling
- Index optimization (compound indexes for common queries)
- Write batching for non-critical updates (cluster membership)
- Consider sharding by workspace_id if multi-tenant

#### 3. ChromaDB Query Latency

**Issue**: Vector similarity search slows down with large corpus (>100K signals)

**Mitigation**:
- Partition embeddings by time window (rolling 30-day index)
- Use ChromaDB server mode with persistent storage (vs in-memory)
- Limit search scope to recent clusters first, expand if no match
- Future: Consider Pinecone or Weaviate for managed vector DB

### Horizontal Scaling

**Application Tier**:
- Stateless FastAPI instances (scale via ECS task count)
- Load balancer distributes traffic
- No shared in-memory state (session in cookies, data in DB)

**Database Tier**:
- MongoDB replica set (read replicas for query scaling)
- ChromaDB can be replicated (future work)

**Concurrency Model**:
- FastAPI async/await for I/O-bound operations
- Database connections pooled (Motor async driver)
- LLM calls async with `asyncio.gather` for parallel processing

---

## Monitoring and Observability

### Logging

**Structured logging** via `structlog`:

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "cluster_promoted",
    cluster_id=cluster.id,
    candidate_id=candidate.id,
    promoted_by=current_user.id,
    signal_count=cluster.signal_count,
    priority_score=cluster.priority_score
)
```

**Log levels**:
- `DEBUG`: Detailed LLM prompts/responses, internal state
- `INFO`: Business events (promotion, verification, publish)
- `WARNING`: Recoverable errors (rate limits, transient failures)
- `ERROR`: System errors requiring attention

**Log aggregation** (production):
- CloudWatch Logs (AWS)
- Datadog or Splunk for search/alerts
- Retention: 30 days (debug), 90 days (info/warning), 1 year (error/audit)

### Metrics

**Application Metrics**:
- Request latency (p50, p95, p99)
- Error rate (5xx responses)
- LLM call latency and cost
- Signal ingestion rate (messages/minute)
- Facilitator action rate (promotions/verifications/publishes per hour)

**System Metrics**:
- CPU/memory utilization
- Database connection pool usage
- MongoDB query latency
- ChromaDB query latency

**Business Metrics** (FR-METRICS-001):
- Time-to-validated-update (first signal → verified COP line item)
- Conflicting-report rate (% of candidates with conflicts)
- Moderator burden (facilitator actions per COP update)
- Provenance coverage (% of line items with complete evidence)
- Readiness distribution (verified/in-review/blocked counts)

### Alerting

**Critical Alerts** (PagerDuty):
- API error rate >5% for 5 minutes
- Database connection failures
- LLM API failures (all models down)
- COP publish failures

**Warning Alerts** (Slack notification):
- High LLM latency (>10s p95)
- MongoDB slow queries (>1s)
- Abuse detection triggers
- Data retention purge failures

### Tracing

**Distributed tracing** (future, OpenTelemetry):
- Trace signal ingestion through clustering and backlog
- Trace facilitator actions through publish workflow
- Identify bottlenecks in multi-step LLM pipelines

---

## Appendix: Technology Alternatives Considered

| Component | Selected | Alternatives Considered | Rationale for Selection |
|-----------|----------|-------------------------|-------------------------|
| **Database** | MongoDB | PostgreSQL (relational), DynamoDB (NoSQL) | Flexible schema for iteration; document model matches Slack JSON; strong querying |
| **Vector Store** | ChromaDB | Pinecone, Weaviate, Postgres pgvector | Python-native, lightweight, no managed service needed for MVP |
| **LLM Provider** | Anthropic Claude | OpenAI GPT-4, Google Gemini | Structured outputs, cost tiers (Haiku/Sonnet), strong reasoning |
| **API Framework** | FastAPI | Flask, Django REST | Async support, automatic OpenAPI docs, type safety with Pydantic |
| **Message Queue** | N/A (direct) | RabbitMQ, Redis, AWS SQS | Real-time requirements, small scale doesn't justify queue complexity yet |
| **Task Queue** | N/A (direct) | Celery, Dramatiq | Background tasks deferred to v1.0 (metrics export, bulk operations) |
| **Search Engine** | MongoDB text index + ChromaDB | Elasticsearch, Typesense | Avoid operational complexity; MongoDB + ChromaDB sufficient for MVP search |

---

**Document Status**: Draft v1.0
**Last Updated**: 2026-02-15
**Authors**: Aid Arena team with Claude Code assistance
