# Aid Arena Integrity Kit

## Software Development Plan (SDP) — Ambient / Facilitator-Centric Mode (v0.4)

| Field | Value |
|---|---|
| **Version** | 0.4 |
| **Date** | 2026-02-15 |
| **Sprint Duration** | 2 weeks |
| **Source Documents** | CDD v0.4, SRS v0.4, Chat-Diver README |
| **Primary Stack** | Python / FastAPI / MongoDB / ChromaDB / OpenAI / Slack (Block Kit) |

---

## 1. Project Overview

### 1.1 Project Summary

The Aid Arena Integrity Kit is an open-source coordination layer for Slack that helps crisis-response communities produce provenance-backed Common Operating Picture (COP) updates. The system operates primarily in the background — ingesting, clustering, and drafting — while facilitators use private tooling to manage a COP pipeline and publish human-approved updates.

The project extends the existing Chat-Diver codebase (Slack ingestion, MongoDB, ChromaDB, FastAPI, OpenAI integrations) with a stateful workflow engine, role-based access control, COP readiness logic, and facilitator-facing views delivered through Slack App Home and a lightweight metrics dashboard.

### 1.2 Success Criteria

- All MVP requirements (SRS §6) operational and tested in at least one structured exercise.
- Facilitators can move items from backlog → COP Candidate → published COP update within Slack.
- COP updates include provenance (citations), status labels, and clear Verified / In-Review separation.
- Operational metrics (SRS FR-METRICS-001) collected and exportable after exercises.
- Open-source repository with documentation sufficient for community adoption.

### 1.3 Timeline Overview

| Phase | Duration | Sprint | Priority Tier |
|---|---|---|---|
| Sprint 0: Design & Foundation | 1 week | — | Setup |
| Sprint 1: Signal Pipeline & Storage | 2 weeks | S1 | MVP |
| Sprint 2: RBAC & Facilitator Backlog | 2 weeks | S2 | MVP |
| Sprint 3: COP Readiness & Drafting | 2 weeks | S3 | MVP |
| Sprint 4: Publish Workflow & Audit | 2 weeks | S4 | MVP |
| Sprint 5: Risk Gates & Deduplication | 2 weeks | S5 | Pilot |
| Sprint 6: Metrics & Exercise Prep | 2 weeks | S6 | Pilot |
| Sprint 7: Hardening & Release | 2 weeks | S7 | v1 / Release |

**Total: ~15 weeks** (1 setup + 7 × 2-week sprints)

---

## 2. Team and Resources

### 2.1 Agent Assignments

Each sprint assigns tasks to the specialized subagent best equipped for the work. The table below maps agents to their Integrity Kit responsibilities.

| Agent | Primary Integrity Kit Responsibilities | Key Skills Referenced |
|---|---|---|
| **app-planner** | Sprint planning, dependency sequencing, scope adjustments | — |
| **api-designer** | OpenAPI specs for internal facilitator API and Slack interactions | `openapi-templates`, `api-error-handling`, `git-workflow` |
| **database-architect** | MongoDB schema design for signals, clusters, COP candidates, audit log | `git-workflow` |
| **python-backend** | Core application logic: ingestion extensions, clustering, readiness engine, COP drafting, publish workflow, RBAC, search, metrics | `fastapi-patterns`, `api-error-handling`, `authentication-patterns`, `git-workflow` |
| **llm-ops-engineer** | LLM integration: query classification for clustering, COP draft generation, conflict detection, wording guidance, prompt caching | `llm-prompt-patterns`, `git-workflow` |
| **test-engineer** | Unit and integration tests for every sprint's deliverables | `git-workflow` |
| **e2e-test-engineer** | End-to-end Slack interaction tests, facilitator workflow smoke tests | `playwright-patterns`, `github-actions`, `git-workflow` |
| **deploy-engineer** | Docker configuration, CI pipeline, production deployment | `docker-deployment`, `github-actions`, `authentication-patterns`, `git-workflow` |
| **performance-engineer** | Profiling ingestion at scale, LLM call optimization, surge-load testing | — |
| **data-viz-builder** | Metrics dashboard (readiness distribution, time-to-validated-update charts) | — |
| **technical-writer** | README, facilitator guide, Exercise-in-a-Box playbook, evaluation framework | — |

**Agents not used** (and rationale):

