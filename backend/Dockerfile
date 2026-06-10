# ==================================================
# Aditi IT Assist — Backend Dockerfile
# ==================================================
# Targets:
#   development → hot-reload with uvicorn --reload
#   production  → optimized, non-root, no dev deps

# ── Base stage ──────────────────────────────────
FROM python:3.12-slim AS base

WORKDIR /app

# System deps for psycopg2, healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency manifest
COPY pyproject.toml uv.lock* ./

# ── Development stage ───────────────────────────
FROM base AS development

# Install ALL deps (including dev)
RUN uv sync

# Copy application code
COPY . .

EXPOSE 8000

# Uvicorn with hot-reload (source mounted as volume)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]

# ── Production stage ────────────────────────────
FROM base AS production

# Install production deps only
RUN uv sync --no-dev

# Copy application code
COPY . .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health')"

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
