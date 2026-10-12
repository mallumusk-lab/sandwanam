import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch('SELECT * FROM customers')
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
