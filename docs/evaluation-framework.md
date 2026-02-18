# Evaluation Framework: IntegrityKit Operational Metrics

**Version:** 0.4.0
**Last Updated:** February 2026
**SRS Reference:** FR-METRICS-001, FR-METRICS-002

## Overview

This document defines the evaluation framework for measuring IntegrityKit's operational effectiveness in crisis coordination exercises and deployments. It establishes metric definitions, measurement methodology, data collection procedures, and interpretation guidelines.

### Purpose

1. **Quantify effectiveness** of human-AI coordination in producing COP updates
2. **Identify bottlenecks** in the verification and publication workflow
3. **Compare performance** across exercises, configurations, and teams
4. **Support continuous improvement** through data-driven refinement

### Scope

This framework covers the five operational metrics specified in FR-METRICS-001:

| Metric | Purpose | Primary Question |
|--------|---------|------------------|
| Time to Validated Update | Latency | How fast can verified information reach stakeholders? |
| Conflicting Report Rate | Quality | How often does incoming information contain contradictions? |
| Moderator Burden | Workload | How much human effort is required per COP update? |
| Provenance Coverage | Trust | Do published updates have adequate citation support? |
| Readiness Distribution | Health | Is the verification pipeline flowing or blocked? |

---

## Metric Definitions

### 1. Time to Validated Update

**Definition:** The elapsed time from the earliest signal in a COP candidate to the publication of that candidate in a COP update.

**Formula:**
```
time_to_update = published_at - min(signal.created_at for signal in candidate.primary_signals)
```

**Unit:** Seconds (reported as average, median, p90, min, max)

**Measurement Points:**
- **Start:** `signal.created_at` - When the Slack message was ingested
- **End:** `cop_update.published_at` - When the COP update was posted to Slack

**Breakdown by Risk Tier:**
| Risk Tier | Expected Range | Target |
|-----------|----------------|--------|
| HIGH_STAKES | 5-30 min | < 15 min |
| ELEVATED | 10-45 min | < 30 min |
| ROUTINE | 15-60 min | < 45 min |

**Interpretation:**
- Lower values indicate faster information flow
- High variance suggests inconsistent processing
- Breakdown by risk tier reveals prioritization effectiveness

### 2. Conflicting Report Rate

**Definition:** The percentage of clusters that contain conflicting information, plus the rate at which conflicts are resolved.

**Formulas:**
```
conflict_rate = (clusters_with_conflicts / total_clusters) * 100
resolution_rate = (conflicts_resolved / total_conflicts_detected) * 100
```

**Unit:** Percentage (0-100%)

**What Counts as a Conflict:**
- Direct contradictions (e.g., "shelter open" vs "shelter closed")
- Incompatible quantitative claims (e.g., "50 capacity" vs "200 capacity")
- Mutually exclusive statuses or outcomes

**Measurement Points:**
- **Detection:** `cluster.conflicts.detected_at` - When AI flagged the conflict
- **Resolution:** `cluster.conflicts.resolved_at` - When facilitator marked resolved
- **Time Window:** Configurable (default: last 24 hours)

**Targets:**
| Metric | Target | Concerning | Critical |
|--------|--------|------------|----------|
| Conflict Rate | < 20% | 20-35% | > 35% |
| Resolution Rate | > 80% | 60-80% | < 60% |
| Avg Resolution Time | < 30 min | 30-60 min | > 60 min |

**Interpretation:**
- High conflict rate suggests chaotic information environment or low source reliability
- Low resolution rate indicates bottleneck in facilitator verification
- Long resolution times may require more verifiers or clearer protocols

### 3. Moderator Burden

**Definition:** The amount of facilitator effort required to produce COP updates, measured by action counts and distribution.

**Formulas:**
```
actions_per_update = total_facilitator_actions / published_cop_updates
actions_per_facilitator = total_facilitator_actions / unique_active_facilitators
```

