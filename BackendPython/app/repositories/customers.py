from __future__ import annotations

from . import Db, like_pattern

CUSTOMER_COLUMNS = "customerid, customername, phone, address, user_id, branch_prefix, loanstatus, created_at"


class CustomersRepo:
    def __init__(self, db: Db):
        self.db = db

    async def search(self, branch: str | None, term: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
        rows = await self.db.fetch(
            f"""
            SELECT {", ".join("c." + c.strip() for c in CUSTOMER_COLUMNS.split(","))},
                   (SELECT COUNT(*) FROM loan_data l WHERE l.customerid = c.customerid AND l.loantype = 'open') AS open_loans,
                   COUNT(*) OVER () AS total
            FROM customers c
            WHERE ($1::text IS NULL OR c.branch_prefix = $1)
              AND ($2::text IS NULL OR c.customername ILIKE $2 OR c.phone LIKE $2 OR upper(c.user_id) LIKE upper($2))
            ORDER BY c.customerid DESC
            LIMIT $3 OFFSET $4
            """,
            branch, like_pattern(term) if term else None, limit, offset,
        )
        total = rows[0]["total"] if rows else 0
        for row in rows:
            row.pop("total", None)
        return rows, total

    async def get(self, customer_id: int) -> dict | None:
        return await self.db.fetchrow(f"SELECT {CUSTOMER_COLUMNS} FROM customers WHERE customerid = $1", customer_id)

    async def by_phone(self, phone: str) -> dict | None:
        return await self.db.fetchrow(f"SELECT {CUSTOMER_COLUMNS} FROM customers WHERE phone = $1", phone)

    async def lock(self, customer_id: int) -> dict | None:
        return await self.db.fetchrow(
            f"SELECT {CUSTOMER_COLUMNS}, last_loan_no FROM customers WHERE customerid = $1 FOR UPDATE", customer_id
        )

    async def next_customer_number(self, branch: str) -> int | None:
        return await self.db.fetchval(
            """
            UPDATE branch_counters SET next_customer_no = next_customer_no + 1
            WHERE branch_prefix = $1
            RETURNING next_customer_no - 1
            """,
            branch,
        )

    async def user_id_taken(self, user_id: str) -> bool:
        return bool(await self.db.fetchval("SELECT 1 FROM customers WHERE upper(user_id) = upper($1)", user_id))

    async def insert(self, *, name: str, phone: str, address: str, user_id: str, branch: str) -> dict:
        return await self.db.fetchrow(
            f"""
            INSERT INTO customers (customername, phone, address, loanstatus, role, user_id, branch_prefix)
            VALUES ($1, $2, $3, '0', $4, $5, $4)
            RETURNING {CUSTOMER_COLUMNS}
            """,
            name, phone, address, branch, user_id,
        )

    async def next_loan_number(self, customer_id: int) -> int:
        return await self.db.fetchval(
            "UPDATE customers SET last_loan_no = last_loan_no + 1 WHERE customerid = $1 RETURNING last_loan_no",
            customer_id,
        )

    async def refresh_loan_status(self, customer_id: int) -> None:
        await self.db.execute(
            """
            UPDATE customers SET loanstatus = CASE WHEN EXISTS (
                SELECT 1 FROM loan_data l WHERE l.customerid = $1 AND l.loantype = 'open'
            ) THEN '1' ELSE '0' END
            WHERE customerid = $1
            """,
            customer_id,
        )
