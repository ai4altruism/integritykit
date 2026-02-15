# Aid Arena Integrity Kit

## Capability Description Document (CDD) — Ambient / Facilitator-Centric Mode (v0.4)

| Field | Value |
|---|---|
| **Version** | 0.4 (Proposal-aligned; role clarification; quality-target traceability; metrics & search capabilities) |
| **Date** | 2026-02-15 |
| **Scope** | Ambient / facilitator-centric operation. Most participants do not interact with the app; facilitators use private tooling to produce accurate, complete COP updates. |
| **Design intent** | AI scaffolding for information fidelity and COP drafting; humans remain accountable for verification decisions and published updates. |
| **Preceding version** | v0.3 — see changelog at end of document. |

---

## 1. Purpose

Aid Arena's Integrity Kit is an open-source coordination layer (initially for Slack) that helps communities turn fast-moving crisis messages into structured, provenance-backed situational awareness — primarily in the background. Rather than requiring broad participants to file new forms, the system continuously clusters related threads, reduces duplication, surfaces potential conflicts, and assembles citation-linked evidence packs. A small set of facilitators/moderators uses a lightweight review workflow to promote COP-relevant items, record verification actions, and make verification status explicit (in-review, verified, disproven), so communities can distinguish corroborated updates from unconfirmed claims. The kit then produces citation-backed "common operating picture" (COP) updates that moderators can edit, approve, and publish back into Slack — preserving human agency and accountability while increasing speed and clarity.

The central product output is **accurate and complete COP updates** that clearly separate verified information from in-review items, include provenance (i.e., traceable citation links to source messages and external references), and surface gaps/conflicts so facilitators can act quickly under surge conditions.

---

## 2. Ambient Mode Operating Concept

### 2.1 Primary users and responsibilities

**General participants (default)**

- Post and coordinate in Slack normally (messages, threads, shared links).
- No mandatory forms, slash commands, or bot conversations.

**Facilitators / moderators (small core)**

- Review a private COP backlog and promote a small number of items into COP Candidates.
- Resolve duplicates, assign verification, request clarifications when needed.
- Approve and publish COP updates back into Slack.
- May also perform verification actions (see Verifier responsibilities below).

**Verifiers (may be a distinct role or overlap with facilitators)**

- Perform verification actions appropriate to risk and urgency (e.g., confirm with authoritative sources).
- Record evidence and set status (in-review, verified, disproven).

> **Role clarification (v0.4):** In small deployments, the facilitator and verifier roles will typically overlap — the same person reviews the backlog and performs verification. The system must support this overlap but also allow organizations to separate the roles when staffing permits, so that the person who verifies a claim is not the same person who publishes it. Role assignment is managed through the system's RBAC configuration (see SRS FR-ROLE requirements).

**System (Integrity Kit)**

- Ingest and index Slack content; cluster related threads; detect duplicates and conflicts.
- Draft COP Candidates and COP updates with citations and explicit status labels.
- Compute COP readiness and recommend the next best action to improve publishability.
- Enforce permissions, approval gates, and audit logging.
- Provide a searchable index of ingested signals and clusters for facilitator use.

### 2.2 Core objects and terminology

- **Signal:** Any Slack message/thread/link that may be relevant to situational awareness.
- **Cluster:** A system-created grouping of related signals (topic/incident/thread bundle).
- **COP Candidate:** A facilitator-tracked item intended to become a line in a COP update (may be in-review).
- **COP Line Item:** A publishable statement with who/what/when/where (and operational relevance) plus evidence links.
- **COP Update:** A versioned post (or set of posts) published back into Slack, assembled from COP Line Items.
- **Provenance:** The traceable chain linking a published COP statement back to its underlying evidence — Slack permalinks, external source URLs, verification actions, and the identities of actors who promoted, verified, and approved the item. "Provenance-backed" means a reader can follow citations from any COP line item to the original source material.
- **Evidence pack:** The collected set of provenance artifacts (Slack permalinks, external links, verification records) supporting a single COP Candidate.

---

## 3. COP Readiness Framework

The system evaluates each COP Candidate against a publishability checklist. The goal is to ask humans for attention only when it improves COP accuracy.

### 3.1 Minimum fields for COP Line Items

