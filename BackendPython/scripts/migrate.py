"""Apply database migrations.

    py scripts/migrate.py --preflight      read-only data report (run first)
    py scripts/migrate.py                  apply 001–003 plus the data steps
    py scripts/migrate.py --branch-prefix User3=VZM   also give other branch accounts their prefix
    py scripts/migrate.py --post-cutover   004: drop the legacy trigger, validate constraints

Use the direct connection string (port 5432), not the transaction pooler (6543).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from urllib.parse import urlsplit

from _common import ROOT, confirm, connect, database_url, describe

from app.domain import particulars, validation
from app.security import passwords

MIGRATIONS = ROOT / "migrations"
MAIN_STEPS = ("001_baseline", "002_auth_integrity", "003_ledger_reporting")
POST_CUTOVER = "004_post_cutover"


async def ensure_ledger(conn) -> set[str]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(100) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await conn.execute(
        """
        DO $$
        BEGIN
            ALTER TABLE schema_migrations ENABLE ROW LEVEL SECURITY;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE schema_migrations FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE schema_migrations FROM authenticated;
            END IF;
        END $$;
        """
    )
    return {row["version"] for row in await conn.fetch("SELECT version FROM schema_migrations")}


async def apply_sql(conn, version: str, applied: set[str]) -> None:
    if version in applied:
        print(f"  {version}: already applied")
        return
    sql = (MIGRATIONS / f"{version}.sql").read_text(encoding="utf-8")
    async with conn.transaction():
        await conn.execute(sql)
        await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
    print(f"  {version}: applied")


def parse_prefixes(values: list[str]) -> dict[str, str]:
    mapping = {}
    for value in values:
        username, _, prefix = value.partition("=")
        if not username or not prefix:
            sys.exit(f"--branch-prefix expects <username>=<PREFIX>, got {value!r}.")
        try:
            mapping[username.strip()] = validation.branch_prefix(prefix)
        except validation.ValidationError as exc:
            sys.exit(f"{value}: {exc.message}")
    if len(set(mapping.values())) != len(mapping):
        sys.exit("Each branch needs a different prefix.")
    return mapping


async def assign_prefixes(conn, mapping: dict[str, str]) -> None:
    """Runs before 002 so its prefix check passes for accounts beyond Admin/User1/User2."""
    if not mapping:
        return
    async with conn.transaction():
        await conn.execute("ALTER TABLE role ADD COLUMN IF NOT EXISTS branch_prefix VARCHAR(10)")
        for username, prefix in mapping.items():
            found = await conn.fetchval("SELECT username FROM role WHERE lower(username) = lower($1)", username)
            if not found:
                sys.exit(f"No account named {username}.")
            await conn.execute("UPDATE role SET branch_prefix = $1 WHERE username = $2", prefix, found)
            print(f"  {found}: customer ID prefix {prefix}")


async def backfill_items(conn, applied: set[str]) -> None:
    version = "003a_items_backfill"
    if version in applied:
        print(f"  {version}: already applied")
        return
    async with conn.transaction():
        rows = await conn.fetch("SELECT loanid, particulars FROM loan_data WHERE items IS NULL")
        for row in rows:
            items = [item.as_dict() for item in particulars.parse_legacy(row["particulars"])]
            await conn.execute("UPDATE loan_data SET items = $1::jsonb WHERE loanid = $2", json.dumps(items), row["loanid"])
        await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
    print(f"  {version}: {len(rows)} loan(s) converted to structured items")


async def disable_default_passwords(conn) -> None:
    """Runs every time: no account may keep a published default or plaintext password."""
    async with conn.transaction():
        rows = await conn.fetch("SELECT username, password FROM role WHERE password IS NOT NULL")
        disabled = [r["username"] for r in rows if passwords.uses_known_default(r["password"])]
        for username in disabled:
            await conn.execute(
                "UPDATE role SET password = NULL, must_change_password = TRUE WHERE username = $1", username
            )
            await conn.execute("DELETE FROM sessions WHERE username = $1", username)
    if disabled:
        print("  Sign-in disabled (default or plaintext password) for: " + ", ".join(disabled))
        print("  Set new passwords with:  py scripts/set_password.py <username>")
    else:
        print("  No default or plaintext passwords found.")


async def preflight(conn, *, quiet_if_clean: bool = False) -> int:
    sql = (MIGRATIONS / "000_preflight.sql").read_text(encoding="utf-8")
    rows = await conn.fetch(sql)
    if quiet_if_clean and not any(r["severity"] == "blocking" for r in rows):
        return 0
    if not rows:
        print("Preflight: no issues found.")
        return 0
    blocking = 0
    for row in rows:
        blocking += row["severity"] == "blocking"
        print(f"[{row['severity']}] {row['check_name']}: {row['item']}  → {row['action']}")
    print(f"\n{len(rows)} finding(s), {blocking} blocking.")
    return 1 if blocking else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--post-cutover", action="store_true")
    parser.add_argument("--allow-pooler", action="store_true", help="permit port 6543 (not recommended)")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt (CI only)")
    parser.add_argument("--branch-prefix", action="append", default=[], metavar="USERNAME=PREFIX",
                        help="customer ID prefix for a branch account other than Admin/User1/User2")
    args = parser.parse_args()
    prefixes = parse_prefixes(args.branch_prefix)

    url = database_url()
    _, database = describe(url)
    if urlsplit(url).port == 6543 and not args.allow_pooler:
        sys.exit("This is the transaction pooler (port 6543). Use the direct connection (port 5432).")

    conn = await connect(url)
    try:
        if args.preflight:
            return await preflight(conn)
        confirm(database, "apply post-cutover changes" if args.post_cutover else "apply migrations", args.yes)
        applied = await ensure_ledger(conn)
        if args.post_cutover:
            await apply_sql(conn, POST_CUTOVER, applied)
            return 0
        if "002_auth_integrity" not in applied:
            await assign_prefixes(conn, prefixes)
        if "002_auth_integrity" not in applied and await preflight(conn, quiet_if_clean=True):
            print("\nFix the blocking items above, then run the migration again.")
            return 1
        for version in MAIN_STEPS:
            await apply_sql(conn, version, applied)
        await backfill_items(conn, applied)
        await disable_default_passwords(conn)
        print("Done.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
