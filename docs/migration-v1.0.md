# Migration Guide: v0.4.0 → v1.0

**Version:** 1.0
**Sprint:** Sprint 8
**Last Updated:** 2026-03-13

## Overview

This guide provides step-by-step instructions for upgrading from Aid Arena Integrity Kit v0.4.0 to v1.0. The v1.0 release adds multi-language support, external integrations, and advanced analytics while maintaining backward compatibility with existing data and APIs.

## What's New in v1.0

### Major Features

1. **Multi-Language Support** - COP drafts in Spanish and French
2. **External Integrations** - Webhooks, CAP, EDXL-DE, GeoJSON exports
3. **Inbound Verification Sources** - Import from authoritative APIs
4. **Advanced Analytics** - Time-series metrics, trend detection, after-action reports
5. **Integration Health Monitoring** - Track integration status and performance

### Breaking Changes

**None** - v1.0 is fully backward compatible with v0.4.0 data and APIs.

All v0.4.0 endpoints continue to work without modification. New features are additive.

## Pre-Migration Checklist

Before upgrading, complete these steps:

- [ ] **Backup your database** - Full MongoDB backup recommended
- [ ] **Review current configuration** - Document existing environment variables
- [ ] **Check disk space** - Ensure sufficient space for new collections and indexes
- [ ] **Review API usage** - Identify custom integrations that may benefit from new features
- [ ] **Plan downtime** - Estimate 15-30 minutes for upgrade process

## Migration Steps

### Step 1: Backup Current System

```bash
# MongoDB backup
mongodump --uri="mongodb://localhost:27017" --db=integritykit --out=/backup/integritykit-v0.4.0-$(date +%Y%m%d)

# Environment configuration backup
cp .env .env.v0.4.0.backup

# Docker volumes backup (if using Docker)
docker run --rm -v integritykit_mongodb:/data -v $(pwd)/backup:/backup alpine tar czf /backup/mongodb-$(date +%Y%m%d).tar.gz /data
```

### Step 2: Update Environment Variables

Add new v1.0 environment variables to your `.env` file:

```bash
# Multi-Language Configuration
SUPPORTED_LANGUAGES=en,es,fr
DEFAULT_LANGUAGE=en
LANGUAGE_DETECTION_ENABLED=false
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8

# Webhook Configuration
WEBHOOKS_ENABLED=false
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_DELAY_SECONDS=60
WEBHOOK_BACKOFF_MULTIPLIER=2.0

# Export Configuration
CAP_EXPORT_ENABLED=false
CAP_SENDER_ID=integritykit@yourdomain.org
EDXL_DE_EXPORT_ENABLED=false
GEOJSON_EXPORT_ENABLED=false

# External Source Configuration
EXTERNAL_SOURCES_ENABLED=false
MAX_IMPORTS_PER_SOURCE_PER_HOUR=100

# Analytics Configuration
ANALYTICS_RETENTION_DAYS=365
MAX_ANALYTICS_TIME_RANGE_DAYS=90
```

**Note:** All new features are disabled by default. Enable them after successful migration and testing.

### Step 3: Update Code

#### Docker Deployment

```bash
# Pull latest image
docker pull integritykit:v1.0

# Stop current container
docker stop integritykit

# Remove old container
docker rm integritykit

# Start new container
docker run -d \
  --name integritykit \
  -p 8080:8080 \
  --env-file .env \
  integritykit:v1.0
```

#### Source Deployment

```bash
# Pull latest code
git fetch
git checkout v1.0.0

# Update dependencies
pip install -e ".[dev]"

# Restart application
systemctl restart integritykit  # Or your process manager
```

### Step 4: Run Database Migrations

v1.0 adds new collections and indexes. The application will create these automatically on first run, but you can pre-create them for faster startup:

