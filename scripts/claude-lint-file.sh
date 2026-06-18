#!/usr/bin/env bash
# PostToolUse lint hook — lints ONLY the file that was just edited.
#
# Reads the Claude Code hook JSON from stdin, extracts the changed file path,
# and runs the right linter for it:
#   - frontend  *.ts/*.tsx/*.js/*.jsx/*.cjs/*.mjs  -> eslint (--max-warnings=0)
#   - backend   *.py                               -> ruff check
#
# On lint failure it prints the findings to stderr and exits 2, so Claude Code
# surfaces the issues back to the model. Clean or unsupported files exit 0
# (silent). Kept single-file and fast — full-project checks run at git push.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

input="$(cat)"
file="$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_response.filePath // empty' 2>/dev/null)"

[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

out=""
status=0

case "$file" in
  "$ROOT"/frontend/*)
    case "$file" in
      *.ts | *.tsx | *.js | *.jsx | *.cjs | *.mjs) ;;
      *) exit 0 ;;
    esac
    eslint="$ROOT/frontend/node_modules/.bin/eslint"
    # Skip silently if deps/tooling aren't present — don't fail edits.
    { [ -x "$eslint" ] && command -v node >/dev/null 2>&1; } || exit 0
    out="$(cd "$ROOT/frontend" && "$eslint" "$file" --max-warnings=0 2>&1)"
    status=$?
    ;;
  "$ROOT"/backend/*)
    case "$file" in
      *.py) ;;
      *) exit 0 ;;
    esac
    # Prefer ruff on PATH, fall back to the project's uv toolchain, else skip.
    if command -v ruff >/dev/null 2>&1; then
      ruff=(ruff)
    elif command -v uv >/dev/null 2>&1; then
      ruff=(uv run ruff)
    else
      exit 0
    fi
    out="$(cd "$ROOT/backend" && "${ruff[@]}" check "$file" 2>&1)"
    status=$?
    ;;
  *)
    exit 0
    ;;
esac

if [ "$status" -ne 0 ]; then
  echo "Lint issues in ${file#"$ROOT"/}:" >&2
  echo "$out" >&2
  exit 2
fi

exit 0
