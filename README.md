# Aid Arena Integrity Kit

Open-source Slack coordination layer for crisis-response communities that produces provenance-backed Common Operating Picture (COP) updates.

## Overview

The Aid Arena Integrity Kit is a background processing system that helps crisis coordinators turn fast-moving Slack conversations into structured, citation-backed situational awareness updates. Unlike traditional emergency management tools that require participants to file forms or learn new interfaces, this system operates in ambient mode: general participants continue using Slack normally while a small team of facilitators uses AI-assisted tooling to produce accurate COP updates.

### What It Does

- Continuously ingests Slack messages from monitored channels
- Clusters related messages by topic/incident using LLM classification
- Detects duplicate reports and conflicting information
- Surfaces a prioritized backlog of clusters for facilitator review
- Provides a verification workflow with readiness gates for high-stakes information
- Generates draft COP updates with verification-aware wording
- Publishes provenance-backed updates (every claim links to source evidence)
- Maintains full audit logging and role-based access control

### Who It's For

**Primary users:**
- Crisis response coordinators managing multi-channel Slack workspaces
- Emergency management teams running exercises or real-world incidents
- Mutual aid networks coordinating disaster response

**Key value proposition:**
- Reduces information overload: facilitators review curated backlog instead of scanning all channels
- Increases accuracy: verification workflow and conflict detection catch errors before publication
- Provides accountability: full provenance chain from raw Slack messages to published updates
- Preserves human judgment: AI provides suggestions, humans make all publishing decisions

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
git clone https://github.com/aidarena/integritykit.git
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

The API will be available at http://localhost:8080

## Facilitator Quick-Start Guide

This guide covers the end-to-end workflow for facilitators publishing COP updates.

### Overview

As a facilitator, you coordinate the transformation of Slack conversations into verified situational awareness updates. The system helps you:

1. Monitor the prioritized backlog of clustered signals
2. Promote important clusters to COP candidates
3. Review and verify candidate information
4. Generate draft COP updates with proper wording
5. Approve and publish updates to Slack

### Publish Workflow

The publish workflow ensures human approval at every step:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   CREATE    │───▶│    EDIT     │───▶│   APPROVE   │───▶│   PUBLISH   │
│    DRAFT    │    │  (optional) │    │  (required) │    │  to Slack   │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
```

#### Step 1: Create Draft

Select one or more verified COP candidates and generate a draft:

```http
POST /api/v1/publish/drafts
{
  "candidate_ids": ["candidate-id-1", "candidate-id-2"],
  "title": "Crisis Update #5"
}
```

The system generates line items with:
- **VERIFIED** status for confirmed information (direct factual wording)
- **IN REVIEW** status for unconfirmed reports (hedged wording: "Unconfirmed reports indicate...")

#### Step 2: Edit Line Items (Optional)

Review the auto-generated text and edit if needed:

```http
PATCH /api/v1/publish/drafts/{update_id}/line-items
{
  "item_index": 0,
  "new_text": "Corrected text here"
}
```

All edits are logged with before/after snapshots for audit purposes.

#### Step 3: Preview

View how the update will appear in Slack:

```http
GET /api/v1/publish/drafts/{update_id}/preview
```

Returns both markdown and Slack Block Kit format.

#### Step 4: Approve (Required)

No update can be published without explicit human approval:

```http
POST /api/v1/publish/drafts/{update_id}/approve
{
  "notes": "Reviewed and verified all items"
}
```

This is the critical safety gate - the system will not post anything to Slack without this step.

#### Step 5: Publish

After approval, publish to your designated Slack channel:

```http
POST /api/v1/publish/drafts/{update_id}/publish
{
  "channel_id": "C123456789"
}
```

The update is posted with:
- Formatted Block Kit sections for Verified/In Review/Rumor Control
- Clickable citation links to source messages
- IntegrityKit attribution and facilitator review notice

### Clarification Templates

When you need additional information from reporters, use pre-built templates:

```http
POST /api/v1/publish/clarification-template
{
  "template_type": "location",
  "topic": "shelter opening"
}
```

Available template types:
| Type | Purpose |
|------|---------|
| `location` | Request specific address or landmark details |
| `time` | Clarify when something occurred or is expected |
| `source` | Ask for verification source or eyewitness status |
| `status` | Request current status update |
| `impact` | Understand who/what is affected |
| `general` | General follow-up request |

### Audit Trail

Every action is logged for transparency and accountability:

```http
GET /api/v1/audit/logs?target_type=cop_update&target_id={update_id}
```

The audit log captures:
- Who performed each action (actor ID and role)
- What changed (before/after state)
- When it happened (immutable timestamp)
- Why (justification notes for approvals)

### Common Workflows

#### Publishing a Single Verified Item

1. Navigate to COP Candidates list
2. Select a VERIFIED candidate
3. Create draft → Preview → Approve → Publish

#### Handling Conflicting Information

1. Identify candidates with conflicts (🔴 indicator)
2. Use clarification templates to gather more info
3. Resolve conflict in the candidate workflow
4. Only then include in a COP draft

#### Creating a Mixed Update

1. Select multiple candidates (some verified, some in-review)
2. System automatically sections them appropriately
3. Verified items get direct wording
4. In-review items get hedged wording ("Unconfirmed reports...")
5. Open questions appear in a separate section

### Running Tests

Run the full test suite:

```bash
pytest
```

Run with coverage:

```bash
pytest --cov=integritykit --cov-report=html
```

Run only unit tests (fast):

```bash
pytest -m unit
```

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
│   └── fixtures/                   # Test data and factories
├── docs/
│   ├── Aid_Arena_Integrity_Kit_CDD_Ambient_v0_4.md
│   ├── Aid_Arena_Integrity_Kit_SRS_Ambient_v0_4.md
│   ├── mongodb_schema.md
│   ├── openapi.yaml
│   ├── prompts.md
│   └── architecture.md
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

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:7.0
    ports:
      - "27017:27017"
    volumes:
      - mongodb_data:/data/db

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8000:8000"
    volumes:
      - chromadb_data:/chroma/chroma

  integritykit:
    build: .
    ports:
      - "8080:8080"
    env_file: .env
    depends_on:
      - mongodb
      - chromadb

volumes:
  mongodb_data:
  chromadb_data:
```

