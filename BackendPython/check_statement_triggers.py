import asyncio
import asyncpg
from config import DATABASE_URI

async def check_triggers_all():
    conn = await asyncpg.connect(DATABASE_URI)
    triggers = await conn.fetch("""
        SELECT tgname, tgenabled, tgtype
        FROM pg_trigger
        JOIN pg_class ON pg_class.oid = pg_trigger.tgrelid
        WHERE pg_class.relname = 'statement'
    """)
    print(f"Found {len(triggers)} triggers for table 'statement'")
    for t in triggers:
        print(dict(t))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_triggers_all())
