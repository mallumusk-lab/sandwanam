"""Set a new password for an existing account (operator use).

    py scripts/set_password.py <username>             temporary: must be changed at next sign-in
    py scripts/set_password.py <username> --permanent  the user keeps this password
    py scripts/set_password.py <username> --activate   also re-activate a deactivated account

Signs the account out everywhere, clears its login throttling and records an audit entry.
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
    parser.add_argument("--permanent", action="store_true")
    parser.add_argument("--activate", action="store_true", help="re-activate the account if it was deactivated")
    args = parser.parse_args()

    url = database_url()
    _, database = describe(url)
    conn = await connect(url)
    try:
        row = await conn.fetchrow("SELECT username, is_active FROM role WHERE lower(username) = lower($1)", args.username)
        if not row:
            sys.exit(f"No account named {args.username}.")
        username = row["username"]
        if not row["is_active"] and not args.activate:
            print(f"Note: {username} is deactivated and stays so. Add --activate to re-activate it.")
        first = getpass.getpass(f"New password for {username}: ")
        if first != getpass.getpass("Repeat it: "):
            sys.exit("The passwords do not match.")
        try:
            validation.password(first, username)
        except validation.ValidationError as exc:
            sys.exit(exc.message)
        confirm(database, f"set the password of {username}")
        async with conn.transaction():
            await conn.execute(
                """
                UPDATE role SET password = $1, must_change_password = $2, password_changed_at = NOW(),
                                is_active = is_active OR $4
                WHERE username = $3
                """,
                passwords.hash_password(first),
                not args.permanent,
                username,
                args.activate,
            )
            await conn.execute(
                """
                INSERT INTO audit_logs (username, action, entity_type, entity_id, details)
                VALUES ('operator', 'RESET_PASSWORD', 'ACCOUNT', $1, $2)
                """,
                username,
                "Password set with scripts/set_password.py" + (" (account activated)" if args.activate else ""),
            )
            await conn.execute("DELETE FROM sessions WHERE username = $1", username)
            await conn.execute("DELETE FROM login_throttle WHERE username = lower($1)", username)
        print(f"Password set for {username}." + ("" if args.permanent else " It must be changed at next sign-in."))
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
