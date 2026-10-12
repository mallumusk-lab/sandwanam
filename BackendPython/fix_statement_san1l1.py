import asyncio
import asyncpg
from config import DATABASE_URI
from datetime import datetime

def noOfDaysCalculation(start_date_str: str, end_date_str: str) -> int:
    try:
        d1_str = start_date_str.split('T')[0].strip()
        d2_str = end_date_str.split('T')[0].strip()
        d1 = datetime.strptime(d1_str, "%Y-%m-%d")
        d2 = datetime.strptime(d2_str, "%Y-%m-%d")
        return abs((d2 - d1).days)
    except: return 0

async def fix():
    conn = await asyncpg.connect(DATABASE_URI)
    loan_number = 'SAN1L1'
    
    # 1. Get loan data
    loan = await conn.fetchrow("SELECT * FROM loan_data WHERE loan_number = $1", loan_number)
    interest_rate = float(loan['interest'])
    
    # 2. Get all statements
    statements = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY statementid", loan_number)
    
    # 3. Recalculate balances
    prev_principal = 0.0
    prev_interest = 0.0
    prev_date = None
    
    for i, stmt in enumerate(statements):
        stmt_id = stmt['statementid']
        curr_date = stmt['date']
        transaction_type = stmt['transactiontype']
        amount_paid = float(stmt['amountpaid'] or 0)
        
        if transaction_type in ('newLoan', 'disbursement'):
            principle_balance = float(stmt['principlebalance'])
            interest_balance = 0.0
            print(f"STMT {stmt_id}: Initial Loan {principle_balance}")
        else:
            # Calculate interest from prev statement
            days = noOfDaysCalculation(prev_date, curr_date)
            interest_accrued = (prev_principal * interest_rate * days) / (365 * 100)
            
            # Current values
            if transaction_type == 'modify':
                # For SAN1L1, Row 6 modified principal from 99602.74 to 100157.74 (+555)
                # Row 6 amountPaid was 555. 
                # Let's assume the principal update logic from edit_loan:
                # updated_principal = prev_principal_bal + float(req.principleAmount)
                # So if amountPaid is used as adjustment:
                # principle_balance = prev_principal + amount_paid
                # interest_balance = prev_interest + interest_accrued
                principle_balance = prev_principal + amount_paid
                interest_balance = prev_interest + interest_accrued
                current_principal = 0.0
                current_interest = 0.0
            else: # addColl
                interest_due = prev_interest + interest_accrued
                interest_paid = min(amount_paid, interest_due)
                principal_paid = max(0.0, amount_paid - interest_due)
                
                principle_balance = prev_principal - principal_paid
                interest_balance = interest_due - interest_paid
                current_principal = -principal_paid if principal_paid > 0 else 0.0
                current_interest = interest_paid
            
            print(f"STMT {stmt_id}: {transaction_type}, days={days}, interest_accrued={interest_accrued:.2f}, principal_bal={principle_balance:.2f}, interest_bal={interest_balance:.2f}")
            
            # Update the statement
            await conn.execute("""
                UPDATE statement 
                SET currentPrincipal = $1, currentInterest = $2, principleBalance = $3, interestBalance = $4
                WHERE statementid = $5
            """, current_principal if transaction_type != 'modify' else 0.0, 
               current_interest if transaction_type != 'modify' else 0.0,
               principle_balance, interest_balance, stmt_id)
        
        prev_principal = principle_balance
        prev_interest = interest_balance
        prev_date = curr_date

    # Update loan_data refresh fields
    await conn.execute("""
        UPDATE loan_data 
        SET refreshprincipleamount = $1, refreshinterest = $2 
        WHERE loan_number = $3
    """, str(prev_principal), str(round(prev_interest, 2)), loan_number)
    
    print("Fix completed for SAN1L1")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(fix())
