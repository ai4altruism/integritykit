# External Integration Architecture - v1.0

**Document Version:** 1.0
**Date:** 2026-03-10
**Sprint:** Sprint 8
**Status:** Design Complete

---

## 1. Executive Summary

This document describes the external integration architecture for the Aid Arena Integrity Kit v1.0 release. The integration layer enables the Integrity Kit to function as part of a broader emergency management ecosystem by:

- **Pushing updates** to external systems via webhooks
- **Exporting data** in standard emergency management formats (CAP, EDXL-DE, GeoJSON)
- **Importing verified data** from authoritative external sources
- **Monitoring integration health** for operational reliability

The design follows REST API best practices, supports standard emergency management protocols, and maintains security and provenance throughout the integration lifecycle.

---

## 2. Architecture Overview

### 2.1 Integration Components

```
┌─────────────────────────────────────────────────────────┐
│                   Integrity Kit Core                    │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │   Backlog   │→│  Candidates  │→│  COP Updates  │ │
│  └─────────────┘  └──────────────┘  └───────────────┘ │
│                           ↓                ↓            │
└───────────────────────────┼────────────────┼────────────┘
                            │                │
            ┌───────────────┴────────────────┴──────────┐
            │       Integration Layer (v1.0)            │
            │                                            │
            │  ┌──────────────────────────────────────┐ │
            │  │  Outbound: Webhooks & Exports        │ │
            │  │  - Event notification webhooks       │ │
            │  │  - CAP 1.2 XML export               │ │
            │  │  - EDXL-DE export                   │ │
            │  │  - GeoJSON export                   │ │
            │  └──────────────────────────────────────┘ │
            │                                            │
            │  ┌──────────────────────────────────────┐ │
            │  │  Inbound: Verification Sources       │ │
            │  │  - Government API integration        │ │
            │  │  - NGO feed import                   │ │
            │  │  - Verified reporter systems         │ │
            │  └──────────────────────────────────────┘ │
            │                                            │
            │  ┌──────────────────────────────────────┐ │
            │  │  Health Monitoring                   │ │
            │  │  - Webhook delivery tracking         │ │
            │  │  - Source sync status                │ │
            │  │  - Error rate monitoring             │ │
            │  └──────────────────────────────────────┘ │
            └────────────────────────────────────────────┘
                            │                │
                            ↓                ↓
┌──────────────────┐  ┌─────────────────────────────────┐
│ External Systems │  │  Emergency Management Systems   │
│ - Mapping tools  │  │  - Public alerting platforms    │
│ - Dashboards     │  │  - EOC systems                  │
│ - Analytics      │  │  - Government APIs              │
└──────────────────┘  └─────────────────────────────────┘
```

### 2.2 Design Principles

1. **Standards-Based:** Use established emergency management protocols (CAP, EDXL-DE)
2. **Security-First:** Authentication, input validation, rate limiting on all integrations
3. **Resilient:** Retry logic, failure handling, graceful degradation
4. **Observable:** Comprehensive logging, health monitoring, delivery tracking
5. **Provenance-Preserving:** External sources are tracked in audit trail
6. **Bi-Directional:** Both push (webhooks) and pull (API exports) patterns supported

---

## 3. Outbound Integrations

### 3.1 Webhook System

**Purpose:** Notify external systems in real-time when events occur in the Integrity Kit.

#### Event Types

| Event | Trigger | Payload Includes |
|-------|---------|------------------|
| `cop_update.published` | COP update published to Slack | Update ID, version, language, line items, export links |
| `cop_candidate.verified` | Candidate receives verification | Candidate ID, verification method, confidence level |
| `cop_candidate.promoted` | Cluster promoted to candidate | Candidate ID, cluster ID, risk tier |
| `cluster.created` | New cluster formed | Cluster ID, topic type, signal count, priority score |

#### Webhook Configuration

```json
{
  "name": "Emergency Operations Center Webhook",
  "url": "https://eoc.example.org/api/webhooks/integritykit",
  "events": ["cop_update.published", "cop_candidate.verified"],
  "auth_type": "bearer",
  "auth_config": {
    "token": "your_secret_token"
  },
  "retry_config": {
    "max_retries": 3,
    "retry_delay_seconds": 60,
    "backoff_multiplier": 2.0
  },
  "enabled": true
}
```

#### Delivery Semantics

