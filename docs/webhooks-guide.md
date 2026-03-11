# Webhook System Guide - v1.0

**Sprint 8, Task S8-17: Outbound Webhook System**

## Overview

The IntegrityKit webhook system enables external systems to receive real-time notifications when events occur in the platform. This allows integration with emergency management systems, dashboards, analytics platforms, and other tools.

## Features

- **Event-based notifications:** Receive notifications for COP updates, candidate verifications, and more
- **Multiple authentication methods:** Bearer token, Basic auth, API key, custom headers, OAuth2
- **Automatic retry with exponential backoff:** Failed deliveries are automatically retried
- **HMAC payload signing:** Verify payload authenticity with cryptographic signatures
- **Delivery tracking:** Complete history of successful and failed deliveries
- **Test endpoint:** Verify webhook configuration before going live

## Supported Events

| Event Type | Trigger | Payload Includes |
|------------|---------|------------------|
| `cop_update.published` | COP update published to Slack | Update ID, version, language, line items, export links |
| `cop_candidate.verified` | Candidate receives verification | Candidate ID, verification method, confidence level |
| `cop_candidate.promoted` | Cluster promoted to candidate | Candidate ID, cluster ID, risk tier |
| `cluster.created` | New cluster formed | Cluster ID, topic type, signal count, priority score |

## Quick Start

### 1. Create a Webhook

**Request:**
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

**Response:**
```json
{
  "data": {
    "id": "507f1f77bcf86cd799439011",
    "workspace_id": "workspace-123",
    "name": "Emergency Operations Center",
    "url": "https://eoc.example.org/api/webhooks/integritykit",
    "events": ["cop_update.published", "cop_candidate.verified"],
    "auth_type": "bearer",
    "enabled": true,
    "statistics": {
      "total_deliveries": 0,
      "successful_deliveries": 0,
      "failed_deliveries": 0,
      "success_rate": 0.0
    },
    "created_at": "2026-03-10T14:30:00Z"
  }
}
```

### 2. Test Your Webhook

```bash
curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/507f1f77bcf86cd799439011/test \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "data": {
    "success": true,
    "status_code": 200,
    "response_time_ms": 145,
    "response_body": "{\"status\": \"ok\"}",
    "error": null
  }
}
```

### 3. Receive Webhook Events

Your webhook endpoint will receive POST requests with the following structure:

**Headers:**
```
Content-Type: application/json
X-Webhook-Event: cop_update.published
X-Webhook-ID: 507f1f77bcf86cd799439011
X-Webhook-Delivery-ID: 507f191e810c19729de860ea
X-Webhook-Signature: sha256=abc123...
Authorization: Bearer your_secret_token  (if configured)
```

**Payload:**
```json
{
  "event_id": "cop_update_507f191e810c19729de860ea",
  "event_type": "cop_update.published",
  "timestamp": "2026-03-10T14:30:00Z",
  "workspace_id": "workspace-123",
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
        "body": "Shelter Alpha has closed due to capacity.",
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

## Authentication Methods

### Bearer Token

```json
{
  "auth_type": "bearer",
  "auth_config": {
    "token": "your_secret_token"
  }
}
```

The webhook will include: `Authorization: Bearer your_secret_token`

### Basic Auth

```json
{
  "auth_type": "basic",
  "auth_config": {
    "username": "webhook_user",
    "password": "webhook_password"
  }
}
```

The webhook will include: `Authorization: Basic d2ViaG9va191c2VyOndlYmhvb2tfcGFzc3dvcmQ=`

### API Key

```json
{
  "auth_type": "api_key",
  "auth_config": {
    "key_name": "X-API-Key",
    "key_value": "your_api_key"
  }
}
```

The webhook will include: `X-API-Key: your_api_key`

### Custom Header

```json
{
  "auth_type": "custom_header",
  "auth_config": {
    "header_name": "X-Custom-Auth",
    "header_value": "custom_value"
  }
}
```

The webhook will include: `X-Custom-Auth: custom_value`

## Verifying Webhook Signatures

Each webhook includes an `X-Webhook-Signature` header with an HMAC signature of the payload. Verify this to ensure the webhook is authentic.

**Python Example:**
```python
import hmac
import hashlib

