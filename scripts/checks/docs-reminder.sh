#!/usr/bin/env bash
# Docs & memory update reminder (ADVISORY — never blocks).
#
# If a change touches code but no docs/, memory/, or agents/ file, print a reminder to
# update documentation in the same PR (repo policy: every feature needs a doc update).
#
# Usage:  scripts/checks/docs-reminder.sh

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"
root="$(repo_root)"

code_changed=0
docs_changed=0
schema_changed=0
flag_changed=0

while IFS= read -r f; do
  [ -n "$f" ] || continue
  rel="${f#"$root"/}"
  case "$rel" in
    backend/app/*|frontend/src/*) code_changed=1 ;;
  esac
  case "$rel" in
    docs/*|memory/*|agents/*|skills/*|CLAUDE.md|AGENTS.md) docs_changed=1 ;;
  esac
  case "$rel" in
    backend/app/models/*|backend/alembic/*) schema_changed=1 ;;
  esac
  case "$rel" in
    .env.example|backend/app/core/config.py) flag_changed=1 ;;
  esac
done < <(changed_files)

if [ "$code_changed" -eq 1 ] && [ "$docs_changed" -eq 0 ]; then
  echo "⚠  docs-reminder: code changed but no docs/, memory/, or agents/ file updated."
  echo "   Update the owning docs/** and the relevant memory/* in this change."
  echo "   See skills/playbooks/docs-update.md."
fi
[ "$schema_changed" -eq 1 ] && echo "⚠  Schema/migration touched → update memory/domain-model.md + docs/architecture/data-model.md."
[ "$flag_changed" -eq 1 ] && echo "⚠  Config/flags touched → update memory/current-rollout-state.md + the CLAUDE.md status table."

echo "✓ docs-reminder: done (advisory)."
exit 0
