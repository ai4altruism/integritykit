# Aid Arena Integrity Kit

## System Requirements Specification (SRS) — Ambient / Facilitator-Centric Mode (v0.4)

| Field | Value |
|---|---|
| **Version** | 0.4 (Role management; searchable index; wording guidance; metrics; conflict & privacy NFRs) |
| **Date** | 2026-02-15 |
| **System-of-interest** | Aid Arena Integrity Kit: Slack-integrated system that drafts and supports facilitator-approved COP updates. |
| **Primary output** | Accurate, provenance-aware COP updates published into Slack with clear separation of Verified vs In-Review content. |
| **Preceding version** | v0.3 — see changelog at end of document. |

---

## 1. Scope

This SRS specifies requirements for the Ambient / Facilitator-Centric mode. In this mode, most Slack participants do not interact with the system. The system performs background ingestion, clustering, and drafting. Facilitators and moderators use private tooling to manage COP Candidates and publish COP updates.

---

## 2. Definitions

- **COP Candidate:** A facilitator-tracked item intended to become a COP line item.
- **Readiness:** System classification of whether a COP Candidate is publishable (Ready — Verified / Ready — In Review / Blocked).
- **Evidence pack:** Collection of citations supporting a COP Candidate (Slack permalinks and optionally external sources).
- **Provenance:** The traceable chain linking a published COP statement back to its underlying evidence — Slack permalinks, external source URLs, verification actions, and the identities of actors who promoted, verified, and approved the item. *(v0.4)*
- **High-stakes claim:** A claim category that could cause harm if incorrect (e.g., evacuation orders, safety hazards).
- **Signal:** Any Slack message, thread, or shared link that may be relevant to situational awareness. *(v0.4)*
- **Cluster:** A system-created grouping of related signals (topic/incident/thread bundle). *(v0.4)*

---

## 3. Assumptions and Constraints

- Humans remain accountable for verification decisions and publishing actions.
- The system must minimize intrusiveness and avoid posting in public channels by default.
- All AI outputs must be labeled as suggestions/drafts; no automated publishing.
- The system does not require general participants to file structured reports or interact with new forms. Background processing structures unstructured Slack activity without changing participant behavior. *(v0.4)*

---

## 4. Functional Requirements

### 4.1 Role Assignment and Access Control *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-ROLE-001 | The system shall support at least three configurable roles: **General Participant** (no system interaction required), **Facilitator/Moderator** (backlog access, promote, publish, override), and **Verifier** (record verification actions and evidence). A single user may hold multiple roles. | MVP | Test | Roles can be assigned and changed by a workspace admin or designated super-facilitator; a user assigned Facilitator + Verifier can perform both sets of actions; a General Participant cannot access the facilitator backlog. |
| FR-ROLE-002 | The system shall enforce role-based access on all facilitator-facing views and actions (backlog, COP Candidate management, publish). Unauthorized users receive a clear denial message. | MVP | Test | Attempting to access the backlog or publish a COP update without the Facilitator role returns an access-denied response; audit log records the attempt. |
| FR-ROLE-003 | Role changes shall be logged in the audit trail (actor, target user, old role set, new role set, timestamp). | MVP | Test | After a role change, the audit log contains an entry with all specified fields. |

### 4.2 COP Readiness, Risk, and Publish Gates

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-COP-READ-001 | The system shall compute a readiness state for each COP Candidate: (a) Ready — Verified, (b) Ready — In Review, or (c) Blocked. | MVP | Test | Given a COP Candidate with complete required fields and logged verification, readiness is Ready — Verified; given incomplete but non-misleading fields with in-review labeling, readiness is Ready — In Review; given missing critical fields or unresolved high-risk conflicts, readiness is Blocked. |
| FR-COP-READ-002 | The system shall present a "missing/weak fields" checklist for each COP Candidate (who/what/when/where/so-what/evidence) and identify which fields block publishability. | MVP | Test | For any candidate missing a required field, the UI lists the missing field(s) and marks the candidate Blocked or In-Review accordingly with an explanation. |
| FR-COP-READ-003 | The system shall recommend one "best next action" to improve readiness (e.g., request clarification, assign verification, merge duplicate, resolve conflict). | MVP | Test | For each candidate, UI shows a single recommended next action plus 1–3 alternative actions; recommendations cite the reason (missing field, conflict, high-stakes gate). |
| FR-COP-RISK-001 | The system shall classify COP Candidates into risk tiers (Routine / Elevated / High-stakes) based on category and content signals, and allow facilitator override with justification. | Pilot | Test | High-stakes signals (evacuation, shelter closure, hazards, medical guidance, donation instructions) are flagged as High-stakes; changing the risk tier requires entering a brief reason; override is logged. |
| FR-COP-GATE-001 | The system shall enforce publish gates for High-stakes candidates by default: Verified status required unless a facilitator explicitly overrides with a written rationale and "UNCONFIRMED" labeling. | Pilot | Test | Attempting to publish a High-stakes In-Review line item prompts for (a) explicit override confirmation, (b) rationale, and (c) inserts UNCONFIRMED label in the draft COP output. |
| FR-COP-GATE-002 | The system shall support an optional "two-person rule" for High-stakes overrides, requiring a second approver when configured. | v1 | Test | When enabled, High-stakes override COP drafts cannot be published until a second authorized user approves; audit log records both approvals. |

