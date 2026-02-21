# Changelog

All notable changes to the Aid Arena Integrity Kit are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
