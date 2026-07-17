# ==================================================
# Aditi IT Assist — Backend Dockerfile
# ==================================================
# Targets:
#   development → hot-reload with uvicorn --reload
#   production  → optimized, non-root, no dev deps
#
# Build args:
#   UV_INSECURE_HOST — space-separated hosts to skip TLS verification
#                      (for corporate proxies that intercept SSL)
#                      Example: "pypi.org files.pythonhosted.org"

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

# Allow corporate proxy TLS bypass (empty = strict TLS)
ARG UV_INSECURE_HOST=""
ENV UV_INSECURE_HOST=${UV_INSECURE_HOST}

# Copy dependency manifest. No glob on uv.lock — the lockfile is required so a
# missing lock fails the build loudly instead of silently resolving fresh
# (non-reproducible) versions.
COPY pyproject.toml uv.lock ./

# ── Development stage ───────────────────────────
FROM base AS development

# Install ALL deps (including dev). --frozen pins to uv.lock exactly (fails if
# the lock is stale) so the image matches what CI validated.
RUN uv sync --frozen

# Copy application code
COPY . .

EXPOSE 8000

# Uvicorn with hot-reload (source mounted as volume)
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app"]

# ── Production stage ────────────────────────────
FROM base AS production

# Install production deps only, pinned to the lock.
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Use the readiness probe (DB + Redis gated), not the always-200 liveness
# endpoint, so orchestrators only route traffic once dependencies are usable.
HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready')"

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
