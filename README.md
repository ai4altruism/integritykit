# Aid Arena Integrity Kit

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![License](https://img.shields.io/badge/license-MIT-brightgreen)

An open-source coordination layer for crisis response that turns chaotic messages into provenance-backed updates, enabling collective verification, safer organizing, and faster, fairer decisions.

## Overview

The Aid Arena Integrity Kit is a human-AI collaboration platform that helps crisis coordinators transform fast-moving Slack conversations into structured, citation-backed situational awareness updates. AI clusters related reports, surfaces corroborating evidence, and drafts publication-ready wording, while humans perform all verification and validation. Every claim links back to its source evidence, creating an auditable chain of trust from raw message to published update.

Unlike traditional emergency management tools that require participants to file forms or learn new interfaces, this system operates in ambient mode: general participants continue using Slack normally while a small team of facilitators uses AI-assisted tooling to produce accurate COP updates. The result is accountability without bureaucracy: full provenance and audit trails without slowing down response.

### What It Does

- Continuously ingests Slack messages from monitored channels
- Clusters related messages by topic/incident using LLM classification
- Detects duplicate reports and conflicting information
- Surfaces a prioritized backlog of clusters for facilitator review
- Provides a verification workflow with readiness gates for high-stakes information
- Generates draft COP updates with verification-aware wording in multiple languages (English, Spanish, French)
- Publishes provenance-backed updates (every claim links to source evidence)
- Exports to standard emergency management formats (CAP 1.2, EDXL-DE, GeoJSON)
- Integrates with external systems via webhooks and verified data sources
- Provides advanced analytics and after-action reporting
- Maintains full audit logging and role-based access control

### Who It's For

**Primary users:**
- Crisis response coordinators managing multi-channel Slack workspaces
- Emergency management teams running exercises or real-world incidents
- Mutual aid networks coordinating disaster response

**Key value proposition:**
- **Reduces information overload**: Facilitators review a curated, AI-prioritized backlog instead of scanning all channels
- **Increases accuracy**: Verification workflow and conflict detection catch errors before publication
- **Builds trust through transparency**: Every published claim links to source evidence—full provenance from raw Slack message to COP update, with immutable audit logs tracking every action
- **Keeps humans in control**: AI surfaces evidence and drafts wording; humans perform all verification and validation. No update goes out without explicit human approval

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         SLACK WORKSPACE                         │
│  #operations  #logistics  #medical  #shelter  #rumor-control    │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                │ Slack Events API
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SIGNAL INGESTION PIPELINE                  │
│  ┌──────────┐   ┌──────────┐   ┌────────────┐   ┌───────────┐ │
│  │  Slack   │──▶│  Store   │──▶│  Embed &   │──▶│  Cluster  │ │
│  │ Listener │   │ MongoDB  │   │  Index in  │   │  Related  │ │
│  │          │   │          │   │  ChromaDB  │   │  Signals  │ │
│  └──────────┘   └──────────┘   └────────────┘   └───────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  FACILITATOR WORKFLOW (PRIVATE)                 │
│                                                                 │
│  ┌────────────────────┐                                        │
│  │  COP BACKLOG       │  AI-prioritized clusters               │
│  │  ────────────────  │  awaiting promotion                    │
│  │  • Shelter Alpha   │                                        │
│  │    closure (5 msg) │                                        │
│  │  • Bridge damage   │                                        │
│  │    (8 msg) 🔴      │  🔴 = conflict detected                │
│  │  • Water advisory  │                                        │
│  │    (3 msg)         │                                        │
│  └────────┬───────────┘                                        │
│           │ Promote to Candidate                               │
│           ▼                                                     │
│  ┌────────────────────┐                                        │
│  │  COP CANDIDATES    │  Verification workflow                 │
│  │  ────────────────  │                                        │
│  │  ✅ Shelter Alpha  │  ✅ Ready - Verified                   │
│  │  🟨 Water advisory │  🟨 Ready - In Review                  │
│  │  🟥 Bridge damage  │  🟥 Blocked (conflict unresolved)      │
│  └────────┬───────────┘                                        │
│           │ Draft & Approve                                    │
│           ▼                                                     │
│  ┌────────────────────┐                                        │
│  │  COP UPDATE DRAFT  │  AI-generated with human edits         │
│  │  ────────────────  │                                        │
│  │  [VERIFIED]        │                                        │
│  │  Shelter Alpha...  │                                        │
│  │  (citations: ...)  │                                        │
│  │                    │                                        │
│  │  [IN REVIEW]       │                                        │
│  │  Unconfirmed: ...  │                                        │
│  └────────┬───────────┘                                        │
│           │ Publish                                            │
│           ▼                                                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 PUBLISHED COP (PUBLIC CHANNEL)                  │
│  Posted to #cop-updates with full provenance and citations     │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Signal Ingestion**: Slack messages flow continuously into MongoDB and are embedded in ChromaDB for semantic search
2. **Clustering**: LLM assigns each signal to topic/incident clusters based on content similarity
3. **Conflict Detection**: System flags contradictory information within clusters
4. **Backlog Prioritization**: Clusters ranked by urgency, impact, and risk scores
5. **Promotion to Candidates**: Facilitators promote important clusters to the COP candidate pipeline
6. **Readiness Evaluation**: System checks completeness (who/what/when/where/so-what/evidence) and verification status
7. **COP Drafting**: LLM generates publication-ready text with verification-aware wording (direct for verified, hedged for in-review)
8. **Human Approval**: Facilitators review, edit, and approve drafts
9. **Publication**: Versioned COP update posts to Slack with full citation links

## Quick Start

### Prerequisites

- Python 3.11+
- MongoDB 7.0+
- ChromaDB (embedded or server)
- Slack workspace with bot token
- OpenAI API key (for LLM operations)

### Installation

Clone the repository:

```bash
git clone https://github.com/ai4altruism/integritykit.git
cd integritykit
```

Create a virtual environment and install dependencies:

```bash
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Configuration

Create a `.env` file in the project root:

```bash
# Slack Configuration
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_APP_TOKEN=xapp-your-app-token

# MongoDB Configuration
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=integritykit

# ChromaDB Configuration
CHROMA_HOST=localhost
CHROMA_PORT=8000
CHROMA_COLLECTION=integrity_signals

# OpenAI API (for LLM operations)
OPENAI_API_KEY=sk-your-api-key

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### Slack App Setup

1. Create a new Slack app at https://api.slack.com/apps
2. Enable Socket Mode and generate an App Token
3. Add Bot Token Scopes:
   - `channels:history` - Read channel history
   - `channels:read` - View channel information
   - `chat:write` - Post messages
   - `groups:history` - Read private channel history
   - `users:read` - View user information
4. Subscribe to Events:
   - `message.channels` - Public channel messages
   - `message.groups` - Private channel messages
5. Install the app to your workspace

### Running Locally

Start MongoDB and ChromaDB (if not already running):

```bash
# MongoDB (using Docker)
docker run -d -p 27017:27017 --name mongodb mongo:7.0

# ChromaDB (using Docker)
docker run -d -p 8000:8000 --name chromadb chromadb/chroma:latest
```

Run the application:

```bash
# Development mode with auto-reload
uvicorn integritykit.main:app --reload --host 0.0.0.0 --port 8080
```

The application will be available at:

- **API**: http://localhost:8080
- **API Docs**: http://localhost:8080/docs
- **Metrics Dashboard**: http://localhost:8080/dashboard
- **Analytics Dashboard**: http://localhost:8080/analytics

## Facilitator Quick-Start

See the [Facilitator Guide](docs/facilitator-guide.md) for the complete workflow including:

- Backlog monitoring and cluster promotion
- COP candidate verification workflow
- Draft generation with verification-aware wording
- Human approval gates and Slack publishing
- Clarification templates and audit trails

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SLACK_BOT_TOKEN` | Yes | - | Slack bot user OAuth token (xoxb-...) |
| `SLACK_SIGNING_SECRET` | Yes | - | Slack app signing secret |
| `SLACK_APP_TOKEN` | Yes | - | Slack app-level token (xapp-...) for Socket Mode |
| `MONGODB_URI` | Yes | - | MongoDB connection string |
| `MONGODB_DATABASE` | No | `integritykit` | MongoDB database name |
| `CHROMA_HOST` | No | `localhost` | ChromaDB server host |
| `CHROMA_PORT` | No | `8000` | ChromaDB server port |
| `CHROMA_COLLECTION` | No | `integrity_signals` | ChromaDB collection name |
| `OPENAI_API_KEY` | Yes | - | OpenAI API key for LLM operations |
| `ENVIRONMENT` | No | `development` | Environment name (development, staging, production) |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `DATA_RETENTION_DAYS` | No | `90` | Signal retention period in days |
| `SUPPORTED_LANGUAGES` | No | `en` | Comma-separated list of language codes (en, es, fr) |
| `WEBHOOKS_ENABLED` | No | `false` | Enable outbound webhook notifications |
| `CAP_EXPORT_ENABLED` | No | `false` | Enable CAP 1.2 XML export |
| `GEOJSON_EXPORT_ENABLED` | No | `false` | Enable GeoJSON export for mapping |

### Role-Based Access Control

Configure user roles via the API or MongoDB directly:

- **general_participant**: Read-only access to published COPs (default for all workspace users)
- **facilitator**: Full backlog and candidate management, COP publishing
- **verifier**: Can record verification actions on candidates
- **workspace_admin**: User and role management, system configuration

See [docs/openapi.yaml](docs/openapi.yaml) for role management API endpoints.

## Development

### Project Structure

```
integritykit/
├── src/
│   └── integritykit/
│       ├── __init__.py
│       ├── llm/                    # LLM prompt engineering
│       │   └── prompts/
│       │       ├── clustering.py
│       │       ├── conflict_detection.py
│       │       ├── cop_draft_generation.py
│       │       ├── next_action.py
│       │       └── readiness_evaluation.py
│       ├── api/                    # FastAPI routes
│       ├── models/                 # Pydantic models
│       ├── database/               # MongoDB repositories
│       ├── slack/                  # Slack integration
│       └── services/               # Business logic
├── tests/
│   ├── unit/                       # Fast, isolated tests
│   ├── integration/                # Database and API tests
│   ├── e2e/                        # End-to-end tests
│   ├── performance/                # Performance benchmarks
│   └── fixtures/                   # Test data and factories
├── docs/
│   ├── cdd.md                       # Capability Description Document
│   ├── srs.md                       # System Requirements Specification
│   ├── architecture.md              # System architecture
│   ├── mongodb-schema.md            # Database schema
│   ├── api-guide.md                 # API reference
│   ├── analytics.md                 # Analytics guide
│   ├── multi-language.md            # Multi-language support
│   ├── external-integrations.md     # Webhooks, exports, sources
│   └── openapi.yaml                 # OpenAPI specification
├── Dockerfile
├── pyproject.toml
└── README.md
```

### Code Style

This project uses:

- **ruff** for linting and formatting
- **mypy** for type checking
- **pytest** for testing

Run quality checks:

```bash
# Linting and auto-fix
ruff check --fix .

# Type checking
mypy src

# All checks (run this before committing)
pre-commit run --all-files
```

### Running Tests

Run the full test suite:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=integritykit --cov-report=html
```

Run specific test categories:

```bash
pytest tests/unit/           # Fast unit tests
pytest tests/integration/    # Database and API tests
pytest tests/e2e/           # End-to-end tests
pytest tests/performance/   # Performance benchmarks
```

### Adding New LLM Prompts

See [docs/prompts.md](docs/prompts.md) for prompt engineering guidelines.

Example prompt module structure:

```python
# src/integritykit/llm/prompts/example.py

EXAMPLE_SYSTEM_PROMPT = """
You are an expert at [task description].
[Instructions and constraints]
"""

EXAMPLE_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["field1", "field2"],
    "properties": {
        "field1": {"type": "string"},
        "field2": {"type": "number"}
    }
}

def format_example_prompt(data: dict) -> str:
    """Format user prompt for example task."""
    return f"""
INPUT DATA:
{json.dumps(data, indent=2)}

OUTPUT:
Provide response as JSON matching the schema.
"""
```

## Deployment

### Docker

Build the Docker image:

```bash
docker build -t integritykit:latest .
```

Run the container:

```bash
docker run -d \
  --name integritykit \
  -p 8080:8080 \
  --env-file .env \
  integritykit:latest
```

### Docker Compose

A complete `docker-compose.yml` is included for local development with MongoDB, ChromaDB, and optional Mongo Express for database management.

1. Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env with your Slack and OpenAI credentials
```

2. Start the full stack:

```bash
docker-compose up -d
```

3. Optionally, include Mongo Express for database management:

```bash
docker-compose --profile tools up -d
# Access Mongo Express at http://localhost:8081
```

Services:
- **App**: http://localhost:8000 - Main API and dashboard
- **MongoDB**: localhost:27017 - Document database
- **ChromaDB**: localhost:8001 - Vector database for embeddings
- **Mongo Express** (optional): http://localhost:8081 - Database UI

### Security Configuration

IntegrityKit includes several security hardening features (v0.4.0+):

| Feature | Environment Variable | Default | Description |
|---------|---------------------|---------|-------------|
| CORS | `CORS_ALLOWED_ORIGINS` | (empty) | Comma-separated list of allowed origins |
| Rate Limiting | `RATE_LIMIT_ENABLED` | `true` | Enable API rate limiting |
| Rate Limit | `RATE_LIMIT_REQUESTS_PER_MINUTE` | `60` | Max requests per minute per user |
| Two-Person Rule | `TWO_PERSON_RULE_ENABLED` | `true` | Require second approver for high-stakes |
| Abuse Detection | `ABUSE_DETECTION_ENABLED` | `true` | Alert on rapid-fire overrides |

Security headers included by default:
- `X-Frame-Options: DENY` - Clickjacking protection
- `X-Content-Type-Options: nosniff` - MIME type sniffing prevention
- `X-XSS-Protection: 1; mode=block` - XSS protection
- `Content-Security-Policy` - CSP for dashboard
- `Referrer-Policy: strict-origin-when-cross-origin`

### Environment-Specific Configuration

For production deployments:

1. Use managed MongoDB (MongoDB Atlas, AWS DocumentDB)
2. Enable authentication and TLS for MongoDB
3. Use secrets management (AWS Secrets Manager, HashiCorp Vault)
4. Configure log aggregation (Datadog, CloudWatch)
5. Set up monitoring and alerting
6. Enable backup and disaster recovery
7. Configure `CORS_ALLOWED_ORIGINS` for your frontend domains
8. Review and adjust rate limiting based on expected traffic

## Documentation

### Core Documentation

- [Capability Description Document (CDD)](docs/cdd.md) - Product requirements and operating concept
- [System Requirements Specification (SRS)](docs/srs.md) - Functional and non-functional requirements
- [Architecture Documentation](docs/architecture.md) - Detailed system architecture and design
- [MongoDB Schema](docs/mongodb-schema.md) - Database design and schema documentation
- [API Reference](docs/openapi.yaml) - OpenAPI 3.1 specification
- [LLM Prompt Design](docs/prompts.md) - Prompt engineering guide and templates

### Feature Guides

- [API Guide](docs/api-guide.md) - Complete API reference with examples
- [Multi-Language Support](docs/multi-language.md) - Configure and use Spanish/French COP drafts
- [External Integrations](docs/external-integrations.md) - Webhooks, CAP, EDXL-DE, GeoJSON exports
- [Analytics](docs/analytics.md) - Time-series metrics, trends, and after-action reporting

### Operations

- [Deployment Runbook](docs/deployment-runbook.md) - Production deployment guide
- [Migration Guide](docs/migration.md) - Upgrading from v0.4.0 to v1.0
- [Security Review](docs/security-review.md) - Security audit and recommendations

## Contributing

We welcome contributions from the crisis response and open-source communities.

### Getting Started

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes and add tests
4. Run quality checks: `pre-commit run --all-files`
5. Run tests: `pytest`
6. Commit with clear messages: `git commit -m "Add feature: your feature description"`
7. Push to your fork: `git push origin feature/your-feature-name`
8. Open a pull request

### Contribution Guidelines

- All new features must include tests (aim for >80% coverage)
- Follow existing code style (enforced by ruff)
- Add type hints for all functions (checked by mypy)
- Update documentation for user-facing changes
- Add changelog entries for notable changes
- Be respectful and collaborative in discussions

### Code of Conduct

This project follows the [Contributor Covenant](https://www.contributor-covenant.org/) code of conduct.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Support and Contact

- GitHub Issues: https://github.com/ai4altruism/integritykit/issues
- Documentation: https://github.com/ai4altruism/integritykit#readme

## Acknowledgments

The Aid Arena Integrity Kit builds on the foundation of the Chat-Diver application and is informed by real-world crisis coordination needs identified by the Aid Arena community, developed in partnership with crisis response organizations committed to improving information fidelity during emergencies.

## Roadmap

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

### Current: v1.0.0

- Multi-language COP drafts (English, Spanish, French)
- External integrations (webhooks, CAP 1.2, EDXL-DE, GeoJSON)
- Advanced analytics and after-action reporting
- Integration health monitoring

### Planned: v1.1

- Enhanced GIS integration
- Additional EDXL protocols (SitRep, HAVE)
- Mobile-optimized interface

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.