- **At-least-once delivery:** Webhooks may be delivered more than once in failure scenarios
- **Retry with exponential backoff:** Failed deliveries retry with increasing delays
- **Timeout:** 10 seconds per delivery attempt
- **Idempotency:** Webhooks include event ID for deduplication by receiver

#### Security

- HTTPS required in production
- Supported auth types: Bearer token, Basic auth, Custom header
- Webhook URLs validated (no localhost, private IPs in production)
- Rate limiting: Max 1000 webhooks/hour per destination

### 3.2 CAP 1.2 Export

**Purpose:** Export COP updates as Common Alerting Protocol XML for public alerting systems.

#### CAP Field Mapping

| COP Field | CAP Field | Mapping Logic |
|-----------|-----------|---------------|
| COP Update ID | `alert/identifier` | `cop-update-{id}` |
| Organization | `alert/sender` | Configured org identifier |
| Published timestamp | `alert/sent` | ISO 8601 datetime |
| Update type | `alert/msgType` | Always "Update" |
| Verification status | `info/certainty` | verified → Observed, in_review → Likely |
| Risk tier | `info/urgency` | high_stakes → Immediate, elevated → Expected |
| What field | `info/headline` + `info/description` | Headline from draft wording |
| Location | `info/area` | Coordinates converted to CAP circle/polygon |
| When field | `info/effective` | Event timestamp |
| Categories | `info/category` | Mapped from topic type |

#### Export Rules

1. **Only verified items** can be exported to CAP format
2. **In-review items** are excluded (CAP requires certainty)
3. **Language support:** Multi-language COP updates create separate CAP `<info>` blocks
4. **Geospatial:** Coordinates converted to CAP circle format (`lat,lon radius`)

#### Example CAP Output

```xml
<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>cop-update-67890</identifier>
  <sender>integritykit@aidarena.org</sender>
  <sent>2026-03-10T14:30:00-00:00</sent>
  <status>Actual</status>
  <msgType>Update</msgType>
  <scope>Public</scope>
  <info>
    <language>en-US</language>
    <category>Shelter</category>
    <event>Shelter Status Change</event>
    <urgency>Expected</urgency>
    <severity>Moderate</severity>
    <certainty>Observed</certainty>
    <effective>2026-03-10T14:00:00-00:00</effective>
    <headline>Shelter Alpha Closure</headline>
    <description>Shelter Alpha at 123 Main St has reached capacity and is no longer accepting new evacuees. Redirecting to Shelter Bravo (456 Oak Ave).</description>
    <area>
      <areaDesc>Springfield Downtown</areaDesc>
      <circle>39.7817,-89.6501 0</circle>
    </area>
  </info>
</alert>
```

### 3.3 EDXL-DE Export

**Purpose:** Package COP updates for Emergency Data Exchange Language distribution.

EDXL-DE provides a standardized envelope for routing emergency messages. The COP update content is embedded as XML within the EDXL-DE wrapper.

#### Key Components

- **Distribution ID:** Unique message identifier
- **Sender ID:** Organization identifier
- **Distribution Type:** "Update"
- **Content Object:** COP update as XML or JSON
- **Target Area:** Geographic distribution (optional)

### 3.4 GeoJSON Export

**Purpose:** Provide location data for mapping platforms.

#### Feature Properties

Each COP candidate with location becomes a GeoJSON Feature:

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "id": "candidate-12345",
      "geometry": {
        "type": "Point",
        "coordinates": [-89.6501, 39.7817]
      },
      "properties": {
        "what": "Shelter Alpha closure",
        "where": "123 Main St, Springfield",
        "when": "2026-03-10T14:30:00Z",
        "who": "Emergency Management Agency",
        "so_what": "Redirecting evacuees to Shelter Bravo",
        "readiness_state": "verified",
        "risk_tier": "elevated",
        "citations": [
          "https://slack.com/archives/C123/p1234567890"
        ]
      }
    }
  ]
}
```

#### Use Cases

- Display COP updates on web maps (Leaflet, Mapbox, Google Maps)
- Import into GIS platforms (ArcGIS, QGIS)
- Spatial analysis and routing
- Mobile mapping applications

---

## 4. Inbound Integrations

### 4.1 External Verification Sources

**Purpose:** Import pre-verified data from authoritative systems to accelerate COP candidate creation.

#### Source Types

| Type | Description | Examples | Default Trust Level |
|------|-------------|----------|---------------------|
| `government_api` | Official government data sources | FEMA Incident API, NOAA Weather | High |
| `ngo_feed` | NGO-operated verified feeds | Red Cross, UN OCHA | Medium |
| `verified_reporter` | Credentialed reporter systems | Professional journalist feeds | Medium |
| `other` | Custom integrations | Organization-specific APIs | Low |

#### Trust Level Impact

| Trust Level | Import Behavior | Readiness State | Requires Human Review |
|-------------|-----------------|-----------------|----------------------|
| **High** | Auto-promote to verified candidate | `verified` | No (audit review only) |
| **Medium** | Create in-review candidate | `in_review` | Yes (facilitator review) |
| **Low** | Import as signal | N/A | Yes (full verification) |

#### Import Process

```
1. Fetch data from external source API
   ↓
