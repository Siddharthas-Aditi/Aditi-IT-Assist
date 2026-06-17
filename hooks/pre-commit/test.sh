#!/usr/bin/env bash
# Pre-commit hook: quick tests
set -e
echo "Running quick tests..."
cd backend && uv run pytest tests/unit/ -q --no-header
echo "✅ Tests passed"
