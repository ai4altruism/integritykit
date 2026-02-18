# Exercise-in-a-Box: IntegrityKit Crisis Coordination Drill Guide

**Version:** 0.4.0 (Draft)
**Last Updated:** February 2026
**Status:** Draft - Sprint 6 Deliverable

## Overview

This guide helps facilitators run structured crisis-coordination exercises using the IntegrityKit system. It provides templates, checklists, and guidance for designing, executing, and evaluating exercises that test and train teams on producing provenance-backed Common Operating Picture (COP) updates.

### Purpose

- **Training:** Help new facilitators learn the COP workflow
- **Validation:** Test system functionality before real-world deployment
- **Measurement:** Collect operational metrics for evaluation
- **Improvement:** Identify workflow bottlenecks and refinement opportunities

### Who Should Use This Guide

- Exercise coordinators planning crisis-coordination drills
- Facilitators who will manage the COP pipeline during exercises
- Workspace administrators setting up IntegrityKit for exercises
- Evaluators measuring exercise outcomes

---

## Pre-Exercise Preparation

### 1. System Setup Checklist

Complete these steps at least **48 hours before** the exercise:

| Task | Owner | Status |
|------|-------|--------|
| Deploy IntegrityKit to exercise environment | Admin | [ ] |
| Configure Slack workspace and channels | Admin | [ ] |
| Create facilitator and verifier accounts | Admin | [ ] |
| Seed default redaction rules for PII | Admin | [ ] |
| Test signal ingestion from monitored channels | Admin | [ ] |
| Verify metrics dashboard accessible at `/dashboard` | Admin | [ ] |
| Export and review initial metrics baseline | Facilitator | [ ] |
| Confirm Slack bot permissions and OAuth scopes | Admin | [ ] |
| Test COP publish to designated output channel | Facilitator | [ ] |

### 2. Channel Configuration

Configure the following Slack channels for the exercise:

| Channel | Purpose | Monitoring |
|---------|---------|------------|
| `#exercise-ops` | Primary operations channel for simulated reports | Enabled |
| `#exercise-logistics` | Logistics and resource coordination | Enabled |
| `#exercise-medical` | Medical/health-related reports | Enabled |
| `#exercise-shelter` | Shelter status updates | Enabled |
| `#exercise-rumor-control` | Rumor identification and correction | Enabled |
| `#cop-updates` | Published COP updates (output) | Disabled (output only) |
| `#facilitator-private` | Facilitator coordination (private) | Disabled |

### 3. Role Assignment

Assign roles before the exercise begins:

| Role | Permissions | Typical Count |
|------|-------------|---------------|
| **Workspace Admin** | System configuration, role management | 1-2 |
| **Facilitator** | Backlog management, COP drafting, publishing | 2-4 |
| **Verifier** | Verification actions on candidates | 2-4 |
| **General Participant** | Slack messaging (simulated reporters) | 10-50 |

Use the API or admin interface to assign roles:

```http
POST /api/v1/users/{user_id}/roles
{
  "role": "facilitator",
  "justification": "Assigned for Exercise #1 - Feb 2026"
}
```

### 4. Exercise Scenario Design

Design a realistic scenario with these components:

#### Scenario Template

```markdown
# Exercise Scenario: [NAME]

## Situation
[Description of the crisis situation - natural disaster, infrastructure failure, etc.]

## Timeline
- T+0: Exercise start
- T+30min: First reports emerge
- T+1h: Peak information volume
- T+2h: Situation evolves (second phase)
- T+3h: Exercise concludes

## Key Information Elements
1. [Verified fact that should appear in COP]
2. [Conflicting reports requiring resolution]
3. [Unconfirmed rumor that needs verification]
4. [Time-sensitive update requiring rapid response]

## Roles (for participants)
- Reporter A: [Location, perspective, reliability]
- Reporter B: [Location, perspective, reliability]
- Unreliable source: [Will post conflicting/false info]
```

#### Sample Scenario: Shelter Capacity Crisis