### 4.3 Backlog and Promotion Workflow

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-BACKLOG-001 | The system shall maintain a private COP backlog accessible to authorized facilitators, listing candidate clusters prioritized by urgency/impact/risk signals. | MVP | Test | Authorized facilitator can view backlog; unauthorized user cannot. Items are sortable by urgency, risk, and recency. |
| FR-BACKLOG-002 | The system shall support one-click "Promote to COP Candidate" from backlog items and/or Slack message actions. | MVP | Test | From backlog, facilitator can promote an item; resulting COP Candidate includes links to source messages and cluster context. |
| FR-BACKLOG-003 | The system shall suggest likely duplicates and related threads for each backlog item and COP Candidate, and provide a merge workflow. | Pilot | Test | For a duplicated incident represented by multiple threads, system suggests duplicates; facilitator can merge and select a canonical evidence set. |

### 4.4 Facilitator Search *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-SEARCH-001 | The system shall provide a searchable index of all ingested signals, clusters, and COP Candidates, accessible to users with the Facilitator or Verifier role. | MVP | Test | A facilitator can search by keyword, time range, and/or channel and receive ranked results with message previews and Slack permalinks. General participants cannot access the search interface. |
| FR-SEARCH-002 | Search results shall indicate cluster membership and COP Candidate status (if any) for each matching signal. | Pilot | Test | For a signal that belongs to a cluster and has been promoted to a COP Candidate, the search result displays cluster ID/name and current readiness state. |

### 4.5 COP Drafting and Publishing

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-COPDRAFT-001 | The system shall generate draft COP line items from COP Candidates, including explicit status labels (Verified / In Review / Disproven) and citations to evidence. | MVP | Test | Generated draft includes at least one citation link per line item and the correct status label; citations resolve to evidence pack items. |
| FR-COPDRAFT-002 | The system shall assemble a draft COP update grouped into sections: Verified Updates, In-Review Updates, Disproven/Rumor Control, and Open Questions/Gaps. | MVP | Test | COP draft contains all configured sections and places each line item in the correct section based on status. |
| FR-COPDRAFT-003 | The system shall generate a "What changed since last COP" summary (new items, status changes, resolved items). | Pilot | Test | After publishing COP vN, the system can produce a delta summary for vN+1 that references additions and changes. |
| FR-COP-PUB-001 | The system shall not publish COP updates into Slack without an explicit human approval action by an authorized role. | MVP | Test | No automated posting occurs; publish button requires authorization; audit log records publisher identity and timestamp. |

### 4.6 COP Wording Guidance *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-COP-WORDING-001 | When generating draft COP line items with In-Review status, the system shall apply hedged phrasing consistent with CDD Appendix A (e.g., "Reports indicate…," "Unconfirmed: …," "Seeking confirmation of…"). Facilitators may edit all suggested wording. | MVP | Test | A draft COP line item with In-Review status uses hedged phrasing; a draft with Verified status uses direct factual phrasing. Facilitator can freely edit both before publishing. |
| FR-COP-WORDING-002 | For high-stakes in-review items, the system shall include a suggested recheck time and next verification step in the draft wording. | Pilot | Test | A high-stakes In-Review draft line item includes a recheck-time field and a next-step suggestion; the facilitator can accept, edit, or remove them. |

