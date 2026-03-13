# Performance Tests for Aid Arena Integrity Kit v1.0

This directory contains performance tests for critical services in the Integrity Kit v1.0 release.

## Overview

Performance tests validate that services meet response time and resource usage targets under various load conditions. These tests use mocked data sources for isolation and reproducibility.

## Performance Targets

| Service | Target | Notes |
|---------|--------|-------|
| API Response (p95) | <200ms | Analytics endpoints |
| Export Generation | <500ms | CAP, EDXL, GeoJSON |
| Language Detection | <100ms | After warmup |
| Draft Generation | <300ms | 10 candidates |
| Webhook Delivery | <100ms | Single attempt |
| Max Export Memory | <50MB | Large datasets (500 items) |

## Running Tests

### Run all performance tests:
```bash
python -m pytest tests/performance/ -v
```

### Run specific test categories:
```bash
# Analytics performance
python -m pytest tests/performance/ -v -k "Analytics"

# Export services performance
python -m pytest tests/performance/ -v -k "Export"

# Language detection performance
python -m pytest tests/performance/ -v -k "LanguageDetection"

# Draft generation performance
python -m pytest tests/performance/ -v -k "DraftGeneration"

# Webhook performance
python -m pytest tests/performance/ -v -k "Webhook"
```

### Run tests with timing output:
```bash
python -m pytest tests/performance/ -v -s
```

## Test Coverage

### Analytics Service (`TestAnalyticsPerformance`)

Tests MongoDB aggregation pipeline performance:
- **Signal volume time-series**: 100+ time buckets (~4 days hourly)
- **Facilitator actions**: 1000 audit log entries
- **Topic trends**: 50 clusters with trend detection
- **Conflict resolution metrics**: 200 conflicts across risk tiers

### Export Services (`TestExportPerformance`)

Tests export generation with varying dataset sizes:
- **CAP 1.2 XML**: 10, 50, 100, 200 items
- **EDXL-DE 2.0 XML**: 10, 50, 100 items
- **GeoJSON**: 10, 50, 100, 200 items
- **Memory usage**: Large datasets (500 items) - optional with psutil

### Webhook Delivery (`TestWebhookPerformance`)

Tests webhook delivery throughput:
- **Payload construction**: JSON serialization
- **Single delivery**: HTTP request with mocked client
- **Concurrent deliveries**: 10 webhooks simultaneously

### Language Detection (`TestLanguageDetectionPerformance`)

Tests language detection latency:
- **Single detection**: After warmup
- **Batch detection**: 100 signals
- **Varying text length**: 50, 200, 500, 1000 characters

### Draft Generation (`TestDraftGenerationPerformance`)

Tests COP draft generation:
- **Line item generation**: Single candidate
- **Full draft**: 10, 25, 50, 100 candidates
- **Markdown conversion**: 100 items

## Test Methodology

### Isolation
- Uses mocked MongoDB collections
- Uses mocked HTTP clients for webhooks
- No external dependencies or real infrastructure

### Timing
- Uses `time.perf_counter()` for precise measurements
- Includes warmup for services with initialization overhead
- Reports elapsed time in milliseconds

### Assertions
- Validates output correctness
- Enforces performance targets with assertions
- Prints timing information with `print()` for visibility

## Interpreting Results

### Passing Tests
Tests pass when:
- Output is correct (structure, content)
- Elapsed time is below target threshold
- Memory usage is within bounds (when tested)

### Failing Tests
Tests fail when:
- Performance target is exceeded
- Output validation fails
- Service errors occur

### Performance Degradation
If tests start failing:
1. Check if target is realistic for environment
2. Profile the service to identify bottlenecks
3. Review recent code changes
4. Consider caching or optimization

## Integration with CI/CD

### GitHub Actions
Performance tests can be integrated into CI/CD:
```yaml
- name: Run Performance Tests
  run: |
    python -m pytest tests/performance/ -v --tb=short
```

### Performance Monitoring
Track performance over time:
- Run tests on each commit
- Store timing metrics
- Alert on regression (>20% slowdown)
- Review trends in dashboard

## Limitations

### Not Load Tests
These are **service-level performance tests**, not load tests:
- Test single-threaded execution
- Use mocked data sources
- Measure algorithmic complexity, not infrastructure capacity

### For Load Testing, Use:
- **Locust** or **k6** for API load testing
- **MongoDB profiling** for database performance
- **APM tools** (e.g., New Relic, Datadog) for production monitoring

## Memory Profiling (Optional)

The memory usage test requires `psutil`:
```bash
pip install psutil
```

To run memory tests:
```bash
python -m pytest tests/performance/ -v -k "memory" --run-optional
```

## Continuous Improvement

### Baseline Metrics
Run tests periodically to establish baselines:
```bash
python -m pytest tests/performance/ -v -s > performance_baseline_$(date +%Y%m%d).txt
```

### Optimization Targets
Focus optimization efforts on:
1. **Analytics queries**: Slow aggregation pipelines
2. **Export generation**: Large XML serialization
3. **Language detection**: Batch processing patterns
4. **Draft generation**: LLM call optimization (if enabled)

### Best Practices
- Profile before optimizing
- Measure impact of changes
- Document performance decisions
- Monitor production metrics

## Contributing

When adding new services:
1. Create performance test in `test_performance.py`
2. Define realistic target thresholds
3. Test with varying dataset sizes
4. Include in CI/CD pipeline
5. Document in this README

## Contact

For questions about performance testing:
- Review Sprint 8 documentation (`docs/Aid_Arena_Integrity_Kit_SDP_Sprint8_v1_0.md`)
- Check performance engineering docs
- File issue with `performance` label
