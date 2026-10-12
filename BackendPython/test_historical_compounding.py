import asyncio
import asyncpg
from decimal import Decimal
from datetime import datetime, timedelta
from database import DATABASE_URI
from services import process_collection

async def test_historical():
    conn = await asyncpg.connect(DATABASE_URI)
    try:
        # 1. Setup - Create a Customer if not exists
        cid = await conn.fetchval("INSERT INTO customers (customerName, phone, address, loanStatus, role, user_id) VALUES ('Hist Test', '9999911111', 'History Lane', '0', 'Admin', 'HIS001') ON CONFLICT (phone) DO UPDATE SET customerName = EXCLUDED.customerName RETURNING customerid")
        
        # 2. Setup - Create a Loan from 3 years ago (approx 1095 days)
        loan_number = "HIST_TEST_001"
        start_date = datetime.now() - timedelta(days=1100)
        
        await conn.execute("DELETE FROM statement WHERE loan_number = $1", loan_number)
        await conn.execute("DELETE FROM loan_data WHERE loan_number = $1", loan_number)
        
        loan_row = await conn.fetchrow("""
            INSERT INTO loan_data (customerId, particulars, loan_number, number_of_items, weight, 
            net_weight, principle_amount, interest, tenure, loanStatus, role, date, 
            loanType, refreshprincipleamount, refreshinterest, deduction)
            VALUES ($1, 'Test', $2, '1', 10, 10, 100000, 10, 12, '1', 'Admin', $3, 'open', 100000, 0, 0) RETURNING *
        """, cid, loan_number, start_date)
        
        await conn.execute("""
            INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
            VALUES ($1, $2, 0, $3, 0, 0, 100000, 0, 'newLoan')
        """, loan_row['loanid'], loan_number, start_date)

        print(f"Created loan {loan_number} starting on {start_date.date()}")

        # 3. Process a collection TODAY (should catch up 3 years of compounding)
        payment_date = datetime.now()
        print(f"Adding collection of 5000 on {payment_date.date()}")
        await process_collection(conn, loan_number, Decimal("5000.00"), "addColl", payment_date)
        
        # 4. Verify Statements
        statements = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date ASC", loan_number)
        print("\nStatement History:")
        comp_count = 0
        for s in statements:
            print(f"Date: {s['date'].date()} | Type: {s['transactiontype']} | P.Balance: {s['principlebalance']} | Interest: {s['currentinterest']}")
            if s['transactiontype'] == 'compounding':
                comp_count += 1
        
        if comp_count == 3:
            print("\nSUCCESS: 3 historical compounding events were applied!")
        else:
            print(f"\nFAILURE: Expected 3 compounding events, found {comp_count}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(test_historical())
