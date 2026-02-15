# Aid Arena Integrity Kit — MongoDB Schema Design

| Field | Value |
|---|---|
| **Version** | 1.0 |
| **Date** | 2026-02-15 |
| **Database** | MongoDB 7.0+ |
| **Design Philosophy** | Document-oriented with embedded evidence packs, indexed for search and temporal queries, optimized for write-heavy ingestion and read-heavy facilitator workflows |

---

## Table of Contents

1. [Schema Overview](#schema-overview)
2. [Collection Definitions](#collection-definitions)
3. [Index Strategy](#index-strategy)
4. [Relationships and References](#relationships-and-references)
5. [Example Documents](#example-documents)
6. [Data Retention and Archival](#data-retention-and-archival)
7. [Migration Considerations](#migration-considerations)

---

## Schema Overview

### Database Selection Rationale

**MongoDB is chosen for:**
- Flexible schema evolution during rapid iteration (SRS v0.4 indicates active development)
- Document-oriented model aligns naturally with Slack message structure and embedded evidence packs
- Efficient handling of write-heavy ingestion (continuous Slack message streaming)
- Rich querying for facilitator search and backlog prioritization
- Support for text indexes and array queries for cluster membership and conflict detection
- Horizontal scaling path if deployed across multiple aid organizations

### Collections

| Collection | Purpose | Estimated Volume | Write Pattern | Read Pattern |
|---|---|---|---|---|
| `signals` | Ingested Slack messages | High (10K-1M+ messages per crisis event) | Continuous append | Search, cluster lookup, COP candidate creation |
| `clusters` | Topic/incident groupings | Medium (100-10K clusters per event) | Frequent updates (membership changes) | Backlog prioritization, duplicate detection |
| `cop_candidates` | Facilitator-tracked items | Low (10-500 candidates per event) | Moderate updates (state transitions, verification) | Backlog review, COP drafting |
| `cop_updates` | Published COP artifacts | Low (5-100 versions per event) | Append-only (versioned) | Diff generation, audit trail |
| `audit_log` | Immutable action history | Medium (1K-100K actions per event) | Append-only | Compliance review, abuse detection |
| `users` | User records with roles | Low (10-1000 users per workspace) | Infrequent updates (role changes) | RBAC enforcement, suspension checks |

---

## Collection Definitions

### 1. `signals`

**Purpose:** Store all ingested Slack messages with metadata, embeddings reference, and cluster membership.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Slack message identity
  slack_channel_id: String,           // Required. Slack channel ID (e.g., "C01234ABCD")
  slack_thread_ts: String,            // Optional. Parent thread timestamp if reply
  slack_message_ts: String,           // Required. Unique message timestamp (Slack's primary key)
  slack_user_id: String,              // Required. Posting user's Slack ID
  slack_team_id: String,              // Required. Workspace/team ID

  // Message content
  text: String,                       // Required. Message text (may be empty for file-only posts)
  attachments: [Object],              // Optional. Slack attachments (links, files, etc.)
  reactions: [{                       // Optional. Reaction metadata
    name: String,                     // Emoji name (e.g., "heavy_check_mark")
    count: Number,
    users: [String]                   // User IDs who reacted
  }],

  // Temporal metadata
  posted_at: Date,                    // Required. Message timestamp as Date object
  ingested_at: Date,                  // Required. System ingestion timestamp

  // Permalinks for citation
  permalink: String,                  // Required. Slack permalink (e.g., "https://workspace.slack.com/archives/C.../p...")

  // Embedding and vector search
  embedding_id: String,               // Optional. Reference to ChromaDB embedding (external vector store)

  // Cluster membership
  cluster_ids: [ObjectId],            // Array of cluster document IDs this signal belongs to

  // AI-generated flags
  ai_flags: {
    is_duplicate: Boolean,            // AI-detected duplicate of another signal
    duplicate_of_signal_id: ObjectId, // Reference to canonical signal if duplicate
    has_conflict: Boolean,            // AI-detected conflict with other signals
    conflict_signal_ids: [ObjectId],  // References to conflicting signals
    quality_score: Number             // 0.0-1.0 source quality estimate
  },

  // Source quality indicators
  source_quality: {
    is_firsthand: Boolean,            // First-hand observation vs hearsay
    has_external_link: Boolean,       // Contains link to external authoritative source
    external_links: [String],         // URLs extracted from message
    author_credibility_score: Number  // 0.0-1.0 based on historical accuracy (future)
  },

  // Redaction tracking (NFR-PRIVACY-002)
  redaction: {
    is_redacted: Boolean,
    redacted_fields: [String],        // Field paths redacted (e.g., ["text", "attachments.0.title"])
    redaction_reason: String,
    redacted_by: ObjectId,            // User ID who applied redaction
    redacted_at: Date
  },

  // Retention policy (NFR-PRIVACY-003)
  retention: {
    expires_at: Date,                 // TTL expiration date per workspace policy
    is_archived: Boolean              // Marked for long-term archival (exempts from TTL)
  },

  // Audit metadata
  created_at: Date,                   // System creation timestamp
  updated_at: Date                    // Last modification timestamp
}
```

**Validation Rules:**

- `slack_message_ts` + `slack_channel_id` must be unique (composite index)
- `posted_at` must be <= `ingested_at`
- `ai_flags.quality_score` must be in range [0.0, 1.0]
- `cluster_ids` must reference valid cluster documents

---

### 2. `clusters`

**Purpose:** Group related signals by topic/incident for backlog prioritization.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Cluster identity
  name: String,                       // Optional. Human-readable name (e.g., "Shelter Alpha Closure - Feb 15")

  // Topic classification
  topic_type: String,                 // Enum: "incident", "need", "resource_offer", "infrastructure", "rumor", "general"
  keywords: [String],                 // Extracted keywords for search

  // Signal membership
  signal_ids: [ObjectId],             // Array of signal document IDs in this cluster
  signal_count: Number,               // Denormalized count for performance

  // Temporal extent
  first_signal_at: Date,              // Timestamp of earliest signal in cluster
  last_signal_at: Date,               // Timestamp of most recent signal in cluster

  // Conflict detection
  has_conflicts: Boolean,             // True if any signals contradict each other
  conflict_details: [{
    field: String,                    // Conflicting dimension (e.g., "location", "time", "count")
    values: [String],                 // Conflicting values reported
    signal_ids: [ObjectId],           // Signals reporting each value
    severity: String                  // Enum: "minor", "moderate", "critical"
  }],

  // Prioritization scores (for backlog sorting)
  urgency_score: Number,              // 0.0-1.0 time-sensitive urgency
  impact_score: Number,               // 0.0-1.0 estimated impact (people affected, severity)
  risk_score: Number,                 // 0.0-1.0 safety/harm risk
  priority_score: Number,             // Computed composite score for sorting

  // COP candidate linkage
  promoted_to_candidate_id: ObjectId, // Optional. Reference to cop_candidate if promoted
  promoted_at: Date,                  // Optional. Promotion timestamp
  promoted_by: ObjectId,              // Optional. User ID who promoted

  // AI-generated summary
  ai_summary: String,                 // Draft summary of cluster topic/content

  // Audit metadata
  created_at: Date,
  updated_at: Date
}
```

**Validation Rules:**

- `signal_count` must equal `signal_ids.length`
- `urgency_score`, `impact_score`, `risk_score`, `priority_score` must be in range [0.0, 1.0]
- `first_signal_at` must be <= `last_signal_at`
- If `promoted_to_candidate_id` is set, `promoted_at` and `promoted_by` must also be set

---

### 3. `cop_candidates`

**Purpose:** Track facilitator-managed items through readiness workflow to publication.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Linkage to source
  cluster_id: ObjectId,               // Required. Source cluster
  primary_signal_ids: [ObjectId],     // Required. Key signals supporting this candidate

  // Readiness workflow state
  readiness_state: String,            // Required. Enum: "verified", "in_review", "blocked"
  readiness_updated_at: Date,         // Timestamp of last state change
  readiness_updated_by: ObjectId,     // User ID who changed state

  // Risk classification (FR-COP-RISK-001)
  risk_tier: String,                  // Required. Enum: "routine", "elevated", "high_stakes"
  risk_tier_override: {
    original_tier: String,
    overridden_by: ObjectId,          // User ID who overrode
    overridden_at: Date,
    justification: String             // Required for override
  },

  // Structured COP fields (minimum publishability checklist)
  fields: {
    what: String,                     // Required. Scoped claim/situation statement
    where: String,                    // Required. Explicit location (may be approximate)
    when: {
      timestamp: Date,                // Required. Event timestamp or window start
      timezone: String,               // Required. IANA timezone (e.g., "America/New_York")
      is_approximate: Boolean,        // True if time is estimated
      description: String             // Human-readable time description
    },
    who: String,                      // Optional but recommended. Source/actor/affected population
    so_what: String                   // Required. Operational relevance/impact
  },

  // Evidence pack (FR-AUD-002, QT-2)
  evidence: {
    slack_permalinks: [{
      url: String,                    // Slack permalink
      signal_id: ObjectId,            // Reference to signal document
      description: String             // Optional context note
    }],
    external_sources: [{
      url: String,                    // External URL
      title: String,                  // Page title or description
      source_type: String,            // Enum: "official_source", "news", "social_media", "other"
      accessed_at: Date,              // When link was verified accessible
      credibility_score: Number       // 0.0-1.0 source credibility
    }]
  },

  // Verification records
  verifications: [{
    verified_by: ObjectId,            // User ID who verified
    verified_at: Date,
    verification_method: String,      // Enum: "firsthand", "authoritative_source", "cross_reference", "other"
    verification_notes: String,       // Free text explanation
    confidence_level: String          // Enum: "high", "medium", "low"
  }],

  // Missing/weak fields checklist (FR-COP-READ-002)
  missing_fields: [String],           // Array of field names that are missing or weak
  blocking_issues: [{
    issue_type: String,               // Enum: "missing_field", "conflict", "verification_required"
    description: String,
    severity: String                  // Enum: "blocks_publishing", "requires_caveat", "advisory"
  }],

  // Recommended next action (FR-COP-READ-003)
  recommended_action: {
    action_type: String,              // Enum: "request_clarification", "assign_verification", "merge_duplicate", "resolve_conflict", "publish_in_review"
    reason: String,
    alternatives: [{
      action_type: String,
      reason: String
    }]
  },

  // Conflict tracking
  conflicts: [{
    conflict_with_candidate_id: ObjectId, // Conflicting candidate
    conflict_field: String,           // Field with conflict (e.g., "fields.where")
    description: String,
    resolved: Boolean,
    resolution_notes: String,
    resolved_by: ObjectId,
    resolved_at: Date
  }],

  // Draft COP wording (FR-COP-WORDING-001)
  draft_wording: {
    headline: String,                 // AI-suggested or facilitator-written headline
    body: String,                     // Full draft text with appropriate hedging
    hedging_applied: Boolean,         // True if in-review hedging language used
    recheck_time: Date,               // Optional. When to recheck if in-review
    next_verification_step: String    // Optional. Suggested next step for verification
  },

  // Facilitator notes
  facilitator_notes: [{
    author_id: ObjectId,
    created_at: Date,
    note: String
  }],

  // Publication tracking
  published_in_cop_update_ids: [ObjectId], // COP updates this candidate was published in

  // Duplicate/merge tracking
  merged_into_candidate_id: ObjectId, // If this candidate was merged into another
  merged_at: Date,
  merged_by: ObjectId,

  // Audit metadata
  created_at: Date,
  created_by: ObjectId,               // User who promoted to candidate
  updated_at: Date
}
```

**Validation Rules:**

- `readiness_state` must be one of: "verified", "in_review", "blocked"
- `risk_tier` must be one of: "routine", "elevated", "high_stakes"
- If `readiness_state` is "verified", must have at least one entry in `verifications`
- If `risk_tier` is "high_stakes" and `readiness_state` is "in_review", must have `draft_wording.recheck_time` and `draft_wording.next_verification_step`
- All ObjectId references must point to valid documents

---

### 4. `cop_updates`

**Purpose:** Versioned, immutable published COP artifacts with full provenance.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Version tracking
  version_number: Number,             // Required. Monotonically increasing version (1, 2, 3...)
  previous_version_id: ObjectId,      // Optional. Reference to prior COP update

  // Publication metadata
  published_at: Date,                 // Required. Publication timestamp
  published_by: ObjectId,             // Required. User ID who approved publication
  publisher_role: String,             // Role at time of publication (e.g., "facilitator")

  // Target Slack channel
  slack_channel_id: String,           // Required. Where COP was posted
  slack_message_ts: String,           // Optional. Timestamp of posted message (if posted to Slack)
  slack_permalink: String,            // Optional. Permalink to posted COP message

  // COP structure (FR-COPDRAFT-002)
  content: {
    header: {
      title: String,                  // E.g., "Common Operating Picture (COP) — Feb 15, 2026 14:30 EST"
      timestamp: Date,
      timezone: String,
      disclaimer: String              // Standard disclaimer text
    },

    sections: {
      verified: [{                    // Verified updates section
        candidate_id: ObjectId,       // Reference to cop_candidate
        headline: String,
        body: String,
        evidence_links: [String],     // Permalinks and external URLs
        verification_note: String     // Optional verification summary
      }],

      in_review: [{                   // In-review updates section
        candidate_id: ObjectId,
        headline: String,
        body: String,                 // Must include hedging language
        evidence_links: [String],
        uncertainty_note: String,     // Explicit uncertainty statement
        recheck_time: Date            // Optional
      }],

      disproven: [{                   // Rumor control / disproven claims
        candidate_id: ObjectId,
        claim: String,                // What was claimed
        correction: String,           // Why it's disproven
        evidence_links: [String]
      }],

      gaps: [{                        // Open questions / information gaps
        question: String,
        context: String,
        requested_info: String
      }]
    },

    footer: {
      change_summary: String,         // "What changed since last COP" (FR-COPDRAFT-003)
      next_update_time: Date,         // Optional. Expected next update
      contact_info: String            // How to reach facilitators
    }
  },

  // Supporting candidates snapshot (FR-AUD-002)
  candidates_snapshot: [{             // Immutable snapshot of candidates at publish time
    candidate_id: ObjectId,
    readiness_state: String,
    risk_tier: String,
    fields: Object,                   // Full fields object from candidate
    evidence: Object,                 // Full evidence pack
    verifications: [Object]           // Full verification records
  }],

  // Metrics for this update (FR-METRICS-001)
  metrics: {
    total_verified_items: Number,
    total_in_review_items: Number,
    total_disproven_items: Number,
    total_gaps: Number,
    provenance_coverage_pct: Number,  // % of items with complete evidence packs
    time_since_last_update_minutes: Number
  },

  // Override tracking (FR-COP-GATE-001)
  overrides: [{
    candidate_id: ObjectId,
    override_type: String,            // Enum: "high_stakes_unverified", "conflict_unresolved", "missing_evidence"
    justification: String,            // Required written rationale
    overridden_by: ObjectId,
    overridden_at: Date,
    second_approver_id: ObjectId,     // Optional. For two-person rule (FR-COP-GATE-002)
    second_approver_at: Date
  }],

  // Audit metadata
  created_at: Date
}
```

**Validation Rules:**

- `version_number` must be unique and monotonically increasing
- If `version_number` > 1, must have `previous_version_id`
- All `candidate_id` references in content sections must exist in `candidates_snapshot`
- `metrics.provenance_coverage_pct` must be in range [0.0, 100.0]
- For high-stakes overrides, must have `justification`

---

### 5. `audit_log`

**Purpose:** Immutable log of all system actions for compliance and abuse detection.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Action metadata
  timestamp: Date,                    // Required. When action occurred
  actor_id: ObjectId,                 // Required. User who performed action (or system if automated)
  actor_role: String,                 // Role at time of action
  actor_ip: String,                   // Optional. IP address for security audit

  // Action details
  action_type: String,                // Required. Enum: see Action Types below

  // Target entity
  target_entity_type: String,         // Required. Enum: "signal", "cluster", "cop_candidate", "cop_update", "user"
  target_entity_id: ObjectId,         // Required. ID of affected entity

  // Change tracking (before/after values)
  changes: {
    before: Object,                   // State before action (for updates)
    after: Object                     // State after action (for updates/creates)
  },

  // Context and justification
  justification: String,              // Optional. User-provided reason (required for overrides)
  system_context: Object,             // Optional. System state snapshot (e.g., readiness scores, conflicts)

  // Abuse detection signals
  is_flagged: Boolean,                // True if flagged by abuse detection (NFR-ABUSE-001)
  flag_reason: String,                // Reason for flagging

  // Audit metadata
  created_at: Date                    // Immutable creation timestamp
}
```

**Action Types:**

- `signal.ingest` - New signal ingested
- `cluster.create` - New cluster created
- `cluster.update` - Cluster membership or scores changed
- `cop_candidate.promote` - Cluster promoted to candidate
- `cop_candidate.update_state` - Readiness state changed
- `cop_candidate.update_risk_tier` - Risk tier changed (with override tracking)
- `cop_candidate.verify` - Verification action recorded
- `cop_candidate.merge` - Candidate merged into another
- `cop_update.publish` - COP update published
- `cop_update.override` - Publish gate overridden
- `user.role_change` - User role assigned/removed (FR-ROLE-003)
- `user.suspend` - User suspended (NFR-ABUSE-002)
- `user.reinstate` - User reinstated
- `access.denied` - Access denied event (FR-ROLE-002)

**Validation Rules:**

- `timestamp` must be <= current time
- `action_type` must be in allowed enum
- `target_entity_type` must be in allowed enum
- Documents are immutable after insertion (enforced at application level)

---

### 6. `users`

**Purpose:** User records with role-based access control and suspension status.

**Schema:**

```javascript
{
  _id: ObjectId,

  // Slack identity
  slack_user_id: String,              // Required. Unique Slack user ID
  slack_team_id: String,              // Required. Workspace/team ID
  slack_email: String,                // Optional. User email from Slack profile
  slack_display_name: String,         // Optional. Display name
  slack_real_name: String,            // Optional. Real name

  // Role assignment (FR-ROLE-001)
  roles: [String],                    // Array of assigned roles. Enum: "general_participant", "facilitator", "verifier", "workspace_admin"

  // Role history (FR-ROLE-003)
  role_history: [{
    changed_at: Date,
    changed_by: ObjectId,             // User ID who made the change
    old_roles: [String],
    new_roles: [String],
    reason: String                    // Optional justification
  }],

  // Suspension status (NFR-ABUSE-002)
  is_suspended: Boolean,              // True if currently suspended
  suspension_history: [{
    suspended_at: Date,
    suspended_by: ObjectId,
    suspension_reason: String,
    reinstated_at: Date,              // Optional. Null if still suspended
    reinstated_by: ObjectId,          // Optional
    reinstatement_reason: String      // Optional
  }],

  // User preferences
  preferences: {
    timezone: String,                 // IANA timezone for display
    notification_settings: Object     // User-specific notification preferences
  },

  // Activity tracking (for abuse detection)
  activity_stats: {
    last_action_at: Date,
    total_actions: Number,
    high_stakes_overrides_count: Number,
    publish_count: Number
  },

  // Audit metadata
  created_at: Date,
  updated_at: Date
}
```

**Validation Rules:**

- `slack_user_id` + `slack_team_id` must be unique (composite index)
- `roles` array must contain only valid role values
- If `is_suspended` is true, must have at least one entry in `suspension_history` with null `reinstated_at`
- Role changes must be logged in `role_history`

---

## Index Strategy

### Performance Goals

- **Signal ingestion:** < 100ms p95 write latency
- **Facilitator search:** < 500ms p95 for keyword search across signals
- **Backlog loading:** < 200ms p95 for prioritized cluster list
- **COP candidate readiness check:** < 100ms p95

### Index Definitions

#### `signals` Collection

```javascript
// Unique constraint on Slack message identity
db.signals.createIndex(
  { slack_channel_id: 1, slack_message_ts: 1 },
  { unique: true, name: "idx_slack_message_unique" }
)

// Temporal queries (recent signals, time-range filtering)
db.signals.createIndex(
  { posted_at: -1 },
  { name: "idx_posted_at_desc" }
)

// Cluster membership lookups
db.signals.createIndex(
  { cluster_ids: 1 },
  { name: "idx_cluster_membership" }
)

// Text search for facilitator search (FR-SEARCH-001)
db.signals.createIndex(
  { text: "text", "slack_channel_id": 1 },
  { name: "idx_fulltext_search", weights: { text: 10 } }
)

// Channel + time range queries (common search pattern)
db.signals.createIndex(
  { slack_channel_id: 1, posted_at: -1 },
  { name: "idx_channel_time" }
)

// User activity lookups
db.signals.createIndex(
  { slack_user_id: 1, posted_at: -1 },
  { name: "idx_user_activity" }
)

// Duplicate detection queries
db.signals.createIndex(
  { "ai_flags.duplicate_of_signal_id": 1 },
  { sparse: true, name: "idx_duplicate_of" }
)

// TTL index for data retention (NFR-PRIVACY-003)
db.signals.createIndex(
  { "retention.expires_at": 1 },
  { expireAfterSeconds: 0, name: "idx_ttl_expiration" }
)
```

#### `clusters` Collection

```javascript
// Priority-based backlog sorting (FR-BACKLOG-001)
db.clusters.createIndex(
  { priority_score: -1, last_signal_at: -1 },
  { name: "idx_backlog_priority" }
)

// COP candidate promotion tracking
db.clusters.createIndex(
  { promoted_to_candidate_id: 1 },
  { sparse: true, name: "idx_promoted_candidates" }
)

// Temporal queries
db.clusters.createIndex(
  { created_at: -1 },
  { name: "idx_created_at_desc" }
)

// Conflict detection
db.clusters.createIndex(
  { has_conflicts: 1, priority_score: -1 },
  { name: "idx_conflicts_priority" }
)

// Topic-based filtering
db.clusters.createIndex(
  { topic_type: 1, priority_score: -1 },
  { name: "idx_topic_priority" }
)
```

#### `cop_candidates` Collection

```javascript
// Readiness state filtering (backlog views)
db.cop_candidates.createIndex(
  { readiness_state: 1, risk_tier: 1, updated_at: -1 },
  { name: "idx_readiness_risk_time" }
)

// Source cluster lookups
db.cop_candidates.createIndex(
  { cluster_id: 1 },
  { name: "idx_source_cluster" }
)

// Risk tier filtering (high-stakes gate enforcement)
db.cop_candidates.createIndex(
  { risk_tier: 1, readiness_state: 1 },
  { name: "idx_risk_readiness" }
)

// Publication tracking
db.cop_candidates.createIndex(
  { published_in_cop_update_ids: 1 },
  { name: "idx_published_in_updates" }
)

// Conflict resolution queries
db.cop_candidates.createIndex(
  { "conflicts.conflict_with_candidate_id": 1 },
  { sparse: true, name: "idx_conflicting_candidates" }
)

// Temporal queries
db.cop_candidates.createIndex(
  { created_at: -1 },
  { name: "idx_created_at_desc" }
)
```

#### `cop_updates` Collection

```javascript
// Version chronology
db.cop_updates.createIndex(
  { version_number: 1 },
  { unique: true, name: "idx_version_number_unique" }
)

// Publication timeline
db.cop_updates.createIndex(
  { published_at: -1 },
  { name: "idx_published_at_desc" }
)

// Slack channel tracking
db.cop_updates.createIndex(
  { slack_channel_id: 1, published_at: -1 },
  { name: "idx_channel_publish_time" }
)

// Publisher tracking
db.cop_updates.createIndex(
  { published_by: 1, published_at: -1 },
  { name: "idx_publisher_time" }
)

// Override audit queries
db.cop_updates.createIndex(
  { "overrides.overridden_by": 1 },
  { sparse: true, name: "idx_overridden_by" }
)
```

#### `audit_log` Collection

```javascript
// Chronological audit trail
db.audit_log.createIndex(
  { timestamp: -1 },
  { name: "idx_timestamp_desc" }
)

// Actor-based audit queries
db.audit_log.createIndex(
  { actor_id: 1, timestamp: -1 },
  { name: "idx_actor_timeline" }
)

// Entity audit trail
db.audit_log.createIndex(
  { target_entity_type: 1, target_entity_id: 1, timestamp: -1 },
  { name: "idx_entity_audit_trail" }
)

// Action type filtering
db.audit_log.createIndex(
  { action_type: 1, timestamp: -1 },
  { name: "idx_action_type_time" }
)

// Abuse detection queries (NFR-ABUSE-001)
db.audit_log.createIndex(
  { is_flagged: 1, timestamp: -1 },
  { name: "idx_flagged_actions" }
)

// Role change audit (FR-ROLE-003)
db.audit_log.createIndex(
  { action_type: 1, "changes.after.roles": 1 },
  { name: "idx_role_changes" }
)
```

#### `users` Collection

```javascript
// Unique Slack user identity
db.users.createIndex(
  { slack_user_id: 1, slack_team_id: 1 },
  { unique: true, name: "idx_slack_user_unique" }
)

// Role-based access queries (FR-ROLE-002)
db.users.createIndex(
  { roles: 1 },
  { name: "idx_user_roles" }
)

// Suspension status filtering
db.users.createIndex(
  { is_suspended: 1 },
  { name: "idx_suspension_status" }
)

// Activity tracking for abuse detection
db.users.createIndex(
  { "activity_stats.last_action_at": -1 },
  { name: "idx_last_action" }
)
```

---

## Relationships and References

### Relationship Diagram

```
signals (many) ──┐
                 ├──> clusters (one) ──> cop_candidates (one) ──> cop_updates (many)
signals (many) ──┘                               │
                                                  │
users (one) ─────────────────────────────────────┴──> audit_log (many)
```

### Reference Patterns

**Embedded vs Referenced:**

| Pattern | Used For | Rationale |
|---|---|---|
| **Embedded arrays** | `signals.cluster_ids`, `cop_candidates.verifications`, `cop_updates.candidates_snapshot` | Read atomicity, immutable history, moderate array size |
| **ObjectId references** | `cluster.promoted_to_candidate_id`, `cop_candidate.cluster_id`, `audit_log.target_entity_id` | Cross-collection joins, referential integrity checks |
| **Denormalized counts** | `cluster.signal_count` | Performance optimization for backlog sorting |
| **Snapshot embedding** | `cop_updates.candidates_snapshot` | Immutable point-in-time provenance (FR-AUD-002) |

**Referential Integrity:**

MongoDB does not enforce foreign key constraints. Application-level validation is required for:

- Validating `cluster_ids` in signals reference existing clusters
- Ensuring `cop_candidate.cluster_id` references valid cluster
- Checking `audit_log.target_entity_id` references valid entity
- Validating user ObjectIds in `created_by`, `published_by`, `verified_by` fields

**Cascade Behaviors:**

- **Cluster deletion:** Archive or soft-delete; do not cascade delete signals (preserve audit trail)
- **Candidate merge:** Set `merged_into_candidate_id`, preserve original document
- **User suspension:** Update `is_suspended` flag; do not delete user record (preserve audit trail)
- **Signal expiration:** TTL index handles automatic deletion per retention policy (NFR-PRIVACY-003)

---

## Example Documents

### Example Signal

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234567"),

  slack_channel_id: "C01ABCD1234",
  slack_thread_ts: null,
  slack_message_ts: "1708012345.123456",
  slack_user_id: "U01USER1234",
  slack_team_id: "T01TEAM5678",

  text: "Shelter Alpha at 123 Main St is closing at 6pm today due to power outage. Residents being moved to Shelter Beta on Oak Ave.",
  attachments: [],
  reactions: [
    {
      name: "heavy_check_mark",
      count: 3,
      users: ["U01USER5678", "U01USER9012", "U01USER3456"]
    }
  ],

  posted_at: ISODate("2026-02-15T14:23:45.000Z"),
  ingested_at: ISODate("2026-02-15T14:24:01.234Z"),

  permalink: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012345123456",

  embedding_id: "chroma_embedding_abc123",

  cluster_ids: [ObjectId("65d4f2c3e4b0a8c9d1234560")],

  ai_flags: {
    is_duplicate: false,
    duplicate_of_signal_id: null,
    has_conflict: false,
    conflict_signal_ids: [],
    quality_score: 0.85
  },

  source_quality: {
    is_firsthand: true,
    has_external_link: false,
    external_links: [],
    author_credibility_score: 0.90
  },

  redaction: {
    is_redacted: false
  },

  retention: {
    expires_at: ISODate("2027-02-15T14:23:45.000Z"),
    is_archived: false
  },

  created_at: ISODate("2026-02-15T14:24:01.234Z"),
  updated_at: ISODate("2026-02-15T14:24:01.234Z")
}
```

### Example Cluster

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234560"),

  name: "Shelter Alpha Closure - Feb 15",

  topic_type: "infrastructure",
  keywords: ["shelter", "closure", "power outage", "Shelter Alpha"],

  signal_ids: [
    ObjectId("65d4f2c3e4b0a8c9d1234567"),
    ObjectId("65d4f2c3e4b0a8c9d1234568"),
    ObjectId("65d4f2c3e4b0a8c9d1234569")
  ],
  signal_count: 3,

  first_signal_at: ISODate("2026-02-15T14:23:45.000Z"),
  last_signal_at: ISODate("2026-02-15T14:45:12.000Z"),

  has_conflicts: true,
  conflict_details: [
    {
      field: "time",
      values: ["6pm", "6:30pm"],
      signal_ids: [
        ObjectId("65d4f2c3e4b0a8c9d1234567"),
        ObjectId("65d4f2c3e4b0a8c9d1234569")
      ],
      severity: "minor"
    }
  ],

  urgency_score: 0.85,
  impact_score: 0.70,
  risk_score: 0.60,
  priority_score: 0.72,

  promoted_to_candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234570"),
  promoted_at: ISODate("2026-02-15T15:00:00.000Z"),
  promoted_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),

  ai_summary: "Shelter Alpha closing this evening due to power outage; residents relocating to Shelter Beta.",

  created_at: ISODate("2026-02-15T14:24:05.000Z"),
  updated_at: ISODate("2026-02-15T15:00:00.000Z")
}
```

### Example COP Candidate (Verified)

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234570"),

  cluster_id: ObjectId("65d4f2c3e4b0a8c9d1234560"),
  primary_signal_ids: [
    ObjectId("65d4f2c3e4b0a8c9d1234567"),
    ObjectId("65d4f2c3e4b0a8c9d1234568")
  ],

  readiness_state: "verified",
  readiness_updated_at: ISODate("2026-02-15T15:30:00.000Z"),
  readiness_updated_by: ObjectId("65d4f2c3e4b0a8c9d1234501"),

  risk_tier: "elevated",
  risk_tier_override: null,

  fields: {
    what: "Shelter Alpha closure due to power outage",
    where: "123 Main St, Springfield, IL",
    when: {
      timestamp: ISODate("2026-02-15T18:00:00.000Z"),
      timezone: "America/Chicago",
      is_approximate: false,
      description: "6:00 PM CST, February 15, 2026"
    },
    who: "Shelter Alpha residents (approx. 45 people)",
    so_what: "Residents relocated to Shelter Beta at 456 Oak Ave. No shelter capacity lost; temporary disruption only."
  },

  evidence: {
    slack_permalinks: [
      {
        url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012345123456",
        signal_id: ObjectId("65d4f2c3e4b0a8c9d1234567"),
        description: "Initial report from volunteer coordinator"
      },
      {
        url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012567234567",
        signal_id: ObjectId("65d4f2c3e4b0a8c9d1234568"),
        description: "Confirmation from shelter director"
      }
    ],
    external_sources: [
      {
        url: "https://springfieldcounty.gov/emergency-notices/shelter-alpha-temporary-closure",
        title: "Springfield County Emergency Notices: Shelter Alpha Temporary Closure",
        source_type: "official_source",
        accessed_at: ISODate("2026-02-15T15:25:00.000Z"),
        credibility_score: 1.0
      }
    ]
  },

  verifications: [
    {
      verified_by: ObjectId("65d4f2c3e4b0a8c9d1234501"),
      verified_at: ISODate("2026-02-15T15:30:00.000Z"),
      verification_method: "authoritative_source",
      verification_notes: "Confirmed via official county emergency management website; cross-referenced with shelter director's Slack message.",
      confidence_level: "high"
    }
  ],

  missing_fields: [],
  blocking_issues: [],

  recommended_action: {
    action_type: "publish_as_verified",
    reason: "All fields complete, verified via authoritative source",
    alternatives: []
  },

  conflicts: [
    {
      conflict_with_candidate_id: null,
      conflict_field: "fields.when.timestamp",
      description: "Minor time discrepancy (6pm vs 6:30pm) in source signals",
      resolved: true,
      resolution_notes: "Confirmed 6:00 PM with shelter director; 6:30 PM was estimated time from volunteer",
      resolved_by: ObjectId("65d4f2c3e4b0a8c9d1234501"),
      resolved_at: ISODate("2026-02-15T15:28:00.000Z")
    }
  ],

  draft_wording: {
    headline: "Shelter Alpha Temporarily Closed; Residents Relocated",
    body: "Shelter Alpha (123 Main St) is closed as of 6:00 PM CST today due to a power outage. Approximately 45 residents have been relocated to Shelter Beta (456 Oak Ave). No reduction in overall shelter capacity; this is a temporary operational change only.",
    hedging_applied: false,
    recheck_time: null,
    next_verification_step: null
  },

  facilitator_notes: [
    {
      author_id: ObjectId("65d4f2c3e4b0a8c9d1234501"),
      created_at: ISODate("2026-02-15T15:15:00.000Z"),
      note: "High-priority for next COP update; impacts shelter operations team"
    }
  ],

  published_in_cop_update_ids: [ObjectId("65d4f2c3e4b0a8c9d1234580")],

  merged_into_candidate_id: null,
  merged_at: null,
  merged_by: null,

  created_at: ISODate("2026-02-15T15:00:00.000Z"),
  created_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),
  updated_at: ISODate("2026-02-15T15:30:00.000Z")
}
```

### Example COP Candidate (In Review - High Stakes)

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234571"),

  cluster_id: ObjectId("65d4f2c3e4b0a8c9d1234561"),
  primary_signal_ids: [ObjectId("65d4f2c3e4b0a8c9d1234580")],

  readiness_state: "in_review",
  readiness_updated_at: ISODate("2026-02-15T16:00:00.000Z"),
  readiness_updated_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),

  risk_tier: "high_stakes",
  risk_tier_override: null,

  fields: {
    what: "Reported boil water advisory for Zone 3",
    where: "Zone 3 (north of River Rd, east of Highway 50)",
    when: {
      timestamp: ISODate("2026-02-15T16:00:00.000Z"),
      timezone: "America/Chicago",
      is_approximate: true,
      description: "Effective immediately (as of 4:00 PM CST, Feb 15)"
    },
    who: "Approximately 2,500 residents in Zone 3",
    so_what: "Water may be unsafe to drink without boiling; impacts vulnerable populations"
  },

  evidence: {
    slack_permalinks: [
      {
        url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708019876543210",
        signal_id: ObjectId("65d4f2c3e4b0a8c9d1234580"),
        description: "Report from community volunteer, secondhand"
      }
    ],
    external_sources: []
  },

  verifications: [],

  missing_fields: ["verification"],
  blocking_issues: [
    {
      issue_type: "verification_required",
      description: "High-stakes claim (public health advisory) requires authoritative verification before publishing as verified",
      severity: "requires_caveat"
    }
  ],

  recommended_action: {
    action_type: "assign_verification",
    reason: "High-stakes public health claim; needs authoritative source confirmation",
    alternatives: [
      {
        action_type: "publish_in_review",
        reason: "Can publish with UNCONFIRMED label and caveat while verification is in progress"
      }
    ]
  },

  conflicts: [],

  draft_wording: {
    headline: "UNCONFIRMED: Possible Boil Water Advisory for Zone 3",
    body: "Reports indicate a boil water advisory may be in effect for Zone 3 (north of River Rd, east of Highway 50), affecting approximately 2,500 residents. This information is UNCONFIRMED and awaiting official verification from the county water authority. Residents in this area should monitor official county channels for confirmation.",
    hedging_applied: true,
    recheck_time: ISODate("2026-02-15T17:00:00.000Z"),
    next_verification_step: "Contact county water authority Public Information Officer at (555) 123-4567 for official confirmation"
  },

  facilitator_notes: [
    {
      author_id: ObjectId("65d4f2c3e4b0a8c9d1234500"),
      created_at: ISODate("2026-02-15T16:05:00.000Z"),
      note: "Attempting to reach county water authority PIO. If no confirmation by 5pm, publish as in-review with strong caveat."
    }
  ],

  published_in_cop_update_ids: [],

  merged_into_candidate_id: null,
  merged_at: null,
  merged_by: null,

  created_at: ISODate("2026-02-15T16:00:00.000Z"),
  created_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),
  updated_at: ISODate("2026-02-15T16:05:00.000Z")
}
```

### Example COP Update

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234580"),

  version_number: 3,
  previous_version_id: ObjectId("65d4f2c3e4b0a8c9d1234579"),

  published_at: ISODate("2026-02-15T16:30:00.000Z"),
  published_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),
  publisher_role: "facilitator",

  slack_channel_id: "C01COP12345",
  slack_message_ts: "1708020600.987654",
  slack_permalink: "https://aidworkspace.slack.com/archives/C01COP12345/p1708020600987654",

  content: {
    header: {
      title: "Common Operating Picture (COP) — February 15, 2026 16:30 CST",
      timestamp: ISODate("2026-02-15T16:30:00.000Z"),
      timezone: "America/Chicago",
      disclaimer: "Verified updates are confirmed by evidence noted below. In-review items are unconfirmed and may change."
    },

    sections: {
      verified: [
        {
          candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234570"),
          headline: "Shelter Alpha Temporarily Closed; Residents Relocated",
          body: "Shelter Alpha (123 Main St) is closed as of 6:00 PM CST today due to a power outage. Approximately 45 residents have been relocated to Shelter Beta (456 Oak Ave). No reduction in overall shelter capacity; this is a temporary operational change only.",
          evidence_links: [
            "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012345123456",
            "https://springfieldcounty.gov/emergency-notices/shelter-alpha-temporary-closure"
          ],
          verification_note: "Confirmed via official county emergency management website"
        }
      ],

      in_review: [
        {
          candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234571"),
          headline: "UNCONFIRMED: Possible Boil Water Advisory for Zone 3",
          body: "Reports indicate a boil water advisory may be in effect for Zone 3 (north of River Rd, east of Highway 50), affecting approximately 2,500 residents. This information is UNCONFIRMED and awaiting official verification from the county water authority. Residents in this area should monitor official county channels for confirmation.",
          evidence_links: [
            "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708019876543210"
          ],
          uncertainty_note: "Awaiting confirmation from county water authority",
          recheck_time: ISODate("2026-02-15T17:00:00.000Z")
        }
      ],

      disproven: [],

      gaps: [
        {
          question: "Status of Highway 50 bridge repairs?",
          context: "Multiple reports of bridge closure on Feb 14; unclear if reopened",
          requested_info: "Current bridge status and expected reopening time"
        }
      ]
    },

    footer: {
      change_summary: "New: Shelter Alpha closure (verified), Zone 3 boil water advisory (in review). Updated: Highway 50 bridge moved to gaps section pending confirmation.",
      next_update_time: ISODate("2026-02-15T18:00:00.000Z"),
      contact_info: "Questions? Post in #cop-questions or DM @facilitator-on-duty"
    }
  },

  candidates_snapshot: [
    {
      candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234570"),
      readiness_state: "verified",
      risk_tier: "elevated",
      fields: {
        what: "Shelter Alpha closure due to power outage",
        where: "123 Main St, Springfield, IL",
        when: {
          timestamp: ISODate("2026-02-15T18:00:00.000Z"),
          timezone: "America/Chicago",
          is_approximate: false,
          description: "6:00 PM CST, February 15, 2026"
        },
        who: "Shelter Alpha residents (approx. 45 people)",
        so_what: "Residents relocated to Shelter Beta at 456 Oak Ave. No shelter capacity lost; temporary disruption only."
      },
      evidence: {
        slack_permalinks: [
          {
            url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012345123456",
            signal_id: ObjectId("65d4f2c3e4b0a8c9d1234567"),
            description: "Initial report from volunteer coordinator"
          },
          {
            url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708012567234567",
            signal_id: ObjectId("65d4f2c3e4b0a8c9d1234568"),
            description: "Confirmation from shelter director"
          }
        ],
        external_sources: [
          {
            url: "https://springfieldcounty.gov/emergency-notices/shelter-alpha-temporary-closure",
            title: "Springfield County Emergency Notices: Shelter Alpha Temporary Closure",
            source_type: "official_source",
            accessed_at: ISODate("2026-02-15T15:25:00.000Z"),
            credibility_score: 1.0
          }
        ]
      },
      verifications: [
        {
          verified_by: ObjectId("65d4f2c3e4b0a8c9d1234501"),
          verified_at: ISODate("2026-02-15T15:30:00.000Z"),
          verification_method: "authoritative_source",
          verification_notes: "Confirmed via official county emergency management website",
          confidence_level: "high"
        }
      ]
    },
    {
      candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234571"),
      readiness_state: "in_review",
      risk_tier: "high_stakes",
      fields: {
        what: "Reported boil water advisory for Zone 3",
        where: "Zone 3 (north of River Rd, east of Highway 50)",
        when: {
          timestamp: ISODate("2026-02-15T16:00:00.000Z"),
          timezone: "America/Chicago",
          is_approximate: true,
          description: "Effective immediately (as of 4:00 PM CST, Feb 15)"
        },
        who: "Approximately 2,500 residents in Zone 3",
        so_what: "Water may be unsafe to drink without boiling; impacts vulnerable populations"
      },
      evidence: {
        slack_permalinks: [
          {
            url: "https://aidworkspace.slack.com/archives/C01ABCD1234/p1708019876543210",
            signal_id: ObjectId("65d4f2c3e4b0a8c9d1234580"),
            description: "Report from community volunteer, secondhand"
          }
        ],
        external_sources: []
      },
      verifications: []
    }
  ],

  metrics: {
    total_verified_items: 1,
    total_in_review_items: 1,
    total_disproven_items: 0,
    total_gaps: 1,
    provenance_coverage_pct: 100.0,
    time_since_last_update_minutes: 90
  },

  overrides: [
    {
      candidate_id: ObjectId("65d4f2c3e4b0a8c9d1234571"),
      override_type: "high_stakes_unverified",
      justification: "Public health information is time-sensitive; publishing with UNCONFIRMED label and strong caveats while verification is in progress. Residents need awareness even if not yet confirmed.",
      overridden_by: ObjectId("65d4f2c3e4b0a8c9d1234500"),
      overridden_at: ISODate("2026-02-15T16:25:00.000Z"),
      second_approver_id: null,
      second_approver_at: null
    }
  ],

  created_at: ISODate("2026-02-15T16:30:00.000Z")
}
```

