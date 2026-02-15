"""FastAPI application with lifespan management and health endpoints."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from integritykit.config import settings
from integritykit.services.database import close_mongodb_connection, connect_to_mongodb
from integritykit.api.routes import audit, backlog, candidates, drafts, search, users

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
        }
    )
