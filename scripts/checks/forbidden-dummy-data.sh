#!/usr/bin/env bash
# Forbidden dummy-data check (ADVISORY by default).
#
# Enforces memory/known-risks.md #9: no placeholder/mock/dummy data in product flows,
# and no `NaN%` rendering. Scans only runtime/product code paths (tests, seeds, mocks,
# and the dev-only mock MCP session are exempt).
#
# Exit codes: 0 = clean or advisory warnings only. With STRICT_DUMMY_DATA=1, findings
# cause a non-zero exit (use in CI / pre-commit to hard-block).
#
# Usage:  scripts/checks/forbidden-dummy-data.sh
#         STRICT_DUMMY_DATA=1 scripts/checks/forbidden-dummy-data.sh

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"

# Case-insensitive markers that signal placeholder/dummy content in product code.
PATTERN='dummy|placeholder data|lorem ipsum|fakedata|faker\.|mock(response|data|ticket|user)|hardcoded (for now|demo)|TODO: replace with real|NaN%|sampleTickets|fake_tickets|test@example\.com'

findings=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  is_product_path "$f" || continue
  # -n line numbers, -I skip binary, -E extended, -i case-insensitive
  matches="$(grep -nEiI "$PATTERN" "$f" 2>/dev/null)"
  if [ -n "$matches" ]; then
    if [ "$findings" -eq 0 ]; then
      echo "⚠  Possible dummy/placeholder data in product code paths:"
    fi
    root="$(repo_root)"
    echo "  ${f#"$root"/}:"
    printf '%s\n' "$matches" | sed 's/^/    /'
    findings=$((findings+1))
  fi
done < <(changed_files)

if [ "$findings" -eq 0 ]; then
  echo "✓ dummy-data check: no product-path placeholder data found."
  exit 0
fi

echo ""
echo "→ Product flows must use real data. If this is a legitimate constant/label,"
echo "  rename it or add a scoped exception, and prefer rendering \"No data\" over NaN%."
if [ "${STRICT_DUMMY_DATA:-0}" = "1" ]; then
  exit 1
fi
exit 0
