import asyncio
import asyncpg
from config import DATABASE_URI

async def check_triggers():
    conn = await asyncpg.connect(DATABASE_URI)
    triggers = await conn.fetch("""
        SELECT event_object_table, trigger_name, event_manipulation, action_statement
        FROM information_schema.triggers
    """)
    print(f"Found {len(triggers)} triggers")
    for t in triggers:
        print(dict(t))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_triggers())