**Tracked Actions:**
| Action Type | Weight | Notes |
|-------------|--------|-------|
| `cluster.promote` | 1 | Moving cluster to candidates |
| `candidate.update_state` | 1 | State transitions |
| `candidate.verify` | 1 | Recording verification |
| `candidate.update_risk_tier` | 1 | Risk tier changes |
| `draft.edit` | 1 | Editing AI-generated text |
| `draft.approve` | 1 | Approving for publish |
| `cop_update.publish` | 1 | Publishing to Slack |
| `cop_update.override` | 2 | High-stakes override (weighted) |

**Special Metrics:**
- **High-Stakes Overrides:** Count of overrides requiring extra justification
- **Edits to AI Drafts:** Count of manual edits to LLM-generated text

**Targets:**
| Metric | Target | Concerning | Critical |
|--------|--------|------------|----------|
| Actions per Update | < 10 | 10-15 | > 15 |
| Actions per Facilitator | < 50/hr | 50-75/hr | > 75/hr |
| High-Stakes Override Rate | < 5% | 5-10% | > 10% |
| AI Draft Edit Rate | < 30% | 30-50% | > 50% |

**Interpretation:**
- High actions per update suggests workflow inefficiency
- Uneven distribution across facilitators indicates workload imbalance
- High AI draft edit rate suggests prompt tuning needed

### 4. Provenance Coverage

**Definition:** The percentage of published COP line items that include at least one source citation.

**Formula:**
```
coverage_rate = (line_items_with_citations / total_line_items) * 100
```

**Citation Types:**
- **Slack Permalinks:** Links to original Slack messages
- **External Sources:** URLs to external documentation, official sources
- **Verification Records:** References to verification actions

**Measurement Points:**
- Measured at time of publication
- Each line item in COP update is evaluated
- A line item "has citation" if it contains at least one source reference

**Targets:**
| Metric | Target | Acceptable | Concerning |
|--------|--------|------------|------------|
| Coverage Rate | > 95% | 80-95% | < 80% |
| Avg Citations per Item | > 1.5 | 1.0-1.5 | < 1.0 |
| Slack vs External Ratio | Context-dependent | N/A | N/A |

**Interpretation:**
- High coverage demonstrates accountability and traceability
- Low coverage suggests incomplete evidence collection
- Ratio of Slack to external sources indicates information environment

### 5. Readiness Distribution

**Definition:** The distribution of COP candidates across readiness states at a point in time.

**States:**
| State | Description | Healthy % |
|-------|-------------|-----------|
| IN_REVIEW | Being verified | 20-40% |
| VERIFIED | Ready for publication | 30-50% |
| BLOCKED | Blocked by conflict/missing info | < 15% |
| ARCHIVED | Completed or deprecated | 20-40% |

**Formulas:**
```
in_review_pct = (in_review_count / total_candidates) * 100
verified_pct = (verified_count / total_candidates) * 100
blocked_pct = (blocked_count / total_candidates) * 100
```

**Warning Signs:**
| Pattern | Interpretation | Action |
|---------|----------------|--------|
| High IN_REVIEW | Verification bottleneck | Add verifiers, clarify criteria |
| Low VERIFIED | Pipeline blocked | Resolve blockers, prioritize |
| High BLOCKED | Many conflicts | Focus on resolution |
| Low throughput | Pipeline stalled | Investigate bottleneck |

**Risk Tier Breakdown:**
- Report distribution by risk tier to identify if high-stakes items are stuck
- HIGH_STAKES items should progress faster than ROUTINE

---

## Data Collection

### Automatic Collection

All metrics are collected automatically by the IntegrityKit system:

1. **Signal ingestion:** Timestamps captured at ingestion
2. **Audit logging:** All facilitator actions logged with timestamps
3. **State tracking:** Candidate and cluster state changes recorded
4. **Publication tracking:** COP update metadata stored

### Export Methods

**Dashboard:**
- Real-time visualization at `/dashboard`
- Refresh button for current snapshot

