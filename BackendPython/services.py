from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, timedelta, timezone
from typing import Dict, Any, List, Optional
import asyncpg
from fastapi import HTTPException
import json

def round_decimal(val: Decimal) -> Decimal:
    if val is None: return Decimal("0.00")
    return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def to_ist_date(dt_obj):
    if dt_obj is None: return None
    if isinstance(dt_obj, str):
        dt_obj = datetime.fromisoformat(dt_obj.replace('Z', '+00:00'))
    if isinstance(dt_obj, datetime):
        if dt_obj.tzinfo is None:
            dt_obj = dt_obj + timedelta(hours=5, minutes=30)
        else:
            dt_obj = dt_obj.astimezone(timezone(timedelta(hours=5, minutes=30)))
        return dt_obj.date()
    return dt_obj

def calculate_loan_status(loan_data: Dict[str, Any], latest_statement: Dict[str, Any], is_closing: bool = False, as_of_date: Optional[date] = None) -> Dict[str, Any]:
    """Calculates live interest and principal based on latest statement and target date.
    Rules: 
    1. Days elapsed is exactly calendar days difference (target_date - stmt_date) in IST.
    2. If is_closing is True and total loan duration < 7 days, guarantee a total of 7 days interest is charged.
    """
    if not latest_statement:
        return {
            "current_principal": Decimal(str(loan_data['principle_amount'])),
            "current_interest": Decimal("0.00"),
            "days_since_last_payment": 0
        }
    
    interest_rate = Decimal(str(loan_data['interest'])) if loan_data.get('interest') is not None else Decimal("18.0")
    
    target_date = to_ist_date(as_of_date) if as_of_date else (datetime.utcnow() + timedelta(hours=5, minutes=30)).date()
    stmt_date = to_ist_date(latest_statement['date'])
    loan_start = to_ist_date(loan_data['date'])
    
    # Exact calendar days since last statement
    days_diff = max(0, (target_date - stmt_date).days)
    
    # Rule: If closing, minimum 7 days interest for the ENTIRE loan duration
    total_loan_days = max(0, (target_date - loan_start).days)
    if is_closing and total_loan_days < 7:
        previous_days_charged = total_loan_days - days_diff
        modified_days_diff = max(0, 7 - previous_days_charged)
        if modified_days_diff > days_diff:
            days_diff = modified_days_diff
            
    prev_principal_bal = Decimal(str(latest_statement['principlebalance'] or 0))
    
    # Interest = (Principal * Rate * Days) / (365 * 100)
    current_days_interest = (prev_principal_bal * interest_rate * Decimal(str(days_diff))) / Decimal("36500")
    total_unpaid_interest = current_days_interest + Decimal(str(latest_statement['interestbalance'] or 0))
    
    return {
        "current_principal": prev_principal_bal,
        "current_interest": round_decimal(total_unpaid_interest),
        "days_since_last_payment": days_diff
    }

async def check_and_apply_historical_compounding(
    conn: asyncpg.Connection, 
    loan_data: Dict[str, Any], 
    latest_stmt: Dict[str, Any], 
    target_date: date
) -> Dict[str, Any]:
    """Checks if any annual compounding boundaries were crossed between latest_stmt and target_date.
    If so, applies them sequentially.
    """
    current_latest = latest_stmt
    loan_number = loan_data['loan_number']
    
    # Last compounding or loan start
    last_comp_stmt = await conn.fetchrow("SELECT date FROM statement WHERE loan_number = $1 AND transactionType = 'compounding' ORDER BY date DESC LIMIT 1", loan_number)
    base_date_raw = last_comp_stmt['date'] if last_comp_stmt else loan_data['date']
    base_date = to_ist_date(base_date_raw)

    # While gap is >= 365 days, compound
    while (target_date - base_date).days >= 365:
        # Compounding date is base_date + 365 days
        comp_date = base_date + timedelta(days=365)
        # Calculate status as of that compounding day
        status = calculate_loan_status(loan_data, current_latest, as_of_date=comp_date)
        interest_to_compound = status['current_interest']
        new_principal = status['current_principal'] + interest_to_compound
        
        # Insert compounding statement
        comp_datetime = datetime.combine(comp_date, datetime.min.time())
        current_latest = await conn.fetchrow("""
            INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *
        """, loan_data['loanid'], loan_number, Decimal("0.00"), comp_datetime, interest_to_compound, Decimal("0.00"), new_principal, Decimal("0.00"), 'compounding')
        
        base_date = comp_date
        print(f"Applied historical compounding for {loan_number} on {comp_date}")

    return dict(current_latest)

