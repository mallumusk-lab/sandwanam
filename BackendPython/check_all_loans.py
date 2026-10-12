import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch("SELECT loanid, loan_number, length(loan_number) as len FROM loan_data")
    print(f"Total loan_data entries: {len(rows)}")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