**API Endpoints:**
```http
# Full metrics snapshot
GET /api/v1/metrics?workspace_id={workspace}

# Individual metrics
GET /api/v1/metrics/time-to-update?workspace_id={workspace}&start={ISO}&end={ISO}
GET /api/v1/metrics/conflicting-reports?workspace_id={workspace}&start={ISO}&end={ISO}
GET /api/v1/metrics/moderator-burden?workspace_id={workspace}&start={ISO}&end={ISO}
GET /api/v1/metrics/provenance-coverage?workspace_id={workspace}&start={ISO}&end={ISO}
GET /api/v1/metrics/readiness-distribution?workspace_id={workspace}

# Export
GET /api/v1/metrics/export?workspace_id={workspace}&format={json|csv}
```

### Sampling Periods

| Use Case | Recommended Period |
|----------|-------------------|
| Exercise evaluation | Full exercise duration |
| Operational monitoring | Rolling 24 hours |
| Trend analysis | Weekly/monthly aggregations |
| Incident review | Event start to resolution |

---

## Measurement Methodology

### Pre-Exercise Baseline

Before each exercise:

1. **Reset or isolate workspace** - Fresh metrics collection
2. **Document configuration** - Record system settings, team size, roles
3. **Note external factors** - Scenario complexity, participant experience

### During Exercise

1. **Minimal intervention** - Let metrics collect naturally
2. **Note anomalies** - Document any technical issues or unusual events
3. **Periodic snapshots** - Export metrics at intervals if exercise is long

### Post-Exercise Analysis

1. **Export complete dataset** - JSON and CSV for analysis
2. **Compare to targets** - Rate each metric against established targets
3. **Identify patterns** - Look for correlations and root causes
4. **Document findings** - Create evaluation report

### Longitudinal Comparison

When comparing across exercises:

1. **Normalize for scenario complexity** - More complex scenarios naturally have higher conflict rates
2. **Control for team composition** - Different team sizes and experience levels affect burden
3. **Account for duration** - Longer exercises may show different patterns
4. **Note system changes** - Configuration or version differences

---

## Interpretation Guidelines

### Healthy System Indicators

A well-functioning IntegrityKit deployment typically shows:

| Indicator | Value | Meaning |
|-----------|-------|---------|
| Time to Update (avg) | < 15 min | Information flows quickly |
| Conflict Rate | 10-25% | Expected in crisis, being managed |
| Resolution Rate | > 85% | Conflicts addressed promptly |
| Actions per Update | 5-10 | Efficient workflow |
| Provenance Coverage | > 95% | Strong accountability |
| Blocked % | < 10% | Pipeline not stuck |

### Warning Signs

| Pattern | Possible Causes | Recommended Actions |
|---------|-----------------|---------------------|
| Time increasing over exercise | Facilitator fatigue, accumulating backlog | Add facilitators, prioritize ruthlessly |
| Conflict rate spiking | Chaotic information, unreliable sources | Focus verification, clarification requests |
| Resolution rate dropping | Overwhelmed facilitators, unclear criteria | Clarify protocols, reduce scope |
| High actions per update | Inefficient workflow, many edits | Review process, tune prompts |
| Low provenance coverage | Rushing, insufficient evidence | Slow down, require citations |
| High blocked % | Unresolved conflicts, missing info | Focus on resolution, gather info |

### Contextual Factors

Metrics should be interpreted considering:

1. **Scenario complexity** - Real crises are chaotic; some conflict is expected
2. **Team experience** - New teams naturally slower
3. **Information volume** - Surge conditions stress the system
4. **Risk profile** - High-stakes scenarios require more verification

---

## Reporting Template

### Exercise Evaluation Report

