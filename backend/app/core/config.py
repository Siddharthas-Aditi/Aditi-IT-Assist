"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


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

    @property
    def REDIS_URL(self) -> str:
        """Construct Redis URL."""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # Authentication
    AUTH_PROVIDER: str = "local"  # "local" | "saml" | "oidc"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    JWT_ALGORITHM: str = "HS256"

    # SAML Configuration (future SSO integration)
    SAML_ENABLED: bool = False
    SAML_IDP_ENTITY_ID: str = ""
    SAML_IDP_SSO_URL: str = ""
    SAML_IDP_SLO_URL: str = ""
    SAML_IDP_CERTIFICATE: str = ""
    SAML_SP_ENTITY_ID: str = "aditi-it-assist"
    SAML_SP_ACS_URL: str = "http://localhost:8000/api/v1/auth/saml/acs"
    SAML_SP_SLS_URL: str = "http://localhost:8000/api/v1/auth/saml/sls"
    SAML_ATTRIBUTE_MAP_EMAIL: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"
    SAML_ATTRIBUTE_MAP_NAME: str = "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"
    SAML_ATTRIBUTE_MAP_GROUPS: str = "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups"
    SAML_DEFAULT_ROLE: str = "employee"

    # LLM Configuration
    LLM_PROVIDER: str = "openai"
    LLM_MODEL: str = "gpt-4o"
    LLM_API_KEY: str = ""
    LLM_TEMPERATURE: float = 0.3
    LLM_MAX_TOKENS: int = 4096

    # Vector Store
    VECTOR_STORE_TYPE: str = "pgvector"

    # Remote Support
    REMOTE_SUPPORT_PROVIDER: str = "microsoft_remote_help"
    REMOTE_SESSION_TIMEOUT_MINUTES: int = 30
    REMOTE_SESSION_MAX_DURATION_MINUTES: int = 120

    # Observability
    OTEL_EXPORTER_ENDPOINT: str = "http://localhost:4317"
    OTEL_SERVICE_NAME: str = "aditi-it-assist"

    # Email
    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    ESCALATION_EMAIL: str = "it-support@aditiconsulting.com"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = 60
    RATE_LIMIT_BURST: int = 10

    # Document Ingestion
    UPLOAD_DIR: str = "/tmp/aditi_uploads"
    MAX_UPLOAD_MB: int = 50
    INGESTION_PARSER_VERSION: str = "1.0.0"
    INGESTION_LLM_ENABLED: bool = True   # set False to skip LLM enrichment

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