```markdown
# Exercise Scenario: Shelter Capacity Crisis

## Situation
A winter storm has forced emergency shelter activations across the region.
Multiple community shelters are operating at or near capacity.
Communications about shelter status are coming through multiple channels.

## Key Information Elements
1. Shelter Alpha at Community Center: 150/200 capacity (verified)
2. Shelter Beta at High School: Conflicting reports (100 vs 250 capacity)
3. Rumor: "Shelter Gamma is closed" (actually still open)
4. Breaking: Shelter Alpha heating system failing at T+1h

## Injects (scripted messages from exercise controllers)
- T+15: "Shelter Alpha just opened, looks like about 150 people here"
- T+20: "High school shelter capacity is 100" (first conflicting report)
- T+25: "I heard Shelter Gamma shut down" (rumor)
- T+30: "Correction: High school can hold 250" (conflicting report)
- T+45: Verification source confirms High School = 250 capacity
- T+60: "URGENT: Heating at Community Center is failing!"
```

---

## Exercise Execution

### 1. Opening Briefing (15 minutes)

Cover these points with all participants:

1. **Exercise Objectives**
   - Practice the COP workflow end-to-end
   - Test information verification processes
   - Measure system performance metrics

2. **Ground Rules**
   - All messages are in-exercise unless prefixed with `[OOC]` (out-of-character)
   - Facilitators may pause exercise if needed (`[HOLD]`)
   - No real emergency services to be contacted
   - Real names/locations should not be used (use fictional names)

3. **Participant Instructions**
   - General participants: Post messages naturally as assigned roles
   - Facilitators: Monitor backlog, promote, verify, draft, publish
   - Verifiers: Help confirm or flag information

4. **Communication Channels**
   - Remind participants which channels to use
   - Confirm facilitator access to the backlog and dashboard

### 2. Exercise Timeline

#### Phase 1: Warm-Up (T+0 to T+30)
- Initial reports begin flowing
- Facilitators orient to the backlog
- First signals are clustered
- No COP updates expected yet

#### Phase 2: Active Response (T+30 to T+90)
- Peak information volume
- Facilitators promote clusters to candidates
- Verification workflow in active use
- First COP updates drafted and published
- Conflicting reports surface and require resolution

#### Phase 3: Evolving Situation (T+90 to T+150)
- Scenario evolution (inject new developments)
- Delta updates to existing COP items
- High-stakes information requiring careful verification
- Rumor control section active

#### Phase 4: Wind-Down (T+150 to T+180)
- Information flow decreases
- Final COP update with current status
- Preparation for after-action review

### 3. Facilitator Workflow Reference

Quick reference for facilitators during the exercise:

```
BACKLOG → CANDIDATES → DRAFTS → PUBLISH
   ↓          ↓          ↓        ↓
Review     Promote    Generate  Approve
clusters   important   draft    & post
           items
```

#### Key Actions

| Action | Endpoint | When to Use |
|--------|----------|-------------|
| View backlog | `GET /api/v1/backlog` | Check prioritized clusters |
| Promote cluster | `POST /api/v1/candidates` | Cluster ready for COP consideration |
| Update candidate state | `PATCH /api/v1/candidates/{id}/state` | Mark verified/blocked/archived |
| Generate draft | `POST /api/v1/drafts` | Create COP update text |
| Preview draft | `GET /api/v1/drafts/{id}/preview` | Review before publishing |
| Approve draft | `POST /api/v1/publish/drafts/{id}/approve` | Required before publish |
| Publish | `POST /api/v1/publish/drafts/{id}/publish` | Post to Slack channel |

#### Handling Conflicts

When the system flags conflicting information:

1. **Identify the conflict** - Review the cluster details and source messages
2. **Seek verification** - Use clarification templates to request more info
3. **Document resolution** - Update candidate with resolution notes
4. **Proceed or block** - Mark as VERIFIED or keep BLOCKED until resolved

### 4. Exercise Control

Exercise controllers should:

