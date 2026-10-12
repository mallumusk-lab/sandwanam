import asyncio
import asyncpg
from config import DATABASE_URI

async def check_constraints():
    conn = await asyncpg.connect(DATABASE_URI)
    constraints = await conn.fetch("""
        SELECT conname, contype
        FROM pg_constraint
        WHERE conrelid = 'loan_data'::regclass
    """)
    print(f"Found {len(constraints)} constraints for loan_data")
    for c in constraints:
        print(dict(c))
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_constraints())
