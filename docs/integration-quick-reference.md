# Integration API Quick Reference

**Sprint 8 - v1.0**

---

## Webhook Management

### List Webhooks
```http
GET /api/v1/integrations/webhooks?page=1&per_page=20&enabled=true
Authorization: Bearer {token}
```

### Create Webhook
```http
POST /api/v1/integrations/webhooks
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "Emergency Operations Center",
  "url": "https://eoc.example.org/webhook",
  "events": ["cop_update.published"],
  "auth_type": "bearer",
  "auth_config": {
    "token": "secret_token"
  },
  "retry_config": {
    "max_retries": 3,
    "retry_delay_seconds": 60,
    "backoff_multiplier": 2.0
  },
  "enabled": true
}
```

### Update Webhook
```http
PUT /api/v1/integrations/webhooks/{webhook_id}
Authorization: Bearer {token}
Content-Type: application/json

{
  "enabled": false
}
```

### Test Webhook
```http
POST /api/v1/integrations/webhooks/{webhook_id}/test
Authorization: Bearer {token}
```

### Get Delivery History
```http
GET /api/v1/integrations/webhooks/{webhook_id}/deliveries?status=failed
Authorization: Bearer {token}
```

---

## Data Export

### Export as CAP 1.2 XML
```http
GET /api/v1/exports/cap/{update_id}
Authorization: Bearer {token}
Accept: application/xml
```

### Export as GeoJSON
```http
GET /api/v1/exports/geojson/{update_id}
Authorization: Bearer {token}
Accept: application/json
```

### Export as EDXL-DE
```http
GET /api/v1/exports/edxl/{update_id}
Authorization: Bearer {token}
Accept: application/xml
```

---

## External Sources

### List External Sources
```http
GET /api/v1/integrations/sources?source_type=government_api&enabled=true
Authorization: Bearer {token}
```

### Register External Source
```http
POST /api/v1/integrations/sources
Authorization: Bearer {token}
Content-Type: application/json

{
  "name": "FEMA Incident API",
  "source_type": "government_api",
  "endpoint": "https://api.fema.gov/incidents",
  "auth_config": {
    "type": "bearer",
    "token": "fema_api_key"
  },
  "trust_level": "high",
  "sync_interval_minutes": 60,
  "enabled": true
}
```

### Trigger Import
```http
POST /api/v1/integrations/sources/{source_id}/import
Authorization: Bearer {token}
Content-Type: application/json

{
  "start_time": "2026-03-10T00:00:00Z",
  "end_time": "2026-03-10T23:59:59Z",
  "auto_promote": false
}
```

---

## Health Monitoring

### Get Integration Health
```http
GET /api/v1/integrations/health
Authorization: Bearer {token}
```

**Response:**
```json
{
  "data": {
    "webhooks": {
      "total_active": 3,
      "success_rate_24h": 0.98,
      "failed_deliveries_24h": 2
    },
    "external_sources": {
      "total_active": 2,
      "last_sync": "2026-03-10T14:00:00Z",
      "items_imported_24h": 15
    },
    "exports": {
      "cap_exports_24h": 5,
      "geojson_exports_24h": 12
    },
    "overall_status": "healthy"
  }
}
```

---

## Webhook Event Payloads

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
    "line_items": [...],
    "export_links": {
      "cap": "https://api.integritykit.aidarena.org/api/v1/exports/cap/cop-update-12345",
      "geojson": "https://api.integritykit.aidarena.org/api/v1/exports/geojson/cop-update-12345"
    }
  }
}
```

---

## Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `WEBHOOK_DELIVERY_FAILED` | 500 | Webhook delivery failed |
| `CAP_EXPORT_VALIDATION_ERROR` | 422 | CAP XML validation failed |
| `EXTERNAL_SOURCE_UNAVAILABLE` | 503 | External API unavailable |
| `IMPORT_DUPLICATE_DETECTED` | 409 | Duplicate import skipped |
| `EXPORT_UNVERIFIED_ITEMS` | 422 | Cannot export unverified to CAP |

---

## Configuration

### Environment Variables
```bash
# Webhooks
WEBHOOKS_ENABLED=true
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3

# Exports
CAP_EXPORT_ENABLED=true
CAP_SENDER_ID=integritykit@example.org
GEOJSON_EXPORT_ENABLED=true

# External Sources
EXTERNAL_SOURCES_ENABLED=true
MAX_IMPORTS_PER_SOURCE_PER_HOUR=100
```

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| Webhook deliveries | 1000 / destination | 1 hour |
| Exports | 100 / user | 1 hour |
| Imports | 100 / source | 1 hour |
| Health checks | 60 / user | 1 minute |

---

## Trust Levels

| Level | Import Behavior | Readiness State |
|-------|-----------------|-----------------|
| `high` | Auto-promote to verified | `verified` |
| `medium` | Create in-review candidate | `in_review` |
| `low` | Import as signal | N/A |

---

## Webhook Event Types

| Event | Description |
|-------|-------------|
| `cop_update.published` | COP update published |
| `cop_candidate.verified` | Candidate verified |
| `cop_candidate.promoted` | Cluster promoted to candidate |
| `cluster.created` | New cluster formed |

---

## CAP Field Mapping

| COP Field | CAP Field |
|-----------|-----------|
| Update ID | `alert/identifier` |
| Published timestamp | `alert/sent` |
| What field | `info/headline` + `info/description` |
| Location | `info/area` |
| Risk tier | `info/urgency` (high_stakes→Immediate) |
| Verification | `info/certainty` (verified→Observed) |

---

## GeoJSON Properties

```json
{
  "type": "Feature",
  "geometry": {
    "type": "Point",
    "coordinates": [lon, lat]
  },
  "properties": {
    "id": "candidate-12345",
    "what": "Shelter closure",
    "where": "123 Main St",
    "when": "2026-03-10T14:30:00Z",
    "readiness_state": "verified",
    "risk_tier": "elevated",
    "citations": ["https://slack.com/..."]
  }
}
```

---

## Testing Endpoints

### Test Webhook (No Impact)
```bash
curl -X POST \
  https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/{webhook_id}/test \
  -H "Authorization: Bearer $TOKEN"
```

### Validate CAP Export
```bash
# Export CAP
curl https://api.integritykit.aidarena.org/api/v1/exports/cap/{update_id} \
  -H "Authorization: Bearer $TOKEN" > update.cap

# Validate against CAP 1.2 schema
xmllint --schema cap-1.2.xsd update.cap
```

---

## Troubleshooting

### Webhook Not Delivering
1. Check webhook enabled: `GET /webhooks/{id}`
2. Verify URL reachable: `POST /webhooks/{id}/test`
3. Review delivery logs: `GET /webhooks/{id}/deliveries`
4. Check auth configuration

### CAP Export Fails
1. Verify candidates are verified (not in-review)
2. Check location coordinates present
3. Validate required COP fields (what, where, when)
4. Review error details in 422 response

### Import Creates Duplicates
1. Check duplicate detection enabled
2. Review import logs for skipped count
3. Verify source data includes unique identifiers

### Health Shows Degraded
1. Check specific failing integrations
2. Review webhook failure logs
3. Verify external source API availability
4. Check rate limits not exceeded

---

## Support

- **Full Documentation:** `/docs/integration-architecture-v1.0.md`
- **OpenAPI Spec:** `/docs/openapi-integrations-addition.yaml`
- **GitHub Issues:** https://github.com/ai4altruism/integritykit/issues
- **Sprint Plan:** `/docs/Aid_Arena_Integrity_Kit_SDP_Sprint8_v1_0.md`
