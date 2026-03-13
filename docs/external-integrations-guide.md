# External Integrations Guide - v1.0

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

## Overview

The Aid Arena Integrity Kit v1.0 integrates with external emergency management systems through:

- **Outbound webhooks** - Real-time event notifications
- **Standard export formats** - CAP 1.2, EDXL-DE, GeoJSON
- **Inbound verification sources** - Import pre-verified data from authoritative systems
- **Health monitoring** - Track integration status and performance

This guide provides step-by-step instructions for configuring and using each integration type.

## Table of Contents

1. [Webhooks](#webhooks)
2. [CAP 1.2 Export](#cap-12-export)
3. [EDXL-DE Export](#edxl-de-export)
4. [GeoJSON Export](#geojson-export)
5. [External Verification Sources](#external-verification-sources)
6. [Integration Health Monitoring](#integration-health-monitoring)
7. [Troubleshooting](#troubleshooting)

---

## Webhooks

Webhooks enable real-time notifications when events occur in the Integrity Kit.

### Quick Start

#### 1. Create a Webhook

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Emergency Operations Center",
    "url": "https://eoc.example.org/api/webhooks/integritykit",
    "events": ["cop_update.published", "cop_candidate.verified"],
    "auth_type": "bearer",
    "auth_config": {
      "token": "your_secret_token"
    },
    "enabled": true
  }'
```

#### 2. Test Your Webhook

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/{webhook_id}/test \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### 3. Receive Events

Your endpoint will receive POST requests with this structure:

```json
{
  "event_id": "evt_abc123",
  "event_type": "cop_update.published",
  "timestamp": "2026-03-13T14:30:00Z",
  "workspace_id": "workspace-789",
  "data": {
    "update_id": "cop-update-12345",
    "version": 1,
    "language": "en",
    "published_at": "2026-03-13T14:30:00Z",
    "line_items": [...],
    "export_links": {
      "cap": "https://api.integritykit.aidarena.org/api/v1/exports/cap/cop-update-12345",
      "geojson": "https://api.integritykit.aidarena.org/api/v1/exports/geojson/cop-update-12345"
    }
  }
}
```

### Supported Events

| Event Type | Trigger | Payload Includes |
|------------|---------|------------------|
| `cop_update.published` | COP update published to Slack | Update ID, version, language, line items, export links |
| `cop_candidate.verified` | Candidate receives verification | Candidate ID, verification method, confidence level |
| `cop_candidate.promoted` | Cluster promoted to candidate | Candidate ID, cluster ID, risk tier |
| `cluster.created` | New cluster formed | Cluster ID, topic type, signal count, priority score |

### Authentication Types

#### Bearer Token

```json
{
  "auth_type": "bearer",
  "auth_config": {
    "token": "your_secret_token"
  }
}
```

Webhook includes: `Authorization: Bearer your_secret_token`

#### Basic Auth

```json
{
  "auth_type": "basic",
  "auth_config": {
    "username": "webhook_user",
    "password": "webhook_password"
  }
}
```

#### API Key

```json
{
  "auth_type": "api_key",
  "auth_config": {
    "key_name": "X-API-Key",
    "key_value": "your_api_key"
  }
}
```

#### Custom Header

```json
{
  "auth_type": "custom_header",
  "auth_config": {
    "header_name": "X-Custom-Auth",
    "header_value": "custom_value"
  }
}
```

### Verifying Webhook Signatures

Each webhook includes an `X-Webhook-Signature` header for authenticity verification.

**Python Example:**

```python
import hmac
import hashlib

def verify_webhook_signature(payload_body: bytes, signature: str, webhook_id: str) -> bool:
    if not signature.startswith("sha256="):
        return False

    expected_sig = signature[7:]
    secret = webhook_id.encode()
    computed = hmac.new(secret, payload_body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed, expected_sig)
```

**Node.js Example:**

```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payloadBody, signature, webhookId) {
  if (!signature.startsWith('sha256=')) return false;

  const expectedSig = signature.substring(7);
  const computed = crypto
    .createHmac('sha256', webhookId)
    .update(payloadBody)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(computed),
    Buffer.from(expectedSig)
  );
}
```

### Retry Configuration

Customize retry behavior per webhook:

```json
{
  "retry_config": {
    "max_retries": 5,
    "retry_delay_seconds": 30,
    "backoff_multiplier": 2.5
  }
}
```

Default retry schedule:
- Attempt 1: Immediate
- Attempt 2: After 60 seconds
- Attempt 3: After 120 seconds
- Attempt 4: After 240 seconds

### Webhook Management

**List webhooks:**
```bash
GET /api/v1/integrations/webhooks
```

**Get webhook details:**
```bash
GET /api/v1/integrations/webhooks/{webhook_id}
```

**Update webhook:**
```bash
PUT /api/v1/integrations/webhooks/{webhook_id}
```

**Delete webhook:**
```bash
DELETE /api/v1/integrations/webhooks/{webhook_id}
```

**View delivery history:**
```bash
GET /api/v1/integrations/webhooks/{webhook_id}/deliveries?status=failed
```

For complete webhook documentation, see [Webhook System Guide](webhooks-guide.md).

---

## CAP 1.2 Export

Common Alerting Protocol (CAP) is the international standard for emergency alerts and public warnings.

### Use Cases

- Integration with public alerting systems (Integrated Public Alert and Warning System - IPAWS)
- Emergency broadcasting to radio/TV
- Mobile emergency alerts
- Integration with national warning systems

### Export COP Update as CAP

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/exports/cap/{update_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/xml"
```

### CAP Field Mapping

| COP Field | CAP Field | Mapping Logic |
|-----------|-----------|---------------|
| COP Update ID | `alert/identifier` | `cop-update-{id}` |
| Organization | `alert/sender` | Configured org identifier |
| Published timestamp | `alert/sent` | ISO 8601 datetime |
| Verification status | `info/certainty` | verified → Observed, in_review → Likely |
| Risk tier | `info/urgency` | high_stakes → Immediate, elevated → Expected |
| What field | `info/headline` + `info/description` | Headline from draft wording |
| Location | `info/area` | Coordinates converted to CAP circle/polygon |
| When field | `info/effective` | Event timestamp |

### Example CAP Output

```xml
<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>cop-update-67890</identifier>
  <sender>integritykit@aidarena.org</sender>
  <sent>2026-03-13T14:30:00-00:00</sent>
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
    <effective>2026-03-13T14:00:00-00:00</effective>
    <headline>Shelter Alpha Closure</headline>
    <description>Shelter Alpha at 123 Main St has reached capacity...</description>
    <area>
      <areaDesc>Springfield Downtown</areaDesc>
      <circle>39.7817,-89.6501 0</circle>
    </area>
  </info>
</alert>
```

### Multi-Language CAP Export

Multi-language COP updates create separate `<info>` blocks per language:

```xml
<alert>
  <identifier>cop-update-67890</identifier>

  <!-- English -->
  <info>
    <language>en-US</language>
    <headline>Shelter Alpha Closure</headline>
    ...
  </info>

  <!-- Spanish -->
  <info>
    <language>es-ES</language>
    <headline>Cierre del Refugio Alpha</headline>
    ...
  </info>
</alert>
```

### CAP Export Rules

1. **Only verified items** can be exported to CAP format
2. **In-review items** are excluded (CAP requires certainty)
3. **Location required** - Items without location data are skipped
4. **Risk tier mapping** - Automatically maps to CAP urgency/severity

### Configuration

```bash
# Enable CAP export
CAP_EXPORT_ENABLED=true

# Set sender identifier
CAP_SENDER_ID=integritykit@aidarena.org

# Cache exports for performance
CAP_EXPORT_CACHE_TTL_SECONDS=300
```

---

## EDXL-DE Export

Emergency Data Exchange Language - Distribution Element (EDXL-DE) provides a standardized envelope for routing emergency messages.

### Use Cases

- Distribution to multiple emergency management systems
- Routing messages through emergency operations centers (EOCs)
- Integration with emergency management information systems (EMIS)
- Interoperability with government systems

### Export as EDXL-DE

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/exports/edxl/{update_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/xml"
```

### EDXL-DE Structure

```xml
<?xml version="1.0" encoding="UTF-8"?>
<EDXLDistribution xmlns="urn:oasis:names:tc:emergency:EDXL:DE:1.0">
  <distributionID>integritykit-{update_id}</distributionID>
  <senderID>integritykit@aidarena.org</senderID>
  <dateTimeSent>2026-03-13T14:30:00Z</dateTimeSent>
  <distributionStatus>Actual</distributionStatus>
  <distributionType>Update</distributionType>

  <contentObject>
    <contentDescription>COP Update</contentDescription>
    <xmlContent>
      <embeddedXMLContent>
        <!-- COP update content as XML -->
      </embeddedXMLContent>
    </xmlContent>
  </contentObject>
</EDXLDistribution>
```

### Configuration

```bash
# Enable EDXL-DE export
EDXL_DE_EXPORT_ENABLED=true
```

---

## GeoJSON Export

GeoJSON provides location data for mapping platforms.

### Use Cases

- Display COP updates on web maps (Leaflet, Mapbox, Google Maps)
- Import into GIS platforms (ArcGIS, QGIS)
- Spatial analysis and routing
- Mobile mapping applications

### Export as GeoJSON

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/exports/geojson/{update_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/json"
```

### GeoJSON Structure

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
        "when": "2026-03-13T14:30:00Z",
        "who": "Emergency Management Agency",
        "so_what": "Redirecting evacuees to Shelter Bravo",
        "readiness_state": "verified",
        "risk_tier": "elevated",
        "citations": [
          "https://slack.com/archives/C123/p1234567890"
        ],
        "language": "en"
      }
    }
  ]
}
```

### Using GeoJSON with Leaflet

```javascript
// Fetch GeoJSON
const response = await fetch('/api/v1/exports/geojson/cop-update-12345');
const geojson = await response.json();

// Add to Leaflet map
L.geoJSON(geojson, {
  onEachFeature: (feature, layer) => {
    const props = feature.properties;
    layer.bindPopup(`
      <h3>${props.what}</h3>
      <p><strong>Where:</strong> ${props.where}</p>
      <p><strong>When:</strong> ${props.when}</p>
      <p><strong>Status:</strong> ${props.readiness_state}</p>
      <p><a href="${props.citations[0]}" target="_blank">View Source</a></p>
    `);
  }
}).addTo(map);
```

### Configuration

```bash
# Enable GeoJSON export
GEOJSON_EXPORT_ENABLED=true
```

---

## External Verification Sources

Import pre-verified data from authoritative systems to accelerate COP candidate creation.

### Supported Source Types

| Type | Description | Examples | Default Trust Level |
|------|-------------|----------|---------------------|
| `government_api` | Official government data sources | FEMA Incident API, NOAA Weather | High |
| `ngo_feed` | NGO-operated verified feeds | Red Cross, UN OCHA | Medium |
| `verified_reporter` | Credentialed reporter systems | Professional journalist feeds | Medium |
| `other` | Custom integrations | Organization-specific APIs | Low |

### Trust Level Behavior

| Trust Level | Import Behavior | Readiness State | Requires Human Review |
|-------------|-----------------|-----------------|----------------------|
| **High** | Auto-promote to verified candidate | `verified` | No (audit review only) |
| **Medium** | Create in-review candidate | `in_review` | Yes (facilitator review) |
| **Low** | Import as signal | N/A | Yes (full verification) |

### Register External Source

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/sources \
  -H "Authorization: Bearer YOUR_TOKEN" \
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

### Trigger Manual Import

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/sources/{source_id}/import \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2026-03-13T00:00:00Z",
    "end_time": "2026-03-13T23:59:59Z",
    "auto_promote": false,
    "filters": {
      "incident_type": "shelter_status",
      "severity": ["moderate", "high"]
    }
  }'
```

### Import Process

1. Fetch data from external source API
2. Transform to COP candidate schema
3. Check for duplicates (by location, timestamp, content hash)
4. Create candidates with appropriate readiness state
5. Log provenance to external source in audit trail
6. Notify facilitators of new external imports

### Authentication Types

**API Key:**
```json
{
  "type": "api_key",
  "key": "your_api_key"
}
```

**Bearer Token:**
```json
{
  "type": "bearer",
  "token": "your_bearer_token"
}
```

**OAuth 2.0:**
```json
{
  "type": "oauth2",
  "client_id": "your_client_id",
  "client_secret": "your_client_secret",
  "token_endpoint": "https://auth.example.com/token"
}
```

### Configuration

```bash
# Enable external sources
EXTERNAL_SOURCES_ENABLED=true

# Rate limiting
MAX_IMPORTS_PER_SOURCE_PER_HOUR=100

# Batch processing
IMPORT_BATCH_SIZE=50

# Duplicate detection
IMPORT_DUPLICATE_CHECK_ENABLED=true
```

---

## Integration Health Monitoring

Monitor the health and performance of all integrations from a single dashboard.

### Health Status Endpoint

```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/integrations/health \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Response Structure

```json
{
  "data": {
    "overall_status": "healthy",
    "webhooks": {
      "total_active": 5,
      "success_rate_24h": 0.98,
      "failed_deliveries_24h": 3,
      "avg_response_time_ms": 145,
      "last_success_at": "2026-03-13T10:25:00Z",
      "last_failure_at": "2026-03-12T08:15:00Z"
    },
    "external_sources": {
      "total_active": 2,
      "last_sync": "2026-03-13T10:30:00Z",
      "items_imported_24h": 45,
      "sync_errors_24h": 0,
      "sources_with_errors": []
    },
    "exports": {
      "cap_exports_24h": 12,
      "geojson_exports_24h": 18,
      "edxl_exports_24h": 8,
      "export_failures_24h": 0,
      "avg_export_time_ms": 250
    }
  }
}
```

### Overall Status Levels

| Status | Criteria | Action Required |
|--------|----------|-----------------|
| **healthy** | Success rate > 95%, no recent failures | None |
| **degraded** | Success rate 80-95%, some failures | Monitor closely |
| **unhealthy** | Success rate < 80%, frequent failures | Immediate attention required |

### Alerting

Integration health alerts trigger when:

- Webhook success rate drops below 90% (warning) or 80% (critical)
- External source sync fails 3 consecutive times
- Export generation fails 5 times in 1 hour
- Any integration unavailable for > 15 minutes

### Configuration

```bash
# Health monitoring
INTEGRATION_HEALTH_CHECK_INTERVAL_SECONDS=60
WEBHOOK_SUCCESS_RATE_THRESHOLD_WARNING=0.90
WEBHOOK_SUCCESS_RATE_THRESHOLD_CRITICAL=0.80
```

---

## Troubleshooting

### Webhook Deliveries Failing

**Symptoms:**
- Webhooks not received by external system
- High failure rate in delivery history

**Solutions:**

1. **Check webhook status:**
   ```bash
   curl https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/{webhook_id}
   ```
   Verify `enabled: true`

2. **Test webhook delivery:**
   ```bash
   curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/{webhook_id}/test
   ```

3. **Review delivery history:**
   ```bash
   curl "https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/{webhook_id}/deliveries?status=failed"
   ```

4. **Common issues:**
   - **Timeout:** Endpoint taking >10 seconds to respond
   - **Authentication:** Invalid credentials in `auth_config`
   - **URL issues:** Incorrect URL or firewall blocking requests
   - **Certificate errors:** SSL/TLS certificate problems

5. **Verify endpoint is reachable:**
   ```bash
   curl -X POST https://your-webhook-url.com/path \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

### CAP Export Validation Errors

**Symptoms:**
- CAP export returns 422 error
- CAP XML fails validation

**Solutions:**

1. **Check required fields:**
   - Verified status required (in-review items excluded)
   - Location data required for area element
   - What, when, where fields must be complete

2. **Validate CAP XML:**
   Use online CAP validator: http://www.cap-validator.org/

3. **Review error details:**
   ```json
   {
     "error": "CAP_EXPORT_VALIDATION_ERROR",
     "details": [
       {
         "field": "location",
         "message": "Location required for CAP export"
       }
     ]
   }
   ```

### External Source Import Issues

**Symptoms:**
- No candidates created from import
- Import job stuck in "in_progress" status

**Solutions:**

1. **Check source configuration:**
   ```bash
   curl https://api.integritykit.aidarena.org/api/v1/integrations/sources/{source_id}
   ```

2. **Verify external API is accessible:**
   ```bash
   curl -H "Authorization: Bearer API_KEY" https://external-api.example.com/endpoint
   ```

3. **Review import job logs:**
   Check application logs for import errors

4. **Common issues:**
   - **API unavailable:** External source API down or rate-limited
   - **Authentication failed:** Invalid credentials
   - **Schema mismatch:** External data doesn't match expected format
   - **All duplicates:** All imported items already exist

### GeoJSON Not Displaying on Map

**Symptoms:**
- GeoJSON export successful but features don't appear on map

**Solutions:**

1. **Verify GeoJSON structure:**
   ```bash
   curl https://api.integritykit.aidarena.org/api/v1/exports/geojson/{update_id} | jq
   ```

2. **Check coordinate order:**
   GeoJSON uses [longitude, latitude] (not lat, lon)

3. **Verify CRS compatibility:**
   GeoJSON uses WGS84 (EPSG:4326) by default

4. **Test with online viewer:**
   Use http://geojson.io to validate GeoJSON

### Integration Health Shows "Unhealthy"

**Symptoms:**
- Integration health endpoint returns "unhealthy" status

**Solutions:**

1. **Review specific integration metrics:**
   - Check webhook success rate
   - Check external source sync status
   - Check export error rate

2. **Investigate recent failures:**
   - Review webhook delivery history
   - Check external source import logs
   - Review export error logs

3. **Check system resources:**
   - Verify database connectivity
   - Check API rate limits
   - Monitor system load

4. **Restart integrations if needed:**
   - Disable and re-enable problematic integrations
   - Clear cached credentials
   - Retry failed operations

---

## Best Practices

### Webhooks

1. **Implement idempotency** - Check `event_id` before processing
2. **Respond quickly** - Return 200 OK immediately, process asynchronously
3. **Use HTTPS** - Protect webhook data in transit
4. **Verify signatures** - Prevent spoofing attacks
5. **Monitor delivery health** - Check success rate regularly

### CAP/EDXL-DE Exports

1. **Verify items before export** - Only export verified candidates
2. **Include location data** - Required for CAP area element
3. **Test with validators** - Use CAP/EDXL-DE validator tools
4. **Support multi-language** - Provide translations where possible
5. **Cache exports** - Reduce load on frequent export requests

### External Sources

1. **Start with medium trust** - Manually review first imports
2. **Monitor import quality** - Check candidate accuracy
3. **Adjust trust level** - Upgrade to high trust once proven reliable
4. **Enable duplicate detection** - Prevent duplicate candidate creation
5. **Rate limit imports** - Don't overwhelm your facilitators

### Health Monitoring

1. **Check health regularly** - Daily health dashboard review
2. **Set up alerting** - Configure alerts for critical failures
3. **Track trends** - Monitor success rates over time
4. **Document incidents** - Record failures and resolutions
5. **Plan for failures** - Have fallback procedures ready

---

## See Also

- [Webhook System Guide](webhooks-guide.md) - Complete webhook documentation
- [Integration Architecture](integration-architecture-v1.0.md) - Technical architecture details
- [API Guide](api_guide.md) - Full API reference
- [Analytics Guide](analytics-guide.md) - Analytics and reporting
- [Multi-Language Guide](multi-language-guide.md) - Multi-language support

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8
