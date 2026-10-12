import asyncio
import asyncpg
from config import DATABASE_URI

async def clear_data():
    conn = await asyncpg.connect(DATABASE_URI)
    print("Clearing all loan and statement data...")
    try:
        async with conn.transaction():
            # Truncate statement first (it depends on loan_data)
            # RESTART IDENTITY resets the SERIAL counters
            await conn.execute("TRUNCATE TABLE statement RESTART IDENTITY CASCADE")
            await conn.execute("TRUNCATE TABLE loan_data RESTART IDENTITY CASCADE")
            print("Successfully cleared loan_data and statement tables.")
            
            # Reset metadata for customers if needed (e.g. loanStatus)
            await conn.execute("UPDATE customers SET loanStatus = '0'")
            print("Reset customer loanStatus to '0'.")
            
    except Exception as e:
        print(f"Error clearing data: {e}")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(clear_data())
