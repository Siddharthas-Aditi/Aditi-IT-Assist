#!/usr/bin/env bash
# ==================================================
# Aditi IT Assist — Bootstrap Script
# ==================================================
# First-time project setup. Run from the repo root:
#   ./scripts/bootstrap.sh
set -euo pipefail

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BOLD}$1${NC}"; }
ok()    { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail()  { echo -e "  ${RED}✗${NC} $1"; exit 1; }

echo ""
info "🚀 Bootstrapping Aditi IT Assist..."
echo ""

# ── Prerequisites ───────────────────────────────
info "Checking prerequisites..."

command -v python3 >/dev/null 2>&1 && ok "Python 3 found" || fail "Python 3 is required"
command -v node >/dev/null 2>&1    && ok "Node.js found ($(node -v))" || fail "Node.js is required"
command -v docker >/dev/null 2>&1  && ok "Docker found" || fail "Docker is required"

# Install uv if not present
if command -v uv >/dev/null 2>&1; then
    ok "uv found ($(uv --version))"
else
    info "  Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed"
fi

echo ""

# ── Environment Files ───────────────────────────
info "Setting up environment files..."

if [ ! -f .env ]; then
    cp .env.example .env
    ok "Created .env from .env.example"
    warn "Edit .env and add your LLM_API_KEY"
else
    ok ".env already exists"
fi

# Sync backend/.env from root .env (subset)
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    ok "Created backend/.env"
fi

if [ ! -f frontend/.env ]; then
    cp frontend/.env.example frontend/.env
    ok "Created frontend/.env"
fi

echo ""

# ── Dependencies ────────────────────────────────
info "Installing backend dependencies..."
(cd backend && uv sync) && ok "Backend deps installed" || fail "Backend install failed"

echo ""
info "Installing frontend dependencies..."
(cd frontend && npm install --silent) && ok "Frontend deps installed" || fail "Frontend install failed"

echo ""

# ── Git Hooks ───────────────────────────────────
if [ -d .git ]; then
    info "Setting up git hooks..."
    if [ -d hooks ]; then
        cp hooks/pre-commit/format.sh .git/hooks/pre-commit 2>/dev/null && chmod +x .git/hooks/pre-commit
        ok "Pre-commit hook installed"
    else
        ok "No custom hooks found — skipping"
    fi
fi

echo ""
info "✅ Bootstrap complete!"
echo ""
echo "  Quick start options:"
echo ""
echo "    ${BOLD}make dev${NC}         → Full stack in Docker (hot-reload)"
echo "    ${BOLD}make dev-local${NC}   → Backend + frontend locally (needs Postgres/Redis)"
echo "    ${BOLD}make dev-infra${NC}   → Start only Postgres + Redis in Docker"
echo ""
echo "  Then open: ${BOLD}http://localhost:5173${NC}"
echo ""
