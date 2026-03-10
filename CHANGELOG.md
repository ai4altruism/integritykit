# Changelog

All notable changes to the Aid Arena Integrity Kit are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive documentation updates for v0.4.0 features
  - Updated API guide with Sprint 7 endpoints
  - Expanded architecture documentation
  - Enhanced MongoDB schema documentation
  - Extended OpenAPI specification

## [0.4.0] - 2026-02-15

### Added
- **Two-person rule** for high-stakes overrides (S7-1) - Requires second approver for critical operations
- **COP update versioning** with full version history and diff tracking (S7-2)
- **Anti-abuse detection** alerting for rapid-fire override patterns (S7-3)
- **User suspension system** allowing admins to suspend facilitator permissions (S7-4)
- **Data retention TTL** with configurable retention period and automatic purge (S7-5)
- **E2E test suite** for hardening workflows (S7-6)
- **Security hardening** (S7-8)
  - CORS configuration with allowed origins
  - API rate limiting (configurable requests per minute)
  - Security headers (X-Frame-Options, X-Content-Type-Options, CSP, etc.)
  - ReDoS protection
- **Docker Compose** configuration for complete local development stack (S7-9)
- Updated README for v0.4.0 release (S7-10)

## [0.3.0] - 2026-02-01

### Added
- **Operational metrics collection** with five key metrics (S6-1, S6-2)
  - Time-to-validated-update
  - Conflicting-report rate
  - Moderator burden
  - Provenance coverage
  - Readiness distribution
- **Metrics dashboard** with interactive visualizations (S6-3)
- **Enhanced search** showing cluster membership and COP candidate status (S6-4)
- **Configurable redaction rules** for sensitive information in COP drafts (S6-5)
- **LLM prompt caching** optimization for reduced latency and costs (S6-6)
- **Exercise-in-a-Box** facilitator guide (S6-7)
- **Evaluation framework** document with metrics definitions (S6-9)
- Integration tests for metrics collection (S6-8)

## [0.2.0] - 2026-01-15

### Added
- **Risk tier classification** (Routine / Elevated / High-stakes) with facilitator override (S5-1)
- **High-stakes publish gates** requiring Verified status or explicit override with rationale (S5-2)
- **Duplicate merge workflow** with system suggestions and canonical evidence selection (S5-3)
- **Delta summaries** showing "What changed since last COP" (S5-4)
- **Enhanced wording guidance** with recheck-time and next-verification-step for high-stakes items (S5-5)
- LLM output quality evaluation with golden-set tests (S5-7)

## [0.1.0] - 2026-01-01

### Added
- **COP publish workflow** with human approval gates (S4-1 to S4-4)
  - Draft creation from verified candidates
  - Line item editing with audit trail
  - Preview in markdown and Slack Block Kit format
  - Required approval step before publishing
  - Publication to configured Slack channel
- **Slack Block Kit formatting** for published COP updates (S4-2)
- **Full audit logging** for all publish actions (S4-3)
- **Clarification request templates** for gathering additional information (S4-4)
- **Facilitator quick-start guide** (S4-7)
- E2E integration tests for publish pipeline (S4-5, S4-6)

### Sprint 3 - COP Readiness & Drafting
- **Readiness computation** evaluating candidates against minimum fields (S3-1)
  - Ready–Verified / Ready–In Review / Blocked states
- **Missing/weak fields checklist** UI in Slack Block Kit (S3-2)
- **Best next action recommender** (request clarification, assign verification, etc.) (S3-3)
- **COP draft generator** with status labels and evidence-pack citations (S3-4)
- **Sectioned COP update drafts** (Verified, In-Review, Disproven, Open Questions) (S3-5)
- **Wording guidance** with hedged phrasing for In-Review items (S3-6)
- **Conflict blocking** preventing contradictory claims from reaching Verified (S3-7)

### Sprint 2 - RBAC & Facilitator Backlog
- **Role-based access control** with three roles (Participant, Facilitator, Verifier) (S2-1)
- **Role-change audit logging** (S2-2)
- **Private COP backlog** for facilitators with AI-prioritized clusters (S2-3)
- **Promote to COP Candidate** one-click action (S2-4)
- **Facilitator search** endpoint with keyword, time range, and channel filters (S2-5)
- **Slack App Home** view for facilitators (S2-6)
- Access control tests (S2-7, S2-8)

