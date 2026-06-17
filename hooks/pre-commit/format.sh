#!/usr/bin/env bash
# Pre-commit hook: format code
set -e
cd backend && uv run ruff format . 2>/dev/null || true
cd ../frontend && npx prettier --write "src/**/*.{ts,tsx}" 2>/dev/null || true