1. **Monitor progress** via the metrics dashboard (`/dashboard`)
2. **Inject scripted events** at designated times
3. **Adjust pacing** if exercise runs too fast/slow
4. **Document issues** for after-action review
5. **Call holds** if technical issues arise (`[HOLD]` in facilitator channel)

---

## Post-Exercise Evaluation

### 1. Immediate After-Action Review (30 minutes)

Conduct within 1 hour of exercise completion:

#### Facilitator Debrief Questions
- What worked well in the workflow?
- Where did you encounter bottlenecks?
- Were there any unclear processes?
- How effective was the AI-generated draft text?
- What would you do differently?

#### Technical Issues Log
Document any system issues encountered:

| Time | Issue | Impact | Resolution |
|------|-------|--------|------------|
| | | | |

### 2. Metrics Export and Analysis

Export exercise metrics immediately after completion:

```http
GET /api/v1/metrics/export?workspace_id={workspace}&format=json
```

Or use the dashboard export buttons for JSON/CSV download.

#### Key Metrics to Review

| Metric | Target | Notes |
|--------|--------|-------|
| **Time to Validated Update** | < 15 min avg | Signal → Published COP |
| **Conflicting Report Rate** | < 20% | Clusters with conflicts |
| **Resolution Rate** | > 80% | Conflicts resolved |
| **Moderator Actions per Update** | < 10 | Facilitator burden |
| **Provenance Coverage** | > 90% | Items with citations |
| **Readiness Distribution** | Healthy pipeline | Not too many blocked |

### 3. Evaluation Framework Criteria

Rate exercise effectiveness on these dimensions:

#### Information Quality (1-5)
- [ ] COP updates accurately reflected ground truth
- [ ] Conflicting information was correctly identified
- [ ] Verification status was appropriate for each item
- [ ] Citations linked to correct source messages

#### Process Efficiency (1-5)
- [ ] Time from report to COP was acceptable
- [ ] Facilitators could keep up with information flow
- [ ] Bottlenecks were manageable
- [ ] Handoffs between team members were smooth

#### System Performance (1-5)
- [ ] Signal ingestion was reliable
- [ ] Clustering grouped related messages correctly
- [ ] LLM-generated drafts were useful starting points
- [ ] No significant technical issues

#### Human Factors (1-5)
- [ ] Facilitators understood their role
- [ ] Workflow was intuitive
- [ ] Decision-making was well-supported
- [ ] Fatigue/burden was manageable

### 4. Improvement Recommendations

Document specific improvements for:

1. **System Configuration**
   - Redaction rules to add/modify
   - Cluster sensitivity adjustments
   - Channel monitoring changes

2. **Process Refinement**
   - Workflow step changes
   - Role assignment adjustments
   - Communication protocols

3. **Training Needs**
   - Knowledge gaps identified
   - Skills requiring practice
   - Documentation improvements needed

4. **Scenario Design**
   - Realism improvements
   - Pacing adjustments
   - Inject timing changes

---

## Exercise Templates

### Quick Exercise (1 hour)

For training or system testing:

| Phase | Duration | Focus |
|-------|----------|-------|
| Setup & Briefing | 10 min | Roles, channels, scenario |
| Active Exercise | 40 min | Basic promote → publish cycle |
| Debrief | 10 min | Quick feedback, metrics review |

Scenario: Single shelter status update with one conflicting report.

### Standard Exercise (3 hours)

For comprehensive workflow testing:

| Phase | Duration | Focus |
|-------|----------|-------|
| Setup & Briefing | 15 min | Full orientation |
| Phase 1: Warm-Up | 30 min | Initial reports, familiarization |
| Phase 2: Active | 60 min | Peak volume, verification |
| Phase 3: Evolution | 45 min | Situation changes, updates |
| Debrief | 30 min | Full after-action review |

Scenario: Multi-shelter crisis with evolving conditions, conflicting reports, and rumor control needs.

### Full-Day Exercise (8 hours)

For operational readiness validation:

