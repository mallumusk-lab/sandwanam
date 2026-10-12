import asyncpg
import asyncio
from config import DATABASE_URI

async def check_schema():
    conn = await asyncpg.connect(DATABASE_URI)
    try:
        for table in ['loan_data', 'statement', 'audit_logs']:
            print(f"\nColumns for table: {table}")
            columns = await conn.fetch(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table}' AND column_name IN ('date', 'timestamp')
            """)
            for col in columns:
                print(f"  {col['column_name']}: {col['data_type']}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(check_schema())
