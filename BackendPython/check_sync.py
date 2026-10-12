import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("--- Customers ---")
    customers = await conn.fetch("SELECT customerid, user_id, customername FROM customers")
    for c in customers:
        print(dict(c))
        
    print("\n--- Loans ---")
    loans = await conn.fetch("SELECT loanid, customerid, loan_number FROM loan_data")
    for l in loans:
        print(dict(l))
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
