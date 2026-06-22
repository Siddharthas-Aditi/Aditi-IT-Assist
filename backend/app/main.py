"""Aditi IT Assist — FastAPI Application Entry Point."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events.

    Owns: logging setup, dev-mode schema bootstrap, the in-process
    background-job scheduler (idle sweeper for live specialist chat).
    """
    setup_logging()

    # Import all models so their metadata is registered with Base
    import app.models  # noqa: F401

    if settings.APP_ENV == "development":
        # Auto-create all tables on startup in development mode.
        # This avoids the need for running alembic manually during local dev.
        from app.core.database import engine
        from app.models.base import Base

        async with engine.begin() as conn:
            # Enable pgvector extension (safe to run multiple times); if it's
            # not available, skip — vector search falls back to keyword.
            with suppress(Exception):
                await conn.execute(
                    __import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector")
                )
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database_schema_ready", env=settings.APP_ENV)

    # Background jobs — the idle sweeper auto-ends abandoned specialist
    # chat sessions every N seconds. Runs in the same event loop as the
    # API; the context manager cancels + awaits each task on shutdown.
    from app.services.scheduler import start_background_jobs

    async with start_background_jobs(
        idle_sweeper_enabled=settings.IDLE_SWEEPER_ENABLED,
        idle_sweeper_interval_seconds=settings.IDLE_SWEEPER_INTERVAL_SECONDS,
        background_agents_enabled=settings.FEATURE_BACKGROUND_AGENTS,
        background_agents_poll_seconds=settings.AGENT_BACKGROUND_POLL_SECONDS,
    ):
        yield

    # Shutdown
    if settings.APP_ENV == "development":
        from app.core.database import engine
        await engine.dispose()



app = FastAPI(
    title=settings.APP_NAME,
    description="Agentic AI-powered IT support platform for Aditi Consulting",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)
