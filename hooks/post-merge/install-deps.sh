#!/usr/bin/env bash
# Post-merge hook: install dependencies if lock files changed
set -e

CHANGED_FILES=$(git diff-tree -r --name-only --no-commit-id ORIG_HEAD HEAD)

if echo "$CHANGED_FILES" | grep -q "backend/uv.lock\|backend/pyproject.toml"; then
    echo "📦 Backend dependencies changed, syncing..."
    cd backend && uv sync
fi

if echo "$CHANGED_FILES" | grep -q "frontend/package-lock.json\|frontend/package.json"; then
    echo "📦 Frontend dependencies changed, installing..."
    cd frontend && npm ci
fi
