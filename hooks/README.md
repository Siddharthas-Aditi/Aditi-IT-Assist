# Hooks

Git hooks for maintaining code quality.

## Pre-commit
- `format.sh` — Auto-format Python (ruff) and TypeScript (prettier)
- `lint.sh` — Run linters and block commit on errors
- `test.sh` — Run fast unit tests

## Post-merge
- `install-deps.sh` — Auto-install deps after pulling changes

## Setup
Hooks are installed automatically by `make bootstrap`.
Manual setup: `cp hooks/pre-commit/* .git/hooks/`
