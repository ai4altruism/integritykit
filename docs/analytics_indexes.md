# Analytics Service MongoDB Indexes

This document outlines recommended MongoDB indexes for optimal performance of the time-series analytics service (S8-9).

## Overview

The analytics service uses MongoDB aggregation pipelines with time-based queries. Proper indexing is critical for query performance, especially as data volume grows.

## Recommended Indexes

### 1. Signals Collection

**Purpose:** Optimize signal volume time-series queries

```javascript
// Index for signal volume aggregation by workspace and time
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

// Compound index for channel-based filtering
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

**Query Pattern:**
```javascript
{
  "slack_workspace_id": "W123",
  "created_at": { "$gte": ISODate("2026-03-01"), "$lte": ISODate("2026-03-07") }
}
```

### 2. Audit Log Collection

**Purpose:** Optimize facilitator action and readiness transition queries

```javascript
// Index for facilitator actions time-series
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

// Index for facilitator-specific queries
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

// Index for readiness state transitions
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

**Query Patterns:**
```javascript
// Facilitator actions
{
  "action_type": { "$in": ["cop_candidate.promote", "cop_update.publish", ...] },
  "actor_role": { "$in": ["facilitator", "workspace_admin"] },
  "timestamp": { "$gte": ISODate("2026-03-01"), "$lte": ISODate("2026-03-07") }
}

// Facilitator-specific
{
  "action_type": { "$in": [...] },
  "actor_role": { "$in": [...] },
  "actor_id": "U123",
  "timestamp": { "$gte": ..., "$lte": ... }
}

// Readiness transitions
{
  "action_type": "cop_candidate.update_state",
  "timestamp": { "$gte": ..., "$lte": ... }
}
```

### 3. Clusters Collection

**Purpose:** Support workspace-scoped candidate queries

```javascript
// Index for workspace lookup
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

**Query Pattern:**
```javascript
{
  "slack_workspace_id": "W123"
}
```

### 4. COP Candidates Collection

**Purpose:** Support readiness distribution queries (used by existing metrics service)

```javascript
// Index for cluster-based candidate lookup
db.cop_candidates.createIndex(
  {
    "cluster_id": 1,
    "created_at": 1
  },
  {
    name: "analytics_candidates_cluster_idx",
    background: true
  }
);

// Index for readiness state queries
db.cop_candidates.createIndex(
  {
    "cluster_id": 1,
    "readiness_state": 1,
    "created_at": 1
  },
  {
    name: "analytics_candidates_state_idx",
    background: true
  }
);
```

## Index Creation Script

Run this script to create all recommended indexes:

```bash
#!/bin/bash
# create_analytics_indexes.sh

MONGO_URI="${MONGODB_URI:-mongodb://localhost:27017}"
DB_NAME="${MONGODB_DATABASE:-integritykit}"

mongosh "$MONGO_URI/$DB_NAME" <<'EOF'

print("Creating analytics indexes...");

// Signals indexes
db.signals.createIndex(
  { "slack_workspace_id": 1, "created_at": 1 },
  { name: "analytics_signal_volume_idx", background: true }
);
print("✓ Created analytics_signal_volume_idx");

db.signals.createIndex(
  { "slack_workspace_id": 1, "slack_channel_id": 1, "created_at": 1 },
  { name: "analytics_signal_channel_idx", background: true }
);
print("✓ Created analytics_signal_channel_idx");

// Audit log indexes
db.audit_log.createIndex(
  { "action_type": 1, "actor_role": 1, "timestamp": 1 },
  { name: "analytics_facilitator_actions_idx", background: true }
);
print("✓ Created analytics_facilitator_actions_idx");

db.audit_log.createIndex(
  { "action_type": 1, "actor_role": 1, "actor_id": 1, "timestamp": 1 },
  { name: "analytics_facilitator_filter_idx", background: true }
);
print("✓ Created analytics_facilitator_filter_idx");

db.audit_log.createIndex(
  { "action_type": 1, "timestamp": 1 },
  {
    name: "analytics_readiness_transitions_idx",
    background: true,
    partialFilterExpression: { "action_type": "cop_candidate.update_state" }
  }
);
print("✓ Created analytics_readiness_transitions_idx");

// Clusters index
db.clusters.createIndex(
  { "slack_workspace_id": 1 },
  { name: "analytics_workspace_clusters_idx", background: true }
);
print("✓ Created analytics_workspace_clusters_idx");

// COP candidates indexes
db.cop_candidates.createIndex(
  { "cluster_id": 1, "created_at": 1 },
  { name: "analytics_candidates_cluster_idx", background: true }
);
print("✓ Created analytics_candidates_cluster_idx");

