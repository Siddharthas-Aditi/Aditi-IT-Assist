#!/usr/bin/env bash
# Bootstrap script — first-time project setup
set -euo pipefail

echo "🚀 Bootstrapping Aditi IT Assist..."

# Check prerequisites
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ Node.js is required"; exit 1; }
command -v docker >/dev/null 2>&1 || { echo "❌ Docker is required"; exit 1; }

# Install uv if not present
if ! command -v uv >/dev/null 2>&1; then
    echo "📦 Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create .env files from examples
echo "📝 Setting up environment files..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "   Created .env (edit with your API keys)"
fi
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
fi
if [ ! -f frontend/.env ]; then
    cp frontend/.env.example frontend/.env
fi

# Install backend dependencies
echo "🐍 Installing backend dependencies..."
cd backend && uv sync && cd ..

# Install frontend dependencies
echo "⚛️  Installing frontend dependencies..."
cd frontend && npm install && cd ..

# Setup pre-commit hooks
echo "🪝 Setting up git hooks..."
if [ -d .git ]; then
    cp hooks/pre-commit/format.sh .git/hooks/pre-commit 2>/dev/null || true
    chmod +x .git/hooks/pre-commit 2>/dev/null || true
fi

echo ""
echo "✅ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your LLM API key"
echo "  2. Run: make dev (Docker) or make dev-backend + make dev-frontend"
echo "  3. Open http://localhost:5173 in your browser"
echo ""