### Example Audit Log Entry (Role Change)

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234590"),

  timestamp: ISODate("2026-02-15T10:00:00.000Z"),
  actor_id: ObjectId("65d4f2c3e4b0a8c9d1234499"),
  actor_role: "workspace_admin",
  actor_ip: "192.168.1.100",

  action_type: "user.role_change",

  target_entity_type: "user",
  target_entity_id: ObjectId("65d4f2c3e4b0a8c9d1234501"),

  changes: {
    before: {
      roles: ["general_participant"]
    },
    after: {
      roles: ["general_participant", "verifier", "facilitator"]
    }
  },

  justification: "Promoted to facilitator/verifier for upcoming crisis exercise",
  system_context: {
    total_facilitators_before: 2,
    total_facilitators_after: 3
  },

  is_flagged: false,
  flag_reason: null,

  created_at: ISODate("2026-02-15T10:00:00.000Z")
}
```

### Example User

```javascript
{
  _id: ObjectId("65d4f2c3e4b0a8c9d1234501"),

  slack_user_id: "U01USER5678",
  slack_team_id: "T01TEAM5678",
  slack_email: "jane.facilitator@aidorg.org",
  slack_display_name: "Jane F.",
  slack_real_name: "Jane Facilitator",

  roles: ["general_participant", "facilitator", "verifier"],

  role_history: [
    {
      changed_at: ISODate("2026-02-01T12:00:00.000Z"),
      changed_by: ObjectId("65d4f2c3e4b0a8c9d1234499"),
      old_roles: [],
      new_roles: ["general_participant"],
      reason: "Initial user creation"
    },
    {
      changed_at: ISODate("2026-02-15T10:00:00.000Z"),
      changed_by: ObjectId("65d4f2c3e4b0a8c9d1234499"),
      old_roles: ["general_participant"],
      new_roles: ["general_participant", "verifier", "facilitator"],
      reason: "Promoted to facilitator/verifier for upcoming crisis exercise"
    }
  ],

  is_suspended: false,
  suspension_history: [],

  preferences: {
    timezone: "America/Chicago",
    notification_settings: {
      backlog_digest_frequency: "hourly",
      high_priority_alerts: true
    }
  },

  activity_stats: {
    last_action_at: ISODate("2026-02-15T16:25:00.000Z"),
    total_actions: 47,
    high_stakes_overrides_count: 1,
    publish_count: 3
  },

  created_at: ISODate("2026-02-01T12:00:00.000Z"),
  updated_at: ISODate("2026-02-15T10:00:00.000Z")
}
```

---

## Data Retention and Archival

### Retention Policy (NFR-PRIVACY-003)

**Configurable TTL per workspace:**

```javascript
// Example: 90-day retention policy
db.signals.updateMany(
  { "retention.expires_at": null },
  {
    $set: {
      "retention.expires_at": new Date(Date.now() + 90 * 24 * 60 * 60 * 1000)
    }
  }
)
```

**Archival exemptions:**

Signals marked with `retention.is_archived: true` are exempt from TTL deletion. Archival criteria:

- Signal is referenced in a published COP update
- Signal is part of a high-stakes verified candidate
- Signal is flagged for long-term research/evaluation

**Purge logging:**

When TTL index deletes expired signals, application logs purge events to audit trail:

```javascript
{
  action_type: "signal.purge",
  target_entity_type: "signal",
  target_entity_id: ObjectId("..."),
  changes: {
    before: { /* signal snapshot */ },
    after: null
  },
  system_context: {
    purge_reason: "TTL expiration",
    retention_policy_days: 90
  }
}
```

---

## Migration Considerations

### From Chat-Diver Schema

**Existing Chat-Diver collections (assumed):**

- `messages` (Slack messages)
- `embeddings` (ChromaDB references)
- `summaries` (Content summaries)

**Migration steps:**

1. **signals collection:**
   - Copy `messages` → `signals`
   - Add new fields: `cluster_ids`, `ai_flags`, `source_quality`, `redaction`, `retention`
   - Migrate `embeddings` references → `embedding_id`

2. **clusters collection:**
   - Create new collection
   - Run initial clustering algorithm on migrated signals
   - Populate `signal_ids`, scores, and conflict detection

3. **cop_candidates collection:**
   - Create new collection (no Chat-Diver equivalent)

4. **cop_updates collection:**
   - Create new collection (no Chat-Diver equivalent)

5. **audit_log collection:**
   - Create new collection
   - Optionally backfill from Chat-Diver security logs

6. **users collection:**
   - Create new collection
   - Populate from Slack workspace user list
   - Assign initial roles (all users start as "general_participant")

**Schema versioning:**

Add `schema_version` field to all collections for future migrations:

```javascript
db.signals.updateMany({}, { $set: { schema_version: 1 } })
db.clusters.updateMany({}, { $set: { schema_version: 1 } })
// ... etc
```

---

## Appendix: Compound Index Optimization

### High-Traffic Query Patterns

**Pattern 1: Facilitator backlog load**

```javascript
// Query: Get top 50 clusters for backlog, sorted by priority, with conflicts first
db.clusters.find({
  promoted_to_candidate_id: { $exists: false }
}).sort({
  has_conflicts: -1,
  priority_score: -1,
  last_signal_at: -1
}).limit(50)

