import asyncio
import asyncpg
from config import DATABASE_URI

async def check_roles():
    conn = await asyncpg.connect(DATABASE_URI)
    rows = await conn.fetch("SELECT * FROM role")
    print("ROLE TABLE CONTENTS:")
    for row in rows:
        print(dict(row))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_roles())
