import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Repairing statement links...")

    # For Loan 1 (SANFIN21)
    await conn.execute("""
        UPDATE statement 
        SET loanId = 1, loan_number = 'SANFIN21' 
        WHERE loan_number = '1001'
    """)
    print("Repaired Loan 1 statements.")

    # For Loan 2 (SANFIN22)
    await conn.execute("""
        UPDATE statement 
        SET loanId = 2, loan_number = 'SANFIN22' 
        WHERE loan_number = '1002'
    """)
    print("Repaired Loan 2 statements.")

    # Check for any remaining orphans
    orphans = await conn.fetch("SELECT DISTINCT loan_number FROM statement WHERE loanId IS NULL")
    if orphans:
        print(f"Remaining orphans: {[r['loan_number'] for r in orphans]}")
    else:
        print("All statements now linked to loanId.")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
