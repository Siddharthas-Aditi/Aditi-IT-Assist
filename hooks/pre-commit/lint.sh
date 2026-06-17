#!/usr/bin/env bash
# Pre-commit hook: lint
set -e
echo "Running linters..."
cd backend && uv run ruff check . --fix
cd ../frontend && npx eslint src/ --fix
echo "✅ Lint passed"
