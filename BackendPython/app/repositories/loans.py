from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from . import Db

LOAN_FIELDS = (
    "l.loanid, l.customerid, l.loan_number, l.particulars, l.items, l.number_of_items, l.weight, l.net_weight, "
    "l.deduction, l.principle_amount, l.interest, l.tenure, l.date, l.loantype, l.refreshprincipleamount, "
    "l.refreshinterest, l.follow_up_date, l.closed_at, l.created_by"
)
CUSTOMER_FIELDS = "c.branch_prefix, c.customername, c.phone, c.user_id, c.address"

# Totals over a loan's whole ledger. The peak principal and the interest collected only
# matter while the loan is still in its first 7 days, when every entry lies in those days
# (app/domain/ledger.py, first-week rule).
LEDGER_TOTALS = (
    "COUNT(*) FILTER (WHERE s.transactiontype = 'compounding') AS compoundings, "
    "MAX(s.principlebalance) AS peak_principal, "
    "COALESCE(SUM(s.currentinterest) FILTER (WHERE s.transactiontype = 'addColl'), 0) AS interest_collected"
)

# Latest ledger position, ledger totals and last collection, per loan.
POSITION_JOINS = f"""
LEFT JOIN LATERAL (
    SELECT s.date AS last_entry_at, s.principlebalance AS last_principal, s.interestbalance AS last_interest
    FROM statement s WHERE s.loan_number = l.loan_number
    ORDER BY s.date DESC, s.statementid DESC LIMIT 1
) ls ON TRUE
LEFT JOIN LATERAL (
    SELECT {LEDGER_TOTALS} FROM statement s WHERE s.loan_number = l.loan_number
) cc ON TRUE
LEFT JOIN LATERAL (
    SELECT MAX(s.date) AS last_payment_at FROM statement s
    WHERE s.loan_number = l.loan_number AND s.transactiontype = 'addColl' AND s.amountpaid > 0
) lp ON TRUE
"""
POSITION_FIELDS = (
    "ls.last_entry_at, ls.last_principal, ls.last_interest, cc.compoundings, cc.peak_principal, "
    "cc.interest_collected, lp.last_payment_at"
)


class LoansRepo:
    def __init__(self, db: Db):
        self.db = db

    async def get(self, loan_number: str) -> dict | None:
        return await self.db.fetchrow(
            f"""
            SELECT {LOAN_FIELDS}, {CUSTOMER_FIELDS}, {POSITION_FIELDS}
            FROM loan_data l LEFT JOIN customers c ON c.customerid = l.customerid
            {POSITION_JOINS}
            WHERE l.loan_number = $1
            """,
            loan_number,
        )

    async def lock(self, loan_number: str) -> dict | None:
        """Row lock serialising every ledger write for this loan."""
        return await self.db.fetchrow(
            f"""
            SELECT {LOAN_FIELDS}, {CUSTOMER_FIELDS}
            FROM loan_data l LEFT JOIN customers c ON c.customerid = l.customerid
            WHERE l.loan_number = $1
            FOR UPDATE OF l
            """,
            loan_number,
        )

    async def exists(self, loan_number: str) -> bool:
        return bool(await self.db.fetchval("SELECT 1 FROM loan_data WHERE upper(loan_number) = upper($1)", loan_number))

    async def for_customer(self, customer_id: int) -> list[dict]:
        return await self.db.fetch(
            f"""
            SELECT {LOAN_FIELDS}, {CUSTOMER_FIELDS}, {POSITION_FIELDS}
            FROM loan_data l JOIN customers c ON c.customerid = l.customerid
            {POSITION_JOINS}
            WHERE l.customerid = $1
            ORDER BY (l.loantype = 'open') DESC, l.date DESC
            """,
            customer_id,
        )

    async def open_with_position(self, branch: str | None) -> list[dict]:
        return await self.db.fetch(
            f"""
            SELECT {LOAN_FIELDS}, {CUSTOMER_FIELDS}, {POSITION_FIELDS}
            FROM loan_data l JOIN customers c ON c.customerid = l.customerid
            {POSITION_JOINS}
            WHERE l.loantype = 'open' AND ($1::text IS NULL OR c.branch_prefix = $1)
            ORDER BY l.date
            """,
            branch,
        )

    async def insert(
        self,
        *,
        customer_id: int,
        loan_number: str,
        items_json: str,
        particulars: str,
        number_of_items: int,
        weight: Decimal,
        deduction: Decimal,
        net_weight: Decimal,
        principal: Decimal,
        rate: Decimal,
        tenure: int,
        branch: str,
        loan_date: datetime,
        created_by: str,
    ) -> dict:
        return await self.db.fetchrow(
            """
            INSERT INTO loan_data (customerid, loan_number, items, particulars, number_of_items, weight, deduction,
                                   net_weight, principle_amount, interest, tenure, role, date, loantype, loanstatus,
                                   refreshprincipleamount, refreshinterest, created_by)
            VALUES ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 'open', '1', $9, 0, $14)
            RETURNING loanid, loan_number
            """,
            customer_id, loan_number, items_json, particulars, str(number_of_items), weight, deduction, net_weight,
            principal, rate, tenure, branch, loan_date, created_by,
        )

    async def set_items(self, loan_number: str, items_json: str, particulars: str, number_of_items: int) -> None:
        await self.db.execute(
            "UPDATE loan_data SET items = $2::jsonb, particulars = $3, number_of_items = $4 WHERE loan_number = $1",
            loan_number, items_json, particulars, str(number_of_items),
        )

    async def update_cache(self, loan_number: str, principal: Decimal, interest: Decimal) -> None:
        await self.db.execute(
            "UPDATE loan_data SET refreshprincipleamount = $2, refreshinterest = $3 WHERE loan_number = $1",
            loan_number, principal, interest,
        )

    async def mark_closed(self, loan_number: str, closed_at: datetime) -> None:
        await self.db.execute(
            """
            UPDATE loan_data SET loantype = 'closed', closed_at = $2, refreshprincipleamount = 0, refreshinterest = 0,
                                 follow_up_date = NULL
            WHERE loan_number = $1
            """,
            loan_number, closed_at,
        )

    async def set_follow_up(self, loan_number: str, follow_up) -> None:
        await self.db.execute("UPDATE loan_data SET follow_up_date = $2 WHERE loan_number = $1", loan_number, follow_up)