2. Transform to COP candidate schema
   ↓
3. Check for duplicates (by location, timestamp, content hash)
   ↓
4. Create candidates with appropriate readiness state
   ↓
5. Log provenance to external source in audit trail
   ↓
6. Notify facilitators of new external imports
```

#### Security Considerations

- **Authentication required:** API keys, OAuth 2.0, or custom auth
- **Rate limiting:** Max 100 imports per source per hour
- **Input validation:** Sanitize all imported data
- **Duplicate detection:** Prevent duplicate candidate creation
- **Audit logging:** All imports logged with source attribution

### 4.2 Import API Endpoint

**Endpoint:** `POST /api/v1/integrations/sources/{source_id}/import`

**Request Body:**

```json
{
  "start_time": "2026-03-10T00:00:00Z",
  "end_time": "2026-03-10T23:59:59Z",
  "auto_promote": false,
  "filters": {
    "incident_type": "shelter_status",
    "severity": ["moderate", "high"]
  }
}
```

**Response:**

```json
{
  "data": {
    "import_id": "import-abc123",
    "status": "in_progress",
    "items_fetched": 25,
    "items_imported": 20,
    "duplicates_skipped": 5,
    "candidates_created": 20,
    "started_at": "2026-03-10T14:30:00Z"
  }
}
```

---

## 5. Integration Health Monitoring

### 5.1 Health Metrics

**Endpoint:** `GET /api/v1/integrations/health`

#### Webhook Health

- **Total active webhooks:** Count of enabled webhooks
- **Success rate (24h):** Percentage of successful deliveries
- **Failed deliveries (24h):** Count of failures
- **Average response time:** Mean webhook response time
- **Last failure:** Details of most recent failure

#### External Source Health

- **Total active sources:** Count of enabled sources
- **Last sync timestamp:** Most recent successful sync
- **Items imported (24h):** Count of imported items
- **Sync errors (24h):** Count of failed syncs
- **Sources with errors:** List of sources in error state

#### Export Health

- **CAP exports (24h):** Count of CAP exports
- **GeoJSON exports (24h):** Count of GeoJSON exports
- **Export failures (24h):** Count of failed exports
- **Average export time:** Mean export generation time

### 5.2 Overall Status

| Status | Criteria | Action Required |
|--------|----------|-----------------|
| **Healthy** | Success rate > 95%, no recent failures | None |
| **Degraded** | Success rate 80-95%, some failures | Monitor closely |
| **Unhealthy** | Success rate < 80%, frequent failures | Immediate attention required |

### 5.3 Alerting

Integration health alerts trigger when:

- Webhook success rate drops below 90% (warning) or 80% (critical)
- External source sync fails 3 consecutive times
- Export generation fails 5 times in 1 hour
- Any integration unavailable for > 15 minutes

---

## 6. Security Architecture

### 6.1 Authentication & Authorization

#### Webhook Authentication

- **Outbound webhooks:** Support bearer token, basic auth, custom header
- **Inbound requests:** Require workspace_admin role for webhook configuration

#### External Source Authentication

- **API key:** Simple key-based auth
- **OAuth 2.0:** Client credentials flow for government APIs
- **Custom:** Flexible auth configuration per source

#### Export Authentication

- **CAP/EDXL-DE exports:** Require facilitator role
- **GeoJSON exports:** Require facilitator role
- **Public exports:** Optional (if enabled, require authentication)

### 6.2 Input Validation

All inbound data (webhook configs, external source data) validated for:

- **Schema compliance:** JSON/XML schema validation
- **Content sanitization:** Strip HTML, scripts, SQL injection attempts
- **URL validation:** No localhost, private IPs, or malicious domains
- **Rate limiting:** Prevent abuse and DoS

### 6.3 Secrets Management

- **Webhook auth tokens:** Encrypted at rest, redacted in API responses
- **External source credentials:** Stored in encrypted vault, never logged
- **API keys:** Rotatable, audited on access

### 6.4 Network Security

- **HTTPS only:** All external communications require TLS
- **Certificate validation:** Verify webhook endpoint SSL certificates
- **Firewall rules:** Restrict outbound connections to approved domains
- **IP allowlisting:** Optional for external source APIs

---

## 7. Error Handling & Resilience

### 7.1 Webhook Retry Logic

```python
def deliver_webhook(webhook, payload):
    max_retries = webhook.retry_config.max_retries
    base_delay = webhook.retry_config.retry_delay_seconds
    multiplier = webhook.retry_config.backoff_multiplier

    for attempt in range(max_retries + 1):
        try:
            response = http.post(
                webhook.url,
                json=payload,
                headers=build_auth_headers(webhook),
                timeout=10
            )

            if response.status_code < 500:
                # Success or client error (don't retry)
                log_delivery(webhook, payload, response, "success")
                return True
        except Exception as e:
            log_delivery(webhook, payload, None, "failed", str(e))

        if attempt < max_retries:
            delay = base_delay * (multiplier ** attempt)
            time.sleep(delay)

    # All retries exhausted
    alert_webhook_failure(webhook)
    return False
