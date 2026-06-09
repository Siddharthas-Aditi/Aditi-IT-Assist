#!/usr/bin/env bash
# Smoke test — verify services are running
set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:5173}"

echo "🔍 Running smoke tests..."

# Test backend health
echo -n "  Backend health: "
if curl -sf "$BACKEND_URL/api/v1/health" > /dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    exit 1
fi

# Test backend readiness
echo -n "  Backend ready:  "
if curl -sf "$BACKEND_URL/api/v1/health/ready" > /dev/null; then
    echo "✅ OK"
else
    echo "❌ FAILED"
    exit 1
fi

# Test frontend
echo -n "  Frontend:       "
if curl -sf "$FRONTEND_URL" > /dev/null; then
    echo "✅ OK"
else
    echo "⚠️  Not available (may need npm run build first)"
fi

echo ""
echo "🎉 Smoke tests passed!"