### 4.7 Auditability and Versioning

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-AUD-001 | The system shall maintain an immutable audit log of COP Candidate status changes, risk overrides, merges, role changes, and COP publish actions. | MVP | Test | Audit log entries include actor, timestamp, action type, and before/after values; entries cannot be edited by standard users. |
| FR-AUD-002 | The system shall store COP updates as versioned artifacts and preserve the set of supporting COP Candidates and evidence packs used for each version. | Pilot | Test | For each published COP update, reviewers can retrieve the exact supporting candidates and citations as of publish time. |

### 4.8 Operational Metrics and Instrumentation *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| FR-METRICS-001 | The system shall record and make available to facilitators the following operational metrics: (a) time-to-validated-update (first signal → Ready — Verified), (b) conflicting-report rate, (c) moderator burden (facilitator actions per COP update cycle), (d) provenance coverage (% of published line items with complete evidence packs), and (e) readiness distribution (COP Candidates by state). | Pilot | Test | After an exercise or deployment session, a facilitator can retrieve a metrics summary containing all five indicators for a specified time window. |
| FR-METRICS-002 | Metric data shall be exportable in a structured format (JSON or CSV) to support post-exercise evaluation. | Pilot | Test | A facilitator can export metrics for a given time range; exported file parses correctly and contains all fields from FR-METRICS-001. |

---

## 5. Non-Functional Requirements

### 5.1 Privacy and Sensitive Information *(expanded — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-PRIVACY-001 | By default, the system operates in private facilitator views and does not expose analysis outputs (backlog, clusters, COP drafts) to the full workspace. | MVP | Test | No system-generated content appears in public channels unless explicitly published by an authorized facilitator. |
| NFR-PRIVACY-002 | The system shall support configurable redaction rules for sensitive information categories (e.g., personally identifiable information, exact addresses of vulnerable populations) in COP drafts. Facilitators may override redactions with justification. | Pilot | Test | A COP draft containing content matching a configured redaction pattern presents a redaction suggestion; override requires justification and is logged. |
| NFR-PRIVACY-003 | Ingested message data and vector embeddings shall be retained only as long as configured by the workspace administrator. A data-retention policy with configurable TTL shall be enforced. | v1 | Test | After the configured retention period, expired messages and embeddings are purged; a purge log confirms deletion. |

### 5.2 Anti-Abuse *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-ABUSE-001 | The system shall detect and flag potential abuse patterns in facilitator actions (e.g., bulk overrides of risk tiers, publishing high-stakes items without verification in rapid succession) and alert the workspace administrator. | v1 | Test | Simulated rapid-fire high-stakes overrides by a single facilitator trigger an alert to the configured admin; alert includes actor, action count, and time window. |
| NFR-ABUSE-002 | The system shall support temporary suspension of a facilitator's publish permissions by a workspace administrator, with audit logging. | v1 | Test | Admin suspends a facilitator; facilitator cannot publish until reinstated; audit log records suspension and reinstatement. |

### 5.3 Conflict Surfacing *(NEW — v0.4)*

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-CONFLICT-001 | When two or more COP Candidates or signals contain contradictory claims on the same topic, the system shall flag the conflict, link the conflicting items, and prevent the conflicting claims from being published in the Verified section until a facilitator resolves or explicitly acknowledges the conflict. | MVP | Test | Given two signals with contradictory location claims for the same incident, the system flags a conflict; neither can reach Ready — Verified until the facilitator merges, corrects, or marks one as disproven. |

### 5.4 Reliability

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-RELIABILITY-001 | Background ingestion must be resilient to Slack API errors; failed operations must retry with exponential backoff. | MVP | Test | Simulated Slack API failure followed by recovery results in no message loss; retry log shows backoff intervals. |

### 5.5 Transparency

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-TRANSPARENCY-001 | All AI-generated content (cluster suggestions, COP drafts, next-action recommendations) is labeled as draft/suggestion and includes citations to source signals. | MVP | Test | Every AI-generated element in the facilitator UI carries a visible "AI-suggested" or "Draft" label and at least one citation link. |

### 5.6 Usability

| ID | Requirement | Priority | Verification | Acceptance Criteria (summary) |
|---|---|---|---|---|
| NFR-USABILITY-001 | Facilitator workflows should be achievable in one click wherever feasible; avoid forcing data entry under surge conditions. | MVP | Usability review | Promote, publish, and common actions (assign verification, request clarification) are each achievable with a single primary click/tap from the backlog or candidate view. |