Run the stack:

```bash
docker-compose up -d
```

### Environment-Specific Configuration

For production deployments:

1. Use managed MongoDB (MongoDB Atlas, AWS DocumentDB)
2. Enable authentication and TLS for MongoDB
3. Use secrets management (AWS Secrets Manager, HashiCorp Vault)
4. Configure log aggregation (Datadog, CloudWatch)
5. Set up monitoring and alerting
6. Enable backup and disaster recovery

## Documentation

- [Capability Description Document (CDD)](docs/Aid_Arena_Integrity_Kit_CDD_Ambient_v0_4.md) - Product requirements and operating concept
- [System Requirements Specification (SRS)](docs/Aid_Arena_Integrity_Kit_SRS_Ambient_v0_4.md) - Functional and non-functional requirements
- [Architecture Documentation](docs/architecture.md) - Detailed system architecture and design
- [MongoDB Schema](docs/mongodb_schema.md) - Database design and schema documentation
- [API Reference](docs/openapi.yaml) - OpenAPI 3.1 specification
- [LLM Prompt Design](docs/prompts.md) - Prompt engineering guide and templates

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

- GitHub Issues: https://github.com/aidarena/integritykit/issues
- Email: team@aidarena.org
- Documentation: https://github.com/aidarena/integritykit#readme

## Acknowledgments

The Aid Arena Integrity Kit builds on the foundation of the Chat-Diver application and is informed by real-world crisis coordination needs identified by the Aid Arena community.

This project is funded by [funding source] and developed in partnership with crisis response organizations committed to improving information fidelity during emergencies.

## Roadmap

### MVP (Complete)
- ✅ Signal ingestion and clustering
- ✅ Backlog management and promotion workflow
- ✅ Readiness evaluation and conflict detection
- ✅ COP draft generation with verification-aware wording
- ✅ **COP publish workflow with human approval gates** (Sprint 4)
- ✅ **Slack Block Kit formatted output** (Sprint 4)
- ✅ **Full audit logging for publish actions** (Sprint 4)
- ✅ RBAC and role-based permissions
- ✅ Facilitator search

### Pilot (In Progress)
- Risk tier classification and publish gates
- Duplicate merge workflow
- Delta summaries between COP versions
- Clarification request integration with Slack
- Metrics and instrumentation
- Redaction rules for sensitive information

### v1.0 (Planned)
- Two-person rule for high-stakes overrides
- Data retention policies
- Anti-abuse detection
- Exportable metrics for post-exercise evaluation
- Multi-language support (Spanish, French)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.
