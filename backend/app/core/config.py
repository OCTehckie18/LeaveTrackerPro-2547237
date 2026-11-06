"""Application settings (12-factor, validated at start-up). See docs/ARCHITECTURE.md section 8."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: Literal["local", "production"] = "local"
    # Local default matches infra/docker-compose.yml (127.0.0.1, not "localhost": on Windows the IPv6 attempt stalls 8 s). Production must override it (validated below).
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:5433/leavetracker"
    db_pool_size: int = 5

    # Documents: Supabase Storage (S3 API) when STORAGE_S3_ENDPOINT is set, else a local folder.
    local_storage_dir: str = "./data/blobs"
    storage_s3_endpoint: str | None = None
    storage_s3_region: str = "ap-southeast-1"
    storage_bucket: str = "leave-documents"
    storage_s3_access_key_id: SecretStr | None = None
    storage_s3_secret_access_key: SecretStr | None = None

    allowed_origins: str = "http://localhost:5173"  # comma separated; CORS stays off
    cookie_secure: bool = False
    session_idle_min: int = 30
    session_absolute_h: int = 8
    trusted_proxy_hops: int = 0

    org_tz: str = "Asia/Kolkata"

    demo_mode: bool = False
    demo_password: SecretStr | None = None
    max_upload_files: int = 3
    max_upload_mb: int = 3
    demo_quota_mb: int = 20

    log_level: str = "INFO"
    sentry_dsn: str | None = None
    app_version: str = Field(
        default="dev", validation_alias=AliasChoices("APP_VERSION", "RENDER_GIT_COMMIT")
    )

    @property
    def origins(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def sqlalchemy_url(self) -> str:
        """Force the psycopg 3 driver whatever scheme the platform hands us."""
        url = self.database_url
        for prefix in ("postgresql://", "postgres://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @model_validator(mode="after")
    def _production_guards(self) -> Self:
        """Refuse to boot in production with an insecure configuration."""
        if not self.is_production:
            return self
        problems: list[str] = []
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true")
        if "sslmode=verify-full" not in self.database_url:
            problems.append("DATABASE_URL must use sslmode=verify-full")
        if not self.origins or any(not o.startswith("https://") for o in self.origins):
            problems.append("ALLOWED_ORIGINS must all be https:// origins")
        if self.demo_mode and self.demo_password is None:
            problems.append("DEMO_PASSWORD is required when DEMO_MODE=true")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
