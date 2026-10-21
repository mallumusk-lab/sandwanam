"""Data access. The only modules that contain SQL.

Repositories receive a connection object with the asyncpg API (fetch, fetchrow, fetchval,
execute, executemany, transaction). They never import asyncpg, so tests can pass a fake.
Every statement goes through `Db`, which checks that `$n` placeholders match the
arguments before anything reaches the database.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_PLACEHOLDER = re.compile(r"\$(\d+)")


class QueryArgumentError(AssertionError):
    pass


def check_arguments(sql: str, args: tuple) -> None:
    used = {int(n) for n in _PLACEHOLDER.findall(sql)}
    highest = max(used, default=0)
    if used != set(range(1, highest + 1)) or highest != len(args):
        raise QueryArgumentError(f"Query expects {highest} argument(s) but received {len(args)}.")


def like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class Db:
    def __init__(self, conn: Any):
        self.conn = conn

    async def fetch(self, sql: str, *args: Any) -> list[dict]:
        check_arguments(sql, args)
        return [dict(row) for row in await self.conn.fetch(sql, *args)]

    async def fetchrow(self, sql: str, *args: Any) -> dict | None:
        check_arguments(sql, args)
        row = await self.conn.fetchrow(sql, *args)
        return dict(row) if row is not None else None

    async def fetchval(self, sql: str, *args: Any) -> Any:
        check_arguments(sql, args)
        return await self.conn.fetchval(sql, *args)

    async def execute(self, sql: str, *args: Any) -> str:
        check_arguments(sql, args)
        return await self.conn.execute(sql, *args)

    async def executemany(self, sql: str, rows: Iterable[tuple]) -> None:
        rows = list(rows)
        for row in rows:
            check_arguments(sql, tuple(row))
        if rows:
            await self.conn.executemany(sql, rows)

    def transaction(self):
        return self.conn.transaction()


class Repos:
    """All repositories bound to one connection."""

    def __init__(self, conn: Any):
        from .admin import AuditRepo, BackupsRepo, SettingsRepo
        from .customers import CustomersRepo
        from .loans import LoansRepo, StatementsRepo
        from .reports import ReportsRepo
        from .users import SessionsRepo, ThrottleRepo, UsersRepo

        self.db = Db(conn)
        self.users = UsersRepo(self.db)
        self.sessions = SessionsRepo(self.db)
        self.throttle = ThrottleRepo(self.db)
        self.customers = CustomersRepo(self.db)
        self.loans = LoansRepo(self.db)
        self.statements = StatementsRepo(self.db)
        self.reports = ReportsRepo(self.db)
        self.audit = AuditRepo(self.db)
        self.settings = SettingsRepo(self.db)
        self.backups = BackupsRepo(self.db)

    def transaction(self):
        return self.db.transaction()