async def process_collection(
    conn: asyncpg.Connection, 
    loan_number: str, 
    amount_paid: Decimal, 
    transaction_type: str, 
    payment_date: datetime = None,
    is_closing: bool = False
) -> Dict[str, Any]:
    """Handles the business logic for adding a collection or writeoff."""
    loan_row = await conn.fetchrow("SELECT * FROM loan_data WHERE loan_number = $1", loan_number)
    if not loan_row:
        raise HTTPException(status_code=404, detail=f"Loan {loan_number} not found")
        
    latest_stmt = await conn.fetchrow("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC LIMIT 1", loan_number)
    
    effective_date = payment_date or datetime.now()
    eff_date_only = effective_date.date()

    # Rule: Handle annual compounding if we are jumping forward in time
    latest_stmt = await check_and_apply_historical_compounding(conn, loan_row, latest_stmt, eff_date_only)

    # If transaction_type is 'writeoff', it means we are closing the loan.
    is_closing_event = is_closing or (transaction_type == 'writeoff')
    status = calculate_loan_status(loan_row, latest_stmt, is_closing=is_closing_event, as_of_date=eff_date_only)
    
    interest_due = status['current_interest']
    principal_before = status['current_principal']
    
    if transaction_type == 'writeoff':
        interest_balance = Decimal("0.00")
        principal_balance = amount_paid # remainingBalance passed
        current_principal = Decimal("0.00")
        current_interest = Decimal("0.00")
        final_paid = Decimal("0.00")
    elif transaction_type == 'disbursement':
        # Adding to principal (Modify/Add Principal)
        principal_balance = principal_before + amount_paid
        interest_balance = interest_due
        current_principal = amount_paid
        current_interest = Decimal("0.00")
        final_paid = Decimal("0.00")
    elif transaction_type == 'compounding':
        # Interest added to principal manually
        principal_balance = principal_before + interest_due
        interest_balance = Decimal("0.00")
        current_principal = interest_due
        current_interest = -interest_due
        final_paid = Decimal("0.00")
    else: # addColl
        interest_paid = min(amount_paid, interest_due)
        principal_paid = max(Decimal("0.00"), amount_paid - interest_due)
        
        interest_balance = interest_due - interest_paid
        principal_balance = principal_before - principal_paid
        
        current_principal = -principal_paid if principal_paid > 0 else Decimal("0.00")
        current_interest = interest_paid
        final_paid = amount_paid

    # Insert into ledger
    stmt_row = await conn.fetchrow("""
        INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *
    """, loan_row['loanid'], loan_number, final_paid, effective_date, current_principal, current_interest, principal_balance, interest_balance, transaction_type)
    
    # Update quick-sync balance
    await conn.execute("""
        UPDATE loan_data SET refreshprincipleamount = $1, refreshinterest = $2 WHERE loan_number = $3
    """, principal_balance, interest_balance, loan_number)
    
    return dict(stmt_row)

async def log_audit_action(
    conn: asyncpg.Connection,
    username: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: str
):
    """Inserts a record into the audit_logs table."""
    await conn.execute("""
        INSERT INTO audit_logs (username, action, entity_type, entity_id, details)
        VALUES ($1, $2, $3, $4, $5)
    """, username, action, entity_type, entity_id, details)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

async def create_json_backup(conn: asyncpg.Connection) -> str:
    """Exports all major tables to a JSON string."""
    tables = ['customers', 'loan_data', 'statement', 'role', 'audit_logs']
    backup_data = {}
    for table in tables:
        rows = await conn.fetch(f"SELECT * FROM {table}")
        backup_data[table] = [dict(r) for r in rows]
    return json.dumps(backup_data, cls=CustomJSONEncoder)

async def restore_from_json(conn: asyncpg.Connection, data: dict):
    """Restores database from a JSON dict, replacing all existing data."""
    # 1. Clear existing data (TRUNCATE handles FK constraints if CASCADE is used)
    await conn.execute("TRUNCATE TABLE statement, loan_data, customers, role, audit_logs RESTART IDENTITY CASCADE")

    # 2. Insert data in dependency order
    insert_order = ['role', 'customers', 'loan_data', 'statement', 'audit_logs']
    
    decimal_columns = {
        'weight', 'net_weight', 'principle_amount', 'interest', 'deduction', 
        'refreshprincipleamount', 'refreshinterest', 'amountpaid', 
        'currentprincipal', 'currentinterest', 'principlebalance', 'interestbalance'
    }
    date_columns = {'date', 'timestamp'}
    
    for table_name in insert_order:
        rows = data.get(table_name, [])
        if not rows: continue
        
        columns = list(rows[0].keys())
        cols_str = ", ".join(f'"{col}"' for col in columns) # double quote safely
        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
        query = f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})"
        
        values_list = []
        for r in rows:
            row_vals = []
            for col in columns:
                val = r[col]
                # We do basic type casting since postgres driver is picky
                if val is not None and isinstance(val, str):
                    if col.lower() in decimal_columns:
                        val = Decimal(val)
                    elif col.lower() in date_columns:
                        try:
                            # Handle timezone aware strings
                            val = datetime.fromisoformat(val.replace('Z', '+00:00'))
                        except ValueError:
                            pass
                row_vals.append(val)
            values_list.append(tuple(row_vals))
        
        await conn.executemany(query, values_list)
        
        # Reset primary key sequences manually since we inserted explicit IDs
        if table_name == 'customers':
            await conn.execute("SELECT setval('customers_customerid_seq', COALESCE((SELECT MAX(customerid) FROM customers), 0) + 1, false)")
        elif table_name == 'loan_data':
            await conn.execute("SELECT setval('loan_data_loanid_seq', COALESCE((SELECT MAX(loanid) FROM loan_data), 0) + 1, false)")
        elif table_name == 'statement':
            await conn.execute("SELECT setval('statement_statementid_seq', COALESCE((SELECT MAX(statementid) FROM statement), 0) + 1, false)")
        elif table_name == 'audit_logs':
            await conn.execute("SELECT setval('audit_logs_log_id_seq', COALESCE((SELECT MAX(log_id) FROM audit_logs), 0) + 1, false)")
