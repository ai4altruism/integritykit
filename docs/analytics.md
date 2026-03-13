# Analytics Guide

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

This document consolidates all analytics documentation for the Aid Arena Integrity Kit v1.0.

---

## Table of Contents

1. [Overview](#overview)
2. [Available Metrics](#available-metrics)
3. [Time-Series Analytics](#time-series-analytics)
4. [Topic Trend Detection](#topic-trend-detection)
5. [Facilitator Workload Analytics](#facilitator-workload-analytics)
6. [Conflict Resolution Analysis](#conflict-resolution-analysis)
7. [After-Action Reports](#after-action-reports)
8. [API Reference](#api-reference)
9. [Database Indexes](#database-indexes)
10. [Examples](#examples)

---

## Overview

The Aid Arena Integrity Kit v1.0 provides comprehensive analytics for understanding system usage, facilitator workload, and operational performance. Analytics help facilitators and leadership understand patterns, identify bottlenecks, and improve coordination strategies.

### Key Capabilities

- **Time-series analysis** of signal volume, readiness transitions, and facilitator actions
- **Topic trend detection** identifying emerging and declining topics
- **Facilitator workload** distribution and performance metrics
- **Conflict resolution** time analysis by risk tier
- **After-action reports** for post-incident review and exercises
- **Real-time dashboards** with configurable visualizations

---

## Available Metrics

### Signal Volume

Track incoming signal volume over time with channel breakdowns.

**Use cases:**
- Identify peak activity periods
- Monitor channel activity levels
- Detect unusual signal surges
- Capacity planning for facilitators

**Metrics provided:**
- Total signals per time bucket
- Signals by channel
- Peak signal timestamps
- Signal ingestion rate

### Readiness Transitions

Track how COP candidates move through readiness states (IN_REVIEW → VERIFIED → BLOCKED).

**Use cases:**
- Measure verification velocity
- Identify bottlenecks in candidate workflow
- Track blocked → verified resolution time
- Monitor workflow efficiency

**Metrics provided:**
- Transition counts by type
- Transition velocity
- State distribution over time
- Bottleneck identification

### Facilitator Actions

Measure facilitator activity and action velocity (actions per hour).

**Use cases:**
- Track facilitator workload distribution
- Identify peak activity times
- Monitor action velocity
- Capacity planning and shift scheduling

**Metrics provided:**
- Total actions by facilitator
- Actions by type (promote, verify, publish)
- Action velocity (actions/hour)
- Workload distribution statistics

### Topic Trends

Identify emerging, declining, and stable topics through signal clustering.

**Use cases:**
- Allocate resources to growing incidents
- Archive resolved situations
- Monitor ongoing topics

**Metrics provided:**
- Emerging topics (>50% growth)
- Declining topics (>50% decrease)
- Stable topics (<50% change)
- Topic velocity

### Conflict Resolution

Track conflict detection and resolution effectiveness.

**Use cases:**
- Measure resolution time by risk tier
- Track resolution success rates
- Identify conflict types
- Improve conflict workflows

**Metrics provided:**
- Average resolution time
- Resolution rate
- Conflict breakdown by type
- Time-to-resolution distribution

---

## Time-Series Analytics

### Granularity Options

Choose the appropriate time bucket for your analysis:

| Granularity | Best For | Default Time Range |
|-------------|----------|-------------------|
| `hour` | Real-time monitoring, recent activity | Last 24-48 hours |
| `day` | Daily patterns, weekly trends | Last 7-30 days |
| `week` | Long-term trends, capacity planning | Last 12-52 weeks |

### Multi-Metric Queries

Query multiple metrics in a single request for efficiency:

```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/time-series?workspace_id=W123&granularity=day&metrics=signal_volume&metrics=facilitator_actions&metrics=readiness_transitions" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response includes:**
```json
{
  "workspace_id": "W123",
  "signal_volume": [...],
  "facilitator_actions": [...],
  "readiness_transitions": [...],
  "summary": {
    "time_range_days": 7,
    "granularity": "day",
    "metrics_computed": ["signal_volume", "facilitator_actions", "readiness_transitions"],
    "total_signals": 1024,
    "avg_signals_per_bucket": 146.3,
    "total_facilitator_actions": 336,
    "avg_action_velocity": 2.1
  }
}
```

### Time Range Configuration

**Default:** Last 7 days

**Custom range:**
```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/signal-volume?workspace_id=W123&start_date=2026-03-01T00:00:00Z&end_date=2026-03-13T23:59:59Z" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Constraints:**
- `end_date` cannot be in the future
- Maximum time range: 90 days (configurable via `MAX_ANALYTICS_TIME_RANGE_DAYS`)
- `start_date` must be before `end_date`

---

## Topic Trend Detection

### Trend Categories

| Trend Type | Definition | Example |
|------------|------------|---------|
| **Emerging** | Signal volume increasing > 50% | New incident gaining attention |
| **Declining** | Signal volume decreasing > 50% | Resolved incident fading |
| **Stable** | Signal volume change < 50% | Ongoing situation maintaining interest |

### Detecting Trends

```python
from integritykit.services.analytics import AnalyticsService

service = AnalyticsService()

# Analyze trends
trends = await service.detect_topic_trends(
    workspace_id="W123",
    time_range_days=7
)

for trend in trends.emerging:
    print(f"Emerging: {trend.topic_name} (+{trend.growth_pct}%)")
```

---

## Facilitator Workload Analytics

### Individual Facilitator Analysis

Track a specific facilitator's activity:

```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/facilitator-actions?workspace_id=W123&facilitator_id=U456&granularity=hour" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "workspace_id": "W123",
  "facilitator_id": "U456",
  "data": [
    {
      "timestamp": "2026-03-13T14:00:00Z",
      "total_actions": 48,
      "by_action_type": {
        "cop_candidate.promote": 15,
        "cop_update.publish": 12,
        "cop_candidate.verify": 10
      },
      "action_velocity": 2.4
    }
  ],
  "total_actions": 336,
  "avg_velocity": 2.1
}
```

### Performance Targets

| Metric | Target | Action if Below Target |
|--------|--------|------------------------|
| Action velocity | 1.5-3.0 actions/hour | Adjust workload or capacity |
| Workload distribution | <2x variance | Rebalance across facilitators |
| Publish velocity | 5-20 updates/day | Review workflow efficiency |

---

## Conflict Resolution Analysis

### Measuring Resolution Time

```python
from integritykit.services.analytics import AnalyticsService

service = AnalyticsService()

metrics = await service.get_conflict_resolution_metrics(
    workspace_id="W123",
    start_date="2026-03-01T00:00:00Z",
    end_date="2026-03-13T23:59:59Z"
)

print(f"Avg resolution time: {metrics['avg_resolution_time_hours']}h")
```

**Response:**
```json
{
  "total_conflicts": 45,
  "resolved_count": 38,
  "avg_resolution_time_hours": 4.2,
  "median_resolution_time_hours": 2.8,
  "p95_resolution_time_hours": 12.5,
  "resolution_rate": 0.84,
  "by_conflict_type": {
    "location": {
      "count": 15,
      "avg_resolution_hours": 2.1
    },
    "time": {
      "count": 20,
      "avg_resolution_hours": 5.3
    }
  }
}
```

### Performance Targets

| Metric | Target | Action if Below Target |
|--------|--------|------------------------|
| Resolution rate | > 90% | Improve conflict detection accuracy |
| Avg resolution time | < 6 hours | Add facilitator capacity or training |
| Median resolution time | < 3 hours | Streamline conflict resolution workflow |

---

## After-Action Reports

Generate comprehensive reports for post-incident analysis and exercise evaluation.

### Generating a Report

```bash
curl "https://api.integritykit.aidarena.org/api/v1/exports/after-action?workspace_id=W123&start_date=2026-03-01T00:00:00Z&end_date=2026-03-13T23:59:59Z&format=json" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Formats available:**
- `json` - Structured data for analysis
- `markdown` - Human-readable report
- `pdf` - Formatted document (requires additional configuration)

### Report Contents

**Executive Summary:**
- Total signals processed
- COP updates published
- Conflicts detected and resolved
- Facilitator participation
- System performance metrics

**Detailed Metrics:**
- Signal processing statistics
- COP production metrics
- Facilitator performance
- Conflict management
- Timeline analysis (hour-by-hour breakdown)

---

## API Reference

### Time-Series Endpoint

**`GET /api/v1/analytics/time-series`**

Retrieves time-series data with configurable granularity.

**Query Parameters:**
- `workspace_id` (required): Slack workspace ID
- `start_date` (optional): ISO 8601 datetime (default: 7 days ago)
- `end_date` (optional): ISO 8601 datetime (default: now)
- `granularity` (optional): `hour`, `day`, `week` (default: `day`)
- `metrics[]` (optional): Array of metric types (default: `signal_volume`)
- `facilitator_id` (optional): Filter by facilitator

**Response:** `TimeSeriesAnalyticsResponse`

### Signal Volume

**`GET /api/v1/analytics/signal-volume`**

Returns signal ingestion volume over time.

**Response:**
```json
{
  "workspace_id": "W123",
  "start_date": "2026-03-06T00:00:00Z",
  "end_date": "2026-03-13T00:00:00Z",
  "granularity": "day",
  "data": [
    {
      "timestamp": "2026-03-13T00:00:00Z",
      "signal_count": 145,
      "by_channel": {
        "C123": 95,
        "C456": 50
      }
    }
  ],
  "total_signals": 1024
}
```

### Readiness Transitions

**`GET /api/v1/analytics/readiness-transitions`**

Returns COP candidate state transition data.

### Facilitator Actions

**`GET /api/v1/analytics/facilitator-actions`**

Returns facilitator activity and action velocity.

### Topic Trends

**`GET /api/v1/analytics/trends`**

Identifies emerging and declining topics.

**Query Parameters:**
- `start_date` (required)
- `end_date` (required)
- `min_signals`: Minimum signal count (default: 5)
- `direction`: `emerging` | `declining` | `all` (default: `all`)
- `topic_type`: Filter by topic type

### Conflict Resolution

**`GET /api/v1/analytics/conflict-resolution`**

Analyzes conflict detection and resolution effectiveness.

**Query Parameters:**
- `start_date` (required)
- `end_date` (required)
- `risk_tier`: Filter by `routine` | `elevated` | `high_stakes`
- `resolved_only`: Only resolved conflicts (default: `false`)

### After-Action Report Export

**`POST /api/v1/analytics/reports/export`**

Generates comprehensive after-action reports asynchronously.

**Request Body:**
```json
{
  "start_date": "2026-03-10T08:00:00Z",
  "end_date": "2026-03-10T16:00:00Z",
  "format": "json",
  "include_sections": ["executive_summary", "signal_volume_chart"],
  "language": "en"
}
```

---

## Database Indexes

### Signals Collection

```javascript
// Signal volume aggregation by workspace and time
db.signals.createIndex(
  {
    "slack_workspace_id": 1,
    "created_at": 1
  },
  {
    name: "analytics_signal_volume_idx",
    background: true
  }
);

// Channel-based filtering
db.signals.createIndex(
  {
    "slack_workspace_id": 1,
    "slack_channel_id": 1,
    "created_at": 1
  },
  {
    name: "analytics_signal_channel_idx",
    background: true
  }
);
```

### Audit Log Collection

```javascript
// Facilitator actions time-series
db.audit_log.createIndex(
  {
    "action_type": 1,
    "actor_role": 1,
    "timestamp": 1
  },
  {
    name: "analytics_facilitator_actions_idx",
    background: true
  }
);

// Facilitator-specific queries
db.audit_log.createIndex(
  {
    "action_type": 1,
    "actor_role": 1,
    "actor_id": 1,
    "timestamp": 1
  },
  {
    name: "analytics_facilitator_filter_idx",
    background: true
  }
);

// Readiness state transitions
db.audit_log.createIndex(
  {
    "action_type": 1,
    "timestamp": 1
  },
  {
    name: "analytics_readiness_transitions_idx",
    background: true,
    partialFilterExpression: {
      "action_type": "cop_candidate.update_state"
    }
  }
);
```

### COP Candidates Collection

```javascript
// Cluster-based queries
db.cop_candidates.createIndex(
  {
    "cluster_id": 1,
    "created_at": 1
  },
  {
    name: "analytics_cluster_candidates_idx",
    background: true
  }
);

// Readiness state queries
db.cop_candidates.createIndex(
  {
    "cluster_id": 1,
    "readiness_state": 1,
    "created_at": 1
  },
  {
    name: "analytics_readiness_state_idx",
    background: true
  }
);
```

### Clusters Collection

```javascript
// Workspace-based queries
db.clusters.createIndex(
  {
    "slack_workspace_id": 1
  },
  {
    name: "analytics_workspace_clusters_idx",
    background: true
  }
);
```

### Index Creation Script

```bash
#!/bin/bash
# create_analytics_indexes.sh

mongo integritykit --eval '
  db.signals.createIndex(
    {"slack_workspace_id": 1, "created_at": 1},
    {name: "analytics_signal_volume_idx", background: true}
  );

  db.signals.createIndex(
    {"slack_workspace_id": 1, "slack_channel_id": 1, "created_at": 1},
    {name: "analytics_signal_channel_idx", background: true}
  );

  db.audit_log.createIndex(
    {"action_type": 1, "actor_role": 1, "timestamp": 1},
    {name: "analytics_facilitator_actions_idx", background: true}
  );

  db.audit_log.createIndex(
    {"action_type": 1, "actor_role": 1, "actor_id": 1, "timestamp": 1},
    {name: "analytics_facilitator_filter_idx", background: true}
  );

  db.audit_log.createIndex(
    {"action_type": 1, "timestamp": 1},
    {name: "analytics_readiness_transitions_idx", background: true, partialFilterExpression: {"action_type": "cop_candidate.update_state"}}
  );

  db.cop_candidates.createIndex(
    {"cluster_id": 1, "created_at": 1},
    {name: "analytics_cluster_candidates_idx", background: true}
  );

  db.cop_candidates.createIndex(
    {"cluster_id": 1, "readiness_state": 1, "created_at": 1},
    {name: "analytics_readiness_state_idx", background: true}
  );

  db.clusters.createIndex(
    {"slack_workspace_id": 1},
    {name: "analytics_workspace_clusters_idx", background: true}
  );
'
```

---

## Examples

### Example 1: Signal Volume (Last 7 Days)

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/signal-volume?workspace_id=W123&granularity=day" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "workspace_id": "W123",
  "start_date": "2026-03-06T00:00:00Z",
  "end_date": "2026-03-13T00:00:00Z",
  "granularity": "day",
  "data": [
    {
      "timestamp": "2026-03-13T00:00:00Z",
      "signal_count": 145,
      "by_channel": {
        "C123": 95,
        "C456": 50
      }
    }
  ],
  "total_signals": 1024
}
```

### Example 2: Hourly Facilitator Actions

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/facilitator-actions?workspace_id=W123&facilitator_id=U456&granularity=hour" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Example 3: Multi-Metric Query

```bash
curl -X GET "http://localhost:8000/api/v1/analytics/time-series?workspace_id=W123&granularity=day&metrics=signal_volume&metrics=facilitator_actions" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### Example 4: Exercise After-Action Report

```python
from integritykit.services.report_export import ReportExportService

service = ReportExportService()

report = await service.generate_after_action_report(
    workspace_id="W123",
    start_date="2026-03-10T08:00:00Z",
    end_date="2026-03-10T16:00:00Z",
    format="markdown",
    title="Hurricane Response Exercise - After Action Report"
)

print(f"Signals processed: {report['summary']['total_signals']}")
print(f"COP updates: {report['summary']['cop_updates_published']}")
```

---

## Configuration

### Environment Variables

```bash
# Analytics retention
ANALYTICS_RETENTION_DAYS=365

# Time range limits
MAX_ANALYTICS_TIME_RANGE_DAYS=90

# Default granularity
DEFAULT_ANALYTICS_GRANULARITY=day

# Cache TTL
ANALYTICS_CACHE_TTL_SECONDS=300
```

---

## Best Practices

### 1. Choose Appropriate Granularity

- **Hourly**: Real-time monitoring (last 24-48 hours)
- **Daily**: Weekly trends (last 7-30 days)
- **Weekly**: Long-term analysis (12-52 weeks)

### 2. Query Multiple Metrics Together

More efficient than separate requests:
```bash
# Good: Single request
curl "/api/v1/analytics/time-series?metrics=signal_volume&metrics=facilitator_actions"

# Less efficient: Two requests
curl "/api/v1/analytics/signal-volume"
curl "/api/v1/analytics/facilitator-actions"
```

### 3. Monitor Key Ratios

| Ratio | Formula | Healthy Range |
|-------|---------|---------------|
| Verification rate | Verified / Total candidates | > 80% |
| Conflict resolution rate | Resolved / Total conflicts | > 90% |
| Publish velocity | Updates / Day | 5-20 |
| Action velocity | Actions / Hour | 1.5-3.0 |

### 4. Regular Reporting Schedule

- **Daily**: Review yesterday's metrics (5 min)
- **Weekly**: Team meeting with workload review (15 min)
- **Monthly**: Trend analysis and capacity planning (30 min)
- **Post-incident**: After-action report (1-2 hours)

---

## Troubleshooting

### Query Returns Empty Data

**Solutions:**
1. Check time range spans period with data
2. Verify workspace ID is correct
3. Ensure dates are in ISO 8601 format
4. Try `granularity=day` as default

### Slow Query Performance

**Solutions:**
1. Reduce time range to 30 days or less
2. Verify indexes exist (see Database Indexes section)
3. Use appropriate granularity (don't use `hour` for >30 day ranges)

### Inconsistent Metric Values

**Solutions:**
1. Check data retention settings
2. Verify all timestamps are UTC
3. Ensure filters are applied consistently

---

## See Also

- [API Guide](api_guide.md) - Full API reference
- [External Integrations Guide](external-integrations.md) - Export and integration options
- [MongoDB Schema](mongodb_schema.md) - Database structure
- [Multi-Language Guide](multi-language.md) - Multi-language support

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8

**Sources Consolidated:**
- `analytics-guide.md`
- `analytics-api-summary.md`
- `analytics_api_examples.md`
- `analytics_indexes.md`
