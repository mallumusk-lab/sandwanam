import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch("SELECT * FROM statement WHERE loan_number = 'SAN2L3'")
    print(f"Total statements for loan SAN2L3: {len(rows)}")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
