import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch('SELECT * FROM statement WHERE loan_number = $1', 'SAN2L6')
    print(f"Found {len(rows)} statement entries for SAN2L6")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
