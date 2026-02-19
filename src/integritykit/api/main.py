"""FastAPI application with lifespan management and health endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from integritykit.api.routes import (
    audit,
    backlog,
    candidates,
    drafts,
    metrics,
    publish,
    search,
    users,
)
from integritykit.config import settings
from integritykit.services.database import close_mongodb_connection, connect_to_mongodb

logger = structlog.get_logger(__name__)

# Simple in-memory rate limiter (for production, use Redis-based limiter)
_rate_limit_store: dict[str, list[float]] = {}


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key from request (user ID or IP)."""
    # Try to get user from request state (set by auth middleware)
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return f"user:{user.id}"
    # Fall back to IP address
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifespan (startup and shutdown).

    Args:
        app: FastAPI application instance

    Yields:
        None
    """
    # Startup: Connect to MongoDB
    logger.info(
        "Starting IntegrityKit",
        app_name=settings.app_name,
        version=settings.app_version,
        database=settings.mongodb_database,
    )

    try:
        await connect_to_mongodb(
            uri=settings.mongodb_uri,
            database_name=settings.mongodb_database,
        )
        logger.info("Connected to MongoDB", database=settings.mongodb_database)
    except Exception as e:
        logger.error("Failed to connect to MongoDB", error=str(e))
        raise

    yield

    # Shutdown: Close MongoDB connection
    logger.info("Shutting down IntegrityKit")
    await close_mongodb_connection()
    logger.info("Closed MongoDB connection")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Aid Arena Integrity Kit - Slack coordination layer for crisis-response COP updates",
    lifespan=lifespan,
)

# Add CORS middleware if configured (S7-8: Security hardening)
if settings.cors_allowed_origins:
    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
            allow_headers=["*"],
        )
        logger.info("CORS enabled", origins=origins)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next: Callable) -> Response:
    """Add security headers to all responses (S7-8: Security hardening)."""
    response = await call_next(request)
    # Prevent clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    # XSS protection (legacy but still useful)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Referrer policy
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Content Security Policy (basic)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' cdn.jsdelivr.net cdn.tailwindcss.com; "
        "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """Rate limiting middleware (S7-8: Security hardening).

    Simple in-memory rate limiter. For production, use Redis-based limiter.
    """
    import time

    # Skip rate limiting for health checks and static files
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)
    if request.url.path.startswith("/static"):
        return await call_next(request)

    if not settings.rate_limit_enabled:
        return await call_next(request)

    key = get_rate_limit_key(request)
    now = time.time()
    window = 60.0  # 1 minute window
    max_requests = settings.rate_limit_requests_per_minute

    # Clean old entries and add current request
    if key not in _rate_limit_store:
        _rate_limit_store[key] = []

    _rate_limit_store[key] = [
        t for t in _rate_limit_store[key] if t > now - window
    ]

    if len(_rate_limit_store[key]) >= max_requests:
        logger.warning(
            "Rate limit exceeded",
            key=key,
            requests=len(_rate_limit_store[key]),
            limit=max_requests,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "detail": f"Maximum {max_requests} requests per minute",
                "retry_after": 60,
            },
            headers={"Retry-After": "60"},
        )

    _rate_limit_store[key].append(now)
    return await call_next(request)


# Register API routers
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(backlog.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(candidates.router, prefix="/api/v1")
app.include_router(drafts.router, prefix="/api/v1")
app.include_router(publish.router, prefix="/api/v1")
app.include_router(metrics.router, prefix="/api/v1")

# Mount static files for dashboard
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health_check() -> JSONResponse:
    """Health check endpoint.

    Returns:
        JSONResponse with health status
    """
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
        }
    )


@app.get("/")
async def root() -> JSONResponse:
    """Root endpoint with API information.

    Returns:
        JSONResponse with API information
    """
    return JSONResponse(
        content={
            "app": settings.app_name,
            "version": settings.app_version,
            "description": "Aid Arena Integrity Kit API",
            "docs_url": "/docs",
            "dashboard_url": "/dashboard",
        }
    )


@app.get("/dashboard")
async def dashboard() -> FileResponse:
    """Serve the metrics dashboard.

    Returns:
        FileResponse with dashboard HTML
    """
    dashboard_path = Path(__file__).parent.parent / "static" / "dashboard.html"
    return FileResponse(dashboard_path, media_type="text/html")