---

## 6. Priority Tiers and Sequencing *(NEW — v0.4)*

| Tier | Description | Indicative Scope |
|---|---|---|
| **MVP** | Minimum functionality required for a useful first exercise. Must be complete before the first structured drill with the Aid Arena community. | Ingestion, backlog, promote, readiness computation, COP drafting with citations and status labels, publish with human approval, RBAC, facilitator search, audit log, conflict flagging. |
| **Pilot** | Enhancements validated during early exercises; implemented iteratively based on facilitator feedback. | Risk-tier classification, publish gates for high-stakes, duplicate merge workflow, delta summaries, wording guidance for high-stakes items, metrics/instrumentation, search showing cluster/candidate status, redaction rules, COP versioning. |
| **v1** | Full-featured release for sustained operational use and community adoption. | Two-person rule, data retention policies, anti-abuse detection, exportable metrics, permission suspension. |

MVP is prerequisite to Pilot; Pilot is prerequisite to v1. Specific timelines will be established in the project plan aligned with the funding period.

---

## Appendix A. COP Readiness Checklist (operational)

Use this checklist as the human-readable standard for publishability:

**For any COP line item (minimum):**

- What is the claim, and is it scoped to what we actually know?
- Where is it happening (explicit location, even if approximate)?
- When is it relevant (explicit timestamp/time window + timezone)?
- Who is the source/actor/affected population (as applicable)?
- Do we have citations (Slack permalink(s) and/or external source link)?

**For In-Review publication:**

- Label as IN REVIEW / UNCONFIRMED.
- State uncertainty plainly (what is unknown).
- Include "next verification step" and recheck time if high-stakes.

**For Verified publication:**

- Verification action recorded and evidence attached.
- Conflicts reconciled or explained.

---

## Appendix B. UI Copy and Templates (Slack)

### B1. Readiness badges (short labels)

- ✅ **Ready — Verified**
- 🟨 **Ready — In Review**
- 🟥 **Blocked** (missing details)

### B2. Readiness badge tooltips

- ✅ Ready — Verified: "All required fields present; verification recorded. Safe to include in Verified section."
- 🟨 Ready — In Review: "Minimum fields present. Must be labeled as in-review and separated from verified updates."
- 🟥 Blocked: "Missing a critical detail (e.g., where/when) or unresolved conflict. Not publishable yet."

### B3. Recommended action phrasing

- Best next action: Request clarification
- Best next action: Assign verification
- Best next action: Merge duplicate
- Best next action: Resolve conflict
- Best next action: Publish as In Review

### B4. Clarification templates (for facilitators to post)

**Template 1 — location/time clarification (reply in thread):**

> "Thanks — to include this in the COP, can you confirm: (1) the exact location (city/county/landmark), and (2) the time/date + timezone? If you have a source link or official confirmation, please share it here."

**Template 2 — source request (DM or thread):**

> "Quick check: is this first-hand, second-hand, or from an external source? If external, can you share the link or the name of the originating org?"

**Template 3 — conflict resolution:**

> "We're seeing two different values reported (A vs B). Do you know which is current, or can you share where your value came from?"

### B5. COP publishing header copy (suggested)

> **Common Operating Picture (COP) — {DATE/TIME TZ}**
>
> Verified updates are confirmed by evidence noted below. In-review items are unconfirmed and may change.

---

## Changelog

| Version | Date | Summary of Changes |
|---|---|---|
| v0.3 | 2026-02-15 | Initial ambient mode readiness + COP gating + UI copy appendix. |
| v0.4 | 2026-02-15 | Added §2 definitions: Provenance, Signal, Cluster. Added §3 constraint re: no structured intake forms. **New FR sections:** §4.1 Role Assignment/RBAC (FR-ROLE-001–003), §4.4 Facilitator Search (FR-SEARCH-001–002), §4.6 COP Wording Guidance (FR-COP-WORDING-001–002), §4.8 Metrics/Instrumentation (FR-METRICS-001–002). **New/expanded NFRs:** NFR-PRIVACY-002–003, NFR-ABUSE-001–002, NFR-CONFLICT-001. Expanded FR-AUD-001 to include role changes. Added §6 Priority Tiers and Sequencing. |