STATEMENT_FIELDS = (
    "statementid, loanid, loan_number, transactiontype, date, amountpaid, currentprincipal, currentinterest, "
    "principlebalance, interestbalance, accrued_days, writeoff_principal, writeoff_interest, created_by, created_at"
)


class StatementsRepo:
    def __init__(self, db: Db):
        self.db = db

    async def latest(self, loan_number: str) -> dict | None:
        return await self.db.fetchrow(
            f"SELECT {STATEMENT_FIELDS} FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC LIMIT 1",
            loan_number,
        )

    async def totals(self, loan_number: str) -> dict:
        """Compoundings, peak principal and interest collected (see LEDGER_TOTALS)."""
        return await self.db.fetchrow(
            f"SELECT {LEDGER_TOTALS} FROM statement s WHERE s.loan_number = $1", loan_number
        )

    async def by_request_id(self, request_id: str) -> dict | None:
        return await self.db.fetchrow(
            "SELECT statementid, loan_number FROM statement WHERE client_request_id = $1", request_id
        )

    async def insert(
        self,
        *,
        loan_id: int,
        loan_number: str,
        kind: str,
        at: datetime,
        amount_paid: Decimal,
        current_principal: Decimal,
        current_interest: Decimal,
        principal_balance: Decimal,
        interest_balance: Decimal,
        accrued_days: int,
        writeoff_principal: Decimal | None,
        writeoff_interest: Decimal | None,
        created_by: str,
        request_id: str | None,
    ) -> int:
        return await self.db.fetchval(
            """
            INSERT INTO statement (loanid, loan_number, transactiontype, date, amountpaid, currentprincipal,
                                   currentinterest, principlebalance, interestbalance, accrued_days,
                                   writeoff_principal, writeoff_interest, created_by, client_request_id, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW())
            RETURNING statementid
            """,
            loan_id, loan_number, kind, at, amount_paid, current_principal, current_interest, principal_balance,
            interest_balance, accrued_days, writeoff_principal, writeoff_interest, created_by, request_id,
        )

    async def for_loan(self, loan_number: str) -> list[dict]:
        return await self.db.fetch(
            f"SELECT {STATEMENT_FIELDS} FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC",
            loan_number,
        )

    async def get(self, statement_id: int) -> dict | None:
        return await self.db.fetchrow(f"SELECT {STATEMENT_FIELDS} FROM statement WHERE statementid = $1", statement_id)
