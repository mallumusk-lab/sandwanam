"""Reporting queries. Metric definitions are documented in app/domain/reports.py.

All period queries take the same parameters: $1 branch (NULL = all), $2/$3 the
half-open UTC range of the IST business days, so they use the date indexes.
"""
from __future__ import annotations

from datetime import datetime

from . import Db, like_pattern

_SCOPED_LOANS = """
scoped_loans AS (
    SELECT l.*, c.customername, c.phone, c.branch_prefix
    FROM loan_data l JOIN customers c ON c.customerid = l.customerid
    WHERE ($1::text IS NULL OR c.branch_prefix = $1)
)"""
_ENTRIES = """
entries AS (
    SELECT s.*, l.customername, l.phone, l.branch_prefix
    FROM statement s JOIN scoped_loans l ON l.loan_number = s.loan_number
    WHERE s.date >= $2 AND s.date < $3
)"""

PERIOD_TOTALS = f"""
WITH {_SCOPED_LOANS}, {_ENTRIES}
SELECT
    (SELECT COALESCE(SUM(principle_amount), 0) FROM scoped_loans WHERE date >= $2 AND date < $3) AS new_principal,
    (SELECT COUNT(*) FROM scoped_loans WHERE date >= $2 AND date < $3) AS new_loans,
    (SELECT COUNT(*) FROM customers WHERE ($1::text IS NULL OR branch_prefix = $1) AND created_at >= $2 AND created_at < $3) AS new_customers,
    (SELECT COALESCE(SUM(CASE transactiontype WHEN 'disbursement' THEN currentprincipal
                                              WHEN 'modify' THEN amountpaid END), 0)
       FROM entries WHERE transactiontype IN ('disbursement', 'modify')) AS top_ups,
    (SELECT COALESCE(SUM(currentinterest), 0) FROM entries WHERE transactiontype = 'addColl') AS interest_collected,
    (SELECT COALESCE(SUM(-currentprincipal), 0) FROM entries
       WHERE transactiontype = 'addColl' AND currentprincipal < 0) AS principal_collected,
    (SELECT COALESCE(SUM(amountpaid), 0) FROM entries WHERE transactiontype = 'addColl') AS total_collected,
    (SELECT COUNT(*) FROM entries WHERE transactiontype = 'addColl' AND amountpaid > 0) AS collections,
    (SELECT COALESCE(SUM(currentprincipal), 0) FROM entries WHERE transactiontype = 'compounding') AS compounded,
    (SELECT COUNT(DISTINCT loan_number) FROM entries WHERE transactiontype = 'compounding') AS compounded_loans,
    (SELECT COALESCE(SUM(COALESCE(writeoff_principal + writeoff_interest, principlebalance)), 0)
       FROM entries WHERE transactiontype = 'writeoff') AS written_off,
    (SELECT COUNT(*) FROM scoped_loans WHERE closed_at >= $2 AND closed_at < $3) AS closures,
    (SELECT COALESCE(SUM(net_weight), 0) FROM scoped_loans WHERE date >= $2 AND date < $3) AS gold_pledged,
    (SELECT COALESCE(SUM(net_weight), 0) FROM scoped_loans WHERE closed_at >= $2 AND closed_at < $3) AS gold_released
"""

_DETAIL_ENTRY_COLUMNS = (
    "loan_number, customername, phone, branch_prefix, date, transactiontype, amountpaid, "
    "currentprincipal, currentinterest, principlebalance, writeoff_principal, writeoff_interest"
)
_DETAIL_LOAN_COLUMNS = (
    "loan_number, customername, phone, branch_prefix, date, closed_at, principle_amount, interest, net_weight, loantype"
)
DETAILS = {
    "disbursed": f"""
        WITH {_SCOPED_LOANS}, {_ENTRIES}
        SELECT loan_number, customername, phone, branch_prefix, date, 'New loan' AS kind, principle_amount AS amount
        FROM scoped_loans WHERE date >= $2 AND date < $3
        UNION ALL
        SELECT loan_number, customername, phone, branch_prefix, date, 'Top-up' AS kind,
               CASE transactiontype WHEN 'disbursement' THEN currentprincipal ELSE amountpaid END AS amount
        FROM entries WHERE transactiontype IN ('disbursement', 'modify')
        ORDER BY date DESC LIMIT $4""",
    "new_loans": f"""
        WITH {_SCOPED_LOANS}
        SELECT {_DETAIL_LOAN_COLUMNS} FROM scoped_loans
        WHERE date >= $2 AND date < $3 ORDER BY date DESC LIMIT $4""",
    "new_customers": f"""
        SELECT customerid, customername, phone, branch_prefix, user_id, created_at
        FROM customers
        WHERE ($1::text IS NULL OR branch_prefix = $1)
          AND created_at >= $2 AND created_at < $3
        ORDER BY created_at DESC LIMIT $4""",
    "collections": f"""
        WITH {_SCOPED_LOANS}, {_ENTRIES}
        SELECT {_DETAIL_ENTRY_COLUMNS} FROM entries
        WHERE transactiontype = 'addColl' AND amountpaid > 0 ORDER BY date DESC LIMIT $4""",
    "compounded": f"""
        WITH {_SCOPED_LOANS}, {_ENTRIES}
        SELECT {_DETAIL_ENTRY_COLUMNS} FROM entries
        WHERE transactiontype = 'compounding' ORDER BY date DESC LIMIT $4""",
    "written_off": f"""
        WITH {_SCOPED_LOANS}, {_ENTRIES}
        SELECT {_DETAIL_ENTRY_COLUMNS} FROM entries
        WHERE transactiontype = 'writeoff' ORDER BY date DESC LIMIT $4""",
    "closures": f"""
        WITH {_SCOPED_LOANS}
        SELECT {_DETAIL_LOAN_COLUMNS} FROM scoped_loans
        WHERE closed_at >= $2 AND closed_at < $3 ORDER BY closed_at DESC LIMIT $4""",
}
DETAILS["gold_pledged"] = DETAILS["new_loans"]
DETAILS["gold_released"] = DETAILS["closures"]
for _metric in ("interest_collected", "principal_collected", "total_collected"):
    DETAILS[_metric] = DETAILS["collections"]

