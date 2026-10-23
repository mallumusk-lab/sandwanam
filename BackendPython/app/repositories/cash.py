"""Branch cash ledger: cash_days and cash_entries (migration 005). Nothing here touches loans."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from . import Db

DAY_FIELDS = (
    "d.id, d.branch_prefix, d.day, d.carried_forward, d.opening_counted, d.opened_by, d.opened_at, "
    "d.client_request_id, d.closing_expected, d.closing_counted, d.closed_by, d.closed_at, d.closed_automatically"
)
ENTRY_FIELDS = (
    "e.id, e.day_id, e.direction, e.category, e.description, e.reference, e.amount, e.client_request_id, "
    "e.created_by, e.created_at, e.voided_at, e.voided_by, e.void_reason"
)


class CashRepo:
    def __init__(self, db: Db):
        self.db = db

    async def latest_day(self, branch: str, before: date | None = None) -> dict | None:
        """The branch's newest day, or its newest day before `before`."""
        return await self.db.fetchrow(
            f"""
            SELECT {DAY_FIELDS} FROM cash_days d
            WHERE d.branch_prefix = $1 AND ($2::date IS NULL OR d.day < $2)
            ORDER BY d.day DESC LIMIT 1
            """,
            branch, before,
        )

    async def day_for_update(self, day_id: int) -> dict | None:
        """Row lock serialising every write to this day and its entries."""
        return await self.db.fetchrow(
            f"""
            SELECT {DAY_FIELDS} FROM cash_days d WHERE d.id = $1 FOR UPDATE
            """,
            day_id,
        )

    async def days_since(self, branch: str, since: date) -> list[dict]:
        """The branch's days on or after `since`, newest first."""
        return await self.db.fetch(
            f"""
            SELECT {DAY_FIELDS} FROM cash_days d
            WHERE d.branch_prefix = $1 AND d.day >= $2
            ORDER BY d.day DESC
            """,
            branch, since,
        )

    async def entries_for_days(self, day_ids: list[int]) -> list[dict]:
        """Entries of these days, oldest first."""
        if not day_ids:
            return []
        return await self.db.fetch(
            f"""
            SELECT {ENTRY_FIELDS} FROM cash_entries e
            WHERE e.day_id = ANY($1::int[])
            ORDER BY e.created_at, e.id
            """,
            list(day_ids),
        )

    async def entry(self, entry_id: int) -> dict | None:
        return await self.db.fetchrow(
            f"""
            SELECT {ENTRY_FIELDS}, d.branch_prefix FROM cash_entries e JOIN cash_days d ON d.id = e.day_id
            WHERE e.id = $1
            """,
            entry_id,
        )

    async def entry_by_request_id(self, request_id: str) -> dict | None:
        return await self.db.fetchrow(
            "SELECT id, day_id FROM cash_entries WHERE client_request_id = $1", request_id
        )

    async def create_day(self, *, branch: str, day: date, carried_forward: Decimal, opening_counted: Decimal,
                         opened_by: str, opened_at: datetime, request_id: str | None) -> int | None:
        """The new day's id, or None when the branch already has this day."""
        return await self.db.fetchval(
            """
            INSERT INTO cash_days (branch_prefix, day, carried_forward, opening_counted, opened_by, opened_at,
                                   client_request_id)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (branch_prefix, day) DO NOTHING
            RETURNING id
            """,
            branch, day, carried_forward, opening_counted, opened_by, opened_at, request_id,
        )

    async def add_entry(self, *, day_id: int, direction: str, category: str, description: str | None,
                        reference: str | None, amount: Decimal, request_id: str, created_by: str,
                        created_at: datetime) -> int | None:
        """The new entry's id, or None when the request id was already used (idempotency)."""
        return await self.db.fetchval(
            """
            INSERT INTO cash_entries (day_id, direction, category, description, reference, amount,
                                      client_request_id, created_by, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (client_request_id) DO NOTHING
            RETURNING id
            """,
            day_id, direction, category, description, reference, amount, request_id, created_by, created_at,
        )

    async def void_entry(self, entry_id: int, *, voided_by: str, reason: str, at: datetime) -> bool:
        """False when the entry was already voided."""
        voided = await self.db.fetchval(
            """
            UPDATE cash_entries SET voided_at = $2, voided_by = $3, void_reason = $4
            WHERE id = $1 AND voided_at IS NULL
            RETURNING id
            """,
            entry_id, at, voided_by, reason,
        )
        return voided is not None

    async def close_day(self, day_id: int, *, expected: Decimal, counted: Decimal, closed_by: str, at: datetime,
                        automatically: bool) -> None:
        await self.db.execute(
            """
            UPDATE cash_days SET closing_expected = $2, closing_counted = $3, closed_by = $4, closed_at = $5,
                                 closed_automatically = $6
            WHERE id = $1 AND closed_at IS NULL
            """,
            day_id, expected, counted, closed_by, at, automatically,
        )

    async def reopen_day(self, day_id: int) -> None:
        await self.db.execute(
            """
            UPDATE cash_days SET closing_expected = NULL, closing_counted = NULL, closed_by = NULL, closed_at = NULL,
                                 closed_automatically = FALSE
            WHERE id = $1
            """,
            day_id,
        )

    async def open_days_before(self, today: date, branch: str | None = None) -> list[dict]:
        """Days left open before `today` (every branch when `branch` is None), oldest first."""
        return await self.db.fetch(
            f"""
            SELECT {DAY_FIELDS} FROM cash_days d
            WHERE d.closed_at IS NULL AND d.day < $1 AND ($2::text IS NULL OR d.branch_prefix = $2)
            ORDER BY d.day, d.id
            """,
            today, branch,
        )

    async def purge(self, cutoff: date) -> int:
        """Delete days before `cutoff` (their entries go with them), always keeping each
        branch's latest day so the carry forward survives. Returns the days deleted."""
        return await self.db.fetchval(
            """
            WITH gone AS (
                DELETE FROM cash_days d
                WHERE d.day < $1
                  AND d.day < (SELECT MAX(l.day) FROM cash_days l WHERE l.branch_prefix = d.branch_prefix)
                RETURNING d.id
            )
            SELECT COUNT(*) FROM gone
            """,
            cutoff,
        )

    async def recent_custom_descriptions(self, branch: str, since: date, limit: int) -> list[str]:
        """Descriptions typed for 'Other' entries since `since`, most used first."""
        rows = await self.db.fetch(
            """
            SELECT e.description FROM cash_entries e JOIN cash_days d ON d.id = e.day_id
            WHERE d.branch_prefix = $1 AND d.day >= $2 AND e.category = 'other'
              AND e.description IS NOT NULL AND e.voided_at IS NULL
            GROUP BY e.description
            ORDER BY COUNT(*) DESC, MAX(e.created_at) DESC, e.description
            LIMIT $3
            """,
            branch, since, limit,
        )
        return [row["description"] for row in rows]