// Optimized compound index (order matters):
db.clusters.createIndex({
  promoted_to_candidate_id: 1,
  has_conflicts: -1,
  priority_score: -1,
  last_signal_at: -1
})
```

**Pattern 2: COP candidate readiness filter**

```javascript
// Query: Get all blocked high-stakes candidates
db.cop_candidates.find({
  readiness_state: "blocked",
  risk_tier: "high_stakes"
}).sort({ updated_at: -1 })

// Optimized compound index:
db.cop_candidates.createIndex({
  readiness_state: 1,
  risk_tier: 1,
  updated_at: -1
})
```

**Pattern 3: Facilitator search with time bounds**

```javascript
// Query: Full-text search in specific channel within last 7 days
db.signals.find({
  $text: { $search: "water advisory" },
  slack_channel_id: "C01ABCD1234",
  posted_at: { $gte: ISODate("2026-02-08T00:00:00.000Z") }
})

// Text index already created; add covering index for time range:
db.signals.createIndex({
  slack_channel_id: 1,
  posted_at: -1
})
```

**Pattern 4: Audit trail for specific entity**

```javascript
// Query: Get all actions for a specific COP candidate, chronological
db.audit_log.find({
  target_entity_type: "cop_candidate",
  target_entity_id: ObjectId("65d4f2c3e4b0a8c9d1234570")
}).sort({ timestamp: 1 })

