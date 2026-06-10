#!/usr/bin/env bash
# ==================================================
# Wait for infrastructure services to be ready
# ==================================================
# Usage: ./scripts/wait_for_db.sh [--timeout 60]
set -euo pipefail

TIMEOUT="${1:-60}"
PG_HOST="${POSTGRES_HOST:-localhost}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-aditi}"
REDIS_HOST_VAR="${REDIS_HOST:-localhost}"
REDIS_PORT_VAR="${REDIS_PORT:-6379}"

echo "⏳ Waiting for services (timeout: ${TIMEOUT}s)..."

# ── Wait for PostgreSQL ─────────────────────────
echo -n "  PostgreSQL ($PG_HOST:$PG_PORT): "
elapsed=0
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" > /dev/null 2>&1; do
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$TIMEOUT" ]; then
        echo "TIMEOUT ❌"
        exit 1
    fi
    sleep 2
done
echo "ready ✓"

# ── Wait for Redis ──────────────────────────────
echo -n "  Redis ($REDIS_HOST_VAR:$REDIS_PORT_VAR): "
elapsed=0
until redis-cli -h "$REDIS_HOST_VAR" -p "$REDIS_PORT_VAR" ping > /dev/null 2>&1 || \
      nc -z "$REDIS_HOST_VAR" "$REDIS_PORT_VAR" 2>/dev/null; do
    elapsed=$((elapsed + 2))
    if [ "$elapsed" -ge "$TIMEOUT" ]; then
        echo "TIMEOUT ❌"
        exit 1
    fi
    sleep 2
done
echo "ready ✓"

echo ""
echo "✅ All services ready!"
