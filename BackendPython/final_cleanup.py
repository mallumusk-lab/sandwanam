import asyncio
import asyncpg
from config import DATABASE_URI

async def cleanup():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Starting final cleanup...")

    # 1. Sync loanId where it's NULL
    res = await conn.execute("""
        UPDATE statement s
        SET loanId = l.loanid
        FROM loan_data l
        WHERE s.loan_number = l.loan_number AND s.loanId IS NULL
    """)
    print(f"Synced loanId for {res} statement records.")

    # 2. Comprehensive cleanup of duplicates (newLoan only)
    # disbursement (Add Principal) can happen multiple times legitimately.
    duplicates = await conn.fetch("""
        WITH cte AS (
            SELECT statementid,
                   ROW_NUMBER() OVER (
                        PARTITION BY loan_number 
                        ORDER BY statementid ASC
                   ) as rn
            FROM statement
            WHERE transactionType = 'newLoan'
        )
        SELECT statementid FROM cte WHERE rn > 1
    """)
    
    if not duplicates:
        print("No more duplicates found.")
    else:
        ids_to_delete = [d['statementid'] for d in duplicates]
        print(f"Deleting {len(ids_to_delete)} duplicate statement IDs: {ids_to_delete}")
        await conn.execute("DELETE FROM statement WHERE statementid = ANY($1)", ids_to_delete)
        print("Duplicates deleted.")

    # 3. Update the unique index to be more robust
    print("Updating unique index...")
    await conn.execute("DROP INDEX IF EXISTS unique_new_loan_pct")
    await conn.execute("DROP INDEX IF EXISTS unique_initial_statement_pct")
    await conn.execute("""
        CREATE UNIQUE INDEX unique_initial_statement_pct 
        ON statement (loan_number) 
        WHERE transactionType = 'newLoan';
    """)
    print("Unique index updated to cover only newLoan.")

    await conn.close()

if __name__ == "__main__":
    asyncio.run(cleanup())
