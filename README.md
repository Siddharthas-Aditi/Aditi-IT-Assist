# 🤖 Aditi IT Assist

**Agentic AI-powered IT support platform for Aditi Consulting**

An intelligent multi-agent system that resolves employee IT issues through
natural language conversation, powered by LangGraph workflow orchestration.

---

## 🎯 What It Does

| Feature | Description |
|---------|-------------|
| 💬 Natural Language Support | Employees describe IT issues in plain English |
| 🧠 Multi-Agent Workflow | 6 specialized AI agents work together via LangGraph |
| 📚 Knowledge-Grounded | Answers come from curated playbooks, not hallucination |
| 📊 Confidence Scoring | AI knows when it doesn't know |
| 🔄 Graceful Escalation | Structured handoff to human agents with full context |
| 🎫 Ticket Generation | Auto-creates support tickets when escalation needed |
| 📈 Audit Trail | Every decision logged for compliance |

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Frontend (React/Vite/TS)                  │
└─────────────────────────┬──────────────────────────────────┘
                          │ API
┌─────────────────────────▼──────────────────────────────────┐
│                    Backend (FastAPI)                         │
├─────────────────────────────────────────────────────────────┤
│              Agent Workflow (LangGraph)                      │
│  Triage → Retrieval → Resolution → Escalation → Ticketing  │
├─────────────────────────────────────────────────────────────┤
│         PostgreSQL + pgvector │ Redis │ LiteLLM             │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.12+
- Node.js 20+
- Docker & Docker Compose

### Option 1: Docker (Recommended)
```bash
# Clone and enter project
cd aditi-it-assist

# Copy environment file and add your LLM API key
cp .env.example .env

# Start everything
docker compose up --build
```

Open http://localhost:5173 for the frontend and http://localhost:8000/docs for the API.

### Option 2: Local Development
```bash
# First-time setup
make bootstrap

# Start backend (terminal 1)
make dev-backend

# Start frontend (terminal 2)
make dev-frontend
```

### Option 3: Full Bootstrap
```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
make dev
```

## 📁 Project Structure

```
aditi-it-assist/
├── backend/              # Python FastAPI application
│   ├── app/
│   │   ├── api/v1/      # Versioned API routes
│   │   ├── core/        # Config, DB, logging, security
│   │   ├── models/      # SQLAlchemy models
│   │   ├── schemas/     # Pydantic schemas
│   │   ├── services/    # Business logic
│   │   ├── workflows/   # LangGraph agent workflow
│   │   └── knowledge_base/  # Seed knowledge YAMLs
│   └── tests/
├── frontend/             # React TypeScript application
│   └── src/
│       ├── pages/       # Route pages
│       ├── components/  # Shared UI components
│       ├── features/    # Feature modules
│       └── store/       # Zustand state
├── docs/                # Documentation
├── agents/              # Agent specifications
├── prompts/             # AI coding prompts
├── skills/              # Implementation standards
├── scripts/             # Utility scripts
└── docker-compose.yml   # Local development stack
```

## 🧪 Development

```bash
make test              # Run all tests
make lint              # Run linters
make format            # Auto-format code
make typecheck         # Type checking
make seed             # Seed knowledge base
make smoke-test       # Verify services running
```

## 📚 Documentation

- [Product Vision](docs/product/vision.md)
- [System Architecture](docs/architecture/system-architecture.md)
- [Agent Architecture](docs/architecture/agent-architecture.md)
- [Workflows](docs/architecture/workflows.md)
- [Development Setup](docs/development/setup.md)
- [Prompts Guide](docs/development/prompts-guide.md)

## 🤖 AI-Assisted Development

This repo is optimized for AI coding agents (GitHub Copilot, Claude):
- `CLAUDE.md` — Master context for AI agents
- `AGENTS.md` — Multi-agent system specification
- `.github/copilot-instructions.md` — Copilot context
- `prompts/` — Task-specific generation prompts
- `agents/` — Individual agent specs
- `skills/` — Implementation standards

## 🗺️ Roadmap

### Phase 1 ✅ Foundation
- [x] Multi-agent workflow (LangGraph)
- [x] Chat interface
- [x] Knowledge base (Outlook, Zoom, Intune, Camera)
- [x] Escalation and ticket drafting
- [x] Docker development environment

### Phase 2 🔜 Integration
- [ ] Real database with Alembic migrations
- [ ] pgvector semantic search
- [ ] LiteLLM integration with real models
- [ ] Authentication (JWT → Azure AD)
- [ ] WebSocket for real-time chat

### Phase 3 📋 Intelligence
- [ ] Knowledge learning agent
- [ ] Resolution success tracking
- [ ] Proactive issue detection
- [ ] Multi-language support

### Phase 4 🌐 Platform
- [ ] Microsoft 365 integration
- [ ] Intune API integration
- [ ] ServiceNow/Jira ticketing
- [ ] Human agent copilot
- [ ] Analytics dashboard

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend | React + TypeScript + Vite | UI Application |
| Styling | Tailwind CSS + shadcn/ui | Design System |
| State | Zustand + React Query | Client/Server State |
| Backend | FastAPI + Python 3.12 | API Server |
| Database | PostgreSQL + pgvector | Persistence + Vector Search |
| Cache | Redis | Sessions + Queue |
| AI | LangGraph + LiteLLM | Agent Orchestration |
| Infra | Docker Compose | Local Development |
| CI/CD | GitHub Actions | Automation |

## 📄 License

MIT — See [LICENSE](LICENSE)

---

Built with ❤️ by Aditi Consulting Engineering
