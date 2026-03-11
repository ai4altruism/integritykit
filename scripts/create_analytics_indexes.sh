#!/bin/bash
# Create MongoDB indexes for analytics queries (S8-9)
#
# This script creates all recommended indexes for optimal time-series analytics performance.
# Run this before enabling analytics features in production.
#
# Usage:
#   ./scripts/create_analytics_indexes.sh
#
# Environment variables:
#   MONGODB_URI - MongoDB connection URI (default: mongodb://localhost:27017)
#   MONGODB_DATABASE - Database name (default: integritykit)

set -e

MONGO_URI="${MONGODB_URI:-mongodb://localhost:27017}"
DB_NAME="${MONGODB_DATABASE:-integritykit}"

echo "Creating analytics indexes for database: $DB_NAME"
echo "MongoDB URI: $MONGO_URI"
echo ""

mongosh "$MONGO_URI/$DB_NAME" <<'EOF'

print("=== Creating Analytics Indexes ===\n");

// Signals indexes
print("Creating indexes on 'signals' collection...");
db.signals.createIndex(
  { "slack_workspace_id": 1, "created_at": 1 },
  { name: "analytics_signal_volume_idx", background: true }
);
print("✓ Created analytics_signal_volume_idx");

db.signals.createIndex(
  { "slack_workspace_id": 1, "slack_channel_id": 1, "created_at": 1 },
  { name: "analytics_signal_channel_idx", background: true }
);
print("✓ Created analytics_signal_channel_idx\n");

// Audit log indexes
print("Creating indexes on 'audit_log' collection...");
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
print("✓ Created analytics_readiness_transitions_idx (partial)\n");

// Clusters index
print("Creating indexes on 'clusters' collection...");
db.clusters.createIndex(
  { "slack_workspace_id": 1 },
  { name: "analytics_workspace_clusters_idx", background: true }
);
print("✓ Created analytics_workspace_clusters_idx\n");

// COP candidates indexes
print("Creating indexes on 'cop_candidates' collection...");
db.cop_candidates.createIndex(
  { "cluster_id": 1, "created_at": 1 },
  { name: "analytics_candidates_cluster_idx", background: true }
);
print("✓ Created analytics_candidates_cluster_idx");

db.cop_candidates.createIndex(
  { "cluster_id": 1, "readiness_state": 1, "created_at": 1 },
  { name: "analytics_candidates_state_idx", background: true }
);
print("✓ Created analytics_candidates_state_idx\n");

// Summary
print("=== Index Creation Complete ===\n");
print("All analytics indexes created successfully!");
print("\nIndex summary:");
print("  - signals: 2 indexes");
print("  - audit_log: 3 indexes (1 partial)");
print("  - clusters: 1 index");
print("  - cop_candidates: 2 indexes");
print("  Total: 8 new indexes\n");

// Verify index creation
print("Verifying indexes...\n");

var signalsIndexes = db.signals.getIndexes();
var auditIndexes = db.audit_log.getIndexes();
var clustersIndexes = db.clusters.getIndexes();
var candidatesIndexes = db.cop_candidates.getIndexes();

var analyticsIndexes = [
  "analytics_signal_volume_idx",
  "analytics_signal_channel_idx",
  "analytics_facilitator_actions_idx",
  "analytics_facilitator_filter_idx",
  "analytics_readiness_transitions_idx",
  "analytics_workspace_clusters_idx",
  "analytics_candidates_cluster_idx",
  "analytics_candidates_state_idx"
];

var found = 0;
analyticsIndexes.forEach(function(name) {
  var exists = false;
  [signalsIndexes, auditIndexes, clustersIndexes, candidatesIndexes].forEach(function(indexes) {
    indexes.forEach(function(idx) {
      if (idx.name === name) {
        exists = true;
      }
    });
  });
  if (exists) {
    print("✓ " + name);
    found++;
  } else {
    print("✗ " + name + " - NOT FOUND!");
  }
});

print("\nVerification: " + found + "/" + analyticsIndexes.length + " indexes found");

if (found === analyticsIndexes.length) {
  print("\n✓ All analytics indexes verified successfully!");
} else {
  print("\n⚠ Warning: Some indexes were not created. Check for errors above.");
  quit(1);
}

EOF

echo ""
echo "Analytics indexes created and verified successfully!"
echo ""
echo "You can now use the time-series analytics API endpoints:"
echo "  GET /api/v1/analytics/time-series"
echo "  GET /api/v1/analytics/signal-volume"
echo "  GET /api/v1/analytics/readiness-transitions"
echo "  GET /api/v1/analytics/facilitator-actions"
echo ""
echo "For more information, see docs/analytics_indexes.md"