| Agent | Reason Not Used |
|---|---|
| `nextjs-ui-builder` | Primary UI is Slack App Home (Block Kit), not a Next.js site. |
| `react-spa-builder` | Metrics dashboard is lightweight; `data-viz-builder` covers it. If scope grows, this agent can be added. |
| `nodejs-backend` | Backend is Python/FastAPI (consistent with Chat-Diver). |

### 2.2 Tools and Infrastructure

| Category | Tool | Purpose |
|---|---|---|
| Version Control | Git / GitHub | Code repository |
| CI | GitHub Actions | Automated testing and image builds (no auto-deploy) |
| Project Management | GitHub Issues + Milestones | Task tracking per sprint |
| Container Runtime | Docker (individual Dockerfiles, no docker-compose in prod) | Deployment |
| Transfer/Deploy | scp + docker run | Production deployment per `docker-deployment` skill |
| Primary Database | MongoDB | Document store for signals, clusters, COP candidates, audit log |
| Vector Store | ChromaDB | Embeddings for similarity/clustering |
| LLM Provider | OpenAI API | Classification, draft generation, conflict detection |
| Messaging Platform | Slack (Block Kit, App Home, Events API) | User-facing interface |

---

## 3. Git Workflow

Per the `git-workflow` skill, all agents follow this protocol:

### 3.1 Branching Strategy

```
main (production)
  └── develop (integration)
        ├── feature/FR-ROLE-001-rbac-model
        ├── feature/FR-BACKLOG-001-private-backlog
        ├── fix/clustering-duplicate-threshold
        └── docs/facilitator-guide-draft
```

### 3.2 Branch Naming Convention

| Type | Pattern | Example |
|---|---|---|
| Feature | `feature/FR-X.X-short-description` | `feature/FR-ROLE-001-rbac-model` |
| Bug Fix | `fix/issue-number-description` | `fix/42-cluster-merge-error` |
| Documentation | `docs/short-description` | `docs/facilitator-guide` |
| Release | `release/vX.Y.Z` | `release/v0.4.0-mvp` |

### 3.3 Commit Convention