- **What:** A scoped claim or situation statement.
- **Where:** A location at the best available granularity (may be approximate, but must be explicit).
- **When:** Timestamp or time window with timezone (may be approximate, but must be explicit).
- **Who (as applicable):** Source/actor/affected population (e.g., "county DOT," "shelter staff," "residents in X").
- **So what / operational relevance:** Why it matters (impact, need, offer, constraint).
- **Evidence pack:** Links back to Slack permalinks and/or external sources; must be sufficient for a reviewer to audit the claim.

### 3.2 Readiness states

| State | Minimum Criteria (summary) | Allowed COP Placement | Human Action |
|---|---|---|---|
| **Ready — Verified** | All minimum fields present. Evidence includes an authoritative confirmation or equivalent verification steps logged. Conflicts resolved. | Verified section (default). | Facilitator reviews wording, then publishes. |
| **Ready — In Review** | Minimum fields present enough to avoid misleading readers. Evidence pack exists (at least Slack permalink(s)). Item clearly labeled as in-review with uncertainty/caveats. No unresolved high-risk conflicts. | In-Review section only (must be clearly separated from verified). | Facilitator may publish with caveats OR request/assign verification. |
| **Blocked** | Missing critical field(s) that would cause the statement to be ambiguous or unsafe (e.g., unknown location/time). OR unresolved conflict on a key fact. OR high-risk item lacking required verification. | Not publishable until unblocked. | Facilitator requests clarification, assigns verification, merges duplicates, or defers. |

### 3.3 Risk-based gates

The system applies stricter readiness thresholds for high-stakes claims that could cause harm if wrong.

**High-stakes categories (examples)**

- Evacuation orders, shelter openings/closures, road closures, safety hazards, medical guidance, death/injury counts.
- Accusations of wrongdoing or sensitive attribution.
- Fundraising or donation instructions (fraud risk).

**High-stakes publish rules (default)**

- Verified status required unless a designated facilitator explicitly overrides with a written rationale and "UNCONFIRMED" labeling.
- Second-approver check for overrides (two-person rule) when feasible.
- Any high-stakes in-review item must include the best next verification step and a time-to-recheck.

**Moderator override**

- Risk tier and gating decisions can be overridden by facilitators with justification; all overrides are logged.

---

## 4. Facilitator-Centric High-Level Workflow (Ambient Mode)

### 4.1 Background processing (system)

- Continuously ingest monitored Slack channels and maintain a **searchable index** (messages, threads, links).
- Cluster related signals into topics/incidents; suggest duplicates and conflicts.
- Maintain a private COP backlog prioritized by urgency/impact/risk signals.
- Draft COP Candidate suggestions with evidence packs and readiness classification.

### 4.2 Facilitator loop (human)

- Scan the private COP backlog (Slack App Home and/or mod-only digest).
- **Search** the signal index to locate related messages, threads, or prior COP items when investigating a candidate.
- Promote a small number of items to COP Candidates (one click).
- For each COP Candidate, choose one action: Publish as In-Review (if allowed) · Assign verification · Request clarification · Merge duplicate · Defer/ignore.
- Review system-generated COP update draft (grouped by Verified vs In-Review vs Disproven/Rumor Control).
- Edit for clarity and safety, then approve and publish to configured Slack channels.

### 4.3 COP wording assistance

When generating draft COP line items, the system applies the wording guidance in Appendix A:

- For verified items: uses direct, factual phrasing.
- For in-review items: suggests hedged phrasing (e.g., "Reports indicate…," "Unconfirmed: …," "Seeking confirmation of…").
- Facilitators may edit all system-suggested wording before publishing.

---

## 5. COP Output Quality Targets

Each quality target below is traceable to one or more SRS requirements (cross-references noted).

| # | Quality Target | SRS Traceability |
|---|---|---|
| QT-1 | Clear separation of Verified vs In-Review content. | FR-COPDRAFT-002 |
| QT-2 | Every COP line item includes citations (Slack permalinks and/or external sources). | FR-COPDRAFT-001 |
| QT-3 | Uncertainty is explicit (no implied certainty). | FR-COPDRAFT-001, FR-COP-WORDING-001 |
| QT-4 | Conflicts are either resolved or clearly called out (with plan to resolve). | NFR-CONFLICT-001 |
| QT-5 | Sensitive information is redacted or restricted per policy. | NFR-PRIVACY-001 |
| QT-6 | COP update includes "What changed since last update" and "Top open questions/gaps." | FR-COPDRAFT-003 |

