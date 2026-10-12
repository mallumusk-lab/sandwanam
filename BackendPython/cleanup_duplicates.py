import asyncio
import asyncpg
from config import DATABASE_URI

async def cleanup():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Starting cleanup of duplicate statements...")
    
    # We want to keep ONLY one 'newLoan' per loanId.
    # We'll use a CTE to identify duplicates.
    
    duplicates = await conn.fetch("""
        WITH cte AS (
            SELECT statementid,
                   ROW_NUMBER() OVER (
                       PARTITION BY loanId, transactionType 
                       ORDER BY statementid ASC
                   ) as rn
            FROM statement
            WHERE transactionType = 'newLoan'
        )
        SELECT statementid FROM cte WHERE rn > 1
    """)
    
    if not duplicates:
        print("No duplicate 'newLoan' entries found.")
    else:
        ids_to_delete = [d['statementid'] for d in duplicates]
        print(f"Found {len(ids_to_delete)} duplicate statement IDs to delete: {ids_to_delete}")
        
        await conn.execute("DELETE FROM statement WHERE statementid = ANY($1)", ids_to_delete)
        print("Cleanup completed successfully.")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(cleanup())
