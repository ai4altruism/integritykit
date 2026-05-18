# Aid Arena Integrity Kit - Software Development Plan

This document consolidates the Software Development Plans for v0.4, Sprint 8 (v1.0), and Sprint 9 (v1.1 security hardening).

---

## Table of Contents

1. [v0.4 Baseline](#v04-baseline)
2. [Sprint 8 - v1.0 Features](#sprint-8---v10-features)
3. [Sprint 9 - v1.1 Security Hardening](#sprint-9---v11-security-hardening)

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

# Sprint 9 - v1.1 Security Hardening

## Software Development Plan (SDP) — Sprint 9: Security Hardening

| Field | Value |
|---|---|
| **Version** | 1.1 |
| **Date** | 2026-05-18 |
| **Sprint Duration** | 3 weeks |
| **Source Documents** | security-review.md (v1.0 pre-deployment audit), SDP v1.0 |
| **Primary Stack** | Python / FastAPI / MongoDB / ChromaDB / OpenAI / Slack (Block Kit) |
| **Build On** | v1.0.1 (Multi-language, Analytics, Integrations) |
| **Target Release** | v1.1.0 (security release) |

## 1. Sprint 9 Overview

### 1.1 Sprint Summary

Sprint 9 closes every CRITICAL and HIGH item from the v1.0 pre-release security review so the kit can be deployed outside trusted exercises. v1.0 shipped with a complete feature surface but the security review surfaced four blocking items — incomplete Slack OAuth, SSRF risk in webhooks and external sources, unencrypted credentials at rest — plus a longer tail of MEDIUM/LOW hardening work. This is a pure-hardening sprint: no new product features.

The sprint is sized at **15.5 engineer-days** across 15 working days, with ~23% buffer for the two highest-risk tickets (S9-1 Slack OAuth, S9-9 EncryptedString helper).

### 1.2 Exit Criteria

- Every checkbox in `security-review.md` §13 "Pre-Deployment (REQUIRED)" is closed.
- Pen-test of OAuth + SSRF paths against a staging deployment passes.
- `docs/deployment-runbook.md` includes secrets-management and Mongo-auth sections.
- v1.1.0 tag created, deployment runbook re-verified.

### 1.3 Strategic Goals

**Authentication & Authorization:**
- Replace the OAuth stub at `api/dependencies.py:98` with real Slack `auth.test` validation
- Gate development bypass headers (`X-Test-User-Id`, `X-Test-Team-Id`) behind `DEBUG`
- Add startup validators for required environment variables

**SSRF Prevention:**
- Build a shared URL-safety utility that rejects loopback, RFC 1918, link-local, IPv6 ULA, reserved, and cloud-metadata addresses
- Wire it into webhook delivery and external-source ingestion
- Re-validate after every HTTP redirect hop

**Credential Protection at Rest:**
- Encrypt `auth_config` for webhooks and external sources with Fernet (env-supplied key); document KMS upgrade path
- Audit logs for credential leakage; add a structlog redaction processor

**Operational Hardening:**
- Require MongoDB auth in the production compose profile
- Sanitize API error responses (no `detail=str(e)` leakage)
- Enforce the 90-day analytics window cap and add endpoint-specific rate limits
- Wire dependency vulnerability scanning into CI

## 2. Sprint 9 Feature Areas

Work is grouped into six concurrent streams (A–F). Each group has a single owner pattern (shared utility used by multiple consumers) which keeps PRs small and reviewable.

### 2.1 Group A — Authentication (CRITICAL)

**Strategic Value:** The OAuth bearer-token path is currently stubbed to always return 401, blocking any non-Slack-Bolt client. Closing this is the gate that allows external API consumers to authenticate at all.

**Key Tickets:**
- S9-1: Implement Slack OAuth token validation (auth.test + 60s cache)
- S9-2: Gate test headers behind DEBUG
- S9-3: Add environment-variable validators (`MONGODB_URI`, `SLACK_BOT_TOKEN`, `OPENAI_API_KEY`)

### 2.2 Group B — SSRF Prevention (CRITICAL)

**Strategic Value:** `workspace_admin` users can currently configure webhooks or external sources whose endpoints target internal services (localhost, 169.254.169.254 cloud metadata, RFC 1918 ranges). One shared utility plus two integration points closes this OWASP Top-10 item.

**Key Tickets:**
- S9-4: Build shared URL-safety utility (`utils/url_safety.py`)
- S9-5: Wire SSRF protection into webhook delivery
- S9-6: Wire SSRF protection into external-source ingestion
- S9-7: SSRF unit test coverage (full parametrized sweep + DNS rebinding)

### 2.3 Group C — Credential Encryption at Rest (HIGH)

**Strategic Value:** Webhook and external-source `auth_config` blobs currently sit in MongoDB as plaintext. A database compromise exposes every downstream credential. Field-level encryption with a single env-supplied key is the minimum acceptable bar.

**Key Tickets:**
- S9-8: Document key-management decision and runbook (Fernet baseline confirmed; KMS path documented but deferred)
- S9-9: Implement `EncryptedString` Pydantic field helper
- S9-10: Encrypt webhook `auth_config` at rest
- S9-11: Encrypt external-source `auth_config` at rest
- S9-12: Migration: decide and document procedure (clear-and-reenter vs script)
- S9-13: Log-leakage audit and structlog redaction filter

### 2.4 Group D — MongoDB Authentication (MEDIUM)

**Strategic Value:** Default `docker-compose.yml` runs MongoDB without authentication, which is acceptable for local dev but unacceptable for prod. The fix is configuration plus runbook guidance — no application code changes.

**Key Tickets:**
- S9-14: Require MongoDB auth in `docker-compose.prod.yml`
- S9-15: Expand deployment runbook: MongoDB production setup + secrets

### 2.5 Group E — API Hardening Hygiene (MEDIUM)

**Strategic Value:** A grab-bag of MEDIUM findings from the security review. Each is small; together they close half the LOW/MEDIUM tail.

**Key Tickets:**
- S9-16: Sanitize error-message responses (no `detail=str(e)`)
- S9-17: Enforce analytics time-range cap (90-day window)
- S9-18: Endpoint-specific rate limits (auth, webhook create, source import, report generation)
- S9-19: Verify rate-limit middleware wiring with a regression test

### 2.6 Group F — Supply Chain & Docs (MEDIUM)

**Strategic Value:** Dependency-vulnerability scanning and secrets-management documentation close the operational tail of the pre-deployment checklist.

**Key Tickets:**
- S9-20: Add `pip-audit` to CI pipeline
- S9-21: Pin direct dependencies and generate lockfile
- S9-22: Add Dependabot configuration
- S9-23: Secrets-management documentation (closes the CRITICAL §13 checklist item)

## 3. Sprint 9 Task Plan

### Sprint 9: Security Hardening (3 weeks)

**Goal:** Close every CRITICAL and HIGH item from the v1.0 pre-release security review, plus address the operational hardening tail, so v1.1.0 can be deployed outside trusted exercises.

**Effort Key:** S = 2–4h, M = 4–8h, L = 8–16h, XL = 16–32h. Day estimates assume 7 productive hours.

| Task ID | Title | Group | Priority | Effort (days) | Week | Status |
|---------|-------|-------|----------|--------------|------|--------|
| S9-1 | Implement Slack OAuth token validation | A | CRITICAL | 2 | 1 | **Done** |
| S9-2 | Gate test headers behind DEBUG flag | A | MEDIUM | 0.5 | 1 | Pending |
| S9-3 | Add environment variable validators | A | MEDIUM | 0.5 | 1 | Pending |
| S9-4 | Build shared URL-safety utility | B | CRITICAL | 1 | 1 | **Done** |
| S9-5 | Wire SSRF protection into webhook delivery | B | CRITICAL | 0.5 | 1 | Pending |
| S9-6 | Wire SSRF protection into external-source ingestion | B | CRITICAL | 0.5 | 1 | Pending |
| S9-7 | SSRF unit test coverage | B | CRITICAL | 1 | 1 | Pending |
| **Week 1 subtotal** | | | | **6** | | |
| S9-8 | Document key-management decision and runbook | C | HIGH | 0.5 | 2 | Pending |
| S9-9 | Implement EncryptedString field helper | C | HIGH | 1 | 2 | Pending |
| S9-10 | Encrypt webhook auth_config at rest | C | HIGH | 1 | 2 | Pending |
| S9-11 | Encrypt external-source auth_config at rest | C | HIGH | 1 | 2 | Pending |
| S9-12 | Migration: decide and document procedure | C | HIGH | 0.5 | 2 | Pending |
| S9-13 | Log-leakage audit and redaction filter | C | HIGH | 1 | 2 | Pending |
| S9-14 | Require MongoDB auth in prod compose | D | MEDIUM | 0.25 | 2 | Pending |
| S9-15 | Expand deployment runbook: MongoDB and secrets | D | MEDIUM | 0.5 | 2 | Pending |
| **Week 2 subtotal** | | | | **5.75** | | |
| S9-16 | Sanitize error-message responses | E | MEDIUM | 0.5 | 3 | Pending |
| S9-17 | Enforce analytics time-range cap | E | MEDIUM | 0.5 | 3 | Pending |
| S9-18 | Endpoint-specific rate limits | E | MEDIUM | 1 | 3 | Pending |
| S9-19 | Verify rate-limit middleware wiring | E | MEDIUM | 0.25 | 3 | Pending |
| S9-20 | Add pip-audit to CI pipeline | F | MEDIUM | 0.25 | 3 | Pending |
| S9-21 | Pin direct dependencies and generate lockfile | F | LOW | 0.5 | 3 | Pending |
| S9-22 | Add Dependabot configuration | F | LOW | 0.25 | 3 | Pending |
| S9-23 | Secrets-management documentation | F | CRITICAL | 0.5 | 3 | Pending |
| **Week 3 subtotal** | | | | **3.75** | | |
| **Sprint total** | | | | **15.5 days** | 3 weeks | |

**Capacity note:** 15.5 engineer-days across 15 working days (3 × 5) leaves ~4.5 days buffer (~23%), absorbing unknowns in S9-1 and S9-9.

## 4. Detailed Ticket Definitions

Each ticket includes priority, file paths, acceptance criteria, effort estimate, dependencies, and a test plan. Tickets reference `security-review.md` section numbers throughout.

### Week 1 — Group A (Authentication) + Group B (SSRF)

#### S9-1 — Implement Slack OAuth token validation

**Group:** A • **Priority:** CRITICAL • **Status:** Done (landed 2026-05-18)
**Maps to:** security-review.md §1 ("CRITICAL - Incomplete OAuth Implementation")

**Files touched:**
- `src/integritykit/api/dependencies.py` (replaced TODO stub)
- `tests/integration/test_slack_oauth.py` (new)
- `tests/integration/conftest.py` (new — stubs env vars for package import)

**Description:**
Replaced the stub in `get_current_user_from_token` that raised 401 unconditionally for Bearer tokens. Calls Slack's `auth.test` API with the presented token, parses the response into `TokenPayload`, caches the result for 60 s in a module-level dict (keyed by token), then looks up or creates the user via `UserRepository.get_or_create_by_slack_id`.

**Acceptance criteria (all met):**
- [x] Valid Slack Bearer token returns the authenticated user.
- [x] Invalid/revoked token causes Slack API call to fail and endpoint returns 401.
- [x] Cached token within 60 s does not trigger a second `auth.test` call (asserted via mock call count).
- [x] `TokenPayload` fields populated from Slack response.
- [x] Integration test exercises valid and invalid token paths.

**Estimated effort:** 2 days • **Dependencies:** None

#### S9-2 — Gate test headers behind DEBUG flag

**Group:** A • **Priority:** MEDIUM (elevated for sprint — bypass enabler)
**Maps to:** security-review.md §1 ("MEDIUM - Test Headers in Production")

**Files touched:**
- `src/integritykit/api/dependencies.py` (lines 79–88)
- `src/integritykit/api/main.py` (startup log)
- `tests/` — any test that passes `X-Test-User-Id` / `X-Test-Team-Id`

**Description:**
Wrap the `X-Test-User-Id` / `X-Test-Team-Id` branch in `if settings.debug:`. Emit a `logger.warning` at application startup when `debug=True` so operators cannot miss that the bypass is active. Update existing tests to assert headers are rejected when DEBUG is off.

**Acceptance criteria:**
- [ ] With `settings.debug=False`, requests carrying `X-Test-User-Id` proceed to the OAuth path (not authenticated via test path).
- [ ] With `settings.debug=True`, the existing test-header flow continues to work.
- [ ] Application startup log includes a WARNING line when `debug=True`.
- [ ] All existing unit and integration tests continue to pass.
- [ ] A new test asserts the header is ignored in production mode.

**Estimated effort:** 0.5 days • **Dependencies:** None

**Test plan:** Extend `tests/unit/test_dependencies.py` (or create); assert header ignored when debug=False, accepted when debug=True, startup warning emitted.

#### S9-3 — Add environment variable validators in config

**Group:** A • **Priority:** MEDIUM
**Maps to:** security-review.md §7 ("MEDIUM - Missing Validation")

**Files touched:**
- `src/integritykit/config.py`

**Description:**
Add Pydantic `field_validator` decorators to `Settings` for:
- `mongodb_uri`: must begin with `mongodb://` or `mongodb+srv://`; accept `mongodb://user:pass@host` and SRV forms (covers D3).
- `slack_bot_token`: must begin with `xoxb-`.
- `openai_api_key`: must begin with `sk-`.

On validation failure, Pydantic raises at import time, exiting the process with a clear error.

**Acceptance criteria:**
- [ ] Malformed `MONGODB_URI` causes startup `ValidationError`.
- [ ] `SLACK_BOT_TOKEN` not starting with `xoxb-` fails at startup.
- [ ] `OPENAI_API_KEY` not starting with `sk-` fails at startup.
- [ ] Valid values for all three pass.
- [ ] `mongodb+srv://user:pass@cluster.example.mongodb.net/db` is accepted.

**Estimated effort:** 0.5 days • **Dependencies:** None

**Test plan:** New test class in `tests/unit/test_config.py`; parametrize valid/invalid values per field.

#### S9-4 — Build shared URL-safety utility

**Group:** B • **Priority:** CRITICAL • **Status:** Done (landed 2026-05-18)
**Maps to:** security-review.md §3, §4 ("CRITICAL - SSRF Prevention"), §10 (A10:2021 SSRF)

**Files touched:**
- `src/integritykit/utils/url_safety.py` (new)
- `tests/unit/test_url_safety.py` (new — 26 tests)

**Description:**
Module exposes `validate_external_url(url, *, max_redirects=5)` raising `UnsafeURLError(ValueError)`. Uses stdlib `ipaddress` classifiers to reject loopback (127.0.0.0/8, ::1), RFC 1918 (10/8, 172.16/12, 192.168/16), link-local (169.254.0.0/16), IPv6 ULA (fc00::/7), reserved/multicast/unspecified, and a literal blocklist for cloud metadata (`169.254.169.254`, `fd00:ec2::254`). Follows up to N HTTP redirects via `httpx.HEAD`, re-validating each hop. Detects redirect loops; raises if depth exceeds the cap.

**Acceptance criteria (all met):**
- [x] All listed blocked address literals raise `UnsafeURLError`.
- [x] A redirect chain that terminates at a private IP raises.
- [x] A public HTTPS URL resolves without raising.

**Estimated effort:** 1 day • **Dependencies:** None

#### S9-5 — Wire SSRF protection into webhook delivery

**Group:** B • **Priority:** CRITICAL
**Maps to:** security-review.md §3 ("CRITICAL - SSRF Prevention")

**Files touched:**
- `src/integritykit/services/webhooks.py` (`_validate_webhook_url`, `_attempt_delivery`, `test_webhook`)

**Description:**
Replace the minimal hostname-string check in `_validate_webhook_url` with a call to `validate_external_url`. Also call it inside `_attempt_delivery` just before the `httpx` POST, and inside `test_webhook` before the test delivery. Surface a distinct `UnsafeURLError` as `WebhookStatus = "blocked_ssrf"` in the delivery record. Update the `WebhookStatus` enum if needed.

**Acceptance criteria:**
- [ ] Creating a webhook targeting `http://10.0.0.1/` raises a `ValueError` surfaced as 400.
- [ ] Delivery to a webhook resolving to a private address at delivery time records status `"blocked_ssrf"`.
- [ ] Delivery to a legitimate public endpoint is unaffected.
- [ ] `test_webhook` returns `success=False` with `error` mentioning SSRF when URL is unsafe.

**Estimated effort:** 0.5 days • **Dependencies:** S9-4

**Test plan:** Extend `tests/unit/test_webhook_service.py`; mock `validate_external_url` to raise; assert delivery record status; verify create returns 400.

#### S9-6 — Wire SSRF protection into external-source ingestion

**Group:** B • **Priority:** CRITICAL
**Maps to:** security-review.md §4 ("CRITICAL - SSRF Prevention")

**Files touched:**
- `src/integritykit/services/external_sources.py` (`_validate_endpoint_url`, `_fetch_from_external_api`)

**Description:**
Mirror of S9-5 for external sources. Replace `_validate_endpoint_url` with a call to `validate_external_url`. Add the same call at the top of `_fetch_from_external_api` before the `httpx.AsyncClient.get`. Surface failures in the `ImportResult` as `status=ImportStatus.FAILED` with `error_message="SSRF: target resolves to private address"`. Update source-health metrics accordingly.

**Acceptance criteria:**
- [ ] Creating an external source with `api_endpoint="http://192.168.0.1/"` raises 400.
- [ ] `import_verified_data` for a source resolving to a private IP returns `ImportResult(status=FAILED, error_message contains "SSRF")`.
- [ ] Legitimate public endpoints are unaffected.
- [ ] Source statistics reflect the SSRF failure.

**Estimated effort:** 0.5 days • **Dependencies:** S9-4

**Test plan:** Extend `tests/unit/test_external_source_service.py`; assert create returns 400 and import returns FAILED.

#### S9-7 — SSRF unit test coverage

**Group:** B • **Priority:** CRITICAL
**Maps to:** security-review.md §3, §4, §10

**Files touched:**
- `tests/unit/test_url_safety.py` (primary — already seeded by S9-4)
- `tests/unit/test_webhook_service.py`
- `tests/unit/test_external_source_service.py`

**Description:**
Dedicated test coverage task for the full SSRF surface. This captures work that exceeds what S9-4, S9-5, and S9-6 each include individually:
- Full parametrized sweep of all blocked IP ranges (one assertion per CIDR) — partially seeded by S9-4
- DNS-rebinding regression test: mock DNS returning public IP on first call, private on second — seeded by S9-4
- Redirect-chain depth enforcement — seeded by S9-4

**Acceptance criteria:**
- [ ] At least one test per blocked CIDR in `test_url_safety.py`.
- [ ] DNS-rebinding scenario covered with a mock returning different IPs across calls.
- [ ] Redirect depth limit tested.
- [ ] All SSRF tests pass in CI without network access.

**Estimated effort:** 1 day • **Dependencies:** S9-4, S9-5, S9-6

### Week 2 — Group C (Credential Encryption) + Group D (MongoDB Auth)

#### S9-8 — Document key-management decision and runbook

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §8, §3, §4

**Files touched:**
- `docs/deployment-runbook.md` (new section: "Credential Encryption Key Management")

**Description:**
Blocking design decision for C2–C5. Add a section to `docs/deployment-runbook.md` that:
1. Confirms Fernet symmetric encryption as the baseline (`cryptography` library, key from `CREDENTIAL_ENCRYPTION_KEY` env var, 32-byte URL-safe base64).
2. Documents KMS upgrade path (AWS KMS, GCP KMS, HashiCorp Vault) with the adapter interface contract — without implementing it.
3. Provides a key-rotation runbook: generate new key, re-encrypt all `auth_config` blobs, update env var, restart service.
4. Documents `CREDENTIAL_ENCRYPTION_KEY` (format, generation, never commit).

**Acceptance criteria:**
- [ ] Runbook section exists.
- [ ] Section specifies how to generate a valid Fernet key.
- [ ] KMS upgrade path described at the interface level.
- [ ] Manual key-rotation steps enumerated.
- [ ] Open question C1 (Fernet env-var baseline) is resolved inline.

**Estimated effort:** 0.5 days • **Dependencies:** None (blocks all other C tickets)

**Test plan:** Doc review only.

#### S9-9 — Implement EncryptedString field helper

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §8 ("HIGH - Field-Level Encryption")

**Files touched:**
- `src/integritykit/utils/encryption.py` (new)
- `src/integritykit/config.py` (new optional field `credential_encryption_key`)
- `tests/unit/test_encryption.py` (new)

**Description:**
Implement `EncryptedString`, a Pydantic-compatible annotated type that transparently encrypts on serialization and decrypts on load, using Fernet with the key from `settings.credential_encryption_key`.

Key behaviors:
- Serialize to MongoDB: plain string → Fernet-encrypted bytes → base64 → stored as `enc:<base64>` to distinguish from legacy plaintext.
- Deserialize from MongoDB: detect `enc:` prefix → decrypt → return plain string. No-prefix values treated as legacy plaintext (migration grace period).
- Missing/wrong key at decrypt: raise `EncryptionKeyError` (fail loud, do not silently return garbage).
- `settings.credential_encryption_key` added to `config.py` as optional; absent → encryption disabled and any encrypted-field access raises.

**Acceptance criteria:**
- [ ] Roundtrip test: encrypt → serialize → deserialize → original value recovered.
- [ ] Wrong-key test: key A encrypt, key B decrypt → raises `EncryptionKeyError`.
- [ ] Missing-key test: accessing encrypted field with no key → raises `EncryptionKeyError`.
- [ ] Legacy-plaintext test: no `enc:` prefix passes through.
- [ ] `settings.credential_encryption_key` wired in `config.py`.

**Estimated effort:** 1 day • **Dependencies:** S9-8

#### S9-10 — Encrypt webhook auth_config at rest

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §3, §8

**Files touched:**
- `src/integritykit/models/webhook.py` (`AuthConfig`)
- `src/integritykit/services/webhooks.py` (`create_webhook`, `update_webhook`, `_attempt_delivery`, `test_webhook`, `_build_auth_headers`)

**Description:**
Apply `EncryptedString` to the sensitive fields of `AuthConfig` in `models/webhook.py` (`token`, `password`, `key_value`, `header_value`, `client_secret`).

Update `services/webhooks.py`:
- On write: Pydantic serializes encrypted values automatically.
- On API response read: existing `_redact_auth_config` continues to redact — confirm it operates on decrypted values (returns `***REDACTED***`, not an `enc:` blob).
- On delivery read (`_build_auth_headers`): confirm Pydantic returns plain strings.

**Acceptance criteria:**
- [ ] Stored webhook with bearer token writes `enc:` prefixed blob to MongoDB.
- [ ] Fetching webhook via API returns `token: "***REDACTED***"`, not an `enc:` blob.
- [ ] Delivery uses decrypted token in `Authorization` header (verifiable via mocked httpx).
- [ ] Updating `auth_config` re-encrypts with current key.

**Estimated effort:** 1 day • **Dependencies:** S9-9

#### S9-11 — Encrypt external-source auth_config at rest

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §4, §8

**Files touched:**
- `src/integritykit/models/external_source.py` (`AuthConfig`)
- `src/integritykit/services/external_sources.py` (`create_source`, `update_source`, `_fetch_from_external_api`, `_build_auth_headers`)

**Description:**
Mirror of S9-10 for external sources. Apply `EncryptedString` to `AuthConfig` fields (`key_value`, `token`, `password`, `client_secret`). Verify `_redact_auth_config` returns sanitized values in API responses and `_build_auth_headers` uses decrypted values for external API calls.

**Acceptance criteria:**
- [ ] Stored source with `auth_type=api_key` writes `enc:` prefixed blob.
- [ ] API responses redact sensitive fields.
- [ ] Import calls use decrypted credential.
- [ ] Updating `auth_config` re-encrypts.

**Estimated effort:** 1 day • **Dependencies:** S9-9

#### S9-12 — Migration: decide and document procedure

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §8

**Files touched:**
- `docs/deployment-runbook.md` (new subsection: "Migration: Credential Encryption")
- `scripts/encrypt_existing_credentials.py` (only if live data exists — see open question C5)

**Description:**
Answer open question C5:
- **If no live workspace data** (expected for a pre-production release): document "clear-and-reenter" as the upgrade procedure. No script needed.
- **If live data exists**: write a one-shot script that reads all `webhooks` and `external_sources` documents, encrypts non-`enc:`-prefixed `auth_config` fields, writes back atomically, logs a summary, and is idempotent.

**Acceptance criteria:**
- [ ] Runbook subsection exists.
- [ ] Subsection documents whether a script is needed and why.
- [ ] If script written: idempotent (second run is a no-op).
- [ ] If script written: unit test or dry-run mode against mock data.
- [ ] Open question C5 explicitly resolved in the runbook.

**Estimated effort:** 0.5 days (no live data) or 2 days (with script). Default sprint estimate: 0.5 days.
**Dependencies:** S9-9, S9-8

#### S9-13 — Log-leakage audit and redaction filter

**Group:** C • **Priority:** HIGH
**Maps to:** security-review.md §10, §3, §4

**Files touched:**
- `src/integritykit/services/audit.py`
- `src/integritykit/services/webhooks.py` (retry/error log lines)
- `src/integritykit/services/external_sources.py` (import error log lines)
- `src/integritykit/api/main.py` (structlog config)

**Description:**
Two sub-tasks:
1. **Manual audit:** grep the three services for any log call that could include `auth_config` values, tokens, passwords, or key material. Replace with references to redacted/sanitized versions.
2. **Structlog redaction filter:** add a structlog processor in `main.py` (or shared logging config module) that scans the log-event dict for known sensitive keys (`token`, `password`, `key_value`, `client_secret`, `auth_config`) and replaces values with `[REDACTED]`. Defense in depth.

**Acceptance criteria:**
- [ ] No log statement in the audited files emits a raw credential value (code review).
- [ ] Structlog processor registered and active at startup.
- [ ] Unit test: event dict with sensitive keys → redacted output.
- [ ] Non-sensitive log output unchanged.

**Estimated effort:** 1 day • **Dependencies:** S9-9

#### S9-14 — Require MongoDB auth in prod compose

**Group:** D • **Priority:** MEDIUM
**Maps to:** security-review.md §8

**Files touched:**
- `docker-compose.prod.yml`
- `.env.example`

**Description:**
Update `docker-compose.prod.yml` to pass `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD`. Leave `docker-compose.yml` (dev) permissive for local DX. Update `.env.example` to include an authenticated `MONGODB_URI=mongodb://user:pass@localhost:27017/integritykit?authSource=admin` example.

**Acceptance criteria:**
- [ ] `docker-compose.prod.yml` MongoDB service includes the env references.
- [ ] `docker-compose.yml` unchanged.
- [ ] `.env.example` shows authenticated URI with comment distinguishing dev vs prod.
- [ ] S9-3 validator accepts the authenticated URI format.

**Estimated effort:** 0.25 days • **Dependencies:** S9-3

#### S9-15 — Expand deployment runbook: MongoDB and secrets

**Group:** D • **Priority:** MEDIUM
**Maps to:** security-review.md §8, §7

**Files touched:**
- `docs/deployment-runbook.md`

**Description:**
Add or expand two sections:
1. **MongoDB Production Setup:** managed-Mongo guidance (Atlas TLS, least-privilege roles, encryption at rest with WiredTiger, backup encryption).
2. **Secrets Management (placeholder):** brief D2 guidance pointing forward to the F4 (S9-23) section.

**Acceptance criteria:**
- [ ] "MongoDB Production Setup" section covers Atlas TLS, least-privilege roles, backup.
- [ ] Runbook references `CREDENTIAL_ENCRYPTION_KEY` and `MONGODB_URI` as managed secrets.
- [ ] `authSource` parameter documented for connection strings.

**Estimated effort:** 0.5 days • **Dependencies:** S9-8

### Week 3 — Group E (Hardening Hygiene) + Group F (Supply Chain & Docs)

#### S9-16 — Sanitize error-message responses

**Group:** E • **Priority:** MEDIUM
**Maps to:** security-review.md §10

**Files touched:**
- `src/integritykit/api/routes/exports.py` (line 123 area)
- `src/integritykit/api/routes/` (full grep for `detail=str(e)`)

**Description:**
The `raise HTTPException(detail=str(e))` pattern leaks internal error messages (MongoDB errors, library stack details). For each instance:
1. Log full exception internally at `logger.error` with `exc_info=True`.
2. Return a generic user-facing message.

**Acceptance criteria:**
- [ ] No `detail=str(e)` remains in `src/integritykit/api/routes/`.
- [ ] All replaced handlers log full exceptions internally.
- [ ] 500-class error responses contain generic messages.
- [ ] Existing tests asserting on error detail strings are updated.

**Estimated effort:** 0.5 days • **Dependencies:** None

#### S9-17 — Enforce analytics time-range cap

**Group:** E • **Priority:** MEDIUM
**Maps to:** security-review.md §2, §6

**Files touched:**
- `src/integritykit/api/routes/analytics.py`

**Description:**
`settings.max_analytics_time_range_days` (default 90) exists but is not enforced. Add a check in every endpoint accepting `start_date` / `end_date`: `get_time_series_analytics`, `get_signal_volume_time_series`, `get_readiness_transitions_time_series`, `get_facilitator_actions_time_series`, `get_topic_trends`, `get_facilitator_workload`, `get_conflict_resolution_metrics`, `generate_after_action_report`. Return 400 if range exceeds the cap.

**Acceptance criteria:**
- [ ] 91-day range → 400 with explanation.
- [ ] 90-day range → 200.
- [ ] Limit read from settings, not hardcoded.
- [ ] All eight endpoints enforce the cap.
- [ ] Existing tests with valid ranges continue to pass.

**Estimated effort:** 0.5 days • **Dependencies:** None

#### S9-18 — Endpoint-specific rate limits

**Group:** E • **Priority:** MEDIUM
**Maps to:** security-review.md §9

**Files touched:**
- `src/integritykit/api/main.py` (rate-limit middleware)
- `src/integritykit/config.py` (optional new fields)

**Description:**
Extend the existing global `rate_limit_middleware` with tighter per-path limits:

| Path pattern | Limit |
|---|---|
| Auth endpoints (`/api/v1/users/me`, dependency invocations) | 5 / min per key |
| `POST /api/v1/webhooks` | 10 / hour per key |
| `POST /api/v1/integrations/*/import` | 10 / hour per key |
| `POST /api/v1/analytics/reports/after-action` | 5 / hour per key |

Implementation: extend `_rate_limit_store` with a second dict keyed by `(key, path_pattern)` or introduce `slowapi`. Keep the global limit.

**Acceptance criteria:**
- [ ] `POST /api/v1/webhooks` returns 429 after 10 requests/hour per key.
- [ ] Report generation returns 429 after 5 requests/hour.
- [ ] Global 60/min still applies elsewhere.
- [ ] Tested without real time passing (mock `time.time`).

**Estimated effort:** 1 day • **Dependencies:** S9-19

#### S9-19 — Verify rate-limit middleware wiring

**Group:** E • **Priority:** MEDIUM
**Maps to:** security-review.md §9

**Files touched:**
- `src/integritykit/api/main.py` (review only; fix if needed)
- `tests/unit/test_rate_limiting.py` (new or extended)

**Description:**
The security review flagged the rate-limit middleware registration as unverified. Reading confirms it's registered as `@app.middleware("http")` (lines 131–179). This ticket formalizes verification with a regression test. Fix any gaps found.

**Acceptance criteria:**
- [ ] Automated test confirms enabled-limit returns 429 on overage.
- [ ] Automated test confirms disabled-limit produces no 429s.
- [ ] Middleware registration confirmed correct or fixed.

**Estimated effort:** 0.25 days • **Dependencies:** None

#### S9-20 — Add pip-audit to CI pipeline

**Group:** F • **Priority:** MEDIUM
**Maps to:** security-review.md §11

**Files touched:**
- `.github/workflows/`

**Description:**
Add a `pip-audit` step to the GitHub Actions workflow on every PR and push to `main`. Use the `pypa/gh-action-pip-audit` action or install directly. Fail on known-vulnerability dependencies.

**Acceptance criteria:**
- [ ] CI includes a `pip-audit` step.
- [ ] Step fails workflow on known CVEs (verified manually with a temporarily vulnerable dep).
- [ ] Step passes on current dependency set.
- [ ] Failure message is human-readable.

**Estimated effort:** 0.25 days • **Dependencies:** None

#### S9-21 — Pin direct dependencies and generate lockfile

**Group:** F • **Priority:** LOW
**Maps to:** security-review.md §11

**Files touched:**
- `pyproject.toml`
- `uv.lock` (new) or `requirements.lock`

**Description:**
Change direct dependency specifiers in `pyproject.toml` from `>=` to `~=`. Generate and commit a lockfile via `uv lock` (preferred) or `pip-compile`. Lockfile pins all transitive deps to exact versions. Do not change dev-only deps if grouped separately.

**Acceptance criteria:**
- [ ] All direct prod deps use `~=`.
- [ ] Lockfile committed.
- [ ] `uv sync` produces a working env from the lockfile.
- [ ] CI installs from the lockfile.

**Estimated effort:** 0.5 days • **Dependencies:** S9-20

#### S9-22 — Add Dependabot configuration

**Group:** F • **Priority:** LOW
**Maps to:** security-review.md §11

**Files touched:**
- `.github/dependabot.yml` (new)

**Description:**
Create `.github/dependabot.yml` covering:
- `pip`: weekly cadence, grouped minor/patch updates, target `main`, max 5 open PRs.
- `github-actions`: weekly cadence, grouped updates.

**Acceptance criteria:**
- [ ] Valid YAML.
- [ ] `pip` ecosystem weekly.
- [ ] `github-actions` ecosystem weekly.
- [ ] Minor/patch grouped into one PR per ecosystem.

**Estimated effort:** 0.25 days • **Dependencies:** S9-21

#### S9-23 — Secrets-management documentation

**Group:** F • **Priority:** CRITICAL (per §13 checklist item)
**Maps to:** security-review.md §7, §13

**Files touched:**
- `docs/deployment-runbook.md` (new section: "Secrets Management")

**Description:**
Add a "Secrets Management" section covering:
1. How to source `CREDENTIAL_ENCRYPTION_KEY` per deployment model (env var, AWS Secrets Manager, GCP Secret Manager, Vault).
2. `.env` hygiene: never commit, `chmod 600`, rotate on personnel change.
3. Enumerated list of secret env vars (`CREDENTIAL_ENCRYPTION_KEY`, `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `MONGODB_URI` if auth URI).
4. Container deployment guidance: inject from a secrets manager, not baked into images.

**Acceptance criteria:**
- [ ] Section exists in runbook.
- [ ] Each deployment model addressed.
- [ ] `.env` hygiene present.
- [ ] Secret env vars enumerated.
- [ ] Closes the §13 "Document secrets management practices" checklist item.

**Estimated effort:** 0.5 days • **Dependencies:** S9-8

## 5. Dependency Graph

```
S9-1 (Slack OAuth)             — no upstream                                [DONE]
S9-2 (debug gate)              — no upstream
S9-3 (env validators)          — no upstream; S9-14 confirms after
S9-4 (url_safety module)       — no upstream                                [DONE]
S9-5 (webhook SSRF wire)       → depends on S9-4
S9-6 (ext-source SSRF wire)    → depends on S9-4
S9-7 (SSRF test coverage)      → depends on S9-4, S9-5, S9-6
S9-8 (key-mgmt doc)            — no upstream
S9-9 (EncryptedString)         → depends on S9-8
S9-10 (encrypt webhook creds)  → depends on S9-9
S9-11 (encrypt ext-src creds)  → depends on S9-9
S9-12 (migration decision)     → depends on S9-8, S9-9
S9-13 (log redaction)          → depends on S9-9
S9-14 (mongo prod compose)     → confirms S9-3
S9-15 (runbook: mongo+secrets) → depends on S9-8
S9-16 (error sanitization)     — no upstream
S9-17 (analytics time cap)     — no upstream
S9-18 (endpoint rate limits)   → depends on S9-19
S9-19 (verify rate limit wire) — no upstream
S9-20 (pip-audit CI)           — no upstream
S9-21 (pin deps + lockfile)    → depends on S9-20
S9-22 (dependabot)             → depends on S9-21
S9-23 (secrets-mgmt docs)      → depends on S9-8
```

### Critical paths

1. **Auth chain** (week 1): S9-1 is standalone 2-day effort. If blocked on Slack workspace access, all other week-1 tickets can proceed independently.
2. **Encryption chain** (week 2): `S9-8 → S9-9 → {S9-10, S9-11, S9-12, S9-13}`. S9-8 and S9-9 are sequential. After S9-9, S9-10 and S9-11 can parallelize.
3. **SSRF chain** (week 1): `S9-4 → {S9-5, S9-6} → S9-7` — total 3 days.

## 6. Risks

### R1 — Slack OAuth workspace dependency (S9-1)
**Probability:** Medium • **Impact:** High
A dev Slack workspace is required to smoke-test the `auth.test` path end-to-end. If unavailable, only mock tests can validate.
**Mitigation:** Stand up the dev workspace day 1. If blocked, complete mock tests and document real-token testing as a manual pre-release gate.

### R2 — Key-management decision expanding scope (S9-8, S9-9)
**Probability:** Low-Medium • **Impact:** High
If S9-8 moves away from Fernet env-var baseline (e.g., to AWS KMS), S9-9 grows significantly — async KMS calls, IAM setup, local mock for CI. Could add 2–5 days.
**Mitigation:** The plan explicitly recommends Fernet baseline. If KMS chosen, scope S9-9 to a Fernet adapter only; KMS adapter becomes Sprint 10.

### R3 — Live credential data in production (S9-12)
**Probability:** Unknown (open question C5) • **Impact:** Medium
If pilot workspaces hold unencrypted credentials, the migration script adds ~1.5 days. Sprint table uses the optimistic 0.5-day estimate.
**Mitigation:** Confirm on day 1. If live data exists, re-estimate S9-12 to 2 days and compress one LOW-priority F-group ticket.

### R4 — `detail=str(e)` instances beyond exports.py (S9-16)
**Probability:** Medium • **Impact:** Low
Full grep may reveal more occurrences than the one called out by the security review.
**Mitigation:** S9-16 estimate includes a conservative allowance. If grep finds significantly more, triage by severity (5xx handlers first).

### R5 — In-memory rate limiter limitations (S9-18)
**Probability:** Medium • **Impact:** Low
The existing limiter is in-memory and per-process. In a multi-worker deployment, per-endpoint limits aren't enforced across workers.
**Mitigation:** Add a comment in `main.py` flagging that a Redis-backed limiter is needed for multi-worker prod. Documentation action only.

### R6 — `~=` specifiers breaking transitive deps (S9-21)
**Probability:** Low • **Impact:** Medium
Tightening specifiers may reveal a transitive dep requiring a newer minor than `~=` allows.
**Mitigation:** Run `uv lock` against tightened specifiers before committing; resolve any conflicts in the same PR.

## 7. Open Questions

1. **C1 — Key management mechanism?** Env-var Fernet (simplest, recommended baseline), AWS KMS / GCP KMS, or Vault? Decides scope of S9-9. **Recommended:** Fernet env-var baseline, with documented KMS upgrade path.
2. **C5 — Live workspace data?** Any pilot workspaces with real webhook/external-source credentials yet? If no, skip migration script. Re-estimate S9-12 if yes.
3. **Pilot deadline?** A real-workspace pilot date hardens deadlines on Groups A+B+C and lets E+F slip to a patch release.

## 8. Out of Scope for Sprint 9

Deferred to Sprint 10 (post-pen-test) per security-review.md §13 "Post-Deployment":
- MongoDB encryption at rest (operational config, not code)
- Export endpoint authentication (LOW — published data is intended for distribution)
- Webhook signature-verification documentation (covers consumers, not us)
- Field-level encryption beyond `auth_config` (no other sensitive fields identified)
- MongoDB audit logging
- Log retention policy formalization
- XML/HTML entity escaping in CAP/EDXL exports (LOW — system-to-system only)

## 9. Environment Variables (New for v1.1)

```bash
# Credential encryption (S9-9)
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
CREDENTIAL_ENCRYPTION_KEY=<32-byte URL-safe base64>

# MongoDB authentication (S9-14) — production only
MONGODB_URI=mongodb://user:pass@host:27017/integritykit?authSource=admin
```

## 10. Quality Gates

### 10.1 Sprint Exit Criteria

- [ ] All CRITICAL items in security-review.md §13 closed.
- [ ] All HIGH items in security-review.md §13 closed.
- [ ] Test coverage maintained at ≥80% branch on new business logic.
- [ ] SSRF, OAuth, and encryption test suites passing in CI.
- [ ] No regressions in v1.0 feature tests (1156 baseline).
- [ ] `pip-audit` clean in CI.
- [ ] Deployment runbook updated with all new sections.

### 10.2 v1.1.0 Release Criteria

- [ ] All Sprint 9 tickets complete or explicitly deferred with rationale.
- [ ] Pen-test of OAuth + SSRF paths against staging passes.
- [ ] Credential-encryption end-to-end smoke test on a non-production workspace.
- [ ] CHANGELOG.md updated with the security release notes.
- [ ] Migration documentation validated by an operator who did not write the runbook.
- [ ] v1.1.0 tagged.

---

**Document Version:** Consolidated from v0.4 SDP, Sprint 8 SDP, and Sprint 9 SDP (formerly `sprint-9-security-hardening.md` + `sprint-9-tickets.md`)
**Last Updated:** 2026-05-18
**Maintained By:** technical-writer
