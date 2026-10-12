import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Connected to database. Starting sync migration...")

    # Fetch all customers to have their user_id ready
    customers = await conn.fetch("SELECT customerid, user_id FROM customers")
    cust_map = {c['customerid']: c['user_id'] for c in customers}

    # Fetch all loans ordered by loanId to ensure stable index generation
    loans = await conn.fetch("SELECT loanid, customerid, loan_number FROM loan_data ORDER BY loanid ASC")
    
    # Track index per customer
    cust_counters = {}

    async with conn.transaction():
        for loan in loans:
            cid = loan['customerid']
            lid = loan['loanid']
            old_num = loan['loan_number']
            
            # Increment counter for this customer
            cust_counters[cid] = cust_counters.get(cid, 0) + 1
            idx = cust_counters[cid]
            
            # New loan number format: user_id + index
            user_id = cust_map.get(cid, "UNK")
            new_num = f"{user_id}{idx}"
            
            if old_num != new_num:
                print(f"Updating Loan {lid}: {old_num} -> {new_num}")
                
                # Update loan_data
                await conn.execute("UPDATE loan_data SET loan_number = $1 WHERE loanid = $2", new_num, lid)
                
                # Update statement (linked via loan_number string currently)
                # Note: statement also has loanId as a foreign key, so we use that for safer update
                rows_updated = await conn.execute("UPDATE statement SET loan_number = $1 WHERE loanId = $2", new_num, lid)
                print(f"  Updated {rows_updated} matching statement records.")

    print("Migration completed successfully.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
