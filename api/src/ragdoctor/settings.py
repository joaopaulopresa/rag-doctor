"""Process settings, read once from the environment."""

from __future__ import annotations

import logging
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the API and the worker read from the environment."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://ragdoctor:ragdoctor@localhost:54330/ragdoctor"
    engine_schema: str = Field(
        default="ragbench", description="Schema of the engine's cache, indexes and run results."
    )
    data_dir: Path = Path(".data")
    catalog_path: Path = Path(__file__).resolve().parents[2] / "config" / "catalog.yaml"

    mock_rag_url: str = "http://localhost:8311"
    openrouter_api_key: str = ""
    judge_model: str = "deepseek/deepseek-v4.1-flash-1017"
    chat_model: str = "ibm-granite/granite-4.2-8b"
    seed_model: str = "meta-llama/llama-3.1-8b-instruct"

    admin_email: str = "admin@ragdoctor.demo"
    admin_password: str = "doctor-admin"
    user_email: str = "reader@ragdoctor.demo"
    user_password: str = "doctor-reader"
    jwt_secret: str = Field(
        default="",
        description="Signs session cookies. Empty: a random secret per start (sessions end on "
        "restart).",
    )
    session_hours: int = 12
    chat_requires_login: bool = False
    cookie_secure: bool = False

    @model_validator(mode="after")
    def _session_secret(self) -> Settings:
        if not self.jwt_secret:
            self.jwt_secret = secrets.token_urlsafe(48)
        elif len(self.jwt_secret.encode()) < 32:
            logging.getLogger(__name__).warning(
                "JWT_SECRET is shorter than 32 bytes; use a long random string"
            )
        return self

    @property
    def sqlalchemy_url(self) -> str:
        """The database URL with the psycopg 3 driver SQLAlchemy needs."""
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    @property
    def engine_env(self) -> dict[str, str]:
        """Secrets handed to the engine (it reads every ``*_API_KEY`` entry)."""
        return {"OPENROUTER_API_KEY": self.openrouter_api_key}


@lru_cache
def get_settings() -> Settings:
    """Return the process settings."""
    return Settings()
