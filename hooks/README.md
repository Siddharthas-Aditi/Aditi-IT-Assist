# Hooks

Git hooks for maintaining code quality.

> **Active hooks path is `.githooks/`** (enabled by `make install-hooks`, which sets
> `core.hooksPath`). `.githooks/pre-push` is the authoritative local gate (lint +
> typecheck + tests, mirroring CI). Additional repository safety checks live in
> `scripts/checks/` (secret-scan, forbidden-dummy-data, docs-reminder, commit-msg). See
> **`docs/development/safety-gates.md`** for the full picture and how to wire the safety
> checks into `pre-commit`/`commit-msg`. The scripts below are legacy references.

## Pre-commit
- `format.sh` — Auto-format Python (ruff) and TypeScript (prettier)
- `lint.sh` — Run linters and block commit on errors
- `test.sh` — Run fast unit tests

## Post-merge
- `install-deps.sh` — Auto-install deps after pulling changes

## Setup
Hooks are installed automatically by `make bootstrap`.
Manual setup: `cp hooks/pre-commit/* .git/hooks/`
