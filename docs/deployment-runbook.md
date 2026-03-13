# Aid Arena Integrity Kit v1.0 - Deployment Runbook

**Version:** 1.0.0
**Last Updated:** 2026-03-13
**Maintained By:** Infrastructure Team

## Table of Contents

1. [Overview](#overview)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Environment Setup](#environment-setup)
4. [Database Migration](#database-migration)
5. [Deployment Procedure](#deployment-procedure)
6. [Health Checks & Verification](#health-checks--verification)
7. [Rollback Procedure](#rollback-procedure)
8. [Monitoring & Alerting](#monitoring--alerting)
9. [Post-Deployment Tasks](#post-deployment-tasks)
10. [Troubleshooting](#troubleshooting)

---

## Overview

### About This Release

Aid Arena Integrity Kit v1.0 introduces major new features:
- **Multi-language support** (English, Spanish, French)
- **Analytics & reporting** (time-series, trends, workload analysis)
- **Outbound webhooks** for external system integration
- **External verification sources** for inbound data
- **Export formats** (CAP 1.2, EDXL-DE 2.0, GeoJSON)

### Architecture

```
┌─────────────────┐
│   Nginx/Proxy   │ (Port 443/80)
└────────┬────────┘
         │
┌────────▼────────┐
│  IntegrityKit   │ (Port 8000)
│   FastAPI App   │
└────────┬────────┘
         │
    ┌────┴─────┬─────────┐
    │          │         │
┌───▼───┐  ┌──▼───┐  ┌──▼─────┐
│MongoDB│  │Chroma│  │ Slack  │
│  DB   │  │  DB  │  │  API   │
└───────┘  └──────┘  └────────┘
```

### Deployment Strategy

- **Method:** Docker-based containerized deployment
- **Approach:** Blue-green deployment (recommended for zero downtime)
- **Database:** MongoDB with versioned migrations
- **Reverse Proxy:** Nginx for SSL termination and routing

---

## Pre-Deployment Checklist

### Critical Security Items (MUST Complete Before Deployment)

Review the [Security Review document](./security-review-v1.0.md) and address:

- [ ] **OAuth Implementation** - Verify Slack OAuth token validation is implemented
- [ ] **SSRF Protection** - Confirm webhooks/external sources validate URLs and block private IPs
- [ ] **Credential Encryption** - Verify auth_config fields are encrypted at rest
- [ ] **Test Headers Disabled** - Ensure X-Test-User-Id headers only work when DEBUG=true
- [ ] **MongoDB Authentication** - Production MongoDB has authentication enabled
- [ ] **Rate Limiting** - Verify rate limiting middleware is active

### Infrastructure Preparation

- [ ] Server provisioned with minimum requirements:
  - **CPU:** 4 cores (2 for app, 1 for MongoDB, 1 for ChromaDB)
  - **RAM:** 8GB minimum (16GB recommended)
  - **Disk:** 100GB minimum (SSD recommended)
  - **OS:** Ubuntu 22.04 LTS or similar
- [ ] Docker and Docker Compose installed (Docker 24.0+, Compose 2.20+)
- [ ] Firewall configured (ports 80, 443 open; 8000, 27017, 8001 internal only)
- [ ] SSL certificate obtained (Let's Encrypt or commercial)
- [ ] Backup system in place
- [ ] Monitoring agents installed (Prometheus, DataDog, etc.)

### Application Preparation

- [ ] Repository cloned or code transferred to server
- [ ] `.env.production` file created with all required variables
- [ ] Secrets management configured (AWS Secrets Manager, Vault, etc.)
- [ ] Nginx configuration prepared
- [ ] Log rotation configured
- [ ] Backup of current production environment (if upgrade)

### Communication

- [ ] Deployment window scheduled and communicated
- [ ] Stakeholders notified
- [ ] Rollback plan documented
- [ ] On-call engineer identified

---

## Environment Setup

### Required Environment Variables

Create `/home/integritykit/.env.production` with the following:

```bash
# ============================================================================
# APPLICATION SETTINGS
# ============================================================================
DEBUG=false
APP_VERSION=1.0.0

# ============================================================================
# SLACK CONFIGURATION
# ============================================================================
SLACK_BOT_TOKEN=xoxb-YOUR-PRODUCTION-TOKEN
SLACK_SIGNING_SECRET=YOUR-SIGNING-SECRET
SLACK_WORKSPACE_ID=T123456789
SLACK_APP_TOKEN=xapp-YOUR-APP-TOKEN  # Optional for Socket Mode

# Monitored channels (comma-separated channel IDs)
SLACK_MONITORED_CHANNELS=C123456,C789012

# ============================================================================
# OPENAI CONFIGURATION
# ============================================================================
OPENAI_API_KEY=sk-YOUR-PRODUCTION-KEY
OPENAI_EMBEDDING_MODEL=text-embedding-3-small

# Optional: Anthropic for Claude models
ANTHROPIC_API_KEY=sk-ant-YOUR-KEY

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================
# MongoDB (with authentication for production)
MONGODB_URI=mongodb://integritykit_user:STRONG_PASSWORD@mongodb:27017/integritykit?authSource=admin
MONGODB_DATABASE=integritykit

# MongoDB root credentials (for docker-compose.prod.yml)
MONGO_USERNAME=integritykit_user
MONGO_PASSWORD=STRONG_PASSWORD_HERE

# ChromaDB
CHROMADB_HOST=chromadb
CHROMADB_PORT=8000

# ============================================================================
# DATA RETENTION
# ============================================================================
DEFAULT_RETENTION_DAYS=90

# ============================================================================
# SECURITY SETTINGS
# ============================================================================
# Two-person rule
TWO_PERSON_RULE_ENABLED=true
TWO_PERSON_RULE_TIMEOUT_HOURS=24

# Anti-abuse detection
ABUSE_DETECTION_ENABLED=true
ABUSE_OVERRIDE_THRESHOLD=5
ABUSE_OVERRIDE_WINDOW_MINUTES=30
ABUSE_ALERT_SLACK_CHANNEL=C_SECURITY_ALERTS  # Optional

# CORS (comma-separated allowed origins)
CORS_ALLOWED_ORIGINS=https://yourapp.com,https://www.yourapp.com

# Rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS_PER_MINUTE=60

# ============================================================================
# v1.0 MULTI-LANGUAGE SUPPORT
# ============================================================================
SUPPORTED_LANGUAGES=en,es,fr
DEFAULT_LANGUAGE=en
LANGUAGE_DETECTION_ENABLED=true
LANGUAGE_DETECTION_CONFIDENCE_THRESHOLD=0.8

# ============================================================================
# v1.0 ANALYTICS
# ============================================================================
ANALYTICS_RETENTION_DAYS=365
MAX_ANALYTICS_TIME_RANGE_DAYS=90

# ============================================================================
# v1.0 WEBHOOKS
# ============================================================================
WEBHOOKS_ENABLED=true
WEBHOOK_TIMEOUT_SECONDS=10
WEBHOOK_MAX_RETRIES=3

# ============================================================================
# v1.0 EXPORTS
# ============================================================================
CAP_EXPORT_ENABLED=true
EDXL_DE_EXPORT_ENABLED=true
GEOJSON_EXPORT_ENABLED=true
```

### Secure Secrets Management

**DO NOT** store the `.env.production` file in version control.

**Recommended Approach:**

#### Option 1: AWS Secrets Manager (Recommended)

```bash
# Store secrets in AWS Secrets Manager
aws secretsmanager create-secret \
  --name integritykit/production \
  --secret-string file://.env.production

# Fetch at deployment time
aws secretsmanager get-secret-value \
  --secret-id integritykit/production \
  --query SecretString --output text > .env.production
```

#### Option 2: HashiCorp Vault

```bash
# Store secrets in Vault
vault kv put secret/integritykit/production @.env.production

# Fetch at deployment time
vault kv get -format=json secret/integritykit/production \
  | jq -r '.data.data | to_entries[] | "\(.key)=\(.value)"' > .env.production
```

#### Option 3: Encrypted .env (Minimal)

```bash
# Encrypt .env file with GPG
gpg --symmetric --cipher-algo AES256 .env.production

# Decrypt at deployment time
gpg --decrypt .env.production.gpg > .env.production
```

### File Permissions

```bash
# Restrict .env file permissions
chmod 600 .env.production
chown integritykit:integritykit .env.production

# Verify
ls -la .env.production
# Should show: -rw------- 1 integritykit integritykit
```

---

## Database Migration

### MongoDB Setup

#### 1. Initialize MongoDB with Authentication

```bash
# Start MongoDB container
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d mongodb

# Wait for MongoDB to be ready
sleep 10

# Create application user
docker exec -it integritykit-mongodb mongosh admin <<EOF
db.createUser({
  user: "integritykit_user",
  pwd: "STRONG_PASSWORD_HERE",
  roles: [
    { role: "readWrite", db: "integritykit" },
    { role: "dbAdmin", db: "integritykit" }
  ]
});
EOF

# Verify authentication
docker exec -it integritykit-mongodb mongosh \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin \
  integritykit \
  --eval "db.runCommand({ connectionStatus: 1 })"
```

#### 2. Create Collections and Indexes

```bash
# Run index creation script
docker exec -it integritykit-mongodb mongosh \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin \
  integritykit <<EOF

// Core collections
db.createCollection("users");
db.createCollection("signals");
db.createCollection("cop_candidates");
db.createCollection("cop_updates");
db.createCollection("clusters");
db.createCollection("audit_log");

// v1.0 collections
db.createCollection("webhooks");
db.createCollection("webhook_deliveries");
db.createCollection("external_sources");
db.createCollection("imported_verifications");
db.createCollection("export_logs");

// Users indexes
db.users.createIndex({ "slack_user_id": 1, "workspace_id": 1 }, { unique: true });
db.users.createIndex({ "workspace_id": 1 });
db.users.createIndex({ "role": 1 });

// Signals indexes
db.signals.createIndex({ "workspace_id": 1, "created_at": -1 });
db.signals.createIndex({ "channel_id": 1, "created_at": -1 });
db.signals.createIndex({ "user_id": 1 });
db.signals.createIndex({ "expires_at": 1 });  // TTL index

// COP Candidates indexes
db.cop_candidates.createIndex({ "workspace_id": 1, "readiness_state": 1 });
db.cop_candidates.createIndex({ "cluster_id": 1 });
db.cop_candidates.createIndex({ "risk_tier": 1 });
db.cop_candidates.createIndex({ "created_at": -1 });

// COP Updates indexes
db.cop_updates.createIndex({ "workspace_id": 1, "published_at": -1 });
db.cop_updates.createIndex({ "status": 1 });

// Clusters indexes
db.clusters.createIndex({ "workspace_id": 1, "created_at": -1 });
db.clusters.createIndex({ "readiness_state": 1 });

// Audit log indexes
db.audit_log.createIndex({ "workspace_id": 1, "timestamp": -1 });
db.audit_log.createIndex({ "user_id": 1, "timestamp": -1 });
db.audit_log.createIndex({ "action": 1 });
db.audit_log.createIndex({ "entity_type": 1, "entity_id": 1 });

// v1.0 Webhook indexes
db.webhooks.createIndex({ "workspace_id": 1 });
db.webhooks.createIndex({ "enabled": 1 });
db.webhook_deliveries.createIndex({ "webhook_id": 1, "created_at": -1 });
db.webhook_deliveries.createIndex({ "workspace_id": 1, "status": 1 });

// v1.0 External Sources indexes
db.external_sources.createIndex({ "workspace_id": 1, "source_id": 1 }, { unique: true });
db.external_sources.createIndex({ "enabled": 1 });
db.imported_verifications.createIndex({ "source_id": 1, "external_id": 1 }, { unique: true });
db.imported_verifications.createIndex({ "workspace_id": 1, "imported_at": -1 });

// v1.0 Export logs indexes
db.export_logs.createIndex({ "workspace_id": 1, "exported_at": -1 });
db.export_logs.createIndex({ "export_type": 1 });

print("Indexes created successfully");
EOF
```

#### 3. Enable TTL for Data Retention

```bash
# Create TTL index for signal expiration
docker exec -it integritykit-mongodb mongosh \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin \
  integritykit \
  --eval 'db.signals.createIndex({ "expires_at": 1 }, { expireAfterSeconds: 0 })'
```

### ChromaDB Setup

```bash
# Start ChromaDB container
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d chromadb

# Wait for ChromaDB to be ready
sleep 5

# Verify ChromaDB is running
docker exec -it integritykit-chromadb curl http://localhost:8000/api/v1/heartbeat
```

### Migration from Previous Version (If Applicable)

If upgrading from a previous version, run migration scripts:

```bash
# Backup current database first
docker exec integritykit-mongodb mongodump \
  --out /data/backup/pre-v1.0-$(date +%Y%m%d-%H%M%S) \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin

# Run v1.0 migration script (if provided)
# python scripts/migrate_to_v1.0.py
```

---

## Deployment Procedure

### Blue-Green Deployment (Recommended)

This approach allows zero-downtime deployments with instant rollback capability.

#### Step 1: Prepare Green Environment

```bash
# Clone current environment to green
cd /home/integritykit
git fetch origin
git checkout tags/v1.0.0 -b release-v1.0.0

# Build new images
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build
```

#### Step 2: Start Green Environment

```bash
# Start new containers with green suffix
docker-compose -f docker-compose.yml -f docker-compose.prod.yml \
  -p integritykit-green up -d app

# Wait for application to be ready
sleep 10
```

#### Step 3: Health Check Green Environment

```bash
# Run health checks
curl -f http://localhost:8000/health

# Expected response:
# {"status":"healthy","checks":{"database":"healthy"}}

# Run integration test suite
# pytest tests/integration/ --env=green
```

#### Step 4: Switch Traffic

```bash
# Update Nginx upstream to point to green
# Edit /etc/nginx/conf.d/integritykit.conf
upstream integritykit_backend {
    # Old blue server
    # server 127.0.0.1:8000;

    # New green server
    server 127.0.0.1:8001;  # Green is on different port
}

# Test Nginx configuration
sudo nginx -t

# Reload Nginx (zero downtime)
sudo nginx -s reload
```

#### Step 5: Monitor Green Environment

```bash
# Monitor logs for 10 minutes
docker logs -f integritykit-green-app

# Monitor metrics
# Check Prometheus/Grafana dashboards
# Watch for error rates, latency spikes
```

#### Step 6: Decommission Blue Environment

```bash
# If green is stable, stop blue
docker-compose -p integritykit-blue down app

# Clean up old images
docker image prune -f
```

### Simple Deployment (Maintenance Window)

If a maintenance window is acceptable:

```bash
# 1. Stop current application
docker-compose down app

# 2. Pull latest code
git fetch origin
git checkout tags/v1.0.0

# 3. Build new image
docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

# 4. Start application
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# 5. Verify health
curl -f http://localhost:8000/health
```

---

## Health Checks & Verification

### Application Health Checks

#### 1. Basic Health Endpoint

```bash
curl -f http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "checks": {
    "database": "healthy"
  }
}
```

#### 2. Liveness Check

```bash
curl -f http://localhost:8000/health/live

# Expected: {"status":"alive"}
```

#### 3. Readiness Check

```bash
curl -f http://localhost:8000/health/ready

# Expected: {"status":"ready"}
```

### Database Verification

```bash
# Verify MongoDB connectivity
docker exec -it integritykit-mongodb mongosh \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin \
  integritykit \
  --eval "db.users.countDocuments({})"

# Should return user count without errors
```

### Integration Health Checks

#### Webhook System

```bash
# Check integration health dashboard
curl -H "X-Test-User-Id: admin" \
     -H "X-Test-Team-Id: T123456" \
     http://localhost:8000/api/v1/integrations/health

# Expected: Overall health status and per-integration metrics
```

#### External Sources

```bash
# List external sources
curl -H "X-Test-User-Id: admin" \
     -H "X-Test-Team-Id: T123456" \
     http://localhost:8000/api/v1/integrations/sources

# Should return configured sources
```

### Feature Verification

#### Multi-Language Support

```bash
# Test language detection
curl -X POST http://localhost:8000/api/v1/language/detect \
  -H "Content-Type: application/json" \
  -d '{"text": "Hola mundo"}'

# Expected: {"language": "es", "confidence": 0.99}
```

#### Analytics Endpoints

```bash
# Test analytics endpoint
curl "http://localhost:8000/api/v1/analytics/time-series?workspace_id=T123456&start_date=2026-03-01&end_date=2026-03-13" \
  -H "X-Test-User-Id: admin" \
  -H "X-Test-Team-Id: T123456"

# Should return time-series data
```

#### Export Endpoints

```bash
# Test CAP export (requires published COP update)
# curl http://localhost:8000/api/v1/exports/cap/{update_id}
```

### Performance Verification

```bash
# Check response times
time curl -s -o /dev/null http://localhost:8000/health

# Should be < 200ms

# Run load test (optional)
# ab -n 1000 -c 10 http://localhost:8000/health
```

### Log Verification

```bash
# Check application logs for errors
docker logs integritykit-app --tail=100 | grep -i error

# Should show no critical errors

# Check for startup completion
docker logs integritykit-app | grep "Uvicorn running"
```

---

## Rollback Procedure

### Quick Rollback (Blue-Green)

If using blue-green deployment and issues are detected:

```bash
# 1. Switch Nginx back to blue
# Edit /etc/nginx/conf.d/integritykit.conf
upstream integritykit_backend {
    server 127.0.0.1:8000;  # Back to blue
}

# 2. Reload Nginx
sudo nginx -s reload

# 3. Verify traffic switched back
curl http://yourdomain.com/health

# 4. Stop green environment
docker-compose -p integritykit-green down
```

**Rollback Time:** < 30 seconds

### Database Rollback

If database migration needs rollback:

```bash
# 1. Stop application
docker-compose down app

# 2. Restore database from backup
docker exec -it integritykit-mongodb mongorestore \
  --drop \
  -u integritykit_user \
  -p STRONG_PASSWORD_HERE \
  --authenticationDatabase admin \
  /data/backup/pre-v1.0-TIMESTAMP

# 3. Restart application with previous version
git checkout tags/v0.9.0
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

**Rollback Time:** 5-10 minutes

### Rollback Decision Criteria

Rollback immediately if:
- [ ] Health check fails after 5 minutes
- [ ] Error rate > 5% for 2 minutes
- [ ] Database connectivity issues
- [ ] Critical feature non-functional
- [ ] Security vulnerability discovered

Monitor for 30 minutes before:
- [ ] Performance degradation < 20%
- [ ] Non-critical feature issues
- [ ] Intermittent errors < 1%

---

## Monitoring & Alerting

### Application Metrics

**Key Metrics to Monitor:**

| Metric | Threshold | Alert Level |
|--------|-----------|-------------|
| Request Latency (p95) | > 500ms | Warning |
| Request Latency (p95) | > 1000ms | Critical |
| Error Rate | > 1% | Warning |
| Error Rate | > 5% | Critical |
| Database Query Time (p95) | > 200ms | Warning |
| Memory Usage | > 80% | Warning |
| CPU Usage | > 80% | Warning |
| Disk Usage | > 85% | Critical |

### Integration Health Monitoring

**Webhook Metrics:**
- Delivery success rate (target: > 95%)
- Average delivery latency (target: < 2s)
- Failed deliveries requiring manual intervention

**External Source Metrics:**
- Import success rate (target: > 95%)
- Overdue syncs (alert if > 2 hours overdue)
- API rate limit hits

### Log Monitoring

**Critical Log Patterns to Alert On:**

```bash
# ERROR level logs
"level": "error"

# Authentication failures
"authentication failed"
"invalid token"

# Database connection issues
"connection refused"
"timeout"

# Abuse detection triggers
"abuse pattern detected"

# High-stakes override attempts
"two-person rule violation"
```

### Health Check Monitoring

```bash
# Set up external monitoring (Pingdom, StatusCake, etc.)
# Monitor: https://yourdomain.com/health
# Frequency: Every 60 seconds
# Alert if: Down for 2 consecutive checks
```

### Prometheus Metrics

If using Prometheus, expose metrics:

```python
# Application should expose /metrics endpoint
# Example metrics:
# - http_requests_total
# - http_request_duration_seconds
# - database_queries_total
# - webhook_deliveries_total
# - integration_health_status
```

---

## Post-Deployment Tasks

### Immediate (Within 1 Hour)

- [ ] Verify all health checks passing
- [ ] Review error logs for unexpected issues
- [ ] Test critical user flows (signal ingestion, COP publication)
- [ ] Verify integrations (webhooks, external sources) working
- [ ] Confirm monitoring alerts firing correctly
- [ ] Update status page (if applicable)

### Short-term (Within 24 Hours)

- [ ] Review analytics dashboards for anomalies
- [ ] Check webhook delivery success rates
- [ ] Verify external source imports functioning
- [ ] Monitor database performance
- [ ] Review security logs for suspicious activity
- [ ] Conduct smoke tests for multi-language features
- [ ] Test export endpoints (CAP, EDXL, GeoJSON)

### Medium-term (Within 1 Week)

- [ ] Generate after-action report using new v1.0 feature
- [ ] Collect user feedback on new features
- [ ] Review performance metrics and optimize if needed
- [ ] Document any deployment issues encountered
- [ ] Update runbook with lessons learned
- [ ] Schedule post-deployment review meeting

### Ongoing

- [ ] Weekly review of integration health dashboards
- [ ] Monthly security audit
- [ ] Quarterly dependency updates
- [ ] Regular backup verification

---

## Troubleshooting

### Application Won't Start

**Symptom:** Container starts and immediately exits

**Diagnosis:**
```bash
# Check container logs
docker logs integritykit-app

# Check for common issues
docker logs integritykit-app 2>&1 | grep -E "error|fail|exception"
```

**Common Causes:**

1. **Missing environment variables**
   ```bash
   # Verify .env file exists and is readable
   ls -la .env.production
   cat .env.production | grep SLACK_BOT_TOKEN
   ```

2. **Database connection failure**
   ```bash
   # Test MongoDB connectivity
   docker exec -it integritykit-mongodb mongosh \
     -u integritykit_user -p PASSWORD --eval "db.runCommand({ping:1})"
   ```

3. **Port conflict**
   ```bash
   # Check if port 8000 is in use
   sudo netstat -tulpn | grep 8000
   ```

### Health Check Failing

**Symptom:** `/health` endpoint returns 503 or times out

**Diagnosis:**
```bash
# Check if app is responsive
curl -v http://localhost:8000/health

# Check database connectivity
docker exec integritykit-mongodb mongosh \
  -u integritykit_user -p PASSWORD \
  --authenticationDatabase admin \
  integritykit --eval "db.runCommand({ping:1})"
```

**Solutions:**

1. **Database unhealthy**
   - Restart MongoDB: `docker restart integritykit-mongodb`
   - Wait 30 seconds and retry

2. **App startup not complete**
   - Wait longer (app needs time to initialize)
   - Check logs: `docker logs integritykit-app`

### Webhook Deliveries Failing

**Symptom:** Webhooks showing high failure rates

**Diagnosis:**
```bash
# Check integration health
curl http://localhost:8000/api/v1/integrations/health \
  -H "X-Test-User-Id: admin" -H "X-Test-Team-Id: T123456"

# Review failed deliveries
docker logs integritykit-app | grep "webhook delivery failed"
```

**Solutions:**

1. **Target endpoint down**
   - Test webhook URL manually: `curl https://target-endpoint.com`
   - Contact target system administrator

2. **Authentication failure**
   - Verify webhook auth credentials in database
   - Test with webhook test endpoint

3. **SSRF protection blocking legitimate URL**
   - Review URL validation logic
   - Add URL to allowlist if appropriate

### High Memory Usage

**Symptom:** Container using > 80% of available memory

**Diagnosis:**
```bash
# Check container memory usage
docker stats integritykit-app

# Check for memory leaks in logs
docker logs integritykit-app | grep -i "memory"
```

**Solutions:**

1. **Increase memory limit**
   ```yaml
   # In docker-compose.prod.yml
   deploy:
     resources:
       limits:
         memory: 6G  # Increase from 4G
   ```

2. **Optimize query performance**
   - Review slow queries in MongoDB
   - Add missing indexes

3. **Restart container (temporary fix)**
   ```bash
   docker restart integritykit-app
   ```

### Database Performance Issues

**Symptom:** Slow API response times, database queries timing out

**Diagnosis:**
```bash
# Check MongoDB slow queries
docker exec -it integritykit-mongodb mongosh \
  -u integritykit_user -p PASSWORD \
  --authenticationDatabase admin \
  integritykit <<EOF
db.setProfilingLevel(1, { slowms: 100 })
db.system.profile.find().sort({ts: -1}).limit(10).pretty()
EOF
```

**Solutions:**

1. **Add missing indexes**
   - Identify slow queries from profiler
   - Add indexes for frequently queried fields

2. **Increase MongoDB resources**
   ```yaml
   # In docker-compose.prod.yml
   mongodb:
     deploy:
       resources:
         limits:
           memory: 3G  # Increase from 2G
   ```

3. **Optimize queries**
   - Use projection to limit returned fields
   - Add pagination to large result sets

### External Source Import Failures

**Symptom:** External source imports failing or returning errors

**Diagnosis:**
```bash
# Check external source configuration
curl http://localhost:8000/api/v1/integrations/sources \
  -H "X-Test-User-Id: admin" -H "X-Test-Team-Id: T123456"

# Check logs for import errors
docker logs integritykit-app | grep "external source import"
```

**Solutions:**

1. **Authentication failure**
   - Verify external API credentials
   - Test API endpoint manually with credentials

2. **Rate limiting**
   - Check if external API is rate limiting requests
   - Adjust sync interval in source configuration

3. **Data format issues**
   - Review import error details
   - Verify external API response format matches expected schema

---

## Emergency Contacts

| Role | Name | Contact | Escalation |
|------|------|---------|------------|
| On-Call Engineer | TBD | phone/slack | Primary |
| Infrastructure Lead | TBD | phone/slack | Secondary |
| Application Lead | TBD | phone/slack | Secondary |
| Security Team | TBD | email/slack | For security issues |
| Database Admin | TBD | phone/slack | For DB issues |

---

## Appendix

### A. Nginx Configuration

```nginx
# /etc/nginx/conf.d/integritykit.conf

upstream integritykit_backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_general:10m rate=60r/m;
limit_req_zone $binary_remote_addr zone=api_auth:10m rate=5r/m;
limit_req_zone $binary_remote_addr zone=api_webhooks:10m rate=10r/h;

# HTTP -> HTTPS redirect
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Health check endpoint (no rate limiting)
    location /health {
        proxy_pass http://integritykit_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # API endpoints with rate limiting
    location /api/ {
        limit_req zone=api_general burst=20 nodelay;

        proxy_pass http://integritykit_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Webhook management (stricter rate limiting)
    location /api/v1/integrations/webhooks {
        limit_req zone=api_webhooks burst=5 nodelay;

        proxy_pass http://integritykit_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Export endpoints (large responses)
    location /api/v1/exports/ {
        proxy_pass http://integritykit_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Longer timeout for exports
        proxy_read_timeout 120s;

        # Disable buffering for streaming responses
        proxy_buffering off;
    }

    # Static files (if any)
    location /static/ {
        alias /home/integritykit/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Deny access to sensitive files
    location ~ /\. {
        deny all;
    }
}
```

### B. Systemd Service (Alternative to Docker)

If deploying without Docker:

```ini
# /etc/systemd/system/integritykit.service
[Unit]
Description=Aid Arena Integrity Kit v1.0
After=network.target mongodb.service

[Service]
Type=simple
User=integritykit
Group=integritykit
WorkingDirectory=/home/integritykit/app
EnvironmentFile=/home/integritykit/.env.production

ExecStart=/home/integritykit/venv/bin/uvicorn \
    integritykit.api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --proxy-headers \
    --forwarded-allow-ips='*'

Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/home/integritykit/logs

[Install]
WantedBy=multi-user.target
```

### C. Backup Script

```bash
#!/bin/bash
# /home/integritykit/scripts/backup.sh

set -e

BACKUP_DIR="/home/integritykit/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=30

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup MongoDB
echo "Backing up MongoDB..."
docker exec integritykit-mongodb mongodump \
  --out "/data/backup/mongodb-$TIMESTAMP" \
  -u integritykit_user \
  -p "$MONGO_PASSWORD" \
  --authenticationDatabase admin

# Copy backup out of container
docker cp integritykit-mongodb:/data/backup/mongodb-$TIMESTAMP "$BACKUP_DIR/"

# Backup ChromaDB data
echo "Backing up ChromaDB..."
docker cp integritykit-chromadb:/chroma/chroma "$BACKUP_DIR/chromadb-$TIMESTAMP"

# Backup .env file
cp /home/integritykit/.env.production "$BACKUP_DIR/env-$TIMESTAMP"

# Compress backups
tar -czf "$BACKUP_DIR/integritykit-backup-$TIMESTAMP.tar.gz" \
  "$BACKUP_DIR/mongodb-$TIMESTAMP" \
  "$BACKUP_DIR/chromadb-$TIMESTAMP" \
  "$BACKUP_DIR/env-$TIMESTAMP"

# Clean up temporary files
rm -rf "$BACKUP_DIR/mongodb-$TIMESTAMP" "$BACKUP_DIR/chromadb-$TIMESTAMP" "$BACKUP_DIR/env-$TIMESTAMP"

# Remove old backups
find "$BACKUP_DIR" -name "integritykit-backup-*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "Backup completed: $BACKUP_DIR/integritykit-backup-$TIMESTAMP.tar.gz"
```

### D. Monitoring Queries

```bash
# Application metrics
curl http://localhost:8000/metrics

# Integration health
curl http://localhost:8000/api/v1/integrations/health \
  -H "Authorization: Bearer $TOKEN"

# Database status
docker exec integritykit-mongodb mongosh \
  -u integritykit_user -p $MONGO_PASSWORD \
  --authenticationDatabase admin \
  integritykit \
  --eval "db.serverStatus()"
```

---

**End of Deployment Runbook**

For questions or issues, contact the infrastructure team or refer to the [Security Review](./security-review-v1.0.md) document for security-specific concerns.