```javascript
// Connect to MongoDB
mongo mongodb://localhost:27017/integritykit

// Create new collections
db.createCollection("webhooks");
db.createCollection("webhook_deliveries");
db.createCollection("external_sources");
db.createCollection("import_jobs");

// Create indexes for analytics performance
db.audit_log.createIndex({ workspace_id: 1, timestamp: -1 });
db.audit_log.createIndex({ workspace_id: 1, action_type: 1, timestamp: -1 });
db.audit_log.createIndex({ workspace_id: 1, actor_id: 1, timestamp: -1 });

db.signals.createIndex({ workspace_id: 1, created_at: -1 });
db.signals.createIndex({ workspace_id: 1, channel_id: 1, created_at: -1 });

db.cop_candidates.createIndex({ workspace_id: 1, updated_at: -1 });
db.cop_candidates.createIndex({ workspace_id: 1, readiness_state: 1, updated_at: -1 });

// Create indexes for integration features
db.webhooks.createIndex({ workspace_id: 1, enabled: 1 });
db.webhooks.createIndex({ workspace_id: 1, events: 1 });

db.webhook_deliveries.createIndex({ webhook_id: 1, timestamp: -1 });
db.webhook_deliveries.createIndex({ webhook_id: 1, status: 1, timestamp: -1 });

db.external_sources.createIndex({ workspace_id: 1, enabled: 1 });
db.external_sources.createIndex({ workspace_id: 1, source_type: 1 });

db.import_jobs.createIndex({ source_id: 1, created_at: -1 });
db.import_jobs.createIndex({ workspace_id: 1, status: 1 });

// Verify indexes
db.audit_log.getIndexes();
db.signals.getIndexes();
db.cop_candidates.getIndexes();
db.webhooks.getIndexes();
```

**Expected output:** Index creation commands should complete without errors.

### Step 5: Verify Migration

#### Check Application Health

```bash
curl http://localhost:8080/health
```

**Expected response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-03-13T14:30:00Z"
}
```

#### Verify Database

```bash
# Check collections exist
mongo mongodb://localhost:27017/integritykit --eval "db.getCollectionNames()"
```

**Expected output should include:**
```
[
  "audit_log",
  "cop_candidates",
  "cop_updates",
  "signals",
  "users",
  "webhooks",           // NEW
  "webhook_deliveries", // NEW
  "external_sources",   // NEW
  "import_jobs"         // NEW
]
```

#### Test Existing Functionality

1. **List COP candidates:**
   ```bash
   curl http://localhost:8080/api/v1/candidates \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

2. **Search signals:**
   ```bash
   curl "http://localhost:8080/api/v1/search?q=shelter&type=signal" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

3. **Create COP draft:**
   ```bash
   curl -X POST http://localhost:8080/api/v1/publish/drafts \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{
       "candidate_ids": ["candidate-123"]
     }'
   ```

All existing endpoints should work without modification.

### Step 6: Enable New Features

After verifying the migration, enable new features one at a time.

#### Enable Multi-Language Support

```bash
# Update .env
SUPPORTED_LANGUAGES=en,es,fr
DEFAULT_LANGUAGE=en

# Restart application
systemctl restart integritykit
```

**Test:**
```bash
# Create Spanish draft
curl -X POST http://localhost:8080/api/v1/publish/drafts \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "candidate_ids": ["candidate-123"],
    "language": "es"
  }'
```

#### Enable GeoJSON Export

```bash
# Update .env
GEOJSON_EXPORT_ENABLED=true

# Restart application
systemctl restart integritykit
```

**Test:**
```bash
curl http://localhost:8080/api/v1/exports/geojson/{update_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/json"
```

#### Enable CAP Export

```bash
# Update .env
CAP_EXPORT_ENABLED=true
CAP_SENDER_ID=integritykit@yourdomain.org

# Restart application
systemctl restart integritykit
```

**Test:**
```bash
curl http://localhost:8080/api/v1/exports/cap/{update_id} \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Accept: application/xml"
```

#### Enable Webhooks

```bash
# Update .env
WEBHOOKS_ENABLED=true

# Restart application
systemctl restart integritykit
```

**Test:**
```bash
# Create test webhook
curl -X POST http://localhost:8080/api/v1/integrations/webhooks \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Webhook",
    "url": "https://webhook.site/your-unique-url",
    "events": ["cop_update.published"],
    "auth_type": "none",
    "enabled": true
  }'

# Test webhook delivery
curl -X POST http://localhost:8080/api/v1/integrations/webhooks/{webhook_id}/test \
  -H "Authorization: Bearer YOUR_TOKEN"
```

#### Enable Analytics

Analytics are enabled by default. Test:

```bash
curl "http://localhost:8080/api/v1/analytics/signal-volume?workspace_id=W123&granularity=day" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## Data Migration

### Existing Data Compatibility

**Good news:** All existing v0.4.0 data remains fully compatible.

- **Signals** - No changes required
- **COP Candidates** - No changes required
- **COP Updates** - No changes required
- **Users** - No changes required
- **Audit Log** - No changes required

### Optional: Add Language Metadata

If you want to retroactively add language metadata to existing COP updates:

```javascript
// Mark all existing updates as English
db.cop_updates.updateMany(
  { language: { $exists: false } },
  { $set: { language: "en" } }
);

// Verify
db.cop_updates.find({ language: "en" }).count();
```

This is **optional** - existing updates without language metadata will default to English.

## Configuration Changes