```

### 7.2 Import Failure Handling

- **Partial import success:** Import successful items, log failures
- **Schema mismatch:** Log error, notify admin, skip item
- **Duplicate detection:** Skip duplicate, increment skipped count
- **API unavailable:** Mark source as temporarily unhealthy, retry later

### 7.3 Export Failure Handling

- **CAP validation failure:** Return 422 with validation errors
- **Missing required fields:** Return 422 with field list
- **Large dataset timeout:** Implement pagination or async generation

---

## 8. Performance Considerations

### 8.1 Webhook Delivery

- **Async processing:** Webhooks delivered via background job queue
- **Batch processing:** Group webhook deliveries for same event
- **Connection pooling:** Reuse HTTP connections to same domains
- **Timeout:** 10-second timeout per delivery attempt

### 8.2 Export Generation

- **CAP export:** < 500ms for typical COP update (10 line items)
- **GeoJSON export:** < 200ms for 50 features
- **EDXL-DE export:** < 800ms for complex update
- **Caching:** Cache exports for 5 minutes (configurable)

### 8.3 Import Processing

- **Batch import:** Process imports in batches of 50 items
- **Duplicate check optimization:** Hash-based duplicate detection
- **Rate limiting:** Max 100 imports per source per hour
- **Background processing:** Imports run async, return job ID immediately

---

## 9. Monitoring & Observability

### 9.1 Metrics to Track

| Metric | Type | Purpose |
|--------|------|---------|
| `webhooks.deliveries.total` | Counter | Total webhook deliveries attempted |
| `webhooks.deliveries.success` | Counter | Successful webhook deliveries |
| `webhooks.deliveries.failed` | Counter | Failed webhook deliveries |
| `webhooks.response_time_ms` | Histogram | Webhook response time distribution |
| `exports.cap.total` | Counter | CAP exports generated |
| `exports.geojson.total` | Counter | GeoJSON exports generated |
| `exports.generation_time_ms` | Histogram | Export generation time |
| `imports.items_imported` | Counter | Items imported from external sources |
| `imports.duplicates_skipped` | Counter | Duplicates skipped during import |
| `imports.errors` | Counter | Import errors |

### 9.2 Log Events

- **Webhook delivery:** Log every delivery attempt with status, response code, duration
- **Export generation:** Log export requests, generation time, errors
- **Import execution:** Log import start, items processed, errors, duration
- **Health check failures:** Log when integrations become unhealthy

### 9.3 Dashboards

**Integration Health Dashboard:**
- Webhook success rate chart (24h, 7d)
- External source sync status
- Export volume by type
- Error rate trending

---

## 10. Configuration

### 10.1 Environment Variables

```bash
# Webhook Configuration
WEBHOOKS_ENABLED=true
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_DELAY_SECONDS=60
WEBHOOK_BACKOFF_MULTIPLIER=2.0
WEBHOOK_MAX_PER_HOUR=1000

