"""Aditi IT Assist — FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown events."""
    setup_logging()
    # TODO(team): Initialize database connection pool on startup
    # TODO(team): Initialize Redis connection on startup
    yield
    # Shutdown: close connections
    # TODO(team): Close database pool
    # TODO(team): Close Redis connection


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
