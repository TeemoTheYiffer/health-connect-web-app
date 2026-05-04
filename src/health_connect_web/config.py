"""Centralized settings, loaded from env vars (with .env support in dev)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: str = "dev"
    log_level: str = "INFO"
    session_secret: str = "dev-only-insecure-change-me"

    database_url: str = "sqlite:///./hcw.db"

    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""

    owner_email: str = ""
    # Stored as a raw comma-separated string so pydantic-settings doesn't try to JSON-parse it.
    # Use `allowed_emails_list` to read.
    allowed_emails: str = ""

    drive_folder_id: str = ""
    drive_credentials_json_path: Path = Path(".secrets/drive_credentials.json")
    drive_token_json_path: Path = Path(".secrets/drive_token.json")

    local_health_connect_db: Path | None = None

    @property
    def allowed_emails_list(self) -> list[str]:
        return [e.strip().lower() for e in self.allowed_emails.split(",") if e.strip()]

    def is_email_allowed(self, email: str) -> bool:
        e = email.strip().lower()
        if not e:
            return False
        if self.owner_email and e == self.owner_email.strip().lower():
            return True
        return e in self.allowed_emails_list

    @property
    def is_prod(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
