#!/usr/bin/env bash
# Secret scan (BLOCKING).
#
# Scans the staged diff (or working-tree changes) for high-confidence secret patterns.
# Exit 1 on a likely secret so it never leaves the machine. This is a lightweight guard,
# NOT a replacement for a full secret scanner in CI.
#
# .env is gitignored and .env.example carries only placeholders — real secrets belong in
# neither the diff nor tracked files.
#
# Usage:  scripts/checks/secret-scan.sh

set -uo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
. "$DIR/lib.sh"
root="$(repo_root)"

# High-confidence patterns. Kept specific to limit false positives.
declare -a PATTERNS=(
  'AKIA[0-9A-Z]{16}'                                  # AWS access key id
  'aws_secret_access_key\s*=\s*[A-Za-z0-9/+=]{30,}'   # AWS secret
  'ghp_[A-Za-z0-9]{30,}'                              # GitHub PAT
  'github_pat_[A-Za-z0-9_]{40,}'                      # GitHub fine-grained PAT
  'xox[baprs]-[A-Za-z0-9-]{10,}'                      # Slack token
  'sk-[A-Za-z0-9]{20,}'                               # OpenAI-style key
  'sk-ant-[A-Za-z0-9-]{20,}'                          # Anthropic key
  '-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----' # private key
  '(secret|password|passwd|api_key|apikey|token)["'"'"']?\s*[:=]\s*["'"'"'][^"'"'"'[:space:]]{12,}["'"'"']' # assigned literal secret
)

found=0
report() {
  if [ "$found" -eq 0 ]; then
    echo "✖ Potential secrets detected in changes:"
  fi
  found=1
}

# Scan the staged diff added lines when available; else scan changed files.
diff_text="$(git -C "$root" diff --cached -U0 2>/dev/null)"
[ -z "$diff_text" ] && diff_text="$(git -C "$root" diff -U0 2>/dev/null)"

scan_source() {
  local label="$1" text="$2" pat
  for pat in "${PATTERNS[@]}"; do
    hits="$(printf '%s' "$text" | grep -nEI "$pat" 2>/dev/null | grep -vE '\.env\.example|EXAMPLE|placeholder|your[-_]?key|xxx+' )"
    if [ -n "$hits" ]; then
      report
      echo "  [$label] pattern: $pat"
      printf '%s\n' "$hits" | head -5 | sed 's/^/    /'
    fi
  done
}

if [ -n "$diff_text" ]; then
  # Only added lines (start with + but not +++).
  added="$(printf '%s\n' "$diff_text" | grep -E '^\+' | grep -vE '^\+\+\+')"
  scan_source "diff" "$added"
else
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    case "$f" in *".env.example") continue;; esac
    scan_source "${f#"$root"/}" "$(cat "$f" 2>/dev/null)"
  done < <(changed_files)
fi

if [ "$found" -eq 1 ]; then
  echo ""
  echo "→ Remove the secret, rotate it if it was ever committed, and use config/Settings"
  echo "  (env vars) or a secret reference instead. Bypass intentionally: SKIP_SECRET_SCAN=1."
  [ "${SKIP_SECRET_SCAN:-0}" = "1" ] && { echo "⏭  SKIP_SECRET_SCAN=1 — not blocking."; exit 0; }
  exit 1
fi

echo "✓ secret-scan: no high-confidence secrets found."
exit 0
