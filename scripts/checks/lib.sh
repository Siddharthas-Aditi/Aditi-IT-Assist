#!/usr/bin/env bash
# Shared helpers for scripts/checks/*.sh
#
# Provides:
#   repo_root                     -> prints repo top-level
#   changed_files [--staged]      -> prints changed files (staged by default when in a
#                                     git repo with a staged set; else working-tree changes)
#   is_product_path <path>        -> 0 if path is a runtime/product code path
#
# All check scripts source this file. Kept dependency-light (git + coreutils + grep).

set -uo pipefail

repo_root() {
  git rev-parse --show-toplevel 2>/dev/null || pwd
}

# List candidate files to check. Prefers staged files (pre-commit context); if none are
# staged, falls back to files changed vs. HEAD (working tree). De-dupes, keeps existing files.
changed_files() {
  local root; root="$(repo_root)"
  local files
  files="$(git -C "$root" diff --cached --name-only --diff-filter=ACM 2>/dev/null)"
  if [ -z "$files" ]; then
    files="$(git -C "$root" diff --name-only --diff-filter=ACM 2>/dev/null)"
  fi
  # Absolute paths, existing files only.
  local f
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    [ -f "$root/$f" ] && printf '%s\n' "$root/$f"
  done <<< "$files" | sort -u
}

# Runtime/product code paths (where dummy data must never appear).
# Excludes tests, mocks, seeds, fixtures, stories, docs, and the dev-only mock MCP session.
is_product_path() {
  local f="$1"
  case "$f" in
    *"/backend/app/"*.py|*"/frontend/src/"*.ts|*"/frontend/src/"*.tsx) ;;
    *) return 1 ;;
  esac
  case "$f" in
    *"/tests/"*|*".test."*|*".spec."*|*"/e2e/"*|*"__mocks__"*|*".stories."*) return 1 ;;
    *"/mock_session.py"|*"/scripts/"*|*"/seed"*|*"/fixtures/"*|*"/mocks/"*) return 1 ;;
  esac
  return 0
}
