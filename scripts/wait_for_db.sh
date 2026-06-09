#!/usr/bin/env bash
# Wait for PostgreSQL to be ready
set -euo pipefail

HOST="${POSTGRES_HOST:-localhost}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-aditi}"

echo "Waiting for PostgreSQL at $HOST:$PORT..."

for i in $(seq 1 30); do
    if pg_isready -h "$HOST" -p "$PORT" -U "$USER" > /dev/null 2>&1; then
        echo "PostgreSQL is ready!"
        exit 0
    fi
    echo "  Attempt $i/30 - waiting..."
    sleep 2
done

echo "ERROR: PostgreSQL did not become ready in time"
exit 1
