import asyncio
import asyncpg
from config import DATABASE_URI

async def check_db():
    kwargs = {"statement_cache_size": 0} if ("supabase" in DATABASE_URI or "pooler" in DATABASE_URI or ":6543" in DATABASE_URI) else {}
    conn = await asyncpg.connect(DATABASE_URI, **kwargs)
    
    print("--- Customers ---")
    customers = await conn.fetch("SELECT * FROM customers")
    for c in customers:
        print(dict(c))
        
    print("\n--- Loan Data ---")
    loans = await conn.fetch("SELECT * FROM loan_data")
    for l in loans:
        print(dict(l))
        
    print("\n--- Statements ---")
    statements = await conn.fetch("SELECT * FROM statement")
    for s in statements:
        print(dict(s))
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check_db())
