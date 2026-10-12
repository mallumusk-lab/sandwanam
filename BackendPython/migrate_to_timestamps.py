import asyncpg
import asyncio
from config import DATABASE_URI

async def migrate():
    print("Starting migration to TIMESTAMPTZ...")
    conn = await asyncpg.connect(DATABASE_URI)
    try:
        async with conn.transaction():
            # Check current types
            print("Altering 'statement' table 'date' column...")
            await conn.execute("ALTER TABLE statement ALTER COLUMN date TYPE TIMESTAMPTZ USING date::TIMESTAMPTZ")
            
            print("Altering 'loan_data' table 'date' column...")
            await conn.execute("ALTER TABLE loan_data ALTER COLUMN date TYPE TIMESTAMPTZ USING date::TIMESTAMPTZ")
            
            print("Altering 'audit_logs' table (ensuring TIMESTAMPTZ)...")
            # Audit logs already uses TIMESTAMPTZ according to database.py:147
            
            print("Migration successful!")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())
