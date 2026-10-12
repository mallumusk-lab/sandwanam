import asyncio
import asyncpg
from config import DATABASE_URI

async def check():
    conn = await asyncpg.connect(DATABASE_URI)
    
    # 1. Total orphans
    count = await conn.fetchval('SELECT count(*) FROM statement WHERE loanId IS NULL')
    print(f"Total statements with NULL loanId: {count}")
    
    # 2. Duplicate initial statements (newLoan or disbursement)
    rows = await conn.fetch("""
        SELECT loan_number, count(*) 
        FROM statement 
        WHERE transactionType IN ('newLoan', 'disbursement')
        GROUP BY loan_number
        HAVING count(*) > 1
    """)
    print("\nLoans with duplicate initial statements:")
    for row in rows:
        print(dict(row))
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
