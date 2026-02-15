# Aid Arena Integrity Kit API Guide

| Field | Value |
|---|---|
| **Version** | 1.0 |
| **Date** | 2026-02-15 |
| **API Base URL** | `https://api.integritykit.aidarena.org/api/v1` |

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Authorization & Roles](#authorization--roles)
4. [Common Patterns](#common-patterns)
5. [Workflow Examples](#workflow-examples)
6. [Error Handling](#error-handling)
7. [Rate Limiting](#rate-limiting)
8. [Best Practices](#best-practices)

---

## Overview

The Aid Arena Integrity Kit API provides programmatic access to the Common Operating Picture (COP) facilitator workflow. The API follows REST principles with JSON request/response bodies and standard HTTP methods.

**Key Features:**
- Slack OAuth 2.0 authentication
- Role-based access control (RBAC)
- Comprehensive audit logging
- Evidence-based verification workflow
- Publish gate enforcement for high-stakes information

**Base URL:** `https://api.integritykit.aidarena.org/api/v1`

---

## Authentication

All API endpoints (except `/auth/slack/callback`) require authentication via Slack OAuth 2.0.

### OAuth Flow

1. **Redirect user to Slack authorization URL:**
   ```
   https://slack.com/oauth/v2/authorize?
     client_id=YOUR_CLIENT_ID&
     scope=users:read,channels:read,chat:write&
     redirect_uri=https://your-app.com/auth/callback&
     state=RANDOM_STATE_TOKEN
   ```

2. **User authorizes app in Slack**

3. **Slack redirects to your callback URL:**
   ```
   https://your-app.com/auth/callback?
     code=AUTHORIZATION_CODE&
     state=RANDOM_STATE_TOKEN
   ```

4. **Your app calls our API's callback endpoint:**
   ```
   GET /api/v1/auth/slack/callback?code=AUTHORIZATION_CODE&state=STATE_TOKEN
   ```

5. **API sets session cookie and redirects to application**

### Session-Based Authentication

After OAuth authentication, the API sets a secure, httpOnly session cookie. Include this cookie in all subsequent requests.

**Example authenticated request:**
```bash
curl -X GET https://api.integritykit.aidarena.org/api/v1/auth/me \
  -H "Cookie: session=SESSION_TOKEN"
```

### Get Current User

To verify authentication and retrieve user roles:

```bash
GET /api/v1/auth/me
```

**Response:**
```json
{
  "data": {
    "id": "65d4f2c3e4b0a8c9d1234501",
    "slack_user_id": "U01USER5678",
    "slack_email": "jane@aidorg.org",
    "slack_display_name": "Jane F.",
    "roles": ["general_participant", "facilitator", "verifier"],
    "is_suspended": false,
    "created_at": "2026-02-01T12:00:00.000Z"
  }
}
```

---

## Authorization & Roles

The API enforces role-based access control (RBAC). Every user has one or more roles:

| Role | Permissions |
|---|---|
| **general_participant** | Read-only access to published COPs |
| **facilitator** | Full backlog and candidate management, COP drafting/publishing |
| **verifier** | Verification actions on candidates |
| **workspace_admin** | User and role management, full system access |

### Permission Matrix

| Endpoint | Required Role |
|---|---|
| `GET /backlog`, `GET /candidates` | facilitator, verifier, workspace_admin |
| `POST /backlog/{id}/promote` | facilitator, workspace_admin |
| `PATCH /candidates/{id}` | facilitator, workspace_admin |
| `POST /candidates/{id}/verify` | verifier, facilitator, workspace_admin |
| `POST /cop/publish` | facilitator, workspace_admin |
| `GET /audit` | facilitator, workspace_admin |
| `GET /users`, `POST /users/{id}/roles` | workspace_admin |

### Access Denied Response

If you lack required permissions:

```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Insufficient permissions. Requires facilitator role.",
    "request_id": "req_abc123"
  }
}
```

---

## Common Patterns

### Pagination

All list endpoints support cursor-based pagination via `page` and `per_page` parameters.

**Request:**
```bash
GET /api/v1/backlog?page=2&per_page=20
```

**Response:**
```json
{
  "data": [...],
  "meta": {
    "page": 2,
    "per_page": 20,
    "total": 156,
    "total_pages": 8
  }
}
```

### Filtering

Many endpoints support filtering via query parameters:

```bash
GET /api/v1/candidates?readiness_state=verified&risk_tier=high_stakes
GET /api/v1/backlog?has_conflicts=true&min_priority=0.7
GET /api/v1/search?q=shelter&type=signal&start_time=2026-02-14T00:00:00Z
```

### Sorting

Results are sorted by default (e.g., backlog by `priority_score DESC`, audit log by `timestamp DESC`). Custom sorting is not currently supported.

### Response Envelope

All successful responses use a consistent envelope:

```json
{
  "data": { /* resource or array of resources */ },
  "meta": { /* pagination metadata (for lists) */ }
}
```

---

## Workflow Examples

### Example 1: Promote Cluster to Candidate

**Scenario:** Facilitator reviews backlog and promotes a high-priority cluster to COP candidate.

**Step 1: List backlog clusters**
```bash
GET /api/v1/backlog?min_priority=0.7
```

**Step 2: Get cluster details**
```bash
GET /api/v1/backlog/65d4f2c3e4b0a8c9d1234560
```

**Response includes signals and conflict analysis:**
```json
{
  "data": {
    "id": "65d4f2c3e4b0a8c9d1234560",
    "name": "Shelter Alpha Closure - Feb 15",
    "priority_score": 0.72,
    "has_conflicts": true,
    "signals": [
      {
        "id": "65d4f2c3e4b0a8c9d1234567",
        "text": "Shelter Alpha closing at 6pm...",
        "permalink": "https://workspace.slack.com/archives/..."
      }
    ],
    "conflict_details": [
      {
        "field": "time",
        "values": ["6pm", "6:30pm"],
        "severity": "minor"
      }
    ]
  }
}
```

**Step 3: Promote to candidate**
```bash
POST /api/v1/backlog/65d4f2c3e4b0a8c9d1234560/promote

{
  "primary_signal_ids": ["65d4f2c3e4b0a8c9d1234567"],
  "initial_risk_tier": "elevated",
  "notes": "High-priority for next COP update"
}
```

**Response:**
```json
{
  "data": {
    "id": "65d4f2c3e4b0a8c9d1234570",
    "cluster_id": "65d4f2c3e4b0a8c9d1234560",
    "readiness_state": "blocked",
    "risk_tier": "elevated",
    "missing_fields": ["verification"],
    "recommended_action": {
      "action_type": "assign_verification",
      "reason": "Elevated risk tier requires verification"
    }
  }
}
```

---

### Example 2: Verify Candidate

**Scenario:** Verifier confirms candidate via authoritative source.

**Step 1: Get candidate details**
```bash
GET /api/v1/candidates/65d4f2c3e4b0a8c9d1234570
```

**Step 2: Record verification**
```bash
POST /api/v1/candidates/65d4f2c3e4b0a8c9d1234570/verify

{
  "verification_method": "authoritative_source",
  "verification_notes": "Confirmed via official county emergency management website; cross-referenced with shelter director's Slack message.",
  "confidence_level": "high",
  "external_sources": [
    {
      "url": "https://springfieldcounty.gov/emergency-notices/shelter-alpha-temporary-closure",
      "title": "Springfield County Emergency Notices: Shelter Alpha Temporary Closure",
      "source_type": "official_source"
    }
  ]
}
```

**Response:**
```json
{
  "data": {
    "id": "65d4f2c3e4b0a8c9d1234570",
    "readiness_state": "verified",
    "verifications": [
      {
        "verified_by": "65d4f2c3e4b0a8c9d1234501",
        "verified_at": "2026-02-15T15:30:00.000Z",
        "verification_method": "authoritative_source",
        "confidence_level": "high"
      }
    ],
    "missing_fields": [],
    "recommended_action": {
      "action_type": "publish_as_verified",
      "reason": "All fields complete, verified via authoritative source"
    }
  }
}
```

---

### Example 3: Publish COP Update

**Scenario:** Facilitator assembles draft and publishes COP update to Slack.

**Step 1: Get current draft**
```bash
GET /api/v1/cop/draft
```

**Response:**
```json
{
  "data": {
    "sections": {
      "verified": [
        {
          "id": "65d4f2c3e4b0a8c9d1234570",
          "draft_wording": {
            "headline": "Shelter Alpha Temporarily Closed; Residents Relocated",
            "body": "Shelter Alpha (123 Main St) is closed..."
          }
        }
      ],
      "in_review": [
        {
          "id": "65d4f2c3e4b0a8c9d1234571",
          "draft_wording": {
            "headline": "UNCONFIRMED: Possible Boil Water Advisory for Zone 3",
            "hedging_applied": true
          }
        }
      ]
    },
    "publish_gates": {
      "can_publish": false,
      "blocking_issues": [
        {
          "issue_type": "high_stakes_unverified",
          "description": "Candidate 65d4f2c3e4b0a8c9d1234571 is high-stakes but unverified",
          "requires_override": true
        }
      ]
    }
  }
}
```

**Step 2: Edit draft line (optional)**
```bash
PATCH /api/v1/cop/draft/65d4f2c3e4b0a8c9d1234571

{
  "body": "Reports indicate a boil water advisory may be in effect for Zone 3..."
}
```

**Step 3: Publish with override**
```bash
POST /api/v1/cop/publish

{
  "slack_channel_id": "C01COP12345",
  "overrides": [
    {
      "candidate_id": "65d4f2c3e4b0a8c9d1234571",
      "override_type": "high_stakes_unverified",
      "justification": "Public health information is time-sensitive; publishing with UNCONFIRMED label and strong caveats while verification is in progress. Residents need awareness even if not yet confirmed."
    }
  ],
  "next_update_time": "2026-02-15T18:00:00.000Z"
}
```

**Response:**
```json
{
  "data": {
    "id": "65d4f2c3e4b0a8c9d1234580",
    "version_number": 3,
    "published_at": "2026-02-15T16:30:00.000Z",
    "slack_channel_id": "C01COP12345",
    "slack_permalink": "https://workspace.slack.com/archives/C01COP12345/p1708020600987654",
    "metrics": {
      "total_verified_items": 1,
      "total_in_review_items": 1,
      "provenance_coverage_pct": 100.0
    }
  }
}
```

---

### Example 4: Search Signals

**Scenario:** Facilitator searches for signals related to "water advisory" in last 7 days.

```bash
GET /api/v1/search?q=water+advisory&type=signal&start_time=2026-02-08T00:00:00Z
```

**Response:**
```json
{
  "data": [
    {
      "type": "signal",
      "id": "65d4f2c3e4b0a8c9d1234580",
      "score": 0.92,
      "highlight": {
        "text": "Reports indicate a <em>boil water advisory</em> may be in effect..."
      },
      "entity": {
        "id": "65d4f2c3e4b0a8c9d1234580",
        "text": "Reports indicate a boil water advisory...",
        "posted_at": "2026-02-15T16:00:00.000Z",
        "permalink": "https://workspace.slack.com/archives/..."
      }
    }
  ],
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 1,
    "total_pages": 1,
    "total_matches": 1,
    "search_time_ms": 45
  }
}
```

---

## Error Handling

All errors follow a consistent format:

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error message",
    "details": [
      {
        "field": "field_name",
        "message": "Field-specific error",
        "code": "FIELD_ERROR_CODE"
      }
    ],
    "request_id": "req_abc123"
  }
}
```

### Common Error Codes

| HTTP Status | Error Code | When to Use |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Invalid input data |
| 400 | `INVALID_REQUEST` | Malformed request |
| 401 | `UNAUTHORIZED` | No or invalid authentication |
| 403 | `FORBIDDEN` | Insufficient permissions |
| 404 | `NOT_FOUND` | Resource not found |
| 409 | `ALREADY_EXISTS` | Duplicate resource |
| 409 | `CONFLICT` | State conflict |
| 422 | `UNPROCESSABLE` | Business rule violation |
| 429 | `RATE_LIMIT_EXCEEDED` | Too many requests |
| 500 | `INTERNAL_ERROR` | Server error |

### Example: Validation Error

**Request:**
```bash
POST /api/v1/candidates/123/verify

{
  "verification_method": "invalid_method",
  "confidence_level": "high"
}
```

**Response (400 Bad Request):**
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input data",
    "details": [
      {
        "field": "verification_method",
        "message": "Must be one of: firsthand, authoritative_source, cross_reference, other",
        "code": "INVALID_ENUM_VALUE"
      },
      {
        "field": "verification_notes",
        "message": "Required field missing",
        "code": "REQUIRED_FIELD_MISSING"
      }
    ],
    "request_id": "req_xyz789"
  }
}
```

### Example: Business Rule Violation

**Request:**
```bash
POST /api/v1/cop/publish

{
  "slack_channel_id": "C01COP12345"
}
```

**Response (422 Unprocessable Entity):**
```json
{
  "error": {
    "code": "UNPROCESSABLE",
    "message": "Cannot publish high-stakes unverified candidate without override justification",
    "details": [
      {
        "field": "overrides",
        "message": "Missing override for candidate_id 65d4f2c3e4b0a8c9d1234571",
        "code": "MISSING_OVERRIDE"
      }
    ],
    "request_id": "req_def456"
  }
}
```

---

## Rate Limiting

The API enforces rate limits to prevent abuse and ensure system stability.

### Limits

| Endpoint Pattern | Limit |
|---|---|
| `POST /cop/publish` | 1 request per 5 minutes |
| All other endpoints | 100 requests per minute |

### Rate Limit Headers

All responses include rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1708020660
```

### Rate Limit Exceeded

When rate limit is exceeded:

**Response (429 Too Many Requests):**
```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many COP publish requests. Maximum 1 per 5 minutes.",
    "request_id": "req_ghi789"
  }
}
```

**Headers:**
```
Retry-After: 240
```

---

## Best Practices

### 1. Request IDs

Always log `request_id` from error responses for support and debugging:

```javascript
try {
  const response = await fetch('/api/v1/candidates/123');
  if (!response.ok) {
    const error = await response.json();
    console.error(`Request failed: ${error.error.request_id}`);
  }
} catch (err) {
  console.error('Network error', err);
}
```

### 2. Idempotency

Use idempotent operations where possible:
- `GET`, `PUT`, `DELETE` are naturally idempotent
- `POST` operations (promote, verify, publish) are **not** idempotent; avoid duplicate submissions

### 3. Optimistic UI Updates

For better UX, update UI optimistically and handle errors gracefully:

```javascript
// Optimistically update UI
setCandidateState('verified');

// Send request
try {
  await verifyCandidate(id, data);
} catch (err) {
  // Revert on error
  setCandidateState('blocked');
  showError(err.error.message);
}
```

### 4. Pagination

Always handle pagination for large datasets:

```javascript
async function fetchAllCandidates() {
  let page = 1;
  let allCandidates = [];
  let hasMore = true;

  while (hasMore) {
    const response = await fetch(`/api/v1/candidates?page=${page}&per_page=50`);
    const { data, meta } = await response.json();

    allCandidates = [...allCandidates, ...data];
    hasMore = page < meta.total_pages;
    page++;
  }

  return allCandidates;
}
```

### 5. Date/Time Handling

All timestamps are UTC in ISO 8601 format. Always convert to local timezone for display:

```javascript
const publishedAt = new Date(copUpdate.published_at);
const localTime = publishedAt.toLocaleString('en-US', {
  timeZone: 'America/Chicago',
  dateStyle: 'medium',
  timeStyle: 'short'
});
```

### 6. Evidence Pack Completeness

Always check `missing_fields` and `blocking_issues` before attempting to publish:

```javascript
if (candidate.missing_fields.length > 0) {
  showWarning(`Missing fields: ${candidate.missing_fields.join(', ')}`);
}

if (candidate.blocking_issues.some(i => i.severity === 'blocks_publishing')) {
  disablePublishButton();
}
```

### 7. Audit Trail

All write operations are logged to audit trail. Include meaningful `justification` or `notes` fields:

```javascript
// Good: Clear justification
await assignRole(userId, 'facilitator', {
  justification: 'Promoted to facilitator for Feb 2026 crisis exercise coverage'
});

// Bad: Generic justification
await assignRole(userId, 'facilitator', {
  justification: 'Needed'
});
```

---

## Additional Resources

- **OpenAPI Specification:** `/docs/openapi.yaml`
- **MongoDB Schema:** `/docs/mongodb_schema.md`
- **Support:** support@aidarena.org

---

**End of API Guide**
