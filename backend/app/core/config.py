"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings

# Secrets that must never survive into a production boot.
_PLACEHOLDER_SECRETS = (
    "change-me-in-production",
    "dev-secret-key-change-in-production",
    "",
)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "Aditi IT Assist"
    APP_ENV: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "DEBUG"

    # Server
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    SECRET_KEY: str = "change-me-in-production"
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "aditi_assist"
    POSTGRES_USER: str = "aditi"
    POSTGRES_PASSWORD: str = "aditi_dev_password"

    @property
    def DATABASE_URL(self) -> str:
        """Construct async database URL."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Construct sync database URL (for Alembic migrations)."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""  # required non-empty in production (validated at startup)

    @property
    def REDIS_URL(self) -> str:
        """Construct Redis URL (password-authenticated when configured)."""
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Authentication
    AUTH_PROVIDER: str = "local"  # "local" | "saml" | "oidc"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"
    # Token revocation (logout / refresh rotation) uses a Redis jti denylist.
    # False = fail-open when Redis is down (tokens age out via exp; warning
    # logged). True = fail-closed (401 until Redis is back). See token_store.py.
    TOKEN_DENYLIST_FAIL_CLOSED: bool = False

    # SAML Configuration (future SSO integration)
    SAML_ENABLED: bool = False
    SAML_IDP_ENTITY_ID: str = ""
    SAML_IDP_SSO_URL: str = ""
    SAML_IDP_SLO_URL: str = ""
    SAML_IDP_CERTIFICATE: str = ""
    SAML_SP_ENTITY_ID: str = "aditi-it-assist"
    SAML_SP_ACS_URL: str = "http://localhost:8000/api/v1/auth/saml/acs"
    SAML_SP_SLS_URL: str = "http://localhost:8000/api/v1/auth/saml/sls"
    SAML_ATTRIBUTE_MAP_EMAIL: str = (
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    )
    SAML_ATTRIBUTE_MAP_NAME: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
    SAML_ATTRIBUTE_MAP_GROUPS: str = (
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
    )
    SAML_DEFAULT_ROLE: str = "employee"

    # LLM Configuration
    LLM_PROVIDER: str = "openai"  # "openai" | "azure" | "anthropic"
    LLM_MODEL: str = "gpt-4o"  # used when LLM_PROVIDER != "azure"
    LLM_API_KEY: str = ""  # OpenAI key (ignored when LLM_PROVIDER=azure)
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096

    # Azure OpenAI / Azure AI Services (LLM_PROVIDER=azure)
    AZURE_OPENAI_ENDPOINT: str = ""  # https://resource.services.ai.azure.com
    AZURE_OPENAI_API_KEY: str = ""  # Azure resource key
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    AZURE_OPENAI_LLM_DEPLOYMENT: str = "gpt-4.1"
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT: str = "text-embedding-3-large"
    EMBEDDING_DIMENSIONS: int = 3072  # text-embedding-3-large default (max); 1536 for Ada
    # Set False when running behind a corporate SSL-inspecting proxy.
    # Disables TLS certificate verification for all Azure AI / LiteLLM calls.
    AZURE_OPENAI_VERIFY_SSL: bool = True

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def is_azure(self) -> bool:
        return self.LLM_PROVIDER.lower() == "azure"

    @property
    def effective_llm_model(self) -> str:
        """LiteLLM model string, e.g. 'azure/gpt-4.1' or 'gpt-4o'."""
        if self.is_azure:
            return f"azure/{self.AZURE_OPENAI_LLM_DEPLOYMENT}"
        return self.LLM_MODEL

    @property
    def effective_llm_api_key(self) -> str:
        return self.AZURE_OPENAI_API_KEY if self.is_azure else self.LLM_API_KEY

    @property
    def effective_embedding_model(self) -> str:
        if self.is_azure:
            return f"azure/{self.AZURE_OPENAI_EMBEDDING_DEPLOYMENT}"
        return "text-embedding-3-small"  # fallback for non-azure

    @property
    def llm_is_configured(self) -> bool:
        """True when a real key is present (not placeholder)."""
        key = self.effective_llm_api_key
        return bool(key and key not in ("your-api-key-here", "your-azure-key-here", ""))

    # Vector Store
    VECTOR_STORE_TYPE: str = "pgvector"

    # Remote Support
    REMOTE_SUPPORT_PROVIDER: str = "microsoft_remote_help"
    REMOTE_SESSION_TIMEOUT_MINUTES: int = 30
    REMOTE_SESSION_MAX_DURATION_MINUTES: int = 120
    # Dev/demo: mock provider (no Graph calls) — mirrors MCP_USE_MOCK. Set
    # False in production once the Graph app registration below is configured.
    REMOTE_SUPPORT_USE_MOCK: bool = True
    # Sweeper that expires consent-lapsed sessions and terminates sessions
    # exceeding max duration (runs on the in-process background scheduler).
    REMOTE_SESSION_SWEEPER_ENABLED: bool = True
    REMOTE_SESSION_SWEEPER_INTERVAL_SECONDS: int = 60
    # Microsoft Graph app registration for Remote Help orchestration
    # (client-credential flow; see docs/architecture/remote-support-decision.md).
    REMOTE_HELP_TENANT_ID: str = ""
    REMOTE_HELP_CLIENT_ID: str = ""
    REMOTE_HELP_CLIENT_SECRET: str = ""  # from secrets manager in production
    INTUNE_ADMIN_CENTER_BASE_URL: str = "https://intune.microsoft.com"

    # Observability
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "aditi-it-assist"
    OTEL_ENABLED: bool = False  # opt-in distributed tracing
    METRICS_ENABLED: bool = True  # Prometheus /metrics endpoint + request metrics

    # Email
    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ESCALATION_EMAIL: str = "it-support@aditiconsulting.com"

    # Rate Limiting (see app/core/rate_limit.py — Redis sliding window with
    # in-memory fallback; health/metrics endpoints exempt)
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10
    # Tighter budget for credential endpoints (login/refresh) — brute-force guard.
    RATE_LIMIT_AUTH_REQUESTS_PER_MINUTE: int = 10

    # Background scheduler — the live-specialist-chat idle sweeper runs in
    # the same event loop as the API. Turn off in tests or when running
    # multiple replicas without a distributed lock (see scheduler.py docs).
    IDLE_SWEEPER_ENABLED: bool = True
    IDLE_SWEEPER_INTERVAL_SECONDS: int = 30
    # Live-chat idle policy: warn the user after WARNING seconds of silence, then
    # auto-end after END seconds. Default = 7-minute warning + 2-minute grace.
    LIVE_CHAT_IDLE_WARNING_SECONDS: int = 420
    LIVE_CHAT_IDLE_END_SECONDS: int = 540
    # Live-handoff freshness — the ONE knob for "is the employee still
    # actively waiting for a specialist". Drives BOTH the employee-side
    # fallback message (ChatService.get_waiting_status) and the specialist
    # queue's typed waiting_state ("waiting" vs "likely_left"), so the two
    # sides can never disagree about what "stale" means.
    LIVE_WAIT_TIMEOUT_SECONDS: int = 900  # 15 minutes

    # ── Supervisor routing (Phase-1 dual-run) ────────────────────────
    # When SHADOW is on, the supervisor runs after triage on every turn but
    # its decision is only LOGGED — the legacy graph still drives routing.
    # When PRIMARY is on, the supervisor's decision is acted on. We never
    # set both at once; PRIMARY implies SHADOW for analytics joining.
    # See docs/development/rollout-plan-multi-agent.md.
    FEATURE_SUPERVISOR_SHADOW: bool = True
    FEATURE_SUPERVISOR_PRIMARY: bool = False

    # ── Agent tool calling (Phase 5) ─────────────────────────────────
    # When on, specialists with a non-empty ``allowed_tools`` may run a
    # bounded LLM tool-use loop via AgentToolRuntime. Default OFF: the
    # deterministic step path is unchanged until this is enabled and an LLM
    # is configured. Per-tool RBAC + approval gates apply regardless.
    # Max tool calls the agent may make in a single turn.
    # See docs/architecture/agent-tooling.md.
    FEATURE_AGENT_TOOLS: bool = False
    AGENT_TOOLS_MAX_ITERS: int = 4

    # ── Semantic / hybrid retrieval (Phase 6) ────────────────────────
    # When on AND an embedding provider is configured, the governed
    # retrieval service embeds the query and blends pgvector semantic
    # similarity with the keyword signal (hybrid). Default OFF: pure
    # keyword retrieval (unchanged). Falls back to keyword automatically
    # when no provider/embedding is available, so flipping this on is safe.
    # Weights are tunable in one place and must sum to 1.0 (validated).
    # See docs/architecture/retrieval-and-indexing.md.
    FEATURE_VECTOR_RETRIEVAL: bool = False
    HYBRID_WEIGHT_VECTOR: float = 0.60
    HYBRID_WEIGHT_KEYWORD: float = 0.30
    HYBRID_WEIGHT_USAGE: float = 0.07
    HYBRID_WEIGHT_QUALITY: float = 0.03

    # ── MCP integrations (Phase 7) ───────────────────────────────────
    # Agents consume external systems (Entra/Intune/Exchange via Graph,
    # ServiceNow) as MCP-backed, read-only tools. Master switch + an explicit
    # per-server allow-list; nothing is reachable unless the flag is on AND the
    # server id is listed. All Phase-7 tools are read-only and time-bounded.
    # See docs/architecture/mcp-integrations.md.
    FEATURE_MCP_TOOLS: bool = False
    MCP_ENABLED_SERVERS: list[str] = []  # e.g. ["msgraph", "servicenow"]
    MCP_TOOL_TIMEOUT_SECONDS: float = 8.0
    # Dev/demo: use an in-memory mock MCP session (no real Graph/ServiceNow).
    # Leave True locally to exercise diagnostics + write approvals end-to-end;
    # set False in production once real MCP servers are reachable.
    MCP_USE_MOCK: bool = True
    # Auth material for MCP servers — referenced by McpServerProfile.auth_secret_ref.
    # Empty by default; populate from the secrets manager in production.
    MCP_MSGRAPH_TOKEN: str = ""
    MCP_SERVICENOW_TOKEN: str = ""

    # ── Write actions + background agents (Phase 8) ──────────────────
    # Gate for write/destructive agent tools (reset MFA, unlock account,
    # create incident). Every such tool is human-approved at execution
    # regardless of this flag; the flag controls whether the tools are even
    # built/exposed. Default OFF.
    FEATURE_AGENT_WRITE_ACTIONS: bool = False
    # Async task runner for autonomous/background agents (nightly knowledge
    # improvement, proactive diagnostics). Default OFF.
    FEATURE_BACKGROUND_AGENTS: bool = False
    AGENT_BACKGROUND_CONCURRENCY: int = 2  # max background tasks in flight
    AGENT_BACKGROUND_POLL_SECONDS: int = 60  # runner poll interval
    AGENT_TASK_MAX_ATTEMPTS: int = 3  # retry budget per task

    # Document Ingestion
    UPLOAD_DIR: str = "/tmp/aditi_uploads"
    MAX_UPLOAD_MB: int = 50
    INGESTION_PARSER_VERSION: str = "1.0.0"
    INGESTION_LLM_ENABLED: bool = True  # set False to skip LLM enrichment

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Environment helpers + production guardrails ───────────────────
    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in ("production", "prod")

    def validate_production(self) -> list[str]:
        """Return config violations that make a production boot unsafe.

        Called from the app lifespan: in production, any violation aborts
        startup (fail fast beats booting with a forgeable SECRET_KEY). Pure
        function — returns the list so tests can assert exact messages.
        """
        if not self.is_production:
            return []

        violations: list[str] = []
        if self.SECRET_KEY in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32:
            violations.append(
                "SECRET_KEY is a placeholder or too short (need >=32 chars of real entropy)"
            )
        if self.DEBUG:
            violations.append("DEBUG must be false in production")
        if self.POSTGRES_PASSWORD in ("aditi_dev_password", ""):
            violations.append("POSTGRES_PASSWORD is the dev default or empty")
        if not self.REDIS_PASSWORD:
            violations.append("REDIS_PASSWORD must be set in production")
        if self.MCP_USE_MOCK and self.FEATURE_MCP_TOOLS:
            violations.append("FEATURE_MCP_TOOLS is on but MCP_USE_MOCK is still true")
        if self.REMOTE_SUPPORT_USE_MOCK is False and not (
            self.REMOTE_HELP_TENANT_ID
            and self.REMOTE_HELP_CLIENT_ID
            and self.REMOTE_HELP_CLIENT_SECRET
        ):
            violations.append(
                "REMOTE_SUPPORT_USE_MOCK=false requires REMOTE_HELP_TENANT_ID/"
                "CLIENT_ID/CLIENT_SECRET"
            )
        if any(o.startswith("http://localhost") for o in self.CORS_ORIGINS):
            violations.append("CORS_ORIGINS still contains localhost origins")
        return violations


settings = Settings()