# Export Configuration
CAP_EXPORT_ENABLED=true
CAP_SENDER_ID=integritykit@aidarena.org
CAP_EXPORT_CACHE_TTL_SECONDS=300
EDXL_DE_EXPORT_ENABLED=true
GEOJSON_EXPORT_ENABLED=true

# External Source Configuration
EXTERNAL_SOURCES_ENABLED=true
MAX_IMPORTS_PER_SOURCE_PER_HOUR=100
IMPORT_BATCH_SIZE=50
IMPORT_DUPLICATE_CHECK_ENABLED=true

# Integration Health
INTEGRATION_HEALTH_CHECK_INTERVAL_SECONDS=60
WEBHOOK_SUCCESS_RATE_THRESHOLD_WARNING=0.90
WEBHOOK_SUCCESS_RATE_THRESHOLD_CRITICAL=0.80
```

### 10.2 Database Configuration

**Indexes for Performance:**

```javascript
// Webhooks collection
db.webhooks.createIndex({ enabled: 1, events: 1 });

// Webhook deliveries collection
db.webhook_deliveries.createIndex({ webhook_id: 1, timestamp: -1 });
db.webhook_deliveries.createIndex({ status: 1, timestamp: -1 });

// External sources collection
db.external_sources.createIndex({ enabled: 1, source_type: 1 });

// Imports collection
db.imports.createIndex({ source_id: 1, created_at: -1 });
db.imports.createIndex({ status: 1 });
```

---

## 11. API Examples

### 11.1 Create Webhook

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Emergency Operations Center",
    "url": "https://eoc.example.org/api/webhooks/integritykit",
    "events": ["cop_update.published"],
    "auth_type": "bearer",
    "auth_config": {
      "token": "eoc_secret_token_123"
    },
    "enabled": true
  }'
```

### 11.2 Export COP Update as CAP

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/exports/cap/cop-update-12345 \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Accept: application/xml"
```

### 11.3 Export as GeoJSON

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/exports/geojson/cop-update-12345 \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Accept: application/json"
```

### 11.4 Register External Source

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/sources \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "FEMA Incident API",
    "source_type": "government_api",
    "endpoint": "https://api.fema.gov/incidents",
    "auth_config": {
      "type": "bearer",
      "token": "fema_api_key_456"
    },
    "trust_level": "high",
    "sync_interval_minutes": 60,
    "enabled": true
  }'
```

### 11.5 Trigger Import

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/sources/source-789/import \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2026-03-10T00:00:00Z",
    "end_time": "2026-03-10T23:59:59Z",
    "auto_promote": false
  }'
```

### 11.6 Check Integration Health

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/integrations/health \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

---

## 12. Testing Strategy

### 12.1 Unit Tests

- Webhook delivery logic with mock HTTP responses
- CAP XML generation and validation against schema
- GeoJSON generation and geometry validation
- External source data transformation
- Duplicate detection algorithm
- Retry logic with backoff calculation

### 12.2 Integration Tests

- End-to-end webhook delivery to test endpoint
- CAP export validation with CAP validator tool
- GeoJSON import into mapping platform
- External source API integration with sandbox APIs
- Health monitoring with simulated failures

### 12.3 E2E Tests

**Webhook Flow:**
1. Publish COP update
2. Verify webhook triggered
3. Check webhook delivery logs
4. Confirm external system received payload

**CAP Export Flow:**
1. Create verified COP update
2. Request CAP export
3. Validate CAP XML against schema
4. Import CAP into external alerting system

**Import Flow:**
1. Configure external source
2. Trigger import
3. Verify candidates created
4. Check provenance in audit trail

### 12.4 Load Testing

- 100 concurrent webhook deliveries
- 50 CAP exports per minute
- 10 external sources importing simultaneously
- Health monitoring under load

---

## 13. Migration & Deployment

### 13.1 Database Migrations

**New Collections:**
- `webhooks`
- `webhook_deliveries`
- `external_sources`
- `import_jobs`

**Schema Updates:**
- `cop_updates`: Add `exported_formats`, `webhook_deliveries`
- `cop_candidates`: Add `source_type`, `external_source_id`

### 13.2 Deployment Steps

1. Deploy database migrations
2. Deploy integration service code
3. Configure environment variables
4. Create indexes for performance
5. Run health check tests
6. Enable integrations in production