### Sprint 1 - Signal Pipeline & Storage
- **Signal ingestion** from Slack messages with cluster membership and metadata
- **Clustering service** using ChromaDB embeddings and LLM classification
- **Duplicate detection** within clusters using similarity threshold and LLM confirmation
- **Conflict detection** flagging contradictory claims within clusters
- **Retry with backoff** for Slack API ingestion errors
- **AI output labeling** marking system-generated content as draft/suggestion

### Sprint 0 - Foundation
- MongoDB schema design for signals, clusters, COP candidates, updates, and audit log
- OpenAPI 3.1 specification for facilitator API
- LLM prompt templates for clustering, drafting, readiness, and conflict detection
- GitHub Actions CI pipeline (lint, type-check, pytest)
- Dockerfile for deployment
- pytest infrastructure with fixtures and factories
- Architecture documentation and README

[Unreleased]: https://github.com/aidarena/integritykit/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/aidarena/integritykit/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/aidarena/integritykit/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/aidarena/integritykit/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aidarena/integritykit/releases/tag/v0.1.0
## [0.4.0] - 2026-02-15

### Added

#### Sprint 0 — Foundation
- MongoDB schema design for signals, clusters, COP candidates, audit log, and roles
- OpenAPI 3.1 specification for the facilitator API
- LLM prompt templates for clustering, conflict detection, COP drafting, and readiness evaluation
- GitHub Actions CI pipeline (lint, typecheck, test)
- Dockerfile for container deployment
- pytest infrastructure with fixtures and factories
- Architecture documentation and project README

#### Sprint 1 — Signal Pipeline & Storage
- Signal model and Slack ingestion handlers
- Clustering service with ChromaDB embeddings and LLM classification
- Duplicate detection within clusters (similarity threshold + LLM confirmation)
- Conflict detection for contradictory claims within clusters
- Retry-with-backoff for Slack API ingestion errors
- AI output labeling (system-generated metadata on all LLM outputs)

#### Sprint 2 — RBAC & Facilitator Backlog
- Three-role RBAC model (General Participant, Facilitator, Verifier) with enforcement
- Role-change audit logging
- Private COP backlog service with urgency/impact/risk prioritization
- One-click "Promote to COP Candidate" action
- Facilitator search endpoint (keyword + time range + channel, role-gated)
- Slack App Home view for facilitators

#### Sprint 3 — COP Readiness & Drafting
- COP readiness computation (Ready-Verified / Ready-In Review / Blocked)
- Missing/weak fields checklist UI (Slack Block Kit)
- "Best next action" recommender for improving publishability
- COP draft generator with status labels and evidence-pack citations
- Sectioned COP update drafts (Verified, In-Review, Disproven, Open Questions)
- Wording guidance (hedged phrasing for In-Review, direct for Verified)
- Conflict-blocking logic preventing contradictory claims from reaching Verified

#### Sprint 4 — Publish Workflow & Audit
- Full publish workflow: review, edit, approve, publish to Slack
- Slack Block Kit formatted COP updates with readiness badges and citations
- Immutable audit log for all COP lifecycle actions
- Clarification request templates (location, time, source, status, impact, general)
- End-to-end integration tests for the complete COP pipeline

#### Sprint 5 — Risk Gates & Deduplication
- Risk-tier classification (Routine / Elevated / High-stakes) with facilitator override
- High-stakes publish gates (require Verified status or explicit override with rationale)
- Duplicate merge workflow with canonical evidence set selection
- "What changed since last COP" delta summary generation
- Recheck-time and next-verification-step for high-stakes In-Review wording
- LLM output quality evaluation with golden-set tests

#### Sprint 6 — Metrics & Exercise Prep
- Operational metrics collection (time-to-validated-update, conflicting-report rate, moderator burden, provenance coverage, readiness distribution)
- Metrics API endpoint with JSON/CSV export
- Metrics dashboard with readiness distribution chart and trend visualizations
- Configurable redaction rules for sensitive info in COP drafts
- LLM prompt caching optimization for system prompts and clustering templates
- Exercise-in-a-Box facilitator guide
- Evaluation framework document

#### Sprint 7 — Hardening & Release
- Two-person rule for high-stakes overrides
- COP update versioning with full diff tracking and evidence preservation
- Anti-abuse detection for rapid-fire override patterns
- User suspension system with audit logging
- Data-retention TTL with configurable purge mechanism
- Security hardening: CORS, rate limiting, security headers, ReDoS protection
- Docker Compose for local development (MongoDB, ChromaDB, Mongo Express)
- E2E test suite for hardening workflows

## [Unreleased]

### Planned
- Multi-language support (Spanish, French)
- Advanced analytics and reporting
- External system integrations
