import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "PathFinder"
    VERSION: str = "2.0.0"
    API_V1_STR: str = "/api"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    MARKET: str = "India"

    # Database — SQLite default; set DATABASE_URL to postgresql:// (Cloud SQL / AlloyDB) in prod.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./pathfinder.db")

    # Auth — MUST override JWT_SECRET in production.
    JWT_SECRET: str = os.getenv("JWT_SECRET", "DEV_SECRET_DO_NOT_USE_IN_PROD")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", str(60 * 24 * 7)))

    # Uploads
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))

    # Pluggable AI providers (all optional — see engines/providers.py)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # JD parsing across many jobs stays LOCAL (fast, deterministic) unless explicitly enabled.
    GEMINI_JD_PARSE: bool = False
    VERTEX_PROJECT: str = os.getenv("VERTEX_PROJECT", "")
    VERTEX_RAG_CORPUS: str = os.getenv("VERTEX_RAG_CORPUS", "")
    BQML_DATASET: str = os.getenv("BQML_DATASET", "")

    # Job data providers (professional dashboard) — all optional; local sample fallback.
    RAPIDAPI_KEY: str = os.getenv("RAPIDAPI_KEY", "")           # JSearch (RapidAPI)
    JSEARCH_HOST: str = os.getenv("JSEARCH_HOST", "jsearch.p.rapidapi.com")
    ADZUNA_APP_ID: str = os.getenv("ADZUNA_APP_ID", "")
    ADZUNA_APP_KEY: str = os.getenv("ADZUNA_APP_KEY", "")
    JOBS_COUNTRY: str = os.getenv("JOBS_COUNTRY", "in")         # Adzuna country code (India)

    # Google Sign-In (optional — button appears only when set)
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")

    # Password reset — links delivered by SMTP when configured; otherwise logged server-side.
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "")           # for reset links; else derived from request
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "")

    # Weekly digest — Cloud Scheduler calls /api/internal/digest/run with this token.
    DIGEST_TOKEN: str = os.getenv("DIGEST_TOKEN", "")

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024


settings = Settings()
