# Safety Gates & Hooks

Automated checks that keep quality high and mistakes out of the repo. Three layers,
from fastest/most-local to authoritative.

## 1. Claude post-edit hook (already wired)
`.claude/settings.json` runs `scripts/claude-lint-file.sh` after every Edit/Write —
ESLint (frontend) or Ruff (backend) on just the changed file. Failures are surfaced back
to the model; fix them in the same turn. No setup needed.

## 2. Repository safety checks (`scripts/checks/`)
Lightweight, dependency-light guards you can run anytime and wire into git hooks:

| Script | Type | What it does |
|--------|------|--------------|
| `secret-scan.sh` | **blocking** | High-confidence secret patterns in the diff |
| `forbidden-dummy-data.sh` | advisory* | Placeholder/mock/`NaN%` in product code paths (`memory/known-risks.md` #9) |
| `docs-reminder.sh` | advisory | Warns if code changed with no docs/memory update |
| `commit-msg-check.sh` | advisory* | `<type>: <summary>` convention, subject ≤ 72 chars |
| `run-safety-checks.sh` | mixed | Runs secret-scan (blocking) + dummy-data + docs-reminder |

\* Make blocking with `STRICT=1` / `STRICT_DUMMY_DATA=1` / `STRICT_COMMIT_MSG=1`.
Bypass secret-scan intentionally with `SKIP_SECRET_SCAN=1`.

Run manually before committing:
```bash
bash scripts/checks/run-safety-checks.sh          # advisory dummy-data/docs, blocking secrets
STRICT=1 bash scripts/checks/run-safety-checks.sh  # everything blocking
```

### Wire into git (optional, per clone)
The authoritative gate is the pre-push hook enabled by `make install-hooks`
(`.githooks/pre-push`: lint + typecheck + tests, mirrors CI). To also run the safety
checks locally, add a `pre-commit` and `commit-msg` hook:
```bash
# from repo root, after `make install-hooks` (sets core.hooksPath=.githooks)
cat > .githooks/pre-commit <<'EOF'
#!/usr/bin/env bash
exec bash "$(git rev-parse --show-toplevel)/scripts/checks/run-safety-checks.sh"
EOF
cat > .githooks/commit-msg <<'EOF'
#!/usr/bin/env bash
exec bash "$(git rev-parse --show-toplevel)/scripts/checks/commit-msg-check.sh" "$1"
EOF
chmod +x .githooks/pre-commit .githooks/commit-msg
```
(The older `hooks/pre-commit/*.sh` scripts remain for reference; `.githooks/` is the
active hooks path.)

## 3. Pre-push + CI (authoritative)
`.githooks/pre-push` and `.github/workflows/ci.yml` run the full gate: frontend
lint+typecheck+vitest, backend ruff+mypy+pytest. A change is not "done" until these are
green. Bypass pre-push only intentionally (`SKIP_PREPUSH=1` / `git push --no-verify`).

## Principle
Gates exist so important checks aren't forgotten. If a gate fails, **fix the underlying
issue or explain it in the PR** — don't disable the gate to go green. See
`docs/development/commit-checklist.md`.