```markdown
# Exercise Evaluation Report

**Exercise:** [Name]
**Date:** [Date]
**Duration:** [Hours]
**Workspace:** [ID]

## Summary

| Metric | Value | Target | Assessment |
|--------|-------|--------|------------|
| Avg Time to Update | X min | < 15 min | Pass/Fail |
| Conflict Rate | X% | < 20% | Pass/Fail |
| Resolution Rate | X% | > 80% | Pass/Fail |
| Actions per Update | X | < 10 | Pass/Fail |
| Provenance Coverage | X% | > 95% | Pass/Fail |
| Blocked % | X% | < 10% | Pass/Fail |

## Detailed Analysis

### Time to Validated Update
- Average: X seconds
- Median: X seconds
- P90: X seconds
- Breakdown by risk tier: [table]
- Observations: [text]

### Conflicting Report Rate
- Total clusters: X
- Clusters with conflicts: X (Y%)
- Conflicts resolved: X (Y%)
- Average resolution time: X min
- Observations: [text]

### Moderator Burden
- Total facilitator actions: X
- Actions per COP update: X
- Unique active facilitators: X
- High-stakes overrides: X
- Edits to AI drafts: X
- Observations: [text]

### Provenance Coverage
- Total line items: X
- Items with citations: X (Y%)
- Slack citations: X
- External citations: X
- Observations: [text]

### Readiness Distribution
- IN_REVIEW: X (Y%)
- VERIFIED: X (Y%)
- BLOCKED: X (Y%)
- ARCHIVED: X (Y%)
- Observations: [text]

## Key Findings
1. [Finding 1]
2. [Finding 2]
3. [Finding 3]

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]
3. [Recommendation 3]

## Attachments
- Metrics export (JSON)
- Metrics export (CSV)
- Dashboard screenshots
```

---

## API Reference

### Metrics Snapshot Response

```json
{
  "workspace_id": "T123456",
  "period_start": "2026-02-17T00:00:00Z",
  "period_end": "2026-02-17T12:00:00Z",
  "generated_at": "2026-02-17T12:00:01Z",
  "time_to_validated_update": {
    "metric_type": "time_to_validated_update",
    "average_seconds": 720.5,
    "median_seconds": 600.0,
    "min_seconds": 120.0,
    "max_seconds": 2400.0,
    "p90_seconds": 1500.0,
    "sample_count": 25,
    "breakdown_by_risk_tier": {
      "high_stakes": 480.0,
      "elevated": 720.0,
      "routine": 900.0
    }
  },
  "conflicting_report_rate": {
    "metric_type": "conflicting_report_rate",
    "total_clusters": 50,
    "clusters_with_conflicts": 8,
    "conflict_rate": 16.0,
    "total_conflicts_detected": 12,
    "conflicts_resolved": 10,
    "resolution_rate": 83.3,
    "average_resolution_time_seconds": 900.0
  },
  "moderator_burden": {
    "metric_type": "moderator_burden",
    "total_facilitator_actions": 150,
    "actions_per_cop_update": 6.0,
    "actions_by_type": {
      "cluster.promote": 50,
      "candidate.verify": 40,
      "draft.edit": 20,
      "cop_update.publish": 25,
      "cop_update.override": 2
    },
    "unique_facilitators_active": 3,
    "actions_per_facilitator": 50.0,
    "high_stakes_overrides": 2,
    "edits_to_ai_drafts": 20
  },
  "provenance_coverage": {
    "metric_type": "provenance_coverage",
    "total_published_line_items": 75,
    "line_items_with_citations": 72,
    "coverage_rate": 96.0,
    "average_citations_per_item": 1.8,
    "slack_permalink_citations": 100,
    "external_source_citations": 35
  },
  "readiness_distribution": {
    "metric_type": "readiness_distribution",
    "total_candidates": 60,
    "in_review_count": 15,
    "verified_count": 25,
    "blocked_count": 5,
    "archived_count": 15,
    "in_review_percentage": 25.0,
    "verified_percentage": 41.7,
    "blocked_percentage": 8.3,
    "archived_percentage": 25.0,
    "by_risk_tier": {
      "high_stakes": {"in_review": 2, "verified": 8, "blocked": 1, "archived": 4},
      "elevated": {"in_review": 5, "verified": 10, "blocked": 2, "archived": 5},
      "routine": {"in_review": 8, "verified": 7, "blocked": 2, "archived": 6}
    }
  }
}
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.4.0 | Feb 2026 | Initial framework - Sprint 6 deliverable |

---

*This evaluation framework supports FR-METRICS-001 and FR-METRICS-002 as defined in the IntegrityKit SRS. For exercise setup and execution guidance, see the [Exercise-in-a-Box Guide](exercise-in-a-box.md).*
