# Changelog

All notable changes to the Aid Arena Integrity Kit are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v1.1
- Enhanced GIS integration and spatial analysis
- Additional emergency management protocols (EDXL-SitRep, EDXL-HAVE)
- Mobile-optimized App Home interface
- GraphQL API support
- Advanced AI features for automated verification

## [1.0.0] - 2026-03-13

### Multi-Language Support
- **Spanish and French COP drafts** (S8-2, S8-3, S8-4, S8-5)
  - Language detection service with confidence thresholds
  - Localized LLM prompts for Spanish and French
  - Multi-language COP draft generation with appropriate wording styles
  - Internationalized Slack Block Kit templates with translated status labels
  - Status label translations: VERIFICADO/VÉRIFIÉ, EN REVISIÓN/EN RÉVISION, BLOQUEADO/BLOQUÉ
  - Section header translations for verified updates, in-review reports, open questions

### External Integrations
- **Outbound webhooks** (S8-17)
  - Real-time event notifications for cop_update.published, cop_candidate.verified, cop_candidate.promoted, cluster.created
  - Multiple authentication methods: Bearer token, Basic auth, API key, Custom header
  - Automatic retry with exponential backoff (configurable)
  - HMAC payload signing for verification
  - Delivery tracking and webhook health monitoring
  - Test endpoint for webhook validation
- **CAP 1.2 XML export** (S8-18)
  - Common Alerting Protocol export for public alerting systems
  - Field mapping: verification status → certainty, risk tier → urgency/severity
  - Multi-language CAP support with separate <info> blocks
  - Location data converted to CAP circle/polygon format
- **EDXL-DE 2.0 export** (S8-19)
  - Emergency Data Exchange Language distribution envelope
  - Standardized message routing for emergency management systems
- **GeoJSON export** (S8-21)
  - Location data export for mapping platforms (Leaflet, Mapbox, Google Maps)
  - Feature properties include what/where/when/who/so_what fields
  - Citation links and verification status in properties
- **External verification sources** (S8-20)
  - Inbound API integration with government/NGO/verified reporter sources
  - Trust level configuration (high/medium/low) affecting auto-promotion behavior
  - Duplicate detection to prevent redundant candidate creation
  - Provenance tracking in audit trail
  - Multiple authentication types: API key, Bearer token, OAuth 2.0

### Advanced Analytics
- **Time-series analytics API** (S8-9, S8-10, S8-11, S8-12)
  - Signal volume time-series with channel breakdown
  - Readiness state transition tracking (IN_REVIEW→VERIFIED, VERIFIED→BLOCKED, etc.)
  - Facilitator action metrics with action velocity (actions per hour)
  - Topic trend detection: emerging, declining, and stable topics
  - Conflict resolution time analysis
  - Granularity options: hour, day, week
  - Multi-metric queries for efficient dashboard updates
- **After-action report export** (S8-14, S8-15)
  - Comprehensive post-incident reports with executive summary
  - Signal processing metrics, COP production stats, facilitator performance
  - Conflict management analysis, timeline breakdown
  - JSON and Markdown export formats
  - Configurable time ranges for exercise or incident periods

### Integration Health Monitoring
- **Health monitoring dashboard** (S8-22)
  - Overall integration status: healthy, degraded, unhealthy
  - Webhook metrics: success rate, failed deliveries, avg response time
  - External source metrics: sync status, items imported, sync errors
  - Export metrics: CAP/GeoJSON/EDXL counts, export failures, avg export time
  - Alerting for webhook success rate drops, source sync failures, export errors
- **Integration tests** (S8-23)
  - Unit tests for webhooks, CAP export, EDXL-DE export, GeoJSON export
  - External source import testing with mock APIs
  - Analytics service tests for time-series calculations
  - After-action report generation tests

### Documentation
- **Updated API documentation** (S8-30)
  - Added Sprint 8 endpoints for analytics, integrations, exports
  - Multi-language draft creation examples
  - Webhook management API reference
  - Integration health monitoring endpoints
- **Multi-language configuration guide** (S8-31)
  - Supported languages and translation tables
  - Environment variable configuration
  - LLM prompt localization guide
  - Slack Block Kit internationalization
- **External integrations guide** (S8-32)
  - Webhook setup and authentication
  - CAP 1.2 export field mapping
  - EDXL-DE and GeoJSON export usage
  - External source configuration and trust levels
  - Integration health monitoring
- **Advanced analytics user guide** (S8-33)
  - Available metrics and time-series queries
  - Topic trend detection examples
  - Facilitator workload analytics
  - Conflict resolution analysis
  - After-action report generation
  - Dashboard integration examples
- **Updated README for v1.0** (S8-34)
  - Added v1.0 features to overview
  - Updated feature list with multi-language, integrations, analytics
  - Added new documentation links
  - Updated environment variable table
- **v1.0 migration guide** (S8-35)
  - Step-by-step upgrade instructions from v0.4.0
  - New environment variables and configuration
  - Database migration scripts
  - Rollback procedures
  - Troubleshooting common migration issues
- **Finalized CHANGELOG** (S8-36)
  - Complete v1.0 release notes with all Sprint 8 features

### Technical Improvements
- New MongoDB collections: webhooks, webhook_deliveries, external_sources, import_jobs
- Optimized indexes for analytics queries (audit_log, signals, cop_candidates)
- Webhook delivery job queue with retry logic
- Language detection with confidence scoring
- Multi-language prompt registry with fallback to English
- Export caching for improved performance

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

[Unreleased]: https://github.com/aidarena/integritykit/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/aidarena/integritykit/compare/v0.4.0...v1.0.0
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