db.cop_candidates.createIndex(
  { "cluster_id": 1, "readiness_state": 1, "created_at": 1 },
  { name: "analytics_candidates_state_idx", background: true }
);
print("✓ Created analytics_candidates_state_idx");

print("\nAll analytics indexes created successfully!");

EOF
```

## Performance Considerations

### Query Optimization

1. **Time Range Limits**
   - Max query range: 90 days (configurable via `MAX_ANALYTICS_TIME_RANGE_DAYS`)
   - Prevents expensive queries over large datasets

2. **Index Selection**
   - MongoDB will automatically use the most selective index
   - Use `explain()` to verify index usage in development

3. **Background Index Creation**
   - All indexes created with `background: true` to avoid blocking operations
   - Safe for production deployment

### Aggregation Pipeline Performance

The analytics service uses efficient aggregation patterns:

```javascript
// Signal volume pipeline
[
  { $match: { /* indexed fields */ } },        // Stage 1: Fast index scan
  { $group: { _id: { time_bucket: ..., channel_id: ... } } },  // Stage 2: Group
  { $group: { _id: "$_id.time_bucket", ... } },  // Stage 3: Re-group
  { $sort: { _id: 1 } }                        // Stage 4: Sort
]
```

**Pipeline Optimization:**
- `$match` stage uses indexes for fast filtering
- `$group` stages leverage in-memory aggregation
- Final `$sort` operates on bucketed results (small dataset)

### Monitoring Query Performance

Use MongoDB's built-in profiling to monitor slow queries:

```javascript
// Enable profiling for queries > 100ms
db.setProfilingLevel(1, { slowms: 100 });

// Check slow queries
db.system.profile.find({ ns: "integritykit.signals" }).sort({ ts: -1 }).limit(10);
```

## Cache Strategy

The analytics service supports caching (configurable via `ANALYTICS_CACHE_TTL_SECONDS`):

```python
# Default: 5 minutes
ANALYTICS_CACHE_TTL_SECONDS=300
```

**Cache Key Pattern:**
```
analytics:workspace:{workspace_id}:granularity:{granularity}:start:{start_date}:end:{end_date}:metrics:{metrics}
```

## Scaling Recommendations

### For Large Datasets (>1M signals)

1. **Time-Series Collections**
   - Consider MongoDB time-series collections for signals
   - Automatic bucketing and compression
   - Better query performance for time-based queries

2. **Read Replicas**
   - Route analytics queries to read replicas
   - Reduces load on primary database

3. **Aggregation Optimization**
   - Use `allowDiskUse: true` for large aggregations
   - Consider pre-aggregating data for common queries

### Example: Time-Series Collection

```javascript
// Convert signals to time-series collection
db.createCollection("signals_ts", {
  timeseries: {
    timeField: "created_at",
    metaField: "slack_workspace_id",
    granularity: "hours"
  }
});

// Automatic bucketing and compression
// Better performance for time-based queries
```

## Index Maintenance

### Check Index Usage

```javascript
// Check index statistics
db.signals.aggregate([
  { $indexStats: {} }
]);

// Get index sizes
db.signals.stats().indexSizes;
```

### Rebuild Indexes (if needed)

```javascript
// Rebuild specific index
db.signals.reIndex();

// Or rebuild all indexes
db.signals.reIndex();
```

## Environment Variables

Configure analytics service via environment variables:

```bash
# Analytics retention (days)
ANALYTICS_RETENTION_DAYS=365

# Cache TTL (seconds)
ANALYTICS_CACHE_TTL_SECONDS=300

# Max query time range (days)
MAX_ANALYTICS_TIME_RANGE_DAYS=90
```

## Testing Index Performance

Use `explain()` to verify index usage:

```javascript
// Test signal volume query
db.signals.explain("executionStats").aggregate([
  {
    $match: {
      slack_workspace_id: "W123",
      created_at: {
        $gte: ISODate("2026-03-01"),
        $lte: ISODate("2026-03-07")
      }
    }
  },
  // ... rest of pipeline
]);

// Look for:
// - "stage": "IXSCAN" (index scan, good)
// - NOT "stage": "COLLSCAN" (collection scan, bad)
// - "nReturned" vs "totalDocsExamined" (should be close)
```

## Summary

Proper indexing ensures:
- Fast time-series queries (< 2s p95 for 90-day ranges)
- Efficient workspace-scoped filtering
- Scalability to millions of signals
- Optimal MongoDB aggregation pipeline performance

For production deployments, always create these indexes before enabling analytics features.
