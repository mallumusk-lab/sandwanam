import asyncio
import asyncpg
from config import DATABASE_URI

async def repair_data():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Repairing SAN2L1 loan data...")
    # Reset refresh principal and interest for SAN2L1 which has corrupted values
    await conn.execute("""
        UPDATE loan_data 
        SET refreshprincipleamount = principle_amount, 
            refreshinterest = '0' 
        WHERE loan_number = 'SAN2L1'
    """)
    
    # Also clean up the statements if they have crazy balances
    # Finding the 'newLoan' statement to reset from
    row = await conn.fetchrow("SELECT principlebalance FROM statement WHERE loan_number = 'SAN2L1' AND transactiontype = 'newLoan' LIMIT 1")
    if row:
        pb = row['principlebalance']
        await conn.execute("""
            DELETE FROM statement 
            WHERE loan_number = 'SAN2L1' AND transactiontype != 'newLoan'
        """)
        print(f"Reset loan SAN2L1 to principal balance: {pb}")
    
    await conn.close()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(repair_data())
