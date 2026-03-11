# Analytics API Usage Examples

This document provides practical examples of using the time-series analytics API endpoints.

## Base URL

```
http://localhost:8000/api/v1/analytics
```

## Authentication

All analytics endpoints require authentication with facilitator or workspace_admin role.

For development/testing:
```bash
-H "X-Test-User-Id: U123" \
-H "X-Test-Team-Id: T123"
```

For production:
```bash
-H "Authorization: Bearer <slack_oauth_token>"
```

## Endpoint Examples

### 1. Signal Volume Time-Series

Get signal ingestion volume over time with channel breakdown.

#### Example 1: Last 7 Days, Daily Granularity

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/signal-volume?workspace_id=W123&granularity=day" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

Response:
```json
{
  "workspace_id": "W123",
  "start_date": "2026-03-03T00:00:00Z",
  "end_date": "2026-03-10T00:00:00Z",
  "granularity": "day",
  "data": [
    {
      "timestamp": "2026-03-03T00:00:00Z",
      "signal_count": 15,
      "by_channel": {
        "C123": 10,
        "C456": 5
      }
    },
    {
      "timestamp": "2026-03-04T00:00:00Z",
      "signal_count": 22,
      "by_channel": {
        "C123": 18,
        "C456": 4
      }
    }
  ],
  "total_signals": 145
}
```

#### Example 2: Last 24 Hours, Hourly Granularity

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/signal-volume?workspace_id=W123&granularity=hour&start_date=2026-03-09T00:00:00Z&end_date=2026-03-10T00:00:00Z" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

#### Example 3: Last 12 Weeks, Weekly Granularity

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/signal-volume?workspace_id=W123&granularity=week&start_date=2025-12-16T00:00:00Z&end_date=2026-03-10T00:00:00Z" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

### 2. Readiness State Transitions

Track how COP candidates move through readiness states.

#### Example: Daily Transitions for Last 30 Days

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/readiness-transitions?workspace_id=W123&start_date=2026-02-08T00:00:00Z&end_date=2026-03-10T00:00:00Z&granularity=day" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

Response:
```json
{
  "workspace_id": "W123",
  "start_date": "2026-02-08T00:00:00Z",
  "end_date": "2026-03-10T00:00:00Z",
  "granularity": "day",
  "data": [
    {
      "timestamp": "2026-03-10T00:00:00Z",
      "transitions": {
        "IN_REVIEW->VERIFIED": 8,
        "VERIFIED->BLOCKED": 2,
        "BLOCKED->IN_REVIEW": 1
      },
      "total_transitions": 11
    }
  ],
  "total_transitions": 245
}
```

### 3. Facilitator Actions

Measure facilitator activity and action velocity.

#### Example 1: All Facilitators, Last 7 Days

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/facilitator-actions?workspace_id=W123&granularity=day" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

Response:
```json
{
  "workspace_id": "W123",
  "start_date": "2026-03-03T00:00:00Z",
  "end_date": "2026-03-10T00:00:00Z",
  "granularity": "day",
  "facilitator_id": null,
  "data": [
    {
      "timestamp": "2026-03-10T00:00:00Z",
      "total_actions": 48,
      "by_action_type": {
        "cop_candidate.promote": 15,
        "cop_update.publish": 12,
        "cop_candidate.verify": 10,
        "cop_candidate.update_state": 8,
        "cop_candidate.update_risk_tier": 3
      },
      "by_facilitator": {
        "U123": 25,
        "U456": 15,
        "U789": 8
      },
      "action_velocity": 2.0
    }
  ],
  "total_actions": 336,
  "avg_velocity": 2.0
}
```

#### Example 2: Specific Facilitator

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/facilitator-actions?workspace_id=W123&facilitator_id=U456&granularity=day" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

#### Example 3: Hourly Velocity for Last 24 Hours

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/facilitator-actions?workspace_id=W123&granularity=hour&start_date=2026-03-09T00:00:00Z&end_date=2026-03-10T00:00:00Z" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

### 4. Multi-Metric Time-Series (Combined Query)

Get multiple metrics in a single request for efficiency.

#### Example 1: All Three Metrics, Daily

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/time-series?workspace_id=W123&granularity=day&metrics=signal_volume&metrics=readiness_transitions&metrics=facilitator_actions" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

Response:
```json
{
  "workspace_id": "W123",
  "start_date": "2026-03-03T00:00:00Z",
  "end_date": "2026-03-10T00:00:00Z",
  "granularity": "day",
  "signal_volume": [
    {
      "timestamp": "2026-03-10T00:00:00Z",
      "signal_count": 22,
      "by_channel": {
        "C123": 18,
        "C456": 4
      }
    }
  ],
  "readiness_transitions": [
    {
      "timestamp": "2026-03-10T00:00:00Z",
      "transitions": {
        "IN_REVIEW->VERIFIED": 8
      },
      "total_transitions": 8
    }
  ],
  "facilitator_actions": [
    {
      "timestamp": "2026-03-10T00:00:00Z",
      "total_actions": 48,
      "by_action_type": {
        "cop_candidate.promote": 15,
        "cop_update.publish": 12
      },
      "by_facilitator": {
        "U123": 25,
        "U456": 15
      },
      "action_velocity": 2.0
    }
  ],
  "summary": {
    "time_range_days": 7,
    "granularity": "day",
    "metrics_computed": ["signal_volume", "readiness_transitions", "facilitator_actions"],
    "total_signals": 145,
    "avg_signals_per_bucket": 20.7,
    "total_readiness_transitions": 56,
    "total_facilitator_actions": 336,
    "avg_action_velocity": 2.0
  }
}
```

