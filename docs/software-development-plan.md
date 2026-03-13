# Aid Arena Integrity Kit - Software Development Plan

This document consolidates the Software Development Plans for v0.4 and Sprint 8 (v1.0).

---

## Table of Contents

1. [v0.4 Baseline](#v04-baseline)
2. [Sprint 8 - v1.0 Features](#sprint-8---v10-features)

---

# v0.4 Baseline

## Software Development Plan (SDP) — Ambient / Facilitator-Centric Mode (v0.4)

| Field | Value |
|---|---|
| **Version** | 0.4 |
| **Date** | 2026-02-15 |
| **Sprint Duration** | 2 weeks |
| **Source Documents** | CDD v0.4, SRS v0.4, Chat-Diver README |
| **Primary Stack** | Python / FastAPI / MongoDB / ChromaDB / OpenAI / Slack (Block Kit) |

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

## 5. Sprint Plans (v0.4)

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

### Sprint 1-7 Details

For complete details of Sprints 1-7, see the original v0.4 SDP sections.

## 6. Requirements Traceability Matrix (v0.4)

| Requirement ID | Description | Priority | Sprint | Agent(s) |
|---|---|---|---|---|
| **FR-ROLE-001** | Three configurable roles (Participant, Facilitator, Verifier) | MVP | S2 | `python-backend` |
| **FR-ROLE-002** | Role-based access enforcement | MVP | S2 | `python-backend`, `test-engineer` |
| **FR-ROLE-003** | Role-change audit logging | MVP | S2 | `python-backend` |
| **FR-COP-READ-001** | Compute readiness state (Verified / In Review / Blocked) | MVP | S3 | `python-backend`, `llm-ops-engineer` |
| **FR-COP-READ-002** | Missing/weak fields checklist | MVP | S3 | `python-backend` |
| **FR-COP-READ-003** | Best next action recommender | MVP | S3 | `python-backend`, `llm-ops-engineer` |

*[Additional requirements listed in original document]*

---

# Sprint 8 - v1.0 Features

## Software Development Plan (SDP) — Sprint 8: v1.0 Features

| Field | Value |
|---|---|
| **Version** | 1.0 |
| **Date** | 2026-03-10 |
| **Sprint Duration** | 2 weeks |
| **Source Documents** | CDD v0.4, SRS v0.4, README v0.4.0, SDP v0.4 |
| **Primary Stack** | Python / FastAPI / MongoDB / ChromaDB / OpenAI / Slack (Block Kit) |
| **Build On** | v0.4.0 (Hardening & Release) |

## 1. Sprint 8 Overview

### 1.1 Sprint Summary

Sprint 8 represents the first major feature release (v1.0) following the successful v0.4.0 hardening sprint. This sprint focuses on expanding the system's reach and utility through multi-language support, advanced analytics capabilities, and external system integrations. These features enable the Integrity Kit to serve diverse international crisis response communities and integrate into broader emergency management ecosystems.

The v1.0 release transforms the Integrity Kit from a standalone Slack coordination tool into a multi-language, analytically-rich platform capable of exchanging data with external emergency management systems while maintaining its core commitment to human accountability and provenance-backed updates.

### 1.2 Success Criteria

- Multi-language support operational for Spanish and French COP updates with language-aware wording guidance
- Advanced analytics dashboard providing insights beyond basic operational metrics
- External system integrations working with at least one standard emergency management protocol
- Language selection and translation workflows tested with multilingual test data
- External data exchange validated with sample payloads
- All v1.0 features documented with usage examples and configuration guides

### 1.3 Strategic Goals

**Expand International Reach:**
- Enable crisis response in Spanish and French-speaking communities
- Support multilingual workspaces with language-aware processing

**Enhance Decision Support:**
- Provide trend analysis and predictive insights beyond operational metrics
- Support after-action review and continuous improvement

**Enable Ecosystem Integration:**
- Allow data exchange with external emergency management systems
- Support standardized protocols (CAP, EDXL-DE, etc.)

## 2. Sprint 8 Feature Areas

### 2.1 Multi-Language Support (Theme: Internationalization)

**Strategic Value:** Crisis response is global. Many aid communities operate in Spanish and French-speaking regions. Multi-language support enables the Integrity Kit to serve diverse international communities without requiring English proficiency from participants or facilitators.

**Key Capabilities:**
- Automatic language detection for ingested messages
- Spanish and French COP draft generation with culturally appropriate wording
- Language-aware hedged phrasing (verified vs in-review)
- Mixed-language workspace support (multilingual signal processing)
- Translation of system-generated messages and templates

### 2.2 Advanced Analytics & Reporting (Theme: Intelligence & Insights)

**Strategic Value:** Beyond operational metrics (time-to-validated-update, moderator burden), advanced analytics help facilitators and leadership understand patterns, identify bottlenecks, and improve coordination strategies. After-action reports require rich data exports.

**Key Capabilities:**
- Trend analysis: signal volume over time, readiness state transitions
- Topic clustering trends: emerging vs declining topics
- Facilitator workload distribution and action velocity
- Conflict resolution time analysis
- Gap identification: which topics lack verification
- Export: PDF/DOCX after-action reports with charts

### 2.3 External System Integrations (Theme: Interoperability)

**Strategic Value:** Crisis coordinators rarely work in isolation. Integrating with external emergency management systems, public alerting platforms, and geospatial tools allows the Integrity Kit to be part of a broader ecosystem rather than a silo.

**Key Capabilities:**
- **Outbound webhooks:** Notify external systems when COP updates are published
- **CAP export:** Convert verified COP updates to CAP 1.2 format for public alerting
- **EDXL-DE export:** Package COP updates for emergency data exchange
- **Inbound verification source:** Import verified information from authoritative APIs
- **GeoJSON export:** Provide location data for mapping tools (ArcGIS, Mapbox, etc.)
- **Integration health monitoring:** Track webhook success/failure rates

### 2.4 Additional v1.0 Enhancements (Theme: Maturity & Adoption)

Beyond the core feature areas, several enhancements improve system maturity:

**Mobile-Optimized Facilitator Experience:**
- Responsive App Home layout for mobile devices
- Touch-optimized controls for promote/approve actions
- Mobile-friendly search and backlog views

**Advanced Conflict Resolution:**
- Conflict visualization showing contradictory claims side-by-side
- Facilitator workflow to mark one claim as primary and others as disproven
- Conflict resolution templates (merge, escalate, defer)

**Enhanced Provenance Tracking:**
- Visual provenance graph showing signal → cluster → candidate → COP update lineage
- Export provenance chain for external audit
- Provenance verification API for third-party tools

**Onboarding & Training:**
- Interactive facilitator onboarding flow in Slack
- Sandbox mode for training exercises (no real publishing)
- Sample crisis scenarios for facilitator training

## 3. Sprint 8 Task Plan

### Sprint 8: Multi-Language, Analytics & Integrations (2 weeks)

**Goal:** Implement multi-language support (Spanish, French), advanced analytics and reporting capabilities, and external system integrations to expand the Integrity Kit's reach and utility for international crisis response communities and ecosystem interoperability.

| Task ID | Task | Effort | Agent | Dependencies | Feature Area |
|---------|------|--------|-------|--------------|--------------|
| **Multi-Language Support** |
| S8-1 | Design language configuration schema and API | M | `api-designer` | None | Multi-language |
| S8-2 | Implement language detection service | M | `python-backend` + `llm-ops-engineer` | S8-1 | Multi-language |
| S8-3 | Create Spanish and French LLM prompt templates | L | `llm-ops-engineer` | S8-2 | Multi-language |
| S8-4 | Extend COP draft generation to support Spanish and French output | L | `python-backend` + `llm-ops-engineer` | S8-3 | Multi-language |
| S8-5 | Internationalize Slack Block Kit templates | M | `python-backend` | S8-4 | Multi-language |
| S8-6 | Add language selection to facilitator App Home | M | `python-backend` | S8-5 | Multi-language |
| S8-7 | Unit and integration tests for multi-language | L | `test-engineer` | S8-2 through S8-6 | Multi-language |
| **Advanced Analytics & Reporting** |
| S8-8 | Design analytics API | L | `api-designer` | None | Analytics |
| S8-9 | Implement time-series analytics | L | `python-backend` | S8-8 | Analytics |
| S8-10 | Build topic trend detection | L | `python-backend` + `llm-ops-engineer` | S8-9 | Analytics |
| S8-11 | Implement facilitator workload analytics | M | `python-backend` | S8-9 | Analytics |
| S8-12 | Build conflict resolution time analysis | M | `python-backend` | S8-9 | Analytics |
| S8-13 | Create advanced analytics dashboard | XL | `data-viz-builder` | S8-9 through S8-12 | Analytics |
| S8-14 | Implement after-action report export | L | `python-backend` + `technical-writer` | S8-13 | Analytics |
| S8-15 | Unit and integration tests for analytics | L | `test-engineer` | S8-9 through S8-14 | Analytics |
| **External System Integrations** |
| S8-16 | Design integration architecture | L | `api-designer` | None | Integrations |
| S8-17 | Implement outbound webhook system | L | `python-backend` | S8-16 | Integrations |
| S8-18 | Build CAP 1.2 export | L | `python-backend` | S8-16, S8-17 | Integrations |
| S8-19 | Build EDXL-DE export | M | `python-backend` | S8-16, S8-17 | Integrations |
| S8-20 | Implement inbound verification source integration | L | `python-backend` | S8-16 | Integrations |
| S8-21 | Build GeoJSON export | M | `python-backend` | S8-16 | Integrations |
| S8-22 | Create integration health monitoring dashboard | M | `python-backend` + `data-viz-builder` | S8-17, S8-20 | Integrations |
| S8-23 | Unit and integration tests for integrations | L | `test-engineer` | S8-17 through S8-22 | Integrations |

*[Additional tasks S8-24 through S8-43 omitted for brevity - see original document]*

**Effort Key:** S = 2–4h, M = 4–8h, L = 8–16h, XL = 16–32h

## 4. Requirements Traceability (v1.0)

Since v1.0 features extend beyond the SRS v0.4 scope, we introduce new requirement IDs:

| Requirement ID | Description | Priority | Sprint | Agent(s) |
|---------------|-------------|----------|--------|----------|
| **FR-I18N-001** | System shall detect language of ingested signals | v1.0 | S8 | `python-backend`, `llm-ops-engineer` |
| **FR-I18N-002** | System shall support Spanish and French COP draft generation | v1.0 | S8 | `python-backend`, `llm-ops-engineer` |
| **FR-I18N-003** | Facilitators shall configure language preference per update | v1.0 | S8 | `python-backend` |
| **FR-I18N-004** | System shall use language-appropriate wording guidance | v1.0 | S8 | `llm-ops-engineer` |
| **FR-ANALYTICS-001** | System shall provide time-series analysis of signal volume and readiness | v1.0 | S8 | `python-backend` |
| **FR-ANALYTICS-002** | System shall detect topic trends (emerging, declining) | v1.0 | S8 | `python-backend`, `llm-ops-engineer` |
| **FR-ANALYTICS-003** | System shall analyze facilitator workload and performance | v1.0 | S8 | `python-backend` |
| **FR-ANALYTICS-004** | System shall compute conflict resolution time by risk tier | v1.0 | S8 | `python-backend` |
| **FR-ANALYTICS-005** | System shall export after-action reports (PDF/DOCX) | v1.0 | S8 | `python-backend`, `technical-writer` |
| **FR-INT-001** | System shall send webhooks on COP publish with retry and logging | v1.0 | S8 | `python-backend` |
| **FR-INT-002** | System shall export COP updates in CAP 1.2 format | v1.0 | S8 | `python-backend` |
| **FR-INT-003** | System shall export COP updates in EDXL-DE format | v1.0 | S8 | `python-backend` |
| **FR-INT-004** | System shall import verified updates from external APIs | v1.0 | S8 | `python-backend` |
| **FR-INT-005** | System shall export GeoJSON for mapping platforms | v1.0 | S8 | `python-backend` |
| **FR-INT-006** | System shall monitor integration health | v1.0 | S8 | `python-backend`, `data-viz-builder` |

*[Additional requirements listed in original document]*

## 5. Environment Variables (New for v1.0)

```bash
# Multi-Language
SUPPORTED_LANGUAGES=en,es,fr
LANGUAGE_DETECTION_ENABLED=true
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8

# Analytics
ANALYTICS_RETENTION_DAYS=365
MAX_ANALYTICS_TIME_RANGE_DAYS=90

# Webhooks
WEBHOOKS_ENABLED=true
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3

# Exports
CAP_EXPORT_ENABLED=true
EDXL_DE_EXPORT_ENABLED=true
GEOJSON_EXPORT_ENABLED=true
```

## 6. Quality Gates

### 6.1 Sprint Exit Criteria

- [ ] All planned v1.0 features complete or explicitly deferred with rationale
- [ ] Test coverage meets targets (80% branch on new business logic)
- [ ] Multi-language test suite passing for Spanish and French
- [ ] External integration test suite passing (webhook, CAP, EDXL-DE, GeoJSON)
- [ ] No critical or high-severity bugs open
- [ ] Documentation complete for all v1.0 features
- [ ] E2E tests passing for multi-language and integration workflows
- [ ] Performance benchmarks met for analytics queries and webhook delivery
- [ ] Security review completed for external integrations

### 6.2 v1.0 Release Criteria

- [ ] All v1.0 requirements implemented and tested
- [ ] Multi-language COP generation working for Spanish and French with native speaker validation
- [ ] At least one external integration (CAP export or webhook) validated with real external system
- [ ] Advanced analytics dashboard operational with representative data
- [ ] E2E test suite passing for all v1.0 workflows
- [ ] Performance testing complete: analytics queries < 2s p95, webhook delivery < 5s p95
- [ ] Security review completed with no critical findings
- [ ] All documentation complete (API docs, configuration guides, user guides, migration guide)
- [ ] v1.0 migration guide validated with upgrade from v0.4.0
- [ ] Release tagged and deployment runbook verified

---

**Document Version:** Consolidated from v0.4 SDP and Sprint 8 SDP
**Last Updated:** 2026-03-13
**Maintained By:** technical-writer