### Removed Configuration

**None** - All v0.4.0 configuration options remain valid.

### New Configuration

See [Step 2: Update Environment Variables](#step-2-update-environment-variables) for full list.

**Recommended defaults for production:**

```bash
# Enable core features
SUPPORTED_LANGUAGES=en,es,fr
GEOJSON_EXPORT_ENABLED=true
CAP_EXPORT_ENABLED=true

# Keep disabled until ready
WEBHOOKS_ENABLED=false
EXTERNAL_SOURCES_ENABLED=false
LANGUAGE_DETECTION_ENABLED=false
```

## API Changes

### New Endpoints

All new endpoints - no changes to existing endpoints:

**Analytics:**
- `GET /api/v1/analytics/signal-volume`
- `GET /api/v1/analytics/readiness-transitions`
- `GET /api/v1/analytics/facilitator-actions`
- `GET /api/v1/analytics/time-series`

**Integrations:**
- `GET /api/v1/integrations/health`
- `POST /api/v1/integrations/webhooks`
- `GET /api/v1/integrations/webhooks`
- `GET /api/v1/integrations/webhooks/{id}`
- `PUT /api/v1/integrations/webhooks/{id}`
- `DELETE /api/v1/integrations/webhooks/{id}`
- `POST /api/v1/integrations/webhooks/{id}/test`
- `GET /api/v1/integrations/webhooks/{id}/deliveries`

**External Sources:**
- `POST /api/v1/integrations/sources`
- `GET /api/v1/integrations/sources`
- `GET /api/v1/integrations/sources/{id}`
- `PUT /api/v1/integrations/sources/{id}`
- `DELETE /api/v1/integrations/sources/{id}`
- `POST /api/v1/integrations/sources/{id}/import`

**Exports:**
- `GET /api/v1/exports/cap/{update_id}`
- `GET /api/v1/exports/edxl/{update_id}`
- `GET /api/v1/exports/geojson/{update_id}`
- `GET /api/v1/exports/after-action`

**Language:**
- `POST /api/v1/language/detect`

### Modified Endpoints

**Draft creation now supports `language` parameter:**

```bash
POST /api/v1/publish/drafts

{
  "candidate_ids": ["..."],
  "title": "...",
  "language": "es"  # NEW: Optional language parameter
}
```

**Existing behavior:** If `language` is not specified, defaults to `en` (English).

## Troubleshooting

### Migration Failed

**Symptoms:**
- Application won't start after upgrade
- Database connection errors
- Missing collections

**Solutions:**

1. **Restore from backup:**
   ```bash
   mongorestore --uri="mongodb://localhost:27017" --db=integritykit /backup/integritykit-v0.4.0-YYYYMMDD
   ```

2. **Rollback to v0.4.0:**
   ```bash
   docker pull integritykit:v0.4.0
   docker run -d --name integritykit -p 8080:8080 --env-file .env.v0.4.0.backup integritykit:v0.4.0
   ```

3. **Check logs:**
   ```bash
   docker logs integritykit
   # Or
   journalctl -u integritykit -n 100
   ```

### Indexes Not Created

**Symptoms:**
- Slow analytics queries
- Timeout errors on analytics endpoints

**Solutions:**

1. **Manually create indexes:**
   Run the index creation commands from [Step 4](#step-4-run-database-migrations)

2. **Verify index creation:**
   ```bash
   mongo mongodb://localhost:27017/integritykit --eval "db.audit_log.getIndexes()"
   ```

3. **Wait for background index build:**
   Large databases may take time to build indexes. Check:
   ```bash
   db.currentOp({ "command.createIndexes": { $exists: true } })
   ```

### New Features Not Working

**Symptoms:**
- Webhook creation returns 404
- Analytics endpoints return errors
- Language parameter ignored

**Solutions:**

1. **Verify version:**
   ```bash
   curl http://localhost:8080/health | jq .version
   ```
   Should return `"1.0.0"`

2. **Check feature flags:**
   ```bash
   grep -E "(WEBHOOKS_ENABLED|CAP_EXPORT_ENABLED)" .env
   ```

3. **Restart application:**
   ```bash
   systemctl restart integritykit
   ```

4. **Check application logs for errors:**
   ```bash
   docker logs integritykit --tail 100
   ```

### Analytics Return No Data

**Symptoms:**
- Analytics endpoints return empty arrays
- Total counts are 0

**Solutions:**

1. **Check time range:**
   - Ensure `start_date` and `end_date` span period with data
   - Default is last 7 days

2. **Verify workspace ID:**
   ```bash
   curl "http://localhost:8080/api/v1/analytics/signal-volume?workspace_id=YOUR_WORKSPACE_ID" \
     -H "Authorization: Bearer YOUR_TOKEN"
   ```

3. **Check audit log has data:**
   ```bash
   mongo mongodb://localhost:27017/integritykit --eval "db.audit_log.count()"
   ```

## Post-Migration Tasks

### 1. Enable Integrations Gradually

Don't enable all integrations at once. Recommended order:

1. **Week 1:** Enable GeoJSON export, test with mapping tools
2. **Week 2:** Enable CAP export, test with public alerting system
3. **Week 3:** Enable webhooks, test with 1-2 critical integrations
4. **Week 4:** Enable external sources, test with trusted government API
5. **Week 5:** Enable language detection, test with Spanish/French content

### 2. Configure Monitoring

Set up monitoring for new features:

```bash
# Check integration health daily
curl http://localhost:8080/api/v1/integrations/health \
  -H "Authorization: Bearer YOUR_TOKEN"

# Monitor webhook success rate
curl http://localhost:8080/api/v1/integrations/webhooks \
  -H "Authorization: Bearer YOUR_TOKEN" \
  | jq '.data[] | {name, success_rate: .statistics.success_rate}'
```

### 3. Train Facilitators

- Review new multi-language features
- Demonstrate analytics dashboards
- Explain webhook event types
- Practice export workflows (CAP, GeoJSON)

### 4. Update Documentation

- Update runbooks with new endpoints
- Document webhook configurations
- Add analytics dashboards to monitoring docs
- Update incident response procedures

### 5. Performance Tuning

Monitor performance after migration:

```bash
# Check slow queries
mongo mongodb://localhost:27017/integritykit --eval "db.system.profile.find().pretty()"

# Monitor query performance
db.setProfilingLevel(1, { slowms: 100 })
```

Adjust these settings if needed:
- `MAX_ANALYTICS_TIME_RANGE_DAYS` - Reduce if queries are slow
- `WEBHOOK_TIMEOUT_SECONDS` - Increase if webhooks timing out
- `IMPORT_BATCH_SIZE` - Reduce if imports are slow

## Rollback Procedure

If you need to rollback to v0.4.0:

### 1. Stop v1.0 Application

```bash
docker stop integritykit
# Or
systemctl stop integritykit
```

### 2. Restore v0.4.0 Database (If Modified)

```bash
mongorestore --uri="mongodb://localhost:27017" \
  --db=integritykit \
  --drop \
  /backup/integritykit-v0.4.0-YYYYMMDD
```

**Note:** Only necessary if you created webhooks, external sources, or modified existing data. Analytics and exports don't modify existing data.

### 3. Revert Configuration

```bash
cp .env.v0.4.0.backup .env
```

### 4. Start v0.4.0 Application

```bash
docker run -d --name integritykit -p 8080:8080 --env-file .env integritykit:v0.4.0
# Or
git checkout v0.4.0
pip install -e ".[dev]"
systemctl start integritykit
```

### 5. Verify Rollback

```bash
curl http://localhost:8080/health | jq .version
# Should return "0.4.0"
```

## Getting Help

### Documentation

- [Multi-Language Guide](multi-language-guide.md)
- [External Integrations Guide](external-integrations-guide.md)
- [Analytics Guide](analytics-guide.md)
- [API Guide](api_guide.md)

### Support Channels

- GitHub Issues: https://github.com/aidarena/integritykit/issues
- Email: support@aidarena.org
- Documentation: https://github.com/aidarena/integritykit#readme

### Reporting Migration Issues

When reporting migration issues, include:

1. **Version information:**
   ```bash
   curl http://localhost:8080/health | jq .version
   ```

2. **Environment:**
   - Operating system
   - Docker version (if using Docker)
   - Python version (if source deployment)
   - MongoDB version

3. **Error logs:**
   ```bash
   docker logs integritykit --tail 200 > migration-error.log
   ```

4. **Database state:**
   ```bash
   mongo mongodb://localhost:27017/integritykit --eval "db.getCollectionNames()" > collections.txt
   ```

## Summary

v1.0 is a major feature release that maintains full backward compatibility with v0.4.0. The migration process is straightforward:

1. ✅ Backup database and configuration
2. ✅ Update environment variables
3. ✅ Update application code
4. ✅ Run database migrations (automatic)
5. ✅ Verify existing functionality
6. ✅ Enable new features incrementally

**Estimated migration time:** 15-30 minutes
**Downtime:** Minimal (< 5 minutes)
**Risk level:** Low (fully backward compatible)

---

**Version:** 1.0
**Last Updated:** 2026-03-13
**Sprint:** 8