---

## 6. Operational Metrics

To support measurement of coordination effectiveness (as described in the project proposal), the system shall collect the following operational indicators. These are primarily for facilitator and project-team use during exercises and deployments.

| Metric | Description | SRS Traceability |
|---|---|---|
| Time-to-validated-update | Elapsed time from first signal in a cluster to COP line item reaching Ready — Verified. | FR-METRICS-001 |
| Conflicting-report rate | Percentage of COP Candidates with at least one unresolved conflict at time of first review. | FR-METRICS-001 |
| Moderator burden | Number of facilitator actions (promote, verify, clarify, merge, publish) per COP update cycle. | FR-METRICS-001 |
| Provenance coverage | Percentage of published COP line items with a complete evidence pack. | FR-METRICS-001 |
| Readiness distribution | Count of COP Candidates by readiness state at any point in time. | FR-METRICS-001 |

---

## 7. Relationship to Existing Infrastructure (Chat-Diver)

The Integrity Kit builds on the foundation established by the Chat-Diver application. The following capabilities carry forward with adaptation:

| Chat-Diver Capability | Integrity Kit Reuse | Adaptation Required |
|---|---|---|
| Slack ingestion + MongoDB storage | Signal ingestion pipeline | Extend schema for cluster membership, COP candidate state, and evidence packs. |
| ChromaDB vector embeddings + RAG | Duplicate/conflict detection; facilitator search | Clustering and conflict-detection logic beyond simple similarity search. |
| Content Summarization (map-reduce) | COP draft generation seed | Restructure output to populate structured COP fields (who/what/when/where/so-what). |
| Participant Analysis | Facilitator workload visibility | Adapt metrics to track facilitator/verifier actions, not just message counts. |
| Web Search | External source lookup during verification | Add source-quality signals and integrate results into evidence packs. |
| Security middleware | Foundation for RBAC and access control | Replace rate-limiting-only model with role-based permissions and audit logging. |

**Primary new engineering work:** The stateful workflow engine (backlog → COP Candidate → readiness evaluation → publish gating → versioned COP output) is entirely new and represents the core engineering lift for the Integrity Kit.

---

## 8. Non-Goals (Ambient Mode)

- Requiring all participants to file structured reports or use new forms.
- Automated verification or automated publishing without human approval.
- Replacing facilitator judgment with automated prioritization decisions.

---

## 9. Out-of-Scope Deliverables (referenced in proposal, separate workstreams)

The following items are committed in the project proposal but are not software requirements. They are called out here for completeness and to clarify that they will be developed as companion artifacts alongside the system:

- **Exercise-in-a-Box playbook:** Facilitator guide and exercise design templates for crisis-coordination drills.
- **Public evaluation report:** Methodology and findings from exercises measuring the metrics in §6.
- **Synthetic/redacted example datasets:** For benchmarking and community replication.

---

## Appendix A. COP Wording Guidance (for in-review items)

- Preferred phrasing: "Reports indicate…," "Unconfirmed: …," "Seeking confirmation of…"
- Avoid definitive phrasing unless verified.
- Always include a recheck time or follow-up plan when publishing in-review high-risk items.

The system shall suggest wording consistent with this guidance when drafting COP line items with In-Review status (see SRS FR-COP-WORDING-001).

---

## Changelog

| Version | Date | Summary of Changes |
|---|---|---|
| v0.3 | 2026-02-15 | Initial ambient mode readiness + COP gating. |
| v0.4 | 2026-02-15 | Aligned §1 Purpose with proposal wording. Added Provenance definition (§2.2). Clarified Verifier role and RBAC intent (§2.1). Added searchable index to system responsibilities and facilitator workflow (§4.1, §4.2). Added COP wording assistance section (§4.3). Made quality targets traceable to SRS (§5). Added operational metrics section (§6). Added Chat-Diver relationship section (§7). Added out-of-scope deliverables section (§9). Appendix A now cross-references SRS FR-COP-WORDING-001. |
