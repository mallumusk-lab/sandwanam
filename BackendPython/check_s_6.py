import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch("SELECT * FROM statement WHERE loanid = 6")
    print(f"Total statements for loanid 6: {len(rows)}")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
