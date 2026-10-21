"""Create a SuperAdmin account (there are no default accounts).

    py scripts/create_superadmin.py <username> "<display name>"
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from _common import confirm, connect, database_url, describe

from app.domain import validation
from app.security import passwords


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("username")
    parser.add_argument("display_name")
    args = parser.parse_args()
    try:
        username = validation.username(args.username)
        display_name = validation.person_name(args.display_name, "display_name")
    except validation.ValidationError as exc:
        sys.exit(exc.message)

    url = database_url()
    _, database = describe(url)
    conn = await connect(url)
    try:
        if await conn.fetchval("SELECT 1 FROM role WHERE lower(username) = lower($1)", username):
            sys.exit(f"An account named {username} already exists. Use set_password.py to change its password.")
        first = getpass.getpass(f"Password for {username}: ")
        if first != getpass.getpass("Repeat it: "):
            sys.exit("The passwords do not match.")
        try:
            validation.password(first, username)
        except validation.ValidationError as exc:
            sys.exit(exc.message)
        confirm(database, f"create SuperAdmin {username}")
        await conn.execute(
            """
            INSERT INTO role (username, password, role, display_name, account_type, permissions,
                              is_active, must_change_password, password_changed_at)
            VALUES ($1, $2, 'SuperAdmin', $3, 'superadmin', '', TRUE, FALSE, NOW())
            """,
            username,
            passwords.hash_password(first),
            display_name,
        )
        print(f"SuperAdmin {username} created.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