// Optimized compound index:
db.audit_log.createIndex({
  target_entity_type: 1,
  target_entity_id: 1,
  timestamp: 1
})
```

---

## Appendix: Schema Validation Rules

MongoDB supports JSON schema validation. Example validation for `cop_candidates`:

```javascript
db.createCollection("cop_candidates", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["cluster_id", "primary_signal_ids", "readiness_state", "risk_tier", "fields", "evidence", "created_at", "created_by"],
      properties: {
        readiness_state: {
          enum: ["verified", "in_review", "blocked"]
        },
        risk_tier: {
          enum: ["routine", "elevated", "high_stakes"]
        },
        fields: {
          bsonType: "object",
          required: ["what", "where", "when", "so_what"],
          properties: {
            when: {
              bsonType: "object",
              required: ["timestamp", "timezone"],
              properties: {
                timestamp: { bsonType: "date" },
                timezone: { bsonType: "string" }
              }
            }
          }
        },
        verifications: {
          bsonType: "array",
          items: {
            bsonType: "object",
            required: ["verified_by", "verified_at", "verification_method", "confidence_level"],
            properties: {
              confidence_level: {
                enum: ["high", "medium", "low"]
              }
            }
          }
        }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
```

Apply similar validation to all collections to enforce schema constraints at the database level.

---

**End of MongoDB Schema Design Document**
