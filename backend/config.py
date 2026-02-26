import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://learner_service@localhost:5432/learner_metrics"
    SECRET_KEY: str = "super-secret-key-change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Google OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None

    # NCBI / PubMed (optional - higher rate limits with API key: 10 req/s vs 3 req/s)
    NCBI_API_KEY: Optional[str] = None

    # Environment
    ENVIRONMENT: str = "development"  # development | staging | production

    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        extra="ignore",
    )


settings = Settings()

if settings.SECRET_KEY == "super-secret-key-change-me-in-production":
    if os.environ.get("TESTING") != "true":
        import warnings
        warnings.warn(
            "WARNING: Using default SECRET_KEY. Set SECRET_KEY in .env for production.",
            stacklevel=1,
        )
