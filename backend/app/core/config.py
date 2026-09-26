from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "AI Business Intelligence Copilot"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database — application role (metadata + ingestion)
    POSTGRES_USER: str = "bi_admin"
    POSTGRES_PASSWORD: str = "bi_admin_dev"
    POSTGRES_DB: str = "bi_copilot"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str | None = None

    # Read-only role used for AI-generated / analytics queries
    BI_READER_USER: str = "bi_reader"
    BI_READER_PASSWORD: str = "bi_reader_dev"

    # Security
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # AI providers: none | anthropic | openai
    LLM_PROVIDER: str = "none"
    ANTHROPIC_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    LLM_MODEL: str | None = None

    # Query guardrails
    QUERY_TIMEOUT_SECONDS: int = 10
    QUERY_ROW_LIMIT: int = 5000

    # Uploads
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # CORS (comma-separated)
    CORS_ORIGINS: str = "http://localhost:3000"

    @property
    def database_url(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def reader_database_url(self) -> str:
        return (
            f"postgresql+psycopg://{self.BI_READER_USER}:{self.BI_READER_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_demo_mode(self) -> bool:
        return self.LLM_PROVIDER == "none"


@lru_cache
def get_settings() -> Settings:
    return Settings()
