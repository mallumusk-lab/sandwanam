import asyncpg
import asyncio
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch('SELECT * FROM loan_data WHERE customerid = 2')
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
