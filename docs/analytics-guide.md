# Advanced Analytics User Guide - v1.0

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

## Overview

The Aid Arena Integrity Kit v1.0 provides comprehensive analytics for understanding system usage, facilitator workload, and operational performance. This guide explains how to use the analytics features for monitoring, reporting, and continuous improvement.

## Table of Contents

1. [Available Metrics](#available-metrics)
2. [Time-Series Analytics](#time-series-analytics)
3. [Topic Trend Detection](#topic-trend-detection)
4. [Facilitator Workload Analytics](#facilitator-workload-analytics)
5. [Conflict Resolution Analysis](#conflict-resolution-analysis)
6. [After-Action Reports](#after-action-reports)
7. [Dashboard Integration](#dashboard-integration)
8. [Best Practices](#best-practices)

---

## Available Metrics

### Signal Volume

Track incoming signal volume over time with channel breakdowns.

**Use cases:**
- Identify peak activity periods
- Monitor channel activity levels
- Detect unusual signal surges
- Capacity planning for facilitators

**Example query:**
```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/signal-volume?workspace_id=W123&granularity=day" \
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

### Readiness Transitions

Track how COP candidates move through readiness states over time.

**Use cases:**
- Measure verification velocity
- Identify bottlenecks in candidate workflow
- Track blocked → verified resolution time
- Monitor workflow efficiency

**Example query:**
```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/readiness-transitions?workspace_id=W123&granularity=day" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Response:**
```json
{
  "workspace_id": "W123",
  "data": [
    {
      "timestamp": "2026-03-13T00:00:00Z",
      "transitions": {
        "IN_REVIEW->VERIFIED": 25,
        "VERIFIED->BLOCKED": 3,
        "BLOCKED->IN_REVIEW": 2
      },
      "total_transitions": 30
    }
  ],
  "total_transitions": 210
}
```

### Facilitator Actions

Measure facilitator activity and action velocity.

**Use cases:**
- Track facilitator workload distribution
- Identify peak activity times
- Monitor action velocity (actions per hour)
- Capacity planning and shift scheduling

**Example query:**
```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/facilitator-actions?workspace_id=W123&facilitator_id=U456" \
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
        "cop_candidate.verify": 10,
        "cop_candidate.update_state": 8,
        "cop_candidate.update_risk_tier": 3
      },
      "action_velocity": 2.4
    }
  ],
  "total_actions": 336,
  "avg_velocity": 2.1
}
```

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
- Maximum time range: 90 days (configurable)
- `start_date` must be before `end_date`

---

## Topic Trend Detection

Identify emerging, declining, and stable topics over time.

### Trend Categories

| Trend Type | Definition | Example |
|------------|------------|---------|
| **Emerging** | Signal volume increasing > 50% | New incident gaining attention |
| **Declining** | Signal volume decreasing > 50% | Resolved incident fading |
| **Stable** | Signal volume change < 50% | Ongoing situation maintaining interest |

### Detecting Trends

Trends are computed automatically when analyzing signal volume with topic breakdown.

**Example:**
```python
from integritykit.services.analytics import AnalyticsService

service = AnalyticsService()

# Get signal volume with topic breakdown
data = await service.get_signal_volume_time_series(
    workspace_id="W123",
    granularity="day",
    include_topic_breakdown=True
)

# Analyze trends
trends = await service.detect_topic_trends(
    workspace_id="W123",
    time_range_days=7
)

for trend in trends.emerging:
    print(f"Emerging: {trend.topic_name} (+{trend.growth_pct}%)")

for trend in trends.declining:
    print(f"Declining: {trend.topic_name} (-{trend.decline_pct}%)")
```

### Use Cases

- **Emerging topics:** Allocate facilitator resources to growing incidents
- **Declining topics:** Archive or deprioritize resolved situations
- **Stable topics:** Maintain consistent monitoring and updates

---

## Facilitator Workload Analytics

### Individual Facilitator Analysis

Track a specific facilitator's activity:

```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/facilitator-actions?workspace_id=W123&facilitator_id=U456&granularity=hour" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Metrics included:**
- Total actions per time bucket
- Action breakdown by type
- Action velocity (actions per hour)
- Peak activity periods

### Team-Wide Analysis

Analyze all facilitators together:

```bash
curl "https://api.integritykit.aidarena.org/api/v1/analytics/facilitator-actions?workspace_id=W123&granularity=day" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**Includes:**
- Total team actions
- Breakdown by facilitator
- Average action velocity across team
- Action type distribution

### Workload Distribution

Identify uneven workload distribution:

```python
from integritykit.services.analytics import AnalyticsService

service = AnalyticsService()

# Get facilitator workload over last 7 days
data = await service.get_facilitator_actions(
    workspace_id="W123",
    granularity="day"
)

# Analyze distribution
facilitators = {}
for bucket in data['data']:
    for facilitator_id, count in bucket['by_facilitator'].items():
        if facilitator_id not in facilitators:
            facilitators[facilitator_id] = 0
        facilitators[facilitator_id] += count

# Identify overloaded facilitators
avg_actions = sum(facilitators.values()) / len(facilitators)
for fac_id, actions in facilitators.items():
    if actions > avg_actions * 1.5:
        print(f"Overloaded: {fac_id} ({actions} actions, {actions/avg_actions:.1f}x avg)")
```

### Recommendations

- **High velocity (>3 actions/hour):** Consider adding facilitator capacity
- **Low velocity (<1 action/hour):** May indicate underutilization or low signal volume
- **Uneven distribution (>2x variance):** Rebalance workload across facilitators

---

## Conflict Resolution Analysis

Track how quickly conflicts are detected and resolved.

### Conflict Lifecycle

1. **Conflict detected** - System identifies contradictory claims
2. **Facilitator notified** - Alert sent to facilitator
3. **Investigation** - Facilitator reviews evidence
4. **Resolution** - Conflict marked resolved or candidates merged

### Measuring Resolution Time

```python
from integritykit.services.analytics import AnalyticsService

service = AnalyticsService()

# Get conflict resolution metrics
metrics = await service.get_conflict_resolution_metrics(
    workspace_id="W123",
    start_date="2026-03-01T00:00:00Z",
    end_date="2026-03-13T23:59:59Z"
)

print(f"Total conflicts: {metrics['total_conflicts']}")
print(f"Resolved: {metrics['resolved_count']}")
print(f"Avg resolution time: {metrics['avg_resolution_time_hours']}h")
print(f"Median resolution time: {metrics['median_resolution_time_hours']}h")
```

**Response:**
```json
{
  "total_conflicts": 45,
  "resolved_count": 38,
  "unresolved_count": 7,
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
    },
    "content": {
      "count": 10,
      "avg_resolution_hours": 6.8
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

#### Executive Summary

- Total signals processed
- COP updates published
- Conflicts detected and resolved
- Facilitator participation
- System performance metrics

#### Detailed Metrics

**Signal Processing:**
- Signals ingested by channel
- Clustering accuracy
- Duplicate detection rate

**COP Production:**
- Candidates promoted
- Verification rate
- Publish velocity
- Average time-to-publish

**Facilitator Performance:**
- Actions per facilitator
- Workload distribution
- Action velocity trends
- Peak activity periods

**Conflict Management:**
- Conflicts detected by type
- Resolution time distribution
- Resolution rate
- Unresolved conflicts at end of period

#### Timeline Analysis

Hour-by-hour breakdown of key events:

```json
{
  "timeline": [
    {
      "hour": "2026-03-13T14:00:00Z",
      "signals": 15,
      "candidates_promoted": 3,
      "conflicts_detected": 1,
      "cop_updates_published": 2
    }
  ]
}
```

### Use Cases

- **Post-incident review:** Analyze response effectiveness
- **Exercise evaluation:** Assess training exercise performance
- **Process improvement:** Identify bottlenecks and inefficiencies
- **Compliance reporting:** Document actions for audit trail
- **Capacity planning:** Understand resource requirements

### Example: Exercise Evaluation

```python
from integritykit.services.report_export import ReportExportService

service = ReportExportService()

# Generate after-action report for exercise
report = await service.generate_after_action_report(
    workspace_id="W123",
    start_date="2026-03-10T08:00:00Z",  # Exercise start
    end_date="2026-03-10T16:00:00Z",     # Exercise end
    format="markdown",
    title="Hurricane Response Exercise - After Action Report"
)

# Key findings
print(f"Signals processed: {report['summary']['total_signals']}")
print(f"COP updates: {report['summary']['cop_updates_published']}")
print(f"Avg time-to-publish: {report['summary']['avg_time_to_publish_minutes']}m")
print(f"Conflict resolution rate: {report['summary']['conflict_resolution_rate']:.1%}")

# Recommendations
if report['summary']['avg_time_to_publish_minutes'] > 30:
    print("⚠ Recommendation: Improve COP drafting efficiency")

if report['summary']['conflict_resolution_rate'] < 0.9:
    print("⚠ Recommendation: Enhance conflict resolution training")
```

---

## Dashboard Integration

### Real-Time Dashboard Example

```javascript
// Fetch analytics data every 5 minutes
async function updateDashboard() {
  const data = await fetch(
    '/api/v1/analytics/time-series?workspace_id=W123&granularity=hour&metrics=signal_volume&metrics=facilitator_actions',
    { headers: { Authorization: `Bearer ${token}` } }
  ).then(r => r.json());

  // Update signal volume chart
  updateChart('signal-volume', data.signal_volume);

  // Update facilitator velocity gauge
  updateGauge('facilitator-velocity', data.summary.avg_action_velocity);

  // Update summary cards
  document.getElementById('total-signals').textContent = data.summary.total_signals;
  document.getElementById('total-actions').textContent = data.summary.total_facilitator_actions;
}

setInterval(updateDashboard, 5 * 60 * 1000);
```

### Chart.js Integration

```javascript
// Signal volume time-series chart
const ctx = document.getElementById('signal-volume-chart').getContext('2d');
const chart = new Chart(ctx, {
  type: 'line',
  data: {
    labels: data.signal_volume.map(d => d.timestamp),
    datasets: [{
      label: 'Total Signals',
      data: data.signal_volume.map(d => d.signal_count),
      borderColor: 'rgb(75, 192, 192)',
      tension: 0.1
    }]
  },
  options: {
    responsive: true,
    scales: {
      y: {
        beginAtZero: true
      }
    }
  }
});
```

### Dashboard Components

**Essential widgets:**

1. **Signal Volume Chart** - Line chart showing signal ingestion over time
2. **Facilitator Velocity Gauge** - Real-time action velocity indicator
3. **Readiness Distribution** - Pie chart showing verified/in-review/blocked breakdown
4. **Conflict Status** - Count of open vs. resolved conflicts
5. **Recent Activity Feed** - Latest facilitator actions
6. **Top Channels** - Most active channels by signal volume

**Advanced widgets:**

1. **Topic Trend Heatmap** - Visualize emerging/declining topics
2. **Facilitator Workload Distribution** - Bar chart comparing facilitator actions
3. **Time-to-Publish Histogram** - Distribution of COP publishing speed
4. **Conflict Resolution Timeline** - Gantt-style view of conflict lifecycle

---

## Best Practices

### 1. Choose Appropriate Granularity

**Hourly:**
- Real-time monitoring (last 24-48 hours)
- Incident response active phases
- Shift-level analysis

**Daily:**
- Weekly trend analysis (last 7-30 days)
- Daily standup metrics
- Workload planning

**Weekly:**
- Long-term trend analysis (12-52 weeks)
- Quarterly reviews
- Capacity planning

### 2. Query Multiple Metrics Together

More efficient than separate requests:

```bash
# Good: Single request
curl "/api/v1/analytics/time-series?metrics=signal_volume&metrics=facilitator_actions"

# Less efficient: Two requests
curl "/api/v1/analytics/signal-volume"
curl "/api/v1/analytics/facilitator-actions"
```

### 3. Cache Results Client-Side

Analytics data is relatively stable - cache for 5 minutes:

```javascript
const cache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function getCachedAnalytics(url) {
  const cached = cache.get(url);
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }

  const data = await fetch(url).then(r => r.json());
  cache.set(url, { data, timestamp: Date.now() });
  return data;
}
```

### 4. Set Baseline Metrics

Establish baseline performance during calm periods:

- **Baseline signal volume:** Average signals per day during non-incident
- **Baseline action velocity:** Normal facilitator actions per hour
- **Baseline conflict rate:** Typical conflict detection rate

Use baselines to identify anomalies during incidents.

### 5. Regular Reporting Schedule

- **Daily:** Review yesterday's metrics (5 min)
- **Weekly:** Team meeting with workload review (15 min)
- **Monthly:** Trend analysis and capacity planning (30 min)
- **Post-incident:** After-action report (1-2 hours)

### 6. Monitor Key Ratios

| Ratio | Formula | Healthy Range | Action if Outside Range |
|-------|---------|---------------|------------------------|
| Verification rate | Verified / Total candidates | > 80% | Review verification workflow |
| Conflict resolution rate | Resolved / Total conflicts | > 90% | Improve conflict detection |
| Publish velocity | Updates / Day | 5-20 | Adjust facilitator capacity |
| Action velocity | Actions / Hour | 1.5-3.0 | Balance workload |

### 7. Export for External Analysis

Download analytics data for spreadsheet analysis:

```bash
# Get data as JSON
curl "/api/v1/analytics/signal-volume?workspace_id=W123" > signal_volume.json

# Convert to CSV (using jq)
jq -r '.data[] | [.timestamp, .signal_count] | @csv' signal_volume.json > signal_volume.csv
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

### Database Indexes

Ensure these indexes exist for optimal performance:

```javascript
// Audit log - for facilitator actions
db.audit_log.createIndex({ workspace_id: 1, timestamp: -1 });
db.audit_log.createIndex({ workspace_id: 1, action_type: 1, timestamp: -1 });
db.audit_log.createIndex({ workspace_id: 1, actor_id: 1, timestamp: -1 });

// Signals - for signal volume
db.signals.createIndex({ workspace_id: 1, created_at: -1 });
db.signals.createIndex({ workspace_id: 1, channel_id: 1, created_at: -1 });

// COP candidates - for readiness transitions
db.cop_candidates.createIndex({ workspace_id: 1, updated_at: -1 });
db.cop_candidates.createIndex({ workspace_id: 1, readiness_state: 1, updated_at: -1 });
```

---

## Troubleshooting

### Query Returns Empty Data

**Symptoms:**
- API returns `data: []`
- Total counts are 0

**Solutions:**

1. **Check time range:**
   - Verify `start_date` and `end_date` span the period with data
   - Ensure dates are in correct ISO 8601 format

2. **Verify workspace ID:**
   - Confirm `workspace_id` parameter is correct
   - Check you have data for this workspace

3. **Check granularity:**
   - Ensure granularity is appropriate for time range
   - Try `granularity=day` as default

### Slow Query Performance

**Symptoms:**
- Analytics queries taking >5 seconds
- Timeout errors

**Solutions:**

1. **Reduce time range:**
   - Limit to 30 days or less
   - Use pagination for larger datasets

2. **Check database indexes:**
   - Verify indexes exist (see Configuration section)
   - Run `db.collection.getIndexes()` to confirm

3. **Use appropriate granularity:**
   - Don't use `hour` for >30 day ranges
   - Use `week` for long-term analysis

### Inconsistent Metric Values

**Symptoms:**
- Metrics don't match expected values
- Totals don't sum correctly

**Solutions:**

1. **Check data retention:**
   - Old data may have been purged
   - Verify `ANALYTICS_RETENTION_DAYS` setting

2. **Verify time zones:**
   - All timestamps are UTC
   - Convert to local timezone for display

3. **Check filtering:**
   - Ensure filters are applied consistently
   - Verify facilitator_id filter is correct

---

## See Also

- [Analytics API Examples](analytics_api_examples.md) - Code examples and sample queries
- [API Guide](api_guide.md) - Full API reference
- [MongoDB Schema](mongodb_schema.md) - Database structure
- [External Integrations Guide](external-integrations-guide.md) - Export and integration options

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8
