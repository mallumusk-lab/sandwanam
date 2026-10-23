"""Reset passwords for all existing accounts (operator use).

    py scripts/reset_all_passwords.py                        interactive prompt for password
    py scripts/reset_all_passwords.py --random               generate unique passwords for each account
    py scripts/reset_all_passwords.py --password <secret>    set specific password for all accounts
    py scripts/reset_all_passwords.py --permanent            keep passwords (no forced change on login)
    py scripts/reset_all_passwords.py --activate             also activate deactivated accounts
    py scripts/reset_all_passwords.py --yes                  skip database confirmation prompt

Signs all accounts out everywhere, clears login throttling, and records audit logs.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import secrets
import string
import sys

from _common import confirm, connect, database_url, describe

from app.domain import validation
from app.security import passwords


def generate_secure_password(username: str) -> str:
    """Generate a random 14-character password satisfying validation rules."""
    alphabet = string.ascii_letters + string.digits + "!@#$%&*="
    for _ in range(1000):
        # Ensure at least 2 lowercase, 2 uppercase, 2 digits, 2 symbols
        sample = (
            secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.ascii_lowercase)
            + secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.ascii_uppercase)
            + secrets.choice(string.digits)
            + secrets.choice(string.digits)
            + secrets.choice("!@#$%&*=")
            + secrets.choice("!@#$%&*=")
            + "".join(secrets.choice(alphabet) for _ in range(6))
        )
        # Shuffle
        pwd = "".join(secrets.SystemRandom().sample(sample, len(sample)))
        try:
            validation.password(pwd, username)
            return pwd
        except validation.ValidationError:
            continue
    raise RuntimeError("Unable to generate a compliant password.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--password", help="set this password for all accounts")
    parser.add_argument("--random", action="store_true", help="generate a unique password for each account")
    parser.add_argument("--permanent", action="store_true", help="do not force password change on next sign-in")
    parser.add_argument("--activate", action="store_true", help="also re-activate any deactivated accounts")
    parser.add_argument("--yes", action="store_true", help="skip the database confirmation prompt")
    args = parser.parse_args()

    if args.password and args.random:
        sys.exit("Cannot use both --password and --random together.")

    url = database_url()
    _, database = describe(url)
    conn = await connect(url)
    try:
        rows = await conn.fetch(
            """
            SELECT username, account_type, branch_prefix, is_active
            FROM role
            ORDER BY CASE account_type WHEN 'superadmin' THEN 0 WHEN 'hq' THEN 1 ELSE 2 END, username
            """
        )
        if not rows:
            print("No accounts found in the database.")
            return 0

        print(f"\nFound {len(rows)} account(s):")
        for r in rows:
            status = "active" if r["is_active"] else "deactivated"
            branch = f" ({r['branch_prefix']})" if r["branch_prefix"] else ""
            print(f"  - {r['username']} [{r['account_type']}{branch}] - {status}")

        passwords_to_set: dict[str, str] = {}

        if args.random:
            for r in rows:
                u = r["username"]
                passwords_to_set[u] = generate_secure_password(u)
        elif args.password:
            common_pwd = args.password
            for r in rows:
                u = r["username"]
                try:
                    validation.password(common_pwd, u)
                except validation.ValidationError as exc:
                    sys.exit(f"Password rejected for user '{u}': {exc.message}")
                passwords_to_set[u] = common_pwd
        else:
            first = getpass.getpass("\nEnter new password for ALL accounts: ")
            if first != getpass.getpass("Repeat it: "):
                sys.exit("The passwords do not match.")
            for r in rows:
                u = r["username"]
                try:
                    validation.password(first, u)
                except validation.ValidationError as exc:
                    sys.exit(f"Password rejected for user '{u}': {exc.message}")
                passwords_to_set[u] = first

        confirm(database, f"reset passwords for all {len(rows)} account(s)", args.yes)

        async with conn.transaction():
            for r in rows:
                u = r["username"]
                pwd = passwords_to_set[u]
                hashed = passwords.hash_password(pwd)
                await conn.execute(
                    """
                    UPDATE role
                    SET password = $1, must_change_password = $2, password_changed_at = NOW(),
                        is_active = is_active OR $4
                    WHERE username = $3
                    """,
                    hashed,
                    not args.permanent,
                    u,
                    args.activate,
                )
                await conn.execute(
                    """
                    INSERT INTO audit_logs (username, action, entity_type, entity_id, details)
                    VALUES ('operator', 'RESET_PASSWORD', 'ACCOUNT', $1, $2)
                    """,
                    u,
                    "Password reset by reset_all_passwords.py" + (" (account activated)" if args.activate else ""),
                )
                await conn.execute("DELETE FROM sessions WHERE username = $1", u)
                await conn.execute("DELETE FROM login_throttle WHERE username = lower($1)", u)

        print("\nSuccessfully reset passwords for all accounts:")
        print(f"{'Username':<20} {'Account Type':<15} {'New Password':<22} {'Must Change'}")
        print("-" * 72)
        for r in rows:
            u = r["username"]
            pwd = passwords_to_set[u]
            must_change = "No" if args.permanent else "Yes (at login)"
            print(f"{u:<20} {r['account_type']:<15} {pwd:<22} {must_change}")

        print("\nAll sessions terminated and login throttling cleared.")
        if not args.permanent:
            print("Note: Users will be required to choose a new password upon first login.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
