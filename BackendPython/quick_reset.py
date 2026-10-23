"""Super simple password reset script.

Run directly in terminal:
    py quick_reset.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Set via environment or pass as argument:
DEFAULT_DATABASE_URL = "YOUR_DATABASE_URL_HERE"
DEFAULT_PASSWORD = "Admin@1234"


def normalize_db_url(url: str) -> str:
    """Ensure URL scheme is postgresql:// and password with '@' is properly URL-encoded."""
    url = url.strip().replace("postgres://", "postgresql://", 1)
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            path_idx = rest.find("/")
            authority = rest[:path_idx] if path_idx != -1 else rest
            path_and_query = rest[path_idx:] if path_idx != -1 else ""
            at_parts = authority.split("@")
            if len(at_parts) > 2:
                host_port = at_parts[-1]
                user_pass = "@".join(at_parts[:-1])
                user, _, password = user_pass.partition(":")
                safe_pass = urllib.parse.quote(urllib.parse.unquote(password))
                url = f"{scheme}://{user}:{safe_pass}@{host_port}{path_and_query}"
    return url


async def main() -> int:
    import asyncpg
    from app.security import passwords

    # 1. Parse optional terminal arguments
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    db_url = None
    new_pwd = None

    if len(args) >= 2:
        db_url = args[0]
        new_pwd = args[1]
    elif len(args) == 1:
        if "postgres" in args[0]:
            db_url = args[0]
        else:
            new_pwd = args[0]

    if not db_url:
        db_url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL

    if not new_pwd:
        new_pwd = DEFAULT_PASSWORD

    db_url = normalize_db_url(db_url)
    new_pwd = new_pwd.strip()

    print(f"Connecting to database...")
    try:
        conn = await asyncpg.connect(db_url, statement_cache_size=0)
    except Exception as exc:
        sys.exit(f"Connection failed: {exc}")

    try:
        # Check what columns exist in table 'role'
        col_rows = await conn.fetch("SELECT column_name FROM information_schema.columns WHERE table_name = 'role'")
        cols = {r["column_name"].lower() for r in col_rows}
        print(f"Detected 'role' table columns: {sorted(cols)}")

        user_col = "username" if "username" in cols else "userName"
        rows = await conn.fetch(f"SELECT * FROM role")

        if not rows:
            print("No accounts found in role table.")
            return 0

        hashed = passwords.hash_password(new_pwd)

        has_account_type = "account_type" in cols
        has_must_change = "must_change_password" in cols
        has_pw_changed = "password_changed_at" in cols
        has_is_active = "is_active" in cols

        # Check existing tables
        table_rows = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = {r["table_name"].lower() for r in table_rows}

        async with conn.transaction():
            for r in rows:
                u = r[user_col]
                # Dynamically update the available columns
                updates = ["password = $1"]
                params = [hashed, u]

                if has_must_change:
                    updates.append("must_change_password = FALSE")
                if has_pw_changed:
                    updates.append("password_changed_at = NOW()")
                if has_is_active:
                    updates.append("is_active = TRUE")

                set_clause = ", ".join(updates)
                await conn.execute(f"UPDATE role SET {set_clause} WHERE {user_col} = $2", *params)

                if "audit_logs" in tables:
                    await conn.execute(
                        """
                        INSERT INTO audit_logs (username, action, entity_type, entity_id, details)
                        VALUES ('operator', 'RESET_PASSWORD', 'ACCOUNT', $1, 'Password reset via quick_reset.py')
                        """,
                        u,
                    )
                if "sessions" in tables:
                    await conn.execute(f"DELETE FROM sessions WHERE username = $1", u)
                if "login_throttle" in tables:
                    await conn.execute(f"DELETE FROM login_throttle WHERE username = lower($1)", u)

        print("\n==================================================")
        print(" SUCCESS: ALL ACCOUNTS RESET")
        print("==================================================")
        print(f"Password for all accounts set to: {new_pwd}")
        print("\nFound and updated accounts:")
        for r in rows:
            role_val = r.get("account_type") or r.get("role") or "unknown"
            display = r.get("display_name") or ""
            print(f"  - Username: '{r[user_col]}' | Role: {role_val} | Display: '{display}'")
        print("==================================================\n")
        return 0

    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
