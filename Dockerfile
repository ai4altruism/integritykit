# Build stage
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency files
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install production dependencies only
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Runtime stage
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime dependencies (netcat for health checks if needed)
RUN apt-get update && \
    apt-get install -y --no-install-recommends netcat-openbsd curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appgroup && \
    useradd -r -g appgroup appuser && \
    chown -R appuser:appgroup /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source code
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup pyproject.toml ./

# Switch to non-root user
USER appuser

# Expose application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Security: Set read-only file system (uncomment if application doesn't need write access)
# Note: Uncomment this in production after verifying no write operations needed
# ENV PYTHONUNBUFFERED=1
# Note: /tmp is writable for application temporary files

# Run application with uvicorn
# Production settings: --workers based on CPU cores, --limit-concurrency for load management
CMD ["uvicorn", "integritykit.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
