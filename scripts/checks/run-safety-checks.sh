#!/usr/bin/env bash
# Run all repository safety-gate checks over the current change set.
#
#   secret-scan            (BLOCKING)   — high-confidence secrets in the diff
#   forbidden-dummy-data   (advisory)   — placeholder data in product code paths
#   docs-reminder          (advisory)   — code changed without docs/memory updates
#
# Advisory checks print warnings but don't fail. Set STRICT=1 to make dummy-data
# blocking too. secret-scan always blocks (unless SKIP_SECRET_SCAN=1).
#
# Usage:  scripts/checks/run-safety-checks.sh   [STRICT=1]

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

rc=0
echo "── secret-scan ─────────────────────────────"
bash "$DIR/secret-scan.sh" || rc=1

echo ""
echo "── forbidden-dummy-data ────────────────────"
if [ "${STRICT:-0}" = "1" ]; then
  STRICT_DUMMY_DATA=1 bash "$DIR/forbidden-dummy-data.sh" || rc=1
else
  bash "$DIR/forbidden-dummy-data.sh" || true
fi

echo ""
echo "── docs-reminder ───────────────────────────"
bash "$DIR/docs-reminder.sh" || true

echo ""
if [ "$rc" -eq 0 ]; then
  echo "✓ safety checks passed."
else
  echo "✖ safety checks found blocking issues (see above)."
fi
exit "$rc"
