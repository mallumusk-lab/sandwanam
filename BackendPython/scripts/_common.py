"""Shared helpers for operator scripts. They talk to a real database, so every script
shows exactly which database it will touch and asks for confirmation first."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # optional: lets operators keep DATABASE_URL in BackendPython/.env
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:
    pass


def database_url() -> str:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("Set MIGRATION_DATABASE_URL (preferred: the direct connection, port 5432) or DATABASE_URL.")
    return url.replace("postgres://", "postgresql://", 1)


def describe(url: str) -> tuple[str, str]:
    parts = urlsplit(url)
    host = parts.hostname or "?"
    database = (parts.path or "/").lstrip("/") or "postgres"
    print(f"Target: host={host} port={parts.port or 5432} database={database} user={parts.username or '?'}")
    return host, database


def confirm(database: str, action: str, assume_yes: bool = False) -> None:
    if assume_yes:
        return
    answer = input(f"Type the database name ({database}) to {action}: ").strip()
    if answer != database:
        sys.exit("Cancelled.")


async def connect(url: str):
    import asyncpg

    # statement_cache_size=0 keeps scripts safe behind Supabase's transaction pooler too.
    return await asyncpg.connect(url, statement_cache_size=0)
