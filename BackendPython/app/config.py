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
Optional, for the nightly backup email (the app runs without them; email is then off):
  SMTP_HOST          mail server, for example smtp.gmail.com
  SMTP_PORT          587 (STARTTLS, default) or 465 (TLS); mail is never sent unencrypted
  SMTP_USERNAME      login for the mail server (with SMTP_PASSWORD)
  SMTP_PASSWORD      password or app password for SMTP_USERNAME
  SMTP_FROM          sender address (defaults to SMTP_USERNAME when that is an address)
  BACKUP_ZIP_PASSWORD 12-128 characters; the emailed ZIP is AES-256 encrypted with it
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Mapping

from .domain import validation

DEV_ORIGINS = (
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:5174", "http://127.0.0.1:5174",
)
ZIP_PASSWORD_MIN = 12
ZIP_PASSWORD_MAX = 128


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
    smtp_host: str | None = None
    smtp_port: int | None = 587
    smtp_username: str | None = None
    smtp_password: str | None = field(default=None, repr=False)
    smtp_from: str | None = None
    backup_zip_password: str | None = field(default=None, repr=False)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def cookie_name(self) -> str:
        # The __Host- prefix makes browsers refuse the cookie unless it is Secure,
        # host-only and scoped to "/".
        return "__Host-sid" if self.cookie_secure else "sid"

    def mail_missing(self) -> tuple[str, ...]:
        """What the backup email still needs, in plain words (empty when it is ready)."""
        missing = []
        if not self.smtp_host:
            missing.append("SMTP_HOST")
        if self.smtp_port is None:
            missing.append("SMTP_PORT (a port number such as 587)")
        if bool(self.smtp_username) != bool(self.smtp_password):
            missing.append("SMTP_PASSWORD" if self.smtp_username else "SMTP_USERNAME")
        if not self.smtp_from:
            missing.append("SMTP_FROM (the sender address)")
        if not self.backup_zip_password:
            missing.append(f"BACKUP_ZIP_PASSWORD ({ZIP_PASSWORD_MIN} to {ZIP_PASSWORD_MAX} characters)")
        return tuple(missing)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if env is None else env
    vercel = env.get("VERCEL_ENV", "")
    environment = env.get("APP_ENV") or ("production" if vercel == "production" else "preview" if vercel else "development")
    if environment not in ("production", "preview", "development"):
        raise ConfigError("APP_ENV must be production, preview or development.")

    database_url = env.get("DATABASE_URL") or None
    if database_url:
        database_url = database_url.strip().strip('"').strip("'")
        if database_url.startswith("postgres://"):
            database_url = "postgresql://" + database_url[len("postgres://"):]
        if "://" in database_url and "@" in database_url:
            try:
                from urllib.parse import quote, unquote

                prefix, rest = database_url.split("://", 1)
                userinfo, hostdb = rest.rsplit("@", 1)
                if ":" in userinfo:
                    user, pwd = userinfo.split(":", 1)
                    database_url = f"{prefix}://{user}:{quote(unquote(pwd), safe='')}@{hostdb}"
            except Exception:
                pass
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
    return Settings(environment, database_url, cron_secret, cookie_secure, trusted, docs, trust_proxy,
                    **_mail_settings(env))


def _mail_settings(env: Mapping[str, str]) -> dict:
    """Optional mail settings. Bad values are left unset (reported by mail_missing), never fatal."""
    def text(name: str) -> str | None:
        value = (env.get(name) or "").strip()
        return value or None

    port_text = text("SMTP_PORT") or "587"
    port = int(port_text) if port_text.isdigit() and 0 < int(port_text) < 65536 else None
    username = text("SMTP_USERNAME")
    sender = text("SMTP_FROM") or (username if username and "@" in username else None)
    try:
        sender = validation.email_recipient(sender) if sender else None
    except validation.ValidationError:
        sender = None
    zip_password = env.get("BACKUP_ZIP_PASSWORD") or None
    if zip_password is not None and not (
        ZIP_PASSWORD_MIN <= len(zip_password) <= ZIP_PASSWORD_MAX and zip_password.isprintable()
    ):
        zip_password = None
    return {
        "smtp_host": text("SMTP_HOST"),
        "smtp_port": port,
        "smtp_username": username,
        "smtp_password": env.get("SMTP_PASSWORD") or None,
        "smtp_from": sender,
        "backup_zip_password": zip_password,
    }


@lru_cache(maxsize=1)
def settings() -> Settings:
    return load_settings()