### 13.3 Rollback Plan

- Disable integrations via feature flag
- Revert database migrations if needed
- Webhooks and imports gracefully degrade (fail closed)

---

## 14. Future Enhancements (v1.1+)

### 14.1 Additional Protocols

- **EDXL-SitRep:** Situation report format
- **EDXL-HAVE:** Hospital availability exchange
- **EDXL-RM:** Resource messaging

### 14.2 Advanced Features

- **Bi-directional webhooks:** Receive events from external systems
- **GraphQL subscriptions:** Real-time updates via subscriptions
- **Custom transformations:** User-defined data transformation rules
- **Integration marketplace:** Community-contributed integrations

### 14.3 Performance Improvements

- **Webhook batching:** Group multiple events into single delivery
- **Export streaming:** Stream large exports instead of buffering
- **Import pagination:** Support paginated external APIs

---

## 15. References

- [Common Alerting Protocol (CAP) 1.2 Specification](http://docs.oasis-open.org/emergency/cap/v1.2/)
- [EDXL-DE Specification](http://docs.oasis-open.org/emergency/edxl-de/v1.0/)
- [GeoJSON Specification (RFC 7946)](https://tools.ietf.org/html/rfc7946)
- [Webhook Best Practices](https://github.com/standard-webhooks/standard-webhooks)
- [REST API Security Best Practices](https://owasp.org/www-project-api-security/)

---

## Appendix A: Webhook Payload Examples

### COP Update Published Event

```json
{
  "event_id": "evt_abc123",
  "event_type": "cop_update.published",
  "timestamp": "2026-03-10T14:30:00Z",
  "workspace_id": "workspace-789",
  "data": {
    "update_id": "cop-update-12345",
    "version": 1,
    "language": "en",
    "published_by": "facilitator-user-456",
    "published_at": "2026-03-10T14:30:00Z",
    "slack_channel_id": "C123456",
    "slack_permalink": "https://slack.com/archives/C123456/p1710081000",
    "line_items": [
      {
        "id": "candidate-001",
        "status": "verified",
        "headline": "Shelter Alpha Closure",
        "body": "Shelter Alpha has closed due to capacity. Redirecting to Shelter Bravo.",
        "location": {
          "address": "123 Main St, Springfield",
          "coordinates": {
            "lat": 39.7817,
            "lon": -89.6501
          }
        },
        "risk_tier": "elevated",
        "citations": [
          "https://slack.com/archives/C123/p1234567890"
        ]
      }
    ],
    "export_links": {
      "cap": "https://api.integritykit.aidarena.org/api/v1/exports/cap/cop-update-12345",
      "edxl": "https://api.integritykit.aidarena.org/api/v1/exports/edxl/cop-update-12345",
      "geojson": "https://api.integritykit.aidarena.org/api/v1/exports/geojson/cop-update-12345"
    }
  }
}
```

---

## Appendix B: CAP Category Mapping

| IntegrityKit Topic Type | CAP Category | CAP Event Examples |
|-------------------------|--------------|-------------------|
| `incident` | Safety, Security | Incident Report, Emergency Situation |
| `need` | Health, Infra | Resource Need, Supply Shortage |
| `resource_offer` | Infra, Other | Resource Availability, Supply Offer |
| `infrastructure` | Infra, Transport | Infrastructure Status, Road Closure |
| `rumor` | Other | Unverified Information |
| `general` | Other | General Update |

---

## Appendix C: Error Codes

| Code | HTTP Status | Description | Recovery Action |
|------|-------------|-------------|-----------------|
| `WEBHOOK_DELIVERY_FAILED` | 500 | Webhook delivery failed after retries | Check webhook URL and auth config |
| `WEBHOOK_TIMEOUT` | 500 | Webhook endpoint did not respond in time | Increase timeout or check endpoint |
| `CAP_EXPORT_VALIDATION_ERROR` | 422 | CAP XML failed schema validation | Fix COP update data, check required fields |
| `EXTERNAL_SOURCE_UNAVAILABLE` | 503 | External source API unavailable | Retry later, check source status |
| `IMPORT_DUPLICATE_DETECTED` | 409 | Import skipped due to duplicate | No action needed (expected behavior) |
| `EXPORT_UNVERIFIED_ITEMS` | 422 | Cannot export unverified items to CAP | Verify candidates before exporting |

---

**End of Integration Architecture Document**