#### Example 2: Signal Volume + Facilitator Actions, Hourly

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/time-series?workspace_id=W123&granularity=hour&metrics=signal_volume&metrics=facilitator_actions&start_date=2026-03-09T00:00:00Z&end_date=2026-03-10T00:00:00Z" \
  -H "X-Test-User-Id: U123" \
  -H "X-Test-Team-Id: T123"
```

## Query Parameters Reference

### Common Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `workspace_id` | string | Yes | - | Slack workspace ID |
| `start_date` | ISO 8601 | No | 7 days ago | Start of time range |
| `end_date` | ISO 8601 | No | Now | End of time range |
| `granularity` | enum | No | `day` | Time bucket size: `hour`, `day`, `week` |

### Endpoint-Specific Parameters

**`/analytics/time-series`:**
- `metrics[]` (array of enum): Which metrics to compute
  - `signal_volume`
  - `readiness_transitions`
  - `facilitator_actions`
- `facilitator_id` (string): Filter facilitator actions by user ID

**`/analytics/facilitator-actions`:**
- `facilitator_id` (string): Filter by specific facilitator

## Error Responses

### 400 Bad Request - Invalid Date Range

```json
{
  "detail": "start_date must be before end_date"
}
```

### 400 Bad Request - Future Date

```json
{
  "detail": "end_date cannot be in the future"
}
```

### 400 Bad Request - Time Range Too Large

```json
{
  "detail": "Time range (120 days) exceeds maximum (90 days)"
}
```

### 401 Unauthorized

```json
{
  "detail": "Not authenticated"
}
```

### 403 Forbidden - Insufficient Permissions

```json
{
  "detail": "Insufficient permissions. Requires facilitator or workspace_admin role."
}
```

## Python Client Example

```python
import requests
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1/analytics"

# Authentication headers
headers = {
    "X-Test-User-Id": "U123",
    "X-Test-Team-Id": "T123",
}

# Query signal volume for last 7 days
end_date = datetime.utcnow()
start_date = end_date - timedelta(days=7)

params = {
    "workspace_id": "W123",
    "granularity": "day",
    "start_date": start_date.isoformat(),
    "end_date": end_date.isoformat(),
}

response = requests.get(
    f"{BASE_URL}/signal-volume",
    params=params,
    headers=headers,
)

data = response.json()
print(f"Total signals: {data['total_signals']}")

for point in data['data']:
    print(f"{point['timestamp']}: {point['signal_count']} signals")
```

## JavaScript Client Example

```javascript
const BASE_URL = "http://localhost:8000/api/v1/analytics";

// Authentication headers
const headers = {
  "X-Test-User-Id": "U123",
  "X-Test-Team-Id": "T123",
};

// Query facilitator actions
async function getFacilitatorActions(workspaceId, facilitatorId) {
  const params = new URLSearchParams({
    workspace_id: workspaceId,
    granularity: "day",
    facilitator_id: facilitatorId,
  });

  const response = await fetch(
    `${BASE_URL}/facilitator-actions?${params}`,
    { headers }
  );

  const data = await response.json();

  console.log(`Total actions: ${data.total_actions}`);
  console.log(`Average velocity: ${data.avg_velocity} actions/hour`);

  return data;
}

// Query multiple metrics
async function getTimeSeriesAnalytics(workspaceId, metrics) {
  const params = new URLSearchParams({
    workspace_id: workspaceId,
    granularity: "day",
  });

  // Add multiple metric parameters
  metrics.forEach(metric => params.append("metrics", metric));

  const response = await fetch(
    `${BASE_URL}/time-series?${params}`,
    { headers }
  );

  return await response.json();
}

// Usage
const data = await getTimeSeriesAnalytics("W123", [
  "signal_volume",
  "facilitator_actions"
]);
```

## Performance Tips

1. **Use Appropriate Granularity**
   - Hour: Last 24-48 hours
   - Day: Last 7-30 days
   - Week: Last 12-52 weeks

2. **Query Multiple Metrics Together**
   - More efficient than separate requests
   - Single database query

3. **Limit Time Ranges**
   - Keep ranges under 90 days
   - Use pagination for larger datasets

4. **Cache Results**
   - Results are relatively stable
   - Cache client-side for 5 minutes

5. **Use Filters**
   - `facilitator_id` filter reduces data volume
   - Faster queries and smaller responses

## Dashboard Integration Example

```javascript
// Real-time analytics dashboard update
async function updateAnalyticsDashboard(workspaceId) {
  const data = await fetch(
    `/api/v1/analytics/time-series?workspace_id=${workspaceId}&granularity=hour&metrics=signal_volume&metrics=facilitator_actions`,
    { headers }
  ).then(r => r.json());

  // Update signal volume chart
  updateChart("signal-volume-chart", data.signal_volume);

  // Update facilitator activity gauge
  updateGauge("facilitator-velocity", data.summary.avg_action_velocity);

  // Update summary cards
  updateSummaryCard("total-signals", data.summary.total_signals);
  updateSummaryCard("total-actions", data.summary.total_facilitator_actions);
}

// Refresh every 5 minutes
setInterval(() => updateAnalyticsDashboard("W123"), 5 * 60 * 1000);
```

## See Also

- [MongoDB Indexes Documentation](analytics_indexes.md)
- [Implementation Details](../ANALYTICS_IMPLEMENTATION.md)
- [Sprint 8 SDP](Aid_Arena_Integrity_Kit_SDP_Sprint8_v1_0.md)