def verify_webhook_signature(payload_body: bytes, signature: str, webhook_id: str) -> bool:
    """Verify webhook signature.

    Args:
        payload_body: Raw request body as bytes
        signature: X-Webhook-Signature header value (format: "sha256=...")
        webhook_id: Webhook ID (used as secret)

    Returns:
        True if signature is valid
    """
    if not signature.startswith("sha256="):
        return False

    expected_sig = signature[7:]  # Remove "sha256=" prefix
    secret = webhook_id.encode()
    computed = hmac.new(secret, payload_body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(computed, expected_sig)
```

**Node.js Example:**
```javascript
const crypto = require('crypto');

function verifyWebhookSignature(payloadBody, signature, webhookId) {
  if (!signature.startsWith('sha256=')) {
    return false;
  }

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

## Retry Behavior

Failed webhook deliveries are automatically retried with exponential backoff:

- **Default max retries:** 3
- **Default initial delay:** 60 seconds
- **Default backoff multiplier:** 2.0

**Example retry schedule:**
- Attempt 1: Immediate
- Attempt 2: After 60 seconds (if failed)
- Attempt 3: After 120 seconds (if failed)
- Attempt 4: After 240 seconds (if failed)

Configure retry behavior per webhook:

```json
{
  "retry_config": {
    "max_retries": 5,
    "retry_delay_seconds": 30,
    "backoff_multiplier": 2.5
  }
}
```

## Webhook Delivery Semantics

- **At-least-once delivery:** Webhooks may be delivered more than once in failure scenarios
- **Idempotency:** Use `event_id` field to deduplicate events on your end
- **Timeout:** 10 seconds per delivery attempt (configurable via `WEBHOOK_TIMEOUT_SECONDS`)
- **HTTP status codes:**
  - `2xx`: Success (no retry)
  - `4xx`: Client error (no retry - fix webhook configuration)
  - `5xx`: Server error (retry with backoff)

## Best Practices

### 1. Implement Idempotency

Always check the `event_id` before processing:

```python
processed_events = set()  # Use Redis or database in production

async def handle_webhook(payload: dict):
    event_id = payload['event_id']

    if event_id in processed_events:
        return {"status": "already_processed"}

    # Process event
    await process_event(payload)

    processed_events.add(event_id)
    return {"status": "ok"}
```

### 2. Respond Quickly

Return a `200 OK` response as soon as you receive the webhook. Process the event asynchronously:

```python
from fastapi import BackgroundTasks

@app.post("/webhooks/integritykit")
async def receive_webhook(payload: dict, background_tasks: BackgroundTasks):
    # Verify signature first
    verify_signature(payload)

    # Queue for background processing
    background_tasks.add_task(process_webhook, payload)

    # Return immediately
    return {"status": "ok"}
```

### 3. Use HTTPS in Production

Webhook URLs must use HTTPS in production environments to protect sensitive data.

### 4. Monitor Delivery Health

Check delivery statistics regularly:

```bash
curl https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/507f1f77bcf86cd799439011 \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Look at the `statistics` object:
```json
{
  "statistics": {
    "total_deliveries": 150,
    "successful_deliveries": 147,
    "failed_deliveries": 3,
    "success_rate": 0.98,
    "last_success_at": "2026-03-10T14:25:00Z",
    "last_failure_at": "2026-03-09T08:15:00Z"
  }
}
```

### 5. View Delivery History

Review individual delivery attempts:

```bash
curl https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/507f1f77bcf86cd799439011/deliveries \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Filter by status:
```bash
curl "https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/507f1f77bcf86cd799439011/deliveries?status=failed" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Environment Variables

Configure webhook behavior with environment variables:

```bash
# Enable/disable webhooks
WEBHOOKS_ENABLED=true

# Timeout for webhook requests (seconds)
WEBHOOK_TIMEOUT_SECONDS=10

# Retry configuration
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_DELAY_SECONDS=60
WEBHOOK_BACKOFF_MULTIPLIER=2.0
```

## API Reference

### Create Webhook
`POST /api/v1/integrations/webhooks`

### List Webhooks
`GET /api/v1/integrations/webhooks`

### Get Webhook
`GET /api/v1/integrations/webhooks/{webhook_id}`

### Update Webhook
`PUT /api/v1/integrations/webhooks/{webhook_id}`

### Delete Webhook
`DELETE /api/v1/integrations/webhooks/{webhook_id}`

### Test Webhook
`POST /api/v1/integrations/webhooks/{webhook_id}/test`

### Get Delivery History
`GET /api/v1/integrations/webhooks/{webhook_id}/deliveries`

## Troubleshooting

### Webhook Not Receiving Events

1. **Check webhook is enabled:**
   ```bash
   curl https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/YOUR_WEBHOOK_ID \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```
   Verify `enabled: true` in response.

2. **Check event subscriptions:**
   Ensure your webhook is subscribed to the correct events.

3. **Test webhook delivery:**
   ```bash
   curl -X POST https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/YOUR_WEBHOOK_ID/test \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

### Deliveries Failing

1. **Check delivery history:**
   ```bash
   curl "https://api.integritykit.aidarena.org/api/v1/integrations/webhooks/YOUR_WEBHOOK_ID/deliveries?status=failed" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

2. **Common issues:**
   - **Timeout:** Endpoint taking >10 seconds to respond
   - **Authentication:** Invalid credentials in `auth_config`
   - **URL issues:** Incorrect URL or firewall blocking requests
   - **Certificate errors:** SSL/TLS certificate problems

3. **Verify endpoint is reachable:**
   ```bash
   curl -X POST https://your-webhook-url.com/path \
     -H "Content-Type: application/json" \
     -d '{"test": true}'
   ```

### High Failure Rate

If success rate drops below 90%:

1. Review recent error messages in delivery history
2. Check endpoint logs for errors
3. Verify endpoint has capacity to handle webhook volume
4. Consider increasing timeout if endpoint is slow
5. Implement retry logic on your end for transient failures

## Security Considerations

1. **Always verify webhook signatures** to prevent spoofing
2. **Use HTTPS** for webhook URLs in production
3. **Rotate authentication credentials** periodically
4. **Implement rate limiting** on your webhook endpoint
5. **Log and monitor** webhook activity for anomalies
6. **Use dedicated webhook endpoints** separate from public APIs

## Support

For questions or issues with the webhook system:

- Review delivery history for error details
- Check the integration health endpoint: `/api/v1/integrations/health`
- Consult the full API documentation at `/docs`
- Review the integration architecture document: `docs/integration-architecture-v1.0.md`

---

**Version:** v1.0
**Sprint:** 8
**Task:** S8-17
**Last Updated:** 2026-03-10