| Phase | Duration | Focus |
|-------|----------|-------|
| Setup & Briefing | 30 min | Comprehensive orientation |
| Phase 1 | 2 hours | Initial response |
| Break | 30 min | Facilitator rotation |
| Phase 2 | 2 hours | Sustained operations |
| Break | 30 min | Facilitator rotation |
| Phase 3 | 2 hours | Complex scenarios, handoffs |
| Debrief | 1 hour | Comprehensive review |

Scenario: Multi-day crisis simulation compressed to 8 hours with facilitator shift changes.

---

## Troubleshooting

### Common Issues

| Issue | Likely Cause | Resolution |
|-------|--------------|------------|
| Signals not appearing in backlog | Channel not monitored | Check channel config |
| Clustering not working | Embedding service issue | Restart ChromaDB |
| Publish fails | Bot not in channel | Invite bot to output channel |
| Metrics not updating | Database connectivity | Check MongoDB connection |
| Slow LLM responses | API rate limits | Check OpenAI usage |

### Emergency Procedures

If critical issues arise during exercise:

1. **Announce hold:** `[HOLD] - Technical issue, please stand by`
2. **Assess severity:** Can exercise continue with workaround?
3. **Communicate:** Update participants on status
4. **Resume or cancel:** Based on severity and time remaining
5. **Document:** Log issue for post-exercise review

---

## Appendices

### A. Sample Inject Schedule

| Time | Channel | Message | Purpose |
|------|---------|---------|---------|
| T+5 | #exercise-ops | "Setting up operations at community center" | Warm-up |
| T+10 | #exercise-shelter | "Shelter Alpha open at 123 Main St" | First factual report |
| T+15 | #exercise-shelter | "About 150 people at Shelter Alpha so far" | Capacity info |
| T+20 | #exercise-shelter | "High school shelter can take 100 people" | Conflict setup |
| T+25 | #exercise-rumor | "I heard Shelter Gamma is closed" | Rumor inject |
| T+30 | #exercise-shelter | "Actually the high school holds 250" | Conflicting info |
| T+45 | #exercise-ops | "Confirmed: HS capacity is 250 per fire marshal" | Resolution source |
| T+60 | #exercise-shelter | "URGENT: Heating failure at Community Center!" | Breaking news |

### B. Facilitator Quick Reference Card

```
PROMOTE → VERIFY → DRAFT → APPROVE → PUBLISH
   │         │        │        │         │
   └─ Is cluster    └─ Is info   └─ Is text   └─ Is update
      important?       confirmed?   accurate?    ready?
```

**Keyboard Shortcuts** (if using Slack App Home)
- `P` - Promote selected cluster
- `V` - Mark candidate as verified
- `D` - Generate draft
- `Enter` - Approve and publish

**Status Indicators**
- `✅` VERIFIED - Confirmed information
- `🟨` IN_REVIEW - Not yet confirmed
- `🔴` BLOCKED - Conflict or issue
- `📁` ARCHIVED - No longer relevant

### C. Post-Exercise Report Template

```markdown
# Exercise Report: [NAME]
**Date:** [DATE]
**Duration:** [X hours]
**Participants:** [N total: X facilitators, Y verifiers, Z reporters]

## Executive Summary
[2-3 sentence overview of exercise outcomes]

## Metrics Summary
| Metric | Value | Target | Assessment |
|--------|-------|--------|------------|
| Time to Validated Update | X min | < 15 min | Pass/Fail |
| Conflicting Report Rate | X% | < 20% | Pass/Fail |
| Provenance Coverage | X% | > 90% | Pass/Fail |
| Moderator Actions/Update | X | < 10 | Pass/Fail |

## Observations
### What Worked Well
- [Point 1]
- [Point 2]

### Areas for Improvement
- [Point 1]
- [Point 2]

## Recommendations
1. [Recommendation 1]
2. [Recommendation 2]

## Attachments
- Metrics export (JSON/CSV)
- Inject schedule (as-executed)
- Issue log
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.4.0 | Feb 2026 | Initial draft - Sprint 6 deliverable |

---

*This guide is part of the Aid Arena Integrity Kit project. For system documentation, see the [README](../README.md) and [Architecture Guide](architecture.md).*
