"""Runtime configuration from environment variables.

Required in production and preview deployments:
  DATABASE_URL       Postgres connection string (Supabase pooler URL is fine)
  CRON_SECRET        at least 32 characters; Vercel Cron sends it as a Bearer token
Optional:
  APP_ENV            production | preview | development (derived from VERCEL_ENV otherwise)
  COOKIE_SECURE      "false" only for plain-http local development
  TRUSTED_ORIGINS    extra comma-separated origins allowed to send state-changing requests
  DOCS_ENABLED       "true" to serve /docs outside production
  TRUST_PROXY_HEADERS "true"/"false": use x-real-ip / x-forwarded-for for client addresses
                     (default: true on Vercel, which sets them itself; false elsewhere)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping

DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str | None
    cron_secret: str | None
    cookie_secure: bool
    trusted_origins: tuple[str, ...]
    docs_enabled: bool
    trust_proxy_headers: bool = False

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_name(self) -> str:
        # The __Host- prefix makes browsers refuse the cookie unless it is Secure,
        # host-only and scoped to "/".
        return "__Host-sid" if self.cookie_secure else "sid"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    vercel = env.get("VERCEL_ENV", "")
    environment = env.get("APP_ENV") or ("production" if vercel == "production" else "preview" if vercel else "development")
    if environment not in ("production", "preview", "development"):
        raise ConfigError("APP_ENV must be production, preview or development.")

    database_url = env.get("DATABASE_URL") or None
    if database_url and database_url.startswith("postgres://"):
        database_url = "postgresql://" + database_url[len("postgres://"):]
    cron_secret = env.get("CRON_SECRET") or None
    cookie_secure = env.get("COOKIE_SECURE", "true").strip().lower() != "false"
    extra = tuple(o.strip().rstrip("/") for o in env.get("TRUSTED_ORIGINS", "").split(",") if o.strip())
    trusted = extra + (DEV_ORIGINS if environment == "development" else ())
    docs = env.get("DOCS_ENABLED", "").strip().lower() == "true" and environment != "production"
    trust_default = "true" if env.get("VERCEL") or vercel else "false"
    trust_proxy = env.get("TRUST_PROXY_HEADERS", trust_default).strip().lower() == "true"

    if environment != "development":
        missing = [name for name, value in (("DATABASE_URL", database_url), ("CRON_SECRET", cron_secret)) if not value]
        if missing:
            raise ConfigError(f"Missing required environment variables: {', '.join(missing)}.")
        if len(cron_secret or "") < 32:
            raise ConfigError("CRON_SECRET must be at least 32 characters.")
        if not cookie_secure:
            raise ConfigError("COOKIE_SECURE cannot be disabled outside development.")
    return Settings(environment, database_url, cron_secret, cookie_secure, trusted, docs, trust_proxy)


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()
