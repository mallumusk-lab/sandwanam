import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Connected to database. Starting refinement migration...")

    # 1. Update customers table: user_id (Remove 'FIN')
    print("Refining customers.user_id...")
    await conn.execute("UPDATE customers SET user_id = REPLACE(user_id, 'FIN', '')")

    # 2. Update loan_data and statement tables
    print("Refining loan numbers...")
    
    # We need to selectively insert 'L' if it wasn't there, and remove 'FIN'
    # The current state is SANFIN21, SANFIN22 etc. after previous sync.
    # We want SAN2L1, SAN2L2 etc.
    
    # Fetch all loans
    loans = await conn.fetch("SELECT loanid, customerid, loan_number FROM loan_data")
    
    # We'll use the same logic as sync_loan_numbers but with the new format refinement
    customers = await conn.fetch("SELECT customerid, user_id FROM customers")
    # Note: user_id is already refined in the map because it's updated in DB first if we were serial, 
    # but let's just do it cleanly.
    cust_map = {c['customerid']: c['user_id'].replace('FIN', '') for c in customers}
    
    cust_counters = {}
    
    async with conn.transaction():
        for loan in loans:
            cid = loan['customerid']
            lid = loan['loanid']
            
            cust_counters[cid] = cust_counters.get(cid, 0) + 1
            idx = cust_counters[cid]
            
            clean_user_id = cust_map.get(cid, "UNK")
            new_num = f"{clean_user_id}L{idx}"
            
            print(f"Updating Loan {lid}: -> {new_num}")
            
            await conn.execute("UPDATE loan_data SET loan_number = $1 WHERE loanid = $2", new_num, lid)
            await conn.execute("UPDATE statement SET loan_number = $1 WHERE loanId = $2", new_num, lid)

    print("Migration completed successfully.")
    
    # Verification
    print("\n--- Final Verification ---")
    customers = await conn.fetch("SELECT user_id FROM customers LIMIT 5")
    for c in customers: print(dict(c))
    loans = await conn.fetch("SELECT loan_number FROM loan_data LIMIT 5")
    for l in loans: print(dict(l))

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
