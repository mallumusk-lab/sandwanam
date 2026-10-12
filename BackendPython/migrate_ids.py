import asyncio
import asyncpg
from config import DATABASE_URI

async def run():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Connected to database. Starting migration...")

    # 1. Update customers table: user_id
    print("Updating customers.user_id...")
    await conn.execute("UPDATE customers SET user_id = REPLACE(user_id, '-', '')")

    # 2. Update loan_data table: loan_number
    print("Updating loan_data.loan_number...")
    await conn.execute("UPDATE loan_data SET loan_number = REPLACE(loan_number, '-', '')")

    # 3. Update statement table: loan_number
    print("Updating statement.loan_number...")
    await conn.execute("UPDATE statement SET loan_number = REPLACE(loan_number, '-', '')")

    print("Migration completed successfully.")
    
    # Verification prints
    print("\n--- Verification ---")
    print("Customers Sample:")
    customers = await conn.fetch("SELECT customerid, user_id FROM customers LIMIT 5")
    for c in customers:
        print(dict(c))
        
    print("\nLoans Sample:")
    loans = await conn.fetch("SELECT loanid, loan_number FROM loan_data LIMIT 5")
    for l in loans:
        print(dict(l))

    await conn.close()

if __name__ == "__main__":
    asyncio.run(run())
