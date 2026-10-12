import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("--- Statements Sample ---")
    rows = await conn.fetch("SELECT * FROM statement LIMIT 5")
    for r in rows:
        print(dict(r))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