TRANSACTIONS = """
SELECT s.statementid, s.loan_number, s.transactiontype, s.date, s.amountpaid, s.currentprincipal, s.currentinterest,
       s.principlebalance, s.interestbalance, s.writeoff_principal, s.writeoff_interest, s.created_at,
       l.date AS loan_date, c.customername, c.user_id, c.branch_prefix,
       COUNT(*) OVER () AS total
FROM statement s
JOIN loan_data l ON l.loan_number = s.loan_number
JOIN customers c ON c.customerid = l.customerid
WHERE ($1::text IS NULL OR c.branch_prefix = $1)
  AND s.date >= $2 AND s.date < $3
  AND ($4::text IS NULL OR c.customername ILIKE $4 OR s.loan_number ILIKE $4 OR c.user_id ILIKE $4)
  AND ($5::text IS NULL OR s.transactiontype = $5)
ORDER BY s.date DESC, s.statementid DESC
LIMIT $6 OFFSET $7
"""


class ReportsRepo:
    def __init__(self, db: Db):
        self.db = db

    async def period_totals(self, branch: str | None, lower: datetime, upper: datetime) -> dict:
        return await self.db.fetchrow(PERIOD_TOTALS, branch, lower, upper)

    async def details(self, metric: str, branch: str | None, lower: datetime, upper: datetime, limit: int) -> list[dict]:
        return await self.db.fetch(DETAILS[metric], branch, lower, upper, limit)

    async def monthly_flows(self, branch: str | None, lower: datetime, upper: datetime) -> list[dict]:
        return await self.db.fetch(
            f"""
            WITH {_SCOPED_LOANS}, {_ENTRIES},
            flows AS (
                SELECT date, principle_amount AS disbursed, 0::numeric AS collected FROM scoped_loans
                WHERE date >= $2 AND date < $3
                UNION ALL
                SELECT date,
                       CASE transactiontype WHEN 'disbursement' THEN currentprincipal
                                            WHEN 'modify' THEN amountpaid ELSE 0 END,
                       CASE WHEN transactiontype = 'addColl' THEN amountpaid ELSE 0 END
                FROM entries WHERE transactiontype IN ('disbursement', 'modify', 'addColl')
            )
            SELECT to_char(date_trunc('month', date AT TIME ZONE 'Asia/Kolkata'), 'YYYY-MM') AS month,
                   SUM(disbursed) AS disbursed, SUM(collected) AS collected
            FROM flows GROUP BY 1 ORDER BY 1
            """,
            branch, lower, upper,
        )

    async def recent(self, branch: str | None, limit: int) -> list[dict]:
        return await self.db.fetch(
            """
            SELECT s.statementid, s.loan_number, s.transactiontype, s.date, s.amountpaid, s.currentprincipal,
                   s.principlebalance, s.writeoff_principal, s.writeoff_interest,
                   c.customername, c.customerid, c.branch_prefix
            FROM statement s
            JOIN loan_data l ON l.loan_number = s.loan_number
            JOIN customers c ON c.customerid = l.customerid
            WHERE ($1::text IS NULL OR c.branch_prefix = $1)
            ORDER BY s.statementid DESC
            LIMIT $2
            """,
            branch, limit,
        )

    async def loan_counts(self, branch: str | None) -> dict:
        return await self.db.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE l.loantype = 'open') AS open_loans,
                   COUNT(*) FILTER (WHERE l.loantype = 'closed') AS closed_loans,
                   (SELECT COUNT(*) FROM customers c2 WHERE $1::text IS NULL OR c2.branch_prefix = $1) AS customers
            FROM loan_data l JOIN customers c ON c.customerid = l.customerid
            WHERE ($1::text IS NULL OR c.branch_prefix = $1)
            """,
            branch,
        )

    async def transactions(
        self,
        branch: str | None,
        lower: datetime,
        upper: datetime,
        term: str | None,
        kind: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        rows = await self.db.fetch(
            TRANSACTIONS, branch, lower, upper, like_pattern(term) if term else None, kind, limit, offset
        )
        total = rows[0]["total"] if rows else 0
        for row in rows:
            row.pop("total", None)
        return rows, total
