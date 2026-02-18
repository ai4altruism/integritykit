"""FastAPI application with lifespan management and health endpoints."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
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