```
type(scope): description

Implements: FR-X.X
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `perf`

### 3.4 PR Process

1. Agent creates feature branch from `develop`.
2. Agent implements changes with tests.
3. Agent pushes branch and creates PR.
4. Agent notifies: "PR is ready for review. Please merge when ready."
5. **Human merges PR on GitHub.**
6. Agent pulls latest `develop` and continues.

---

## 4. Testing Strategy

### 4.1 Testing Levels

| Level | Scope | Target | Agent | When |
|---|---|---|---|---|
| Unit | Services, models, utilities | 80% branch coverage on business logic | `test-engineer` | Every PR |
| Integration | API endpoints, MongoDB operations, Slack event handlers | Key workflows | `test-engineer` | Every PR |
| LLM Output | Clustering quality, COP draft structure, wording compliance | Golden-set evaluation | `llm-ops-engineer` + `test-engineer` | Sprint 3+, pre-exercise |
| E2E | Facilitator workflows via Slack (promote → publish cycle) | Critical paths | `e2e-test-engineer` | Sprint 5+, pre-release |
| Load/Surge | Ingestion throughput under simulated surge | Target TBD from exercises | `performance-engineer` | Sprint 7 |

### 4.2 Definition of Done (per story)

- [ ] Code complete and follows project standards.
- [ ] Unit tests written and passing.
- [ ] Integration tests for API/DB boundaries.
- [ ] No critical or high-severity bugs open.
- [ ] Documentation updated (docstrings, README section if user-facing).
- [ ] PR reviewed and merged to `develop`.

---

## 5. Sprint Plans

### Sprint 0: Design & Foundation (1 week)

**Goal:** Establish API contracts, database schema, project structure, and CI pipeline so that implementation sprints can begin with clear interfaces.

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S0-1 | Fork/branch Chat-Diver repo; establish `develop` branch and branch protection rules | S | — | None | — |
| S0-2 | Design MongoDB schema: `signals`, `clusters`, `cop_candidates`, `cop_updates`, `audit_log`, `roles` collections | L | `database-architect` | S0-1 | FR-AUD-001, FR-ROLE-001 |
| S0-3 | Design internal facilitator API (OpenAPI 3.1 spec): backlog, candidate CRUD, publish, search, metrics endpoints | L | `api-designer` | S0-2 | FR-BACKLOG-001, FR-SEARCH-001, FR-COP-PUB-001, FR-METRICS-001 |
| S0-4 | Design LLM prompt templates: clustering, COP draft generation, readiness evaluation, conflict detection | M | `llm-ops-engineer` | None | FR-COP-READ-001, FR-COPDRAFT-001, NFR-CONFLICT-001 |
| S0-5 | Set up GitHub Actions CI: lint, type-check, pytest on PR | M | `deploy-engineer` | S0-1 | — |
| S0-6 | Create Dockerfile for Integrity Kit (extending Chat-Diver) | M | `deploy-engineer` | S0-1 | — |
| S0-7 | Set up pytest infrastructure: conftest, fixtures, factories for new collections | M | `test-engineer` | S0-2 | — |
| S0-8 | Write project README and architecture overview | M | `technical-writer` | S0-2, S0-3 | — |

**Effort Key:** S = 2–4h, M = 4–8h, L = 8–16h, XL = 16–32h

**Deliverables:**
- MongoDB schema document (reviewed, committed)
- OpenAPI 3.1 spec for facilitator API
- LLM prompt template library (initial)
- Working CI pipeline (lint + test on PR)
- Dockerfile and deployment notes
- Test infrastructure ready
- Architecture README

---

### Sprint 1: Signal Pipeline & Storage (2 weeks)

**Goal:** Extend Chat-Diver's ingestion to produce Signals, build the clustering engine, and detect duplicates/conflicts — the foundation for everything downstream.

**Requirements Addressed:** NFR-RELIABILITY-001, NFR-TRANSPARENCY-001, NFR-CONFLICT-001 (foundation)

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S1-1 | Extend Slack event handlers to write ingested messages as Signal documents (with cluster-membership field, source metadata) | L | `python-backend` | S0-2 | — |
| S1-2 | Build clustering service: group related signals by topic/incident using ChromaDB embeddings + LLM-assisted classification | XL | `python-backend` + `llm-ops-engineer` | S1-1, S0-4 | — |
| S1-3 | Implement duplicate detection within clusters (similarity threshold + LLM confirmation) | L | `python-backend` + `llm-ops-engineer` | S1-2 | — |
| S1-4 | Implement conflict detection: flag contradictory claims within a cluster | L | `python-backend` + `llm-ops-engineer` | S1-2 | NFR-CONFLICT-001 |
| S1-5 | Add retry-with-backoff for Slack API ingestion errors | M | `python-backend` | S1-1 | NFR-RELIABILITY-001 |
| S1-6 | Label all AI outputs (cluster suggestions, duplicate flags) as system-generated | S | `python-backend` | S1-2 | NFR-TRANSPARENCY-001 |
| S1-7 | Write unit tests for signal creation, clustering, duplicate and conflict detection | L | `test-engineer` | S1-1 through S1-4 | — |
| S1-8 | Write integration tests for ingestion → MongoDB → ChromaDB pipeline | M | `test-engineer` | S1-1, S1-2 | — |

**Deliverables:**
- Signals ingested and stored with cluster membership
- Clustering engine operational (topic/incident grouping)
- Duplicate and conflict flags surfaced per cluster
- Test coverage report

---

### Sprint 2: RBAC & Facilitator Backlog (2 weeks)

**Goal:** Implement role-based access control and the private facilitator backlog — enabling the core human-in-the-loop workflow.

**Requirements Addressed:** FR-ROLE-001, FR-ROLE-002, FR-ROLE-003, FR-BACKLOG-001, FR-BACKLOG-002, FR-SEARCH-001, NFR-PRIVACY-001

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S2-1 | Implement RBAC model: General Participant / Facilitator / Verifier roles with assignment and enforcement | L | `python-backend` | S0-2 | FR-ROLE-001, FR-ROLE-002 |
| S2-2 | Add role-change audit logging | M | `python-backend` | S2-1 | FR-ROLE-003, FR-AUD-001 |
| S2-3 | Build private COP backlog service: list clusters prioritized by urgency/impact/risk, accessible only to Facilitator role | L | `python-backend` | S1-2, S2-1 | FR-BACKLOG-001 |
| S2-4 | Implement one-click "Promote to COP Candidate" action (API + Slack message action) | M | `python-backend` | S2-3 | FR-BACKLOG-002 |
| S2-5 | Build facilitator search endpoint: keyword + time range + channel, role-gated | L | `python-backend` | S1-1, S2-1 | FR-SEARCH-001 |
| S2-6 | Build Slack App Home view for facilitators: backlog list, search entry, role indicator | L | `python-backend` | S2-3, S2-5 | NFR-PRIVACY-001 |
| S2-7 | Verify that non-facilitators cannot access backlog or search (access-denied tests) | M | `test-engineer` | S2-1, S2-3 | FR-ROLE-002 |
| S2-8 | Unit and integration tests for RBAC, backlog, promote, search | L | `test-engineer` | S2-1 through S2-5 | — |

**Deliverables:**
- Three-role RBAC system with audit logging
- Private backlog visible in Slack App Home (facilitators only)
- Promote-to-candidate action working
- Facilitator search operational
- Access control tests passing

---

### Sprint 3: COP Readiness & Drafting (2 weeks)

**Goal:** Implement the COP readiness engine (the system's core value proposition) and draft generation with provenance and wording guidance.

**Requirements Addressed:** FR-COP-READ-001, FR-COP-READ-002, FR-COP-READ-003, FR-COPDRAFT-001, FR-COPDRAFT-002, FR-COP-WORDING-001, NFR-CONFLICT-001

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S3-1 | Implement readiness computation: evaluate each COP Candidate against minimum fields (who/what/when/where/so-what/evidence) and produce Ready–Verified / Ready–In Review / Blocked | XL | `python-backend` + `llm-ops-engineer` | S2-4, S0-4 | FR-COP-READ-001 |
| S3-2 | Build missing/weak fields checklist UI (Slack Block Kit) showing which fields block publishability | L | `python-backend` | S3-1 | FR-COP-READ-002 |
| S3-3 | Implement "best next action" recommender (request clarification / assign verification / merge duplicate / resolve conflict) | L | `python-backend` + `llm-ops-engineer` | S3-1 | FR-COP-READ-003 |
| S3-4 | Build COP draft generator: produce line items with status labels (Verified / In Review / Disproven) and evidence-pack citations | XL | `python-backend` + `llm-ops-engineer` | S3-1 | FR-COPDRAFT-001 |
| S3-5 | Assemble COP update draft grouped by section: Verified, In-Review, Disproven/Rumor Control, Open Questions/Gaps | L | `python-backend` | S3-4 | FR-COPDRAFT-002 |
| S3-6 | Implement wording guidance: hedged phrasing for In-Review items, direct phrasing for Verified | M | `llm-ops-engineer` | S3-4, S0-4 | FR-COP-WORDING-001 |
| S3-7 | Enforce conflict-blocks: prevent contradictory claims from reaching Ready–Verified until facilitator resolves | M | `python-backend` | S1-4, S3-1 | NFR-CONFLICT-001 |
| S3-8 | Unit tests for readiness computation (all three states), draft generation, wording compliance | L | `test-engineer` | S3-1 through S3-7 | — |
| S3-9 | Integration tests: candidate lifecycle from promotion through draft generation | M | `test-engineer` | S3-5 | — |

**Deliverables:**
- Readiness engine computing three states with field-level diagnostics
- Next-action recommender operational
- COP draft generator producing sectioned, cited, status-labeled output
- Wording guidance applied automatically to In-Review items
- Conflict-blocking logic enforced
- Test coverage report

---

### Sprint 4: Publish Workflow & Audit (2 weeks)

**Goal:** Complete the MVP loop — facilitators can review, edit, and publish COP updates into Slack with full audit trail.

**Requirements Addressed:** FR-COP-PUB-001, FR-AUD-001, NFR-USABILITY-001, NFR-TRANSPARENCY-001

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S4-1 | Build publish workflow: facilitator reviews COP draft in App Home → edits → approves → system posts to configured Slack channel | XL | `python-backend` | S3-5 | FR-COP-PUB-001 |
| S4-2 | Format published COP update using Slack Block Kit (readiness badges, section headers per SRS Appendix B) | L | `python-backend` | S4-1 | — |
| S4-3 | Implement audit log: record all COP Candidate status changes, promotions, publishes, role changes with actor/timestamp/before-after | L | `python-backend` | S2-2, S4-1 | FR-AUD-001 |
| S4-4 | Add clarification request templates (SRS Appendix B4): facilitator can send templated thread replies or DMs to request info | M | `python-backend` | S4-1 | — |
| S4-5 | Verify no automated publishing occurs without human approval action | M | `test-engineer` | S4-1 | FR-COP-PUB-001 |
| S4-6 | End-to-end integration test: ingest signals → cluster → promote → compute readiness → draft → publish → verify audit log | L | `test-engineer` | S4-1, S4-3 | — |
| S4-7 | Update README and add facilitator quick-start guide | M | `technical-writer` | S4-1 | — |

**Sprint 4 Exit = MVP Complete.** At this point, the system supports the full ambient-mode facilitator loop described in CDD §4.

**Deliverables:**
- Complete publish workflow (review → edit → approve → post to Slack)
- COP updates formatted with Block Kit (badges, sections, citations)
- Audit log capturing full action history
- Clarification templates available
- MVP end-to-end test passing
- Facilitator quick-start documentation

---

### Sprint 5: Risk Gates & Deduplication (2 weeks)

**Goal:** Add Pilot-tier features that improve safety for high-stakes content and reduce facilitator workload through deduplication.

**Requirements Addressed:** FR-COP-RISK-001, FR-COP-GATE-001, FR-BACKLOG-003, FR-COPDRAFT-003, FR-COP-WORDING-002

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S5-1 | Implement risk-tier classification: Routine / Elevated / High-stakes based on content signals (evacuation, shelter, hazard, medical, donation keywords) with facilitator override + audit | L | `python-backend` + `llm-ops-engineer` | S3-1 | FR-COP-RISK-001 |
| S5-2 | Enforce publish gates for High-stakes: require Verified status or explicit override with rationale + UNCONFIRMED label | L | `python-backend` | S5-1, S4-1 | FR-COP-GATE-001 |
| S5-3 | Build duplicate merge workflow: system suggests duplicates, facilitator merges and selects canonical evidence set | L | `python-backend` | S1-3, S2-4 | FR-BACKLOG-003 |
| S5-4 | Implement "What changed since last COP" delta summary generation | M | `python-backend` + `llm-ops-engineer` | S4-1 | FR-COPDRAFT-003 |
| S5-5 | Add recheck-time and next-verification-step to high-stakes In-Review draft wording | M | `llm-ops-engineer` | S5-1, S3-6 | FR-COP-WORDING-002 |
| S5-6 | Unit tests for risk classification, gate enforcement, merge workflow, delta summaries | L | `test-engineer` | S5-1 through S5-5 | — |
| S5-7 | LLM output quality evaluation: golden-set tests for clustering accuracy, draft structure, wording compliance | L | `llm-ops-engineer` + `test-engineer` | S3-4, S5-1 | — |

**Deliverables:**
- Risk-tier classification with override + audit
- High-stakes publish gates enforced
- Duplicate merge workflow operational
- Delta summaries generated between COP versions
- High-stakes wording guidance (recheck time, next step)
- LLM quality evaluation baseline established

---

### Sprint 6: Metrics, Search Enhancements & Exercise Prep (2 weeks)

**Goal:** Instrument the system for measurement, enhance search, add redaction, and prepare for the first structured exercise.

**Requirements Addressed:** FR-METRICS-001, FR-METRICS-002, FR-SEARCH-002, NFR-PRIVACY-002

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S6-1 | Implement operational metrics collection: time-to-validated-update, conflicting-report rate, moderator burden, provenance coverage, readiness distribution | L | `python-backend` | S4-3 | FR-METRICS-001 |
| S6-2 | Build metrics API endpoint and JSON/CSV export | M | `python-backend` | S6-1 | FR-METRICS-002 |
| S6-3 | Build metrics dashboard: readiness distribution chart, time-to-validated-update trend, moderator action counts | L | `data-viz-builder` | S6-2 | FR-METRICS-001 |
| S6-4 | Enhance search results to show cluster membership and COP Candidate status | M | `python-backend` | S2-5, S3-1 | FR-SEARCH-002 |
| S6-5 | Implement configurable redaction rules for sensitive info in COP drafts with facilitator override | L | `python-backend` | S3-4 | NFR-PRIVACY-002 |
| S6-6 | Optimize LLM calls: implement prompt caching for system prompts and clustering templates | M | `llm-ops-engineer` | S1-2, S3-4 | — |
| S6-7 | Write Exercise-in-a-Box facilitator guide (draft) | L | `technical-writer` | S4-7 | — |
| S6-8 | Integration tests for metrics collection across a full COP lifecycle | M | `test-engineer` | S6-1 | — |
| S6-9 | Write evaluation framework document (metrics definitions, measurement methodology) | M | `technical-writer` | S6-1 | — |

**Deliverables:**
- Five operational metrics collected and exportable
- Metrics dashboard with visualizations
- Search showing cluster/candidate context
- Redaction rules configurable and overridable
- LLM prompt caching implemented
- Exercise-in-a-Box guide (draft)
- Evaluation framework document

---

### Sprint 7: Hardening & Release (2 weeks)

**Goal:** Add v1 features, harden security and performance, complete documentation, and prepare for production release and first exercise.

**Requirements Addressed:** FR-COP-GATE-002, FR-AUD-002, NFR-ABUSE-001, NFR-ABUSE-002, NFR-PRIVACY-003

| Task ID | Task | Effort | Agent | Dependencies | Req |
|---|---|---|---|---|---|
| S7-1 | Implement optional two-person rule for high-stakes overrides | L | `python-backend` | S5-2 | FR-COP-GATE-002 |
| S7-2 | Implement COP update versioning: store each published COP as a versioned artifact with supporting candidates and evidence packs | L | `python-backend` | S4-1 | FR-AUD-002 |
| S7-3 | Implement anti-abuse detection: flag rapid-fire overrides, alert admin | M | `python-backend` | S4-3 | NFR-ABUSE-001 |
| S7-4 | Implement facilitator permission suspension by admin | M | `python-backend` | S2-1 | NFR-ABUSE-002 |
| S7-5 | Implement data-retention TTL and purge mechanism | M | `python-backend` | S1-1 | NFR-PRIVACY-003 |
| S7-6 | E2E test suite: facilitator workflow from backlog scan through publish, including risk gates and two-person rule | L | `e2e-test-engineer` | S7-1 | — |
| S7-7 | Surge-load testing: simulate high-volume ingestion during crisis event | L | `performance-engineer` | S1-1, S1-2 | — |
| S7-8 | Security review: RBAC enforcement, audit log integrity, Slack signing secret validation | M | `deploy-engineer` | All | — |
| S7-9 | Finalize production Dockerfile and deployment runbook | M | `deploy-engineer` | S0-6 | — |
| S7-10 | Finalize all documentation: README, facilitator guide, Exercise-in-a-Box, CONTRIBUTING.md, CHANGELOG | L | `technical-writer` | All | — |
| S7-11 | Create `release/v0.4.0-mvp` branch; tag and prepare release notes | S | — | All | — |

**Deliverables:**
- Two-person rule for high-stakes overrides
- COP versioning with full evidence preservation
- Anti-abuse detection and permission suspension
- Data-retention enforcement
- E2E test suite passing
- Surge-load test results documented
- Security review complete
- Production deployment package
- Complete documentation set
- Tagged release `v0.4.0`

---

## 6. Requirements Traceability Matrix

| Requirement ID | Description | Priority | Sprint | Agent(s) |
|---|---|---|---|---|
| **FR-ROLE-001** | Three configurable roles (Participant, Facilitator, Verifier) | MVP | S2 | `python-backend` |
| **FR-ROLE-002** | Role-based access enforcement | MVP | S2 | `python-backend`, `test-engineer` |
| **FR-ROLE-003** | Role-change audit logging | MVP | S2 | `python-backend` |
| **FR-COP-READ-001** | Compute readiness state (Verified / In Review / Blocked) | MVP | S3 | `python-backend`, `llm-ops-engineer` |
| **FR-COP-READ-002** | Missing/weak fields checklist | MVP | S3 | `python-backend` |
| **FR-COP-READ-003** | Best next action recommender | MVP | S3 | `python-backend`, `llm-ops-engineer` |
| **FR-COP-RISK-001** | Risk-tier classification with override | Pilot | S5 | `python-backend`, `llm-ops-engineer` |
| **FR-COP-GATE-001** | High-stakes publish gates | Pilot | S5 | `python-backend` |
| **FR-COP-GATE-002** | Two-person rule for overrides | v1 | S7 | `python-backend` |
| **FR-BACKLOG-001** | Private COP backlog for facilitators | MVP | S2 | `python-backend` |
| **FR-BACKLOG-002** | One-click promote to COP Candidate | MVP | S2 | `python-backend` |
| **FR-BACKLOG-003** | Duplicate merge workflow | Pilot | S5 | `python-backend` |
| **FR-SEARCH-001** | Searchable signal/cluster/candidate index | MVP | S2 | `python-backend` |
| **FR-SEARCH-002** | Search shows cluster and candidate status | Pilot | S6 | `python-backend` |
| **FR-COPDRAFT-001** | Generate draft COP line items with status + citations | MVP | S3 | `python-backend`, `llm-ops-engineer` |
| **FR-COPDRAFT-002** | Assemble sectioned COP update draft | MVP | S3 | `python-backend` |
| **FR-COPDRAFT-003** | Delta summary ("What changed since last COP") | Pilot | S5 | `python-backend`, `llm-ops-engineer` |
| **FR-COP-PUB-001** | Human approval required for publish | MVP | S4 | `python-backend`, `test-engineer` |
| **FR-COP-WORDING-001** | Hedged phrasing for In-Review items | MVP | S3 | `llm-ops-engineer` |
| **FR-COP-WORDING-002** | Recheck time + next step for high-stakes In-Review | Pilot | S5 | `llm-ops-engineer` |
| **FR-AUD-001** | Immutable audit log | MVP | S4 | `python-backend` |
| **FR-AUD-002** | COP versioning with evidence preservation | Pilot | S7 | `python-backend` |
| **FR-METRICS-001** | Five operational metrics | Pilot | S6 | `python-backend` |
| **FR-METRICS-002** | Metrics export (JSON/CSV) | Pilot | S6 | `python-backend` |
| **NFR-PRIVACY-001** | Private facilitator views by default | MVP | S2 | `python-backend` |
| **NFR-PRIVACY-002** | Configurable redaction rules | Pilot | S6 | `python-backend` |
| **NFR-PRIVACY-003** | Data-retention TTL and purge | v1 | S7 | `python-backend` |
| **NFR-ABUSE-001** | Anti-abuse pattern detection | v1 | S7 | `python-backend` |
| **NFR-ABUSE-002** | Permission suspension by admin | v1 | S7 | `python-backend` |
| **NFR-CONFLICT-001** | Conflict flagging and blocking | MVP | S1 + S3 | `python-backend`, `llm-ops-engineer` |
| **NFR-RELIABILITY-001** | Retry with backoff for ingestion | MVP | S1 | `python-backend` |
| **NFR-TRANSPARENCY-001** | AI outputs labeled as draft/suggestion | MVP | S1 + S4 | `python-backend` |
| **NFR-USABILITY-001** | One-click facilitator actions | MVP | S2 + S4 | `python-backend` |

---

## 7. Risk Management

### 7.1 Identified Risks

| Risk | Probability | Impact | Mitigation | Sprint Affected |
|---|---|---|---|---|
| LLM clustering/draft quality insufficient for COP use | Medium | High | Golden-set evaluation in S5; iterative prompt tuning with `llm-ops-engineer`; human review always required | S1, S3, S5 |
| Surge-volume ingestion overwhelms system during crisis | Medium | High | Chat-Diver's "nice mode" as baseline; `performance-engineer` load testing in S7; circuit breakers from Chat-Diver Phase 3 | S1, S7 |
| Slack Block Kit limitations constrain facilitator UX | Medium | Medium | Prototype App Home views early (S2); fall back to slash commands if needed; lightweight web dashboard in S6 | S2, S4 |
| Scope creep from exercise feedback | High | Medium | Strict change control after MVP; new features go to backlog for next cycle; 10% buffer per sprint | S5–S7 |
| MongoDB schema migrations during active use | Low | High | Design schema for forward compatibility in S0; use additive-only changes | S0 |
| Slack API rate limits during backfill + live ingestion | Medium | Medium | Existing Chat-Diver rate limiting; stagger backfill with `--nice` mode | S1 |
| OpenAI API cost escalation from LLM-heavy pipeline | Medium | Medium | Prompt caching (S6); use cheaper models for classification; `llm-ops-engineer` cost tracking | S3, S6 |

### 7.2 Contingency Planning

- 10% time buffer built into each sprint.
- MVP (Sprints 0–4) is prioritized; Pilot features (S5–S6) can be descoped without blocking the first exercise.
- If LLM quality is insufficient, facilitators can manually edit all fields — the system degrades to a structured template tool rather than a draft generator.
- If Slack App Home proves too limiting, the `react-spa-builder` agent can be brought in to build a standalone facilitator dashboard in a later sprint.

---

## 8. Quality Gates

### 8.1 Sprint Exit Criteria

- [ ] All planned stories complete or explicitly deferred with rationale.
- [ ] Test coverage meets targets (80% branch on new business logic).
- [ ] No critical or high-severity bugs open.
- [ ] Documentation updated for any user-facing changes.
- [ ] Demo of sprint deliverables completed.
- [ ] Retrospective conducted; findings logged.

### 8.2 MVP Release Criteria (end of Sprint 4)

- [ ] Full facilitator loop operational: ingest → cluster → backlog → promote → readiness → draft → edit → publish.
- [ ] RBAC enforced: non-facilitators cannot access backlog or publish.
- [ ] Audit log captures all COP lifecycle actions.
- [ ] End-to-end integration test passing.
- [ ] Facilitator quick-start guide complete.
- [ ] No known data-loss or security issues.

### 8.3 Production Release Criteria (end of Sprint 7)

- [ ] All MVP and Pilot requirements implemented and tested.
- [ ] E2E test suite passing.
- [ ] Surge-load test results within acceptable bounds.
- [ ] Security review completed with no critical findings.
- [ ] All documentation complete (README, facilitator guide, Exercise-in-a-Box, evaluation framework, CONTRIBUTING, CHANGELOG).
- [ ] Release tagged and deployment runbook verified.

---

## Appendix A. Effort Estimation Guide

| Size | Hours | Complexity | Examples |
|---|---|---|---|
| S | 2–4h | Simple, well-understood | Add field, simple endpoint, config change |
| M | 4–8h | Moderate, clear path | New API endpoint with tests, Slack action handler |
| L | 8–16h | Complex, multiple components | Readiness checklist UI, RBAC model, search service |
| XL | 16–32h | Very complex, significant unknowns | Clustering engine, COP draft generator, readiness computation |

### Sprint Capacity Notes

- Assume 6–7 productive hours per day.
- Testing time is included in feature estimates (typically +30–50%).
- Reserve 10% per sprint for unexpected issues.
- First sprint (S1) may be 20–30% less productive due to ramp-up on new architecture.
- LLM-dependent tasks carry higher uncertainty; pair `llm-ops-engineer` with `test-engineer` for quality evaluation.

---

## Appendix B. Agent Coordination Patterns

The following patterns describe how agents collaborate within sprints:

**Pattern 1: Design → Implement → Test**
Used in Sprint 0 and at the start of each feature.
```
api-designer or database-architect  →  python-backend  →  test-engineer
       (contract/schema)                (implementation)      (verification)
```

**Pattern 2: LLM Feature Development**
Used for clustering, drafting, readiness, wording guidance.
```
llm-ops-engineer (prompt design + caching)
        ↕
python-backend (integration + API)
        ↓
test-engineer (unit + golden-set eval)
```

**Pattern 3: Facilitator UX**
Used for Slack App Home views, Block Kit formatting.
```
python-backend (Slack Block Kit views + event handlers)
        ↓
test-engineer (interaction tests)
        ↓
technical-writer (facilitator guide updates)
```

**Pattern 4: Hardening**
Used in Sprint 7.
```
deploy-engineer (Docker, CI, security review)
        ↕
performance-engineer (load testing, profiling)
        ↕
e2e-test-engineer (full workflow tests)
        ↓
technical-writer (runbook, release notes)
```

---

## Appendix C. Skill Usage Map

| Skill | Sprints Used | Agents Using It |
|---|---|---|
| `git-workflow` | All | All agents |
| `fastapi-patterns` | S1–S7 | `python-backend` |
| `api-error-handling` | S0, S2–S7 | `api-designer`, `python-backend` |
| `openapi-templates` | S0 | `api-designer` |
| `llm-prompt-patterns` | S0, S1, S3, S5, S6 | `llm-ops-engineer` |
| `authentication-patterns` | S2 | `python-backend` (RBAC token validation) |
| `docker-deployment` | S0, S7 | `deploy-engineer` |
| `github-actions` | S0, S7 | `deploy-engineer` |
| `playwright-patterns` | S7 | `e2e-test-engineer` |
| `tailwind-patterns` | S6 | `data-viz-builder` (metrics dashboard) |
| `react-query-patterns` | S6 | `data-viz-builder` (dashboard data fetching) |
| `zustand-patterns` | — | Not used (no SPA client state needed) |
| `prisma-schema-patterns` | — | Not used (MongoDB, not Prisma) |
