from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, Depends, HTTPException, Request, Header, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
import os
import json
from fastapi.middleware.cors import CORSMiddleware
from database import init_db, get_db
import database
import asyncpg
from typing import List, Dict, Any, Optional
from models import AuthRequest, CustomerCreate, LoanDataCreate, StatementCreate, EditLoanRequest, CollectionRequest, HistoryImportRequest, BranchCreate, BranchUpdate, ResetPasswordRequest
from pydantic import BaseModel
from config import API_KEY
from decimal import Decimal
from security import verify_password
import asyncio
import secrets
from services import round_decimal, calculate_loan_status, process_collection, log_audit_action, check_and_apply_historical_compounding
import httpx
from bs4 import BeautifulSoup
import re

# Allowed CORS origins — add your frontend URL here for production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# SuperAdmin session store: maps session_token -> username (in-memory, cleared on restart)
_superadmin_sessions: dict = {}

# ─── Shared cron job logic (called both by background loops AND /cron/* HTTP endpoints) ───

async def run_compounding_check():
    """Core compounding logic — runs all open loans and compounds if >= 365 days have passed."""
    compounded = []
    async with database.pool.acquire() as conn:
        open_loans = await conn.fetch("SELECT * FROM loan_data WHERE loantype = 'open'")
        now = datetime.now()
        for loan in open_loans:
            loan_number = loan['loan_number']
            latest_stmt = await conn.fetchrow(
                "SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC LIMIT 1",
                loan_number
            )
            if not latest_stmt:
                continue
            last_comp_stmt = await conn.fetchrow(
                "SELECT date FROM statement WHERE loan_number = $1 AND transactionType = 'compounding' ORDER BY date DESC LIMIT 1",
                loan_number
            )
            base_date = last_comp_stmt['date'] if last_comp_stmt else loan['date']
            if isinstance(base_date, str):
                base_date = datetime.fromisoformat(base_date.replace('Z', '+00:00'))
            days_since_base = (now - base_date.replace(tzinfo=None)).days
            if days_since_base >= 365:
                print(f"Compounding loan {loan_number} (Days since base: {days_since_base})")
                status = calculate_loan_status(loan, latest_stmt)
                interest_to_compound = status['current_interest']
                new_principal = status['current_principal'] + interest_to_compound
                async with conn.transaction():
                    await conn.execute("""
                        INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """, loan['loanid'], loan_number, Decimal("0.00"), now, interest_to_compound, Decimal("0.00"), new_principal, Decimal("0.00"), 'compounding')
                    await conn.execute("""
                        UPDATE loan_data SET refreshprincipleamount = $1, refreshinterest = $2 WHERE loan_number = $3
                    """, new_principal, Decimal("0.00"), loan_number)
                    await log_audit_action(conn, "System", "COMPOUNDING", "LOAN", loan_number, f"Compounded annual interest: {interest_to_compound}")
                compounded.append(loan_number)
    return compounded

async def run_compounding_cron():
    """Background loop: runs compounding check once a day at midnight (non-Vercel servers only)."""
    while True:
        try:
            await run_compounding_check()
        except Exception as e:
            print(f"Error in compounding cron: {e}")
        now = datetime.now()
        next_run = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        sleep_seconds = (next_run - now).total_seconds()
        print(f"Compounding cron sleeping for {sleep_seconds:.0f}s until {next_run}")
        await asyncio.sleep(sleep_seconds)

async def run_backup_job():
    """Core backup logic — dumps all tables to Backups/finance_backup.json."""
    from services import create_json_backup
    os.makedirs("Backups", exist_ok=True)
    async with database.pool.acquire() as conn:
        backup_json = await create_json_backup(conn)
        with open("Backups/finance_backup.json", "w") as f:
            f.write(backup_json)
    return "Backups/finance_backup.json"

async def run_auto_backup_cron():
    """Background loop: runs backup immediately then every hour (non-Vercel servers only)."""
    while True:
        try:
            await run_backup_job()
            print("Auto-backup complete.")
        except Exception as e:
            print(f"Auto-backup Error: {e}")
        await asyncio.sleep(3600)  # Sleep AFTER backup

LIVE_GOLD_DATA = {"current": Decimal("6250.00"), "change": "Market Live"}

async def fetch_gold_price():
    global LIVE_GOLD_DATA
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        async with httpx.AsyncClient(headers=headers) as client:
            response = await client.get("https://www.goldpriceindia.com/", timeout=15.0)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                text = soup.get_text()
                match = re.search(r"highest gold price.*?month.*?was ([\d,]+) rupees per 10 grams", text)
                if match:
                    val = Decimal(match.group(1).replace(",", ""))
                    price_1g = val / 10
                    LIVE_GOLD_DATA["current"] = price_1g
                    LIVE_GOLD_DATA["change"] = "Live (24K)"
                    print(f"Updated live gold price: ₹{price_1g}/g")
                else:
                    print("Gold price scrape: pattern not matched, keeping previous price.")
            else:
                print(f"Gold price fetch: HTTP {response.status_code}")
    except Exception as e:
        print(f"Error fetching live gold price: {e}")

async def run_gold_price_cron():
    """Background task to fetch live gold price every hour."""
    while True:
        await fetch_gold_price()
        await asyncio.sleep(3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle handler.
    
    Vercel is a serverless platform — each request may spin up a fresh process,
    so long-running asyncio background tasks (crons) are skipped on Vercel.
    They will still run correctly on a persistent server (Railway, Render, VPS, etc).
    """
    await init_db()

    # Only start background tasks when running on a persistent server, not Vercel
    is_vercel = os.getenv("VERCEL") or os.getenv("VERCEL_ENV")
    if not is_vercel:
        asyncio.create_task(run_compounding_cron())
        asyncio.create_task(run_auto_backup_cron())
        asyncio.create_task(run_gold_price_cron())
    else:
        print("Vercel detected: skipping background cron tasks (use external cron service for compounding/backup).")

    yield  # App runs here

    # Shutdown: close the connection pool gracefully
    if database.pool:
        await database.pool.close()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Set ALLOWED_ORIGINS env var in production (e.g. "https://yourapp.com")
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class StripApiPrefixMiddleware:
    """ASGI middleware that strips '/api' prefix from incoming requests
    so that frontend calls to '/api/customers' route cleanly to existing endpoints."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket") and scope.get("path", "").startswith("/api"):
            new_path = scope["path"][4:]
            scope["path"] = new_path if new_path.startswith("/") else "/" + new_path
        await self.app(scope, receive, send)

app.add_middleware(StripApiPrefixMiddleware)

def verify_api_key(x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized. Invalid API key.")
    return x_api_key

# \u2500\u2500\u2500 Cron HTTP Endpoints (for Vercel Cron Jobs & external schedulers) \u2500\u2500\u2500
# Protected by CRON_SECRET env var. Configure in Vercel Dashboard.
# Vercel sends: Authorization: Bearer <CRON_SECRET>

def verify_cron_secret(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None)
):
    """
    Guard for /cron/* endpoints.
    Accepts:
    1. Authorization: Bearer <CRON_SECRET> (sent automatically by Vercel Cron)
    2. x-api-key: <API_KEY> (for manual testing via Swagger/Postman/curl)
    3. Authorization: Bearer <API_KEY>
    """
    cron_secret = os.getenv("CRON_SECRET", "")
    if cron_secret and authorization and secrets.compare_digest(authorization, f"Bearer {cron_secret}"):
        return True
    if x_api_key and secrets.compare_digest(x_api_key, API_KEY):
        return True
    if authorization and secrets.compare_digest(authorization, f"Bearer {API_KEY}"):
        return True
    if not cron_secret and not authorization and not x_api_key:
        raise HTTPException(status_code=401, detail="Missing authorization header. Provide Bearer token or x-api-key.")
    raise HTTPException(status_code=401, detail="Invalid cron authorization.")

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Sandwanam Finance API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
async def health_check():
    db_ok = False
    error_msg = None
    try:
        if database.pool:
            async with database.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            db_ok = True
        else:
            error_msg = "Database pool not initialized"
    except Exception as e:
        error_msg = str(e)
    return {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else "disconnected",
        "error": error_msg,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/cron/compounding")
async def cron_compounding(auth: str = Depends(verify_cron_secret)):
    """Called by Vercel Cron daily at midnight to run annual compounding."""
    try:
        compounded = await run_compounding_check()
        return {"message": "Compounding check complete", "compounded_loans": compounded, "count": len(compounded)}
    except Exception as e:
        print(f"Cron compounding error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cron/backup")
async def cron_backup(auth: str = Depends(verify_cron_secret)):
    """Called by Vercel Cron hourly to create a JSON backup."""
    try:
        path = await run_backup_job()
        return {"message": "Backup complete", "path": path}
    except Exception as e:
        print(f"Cron backup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cron/gold-price")
async def cron_gold_price(auth: str = Depends(verify_cron_secret)):
    """Called by Vercel Cron hourly to refresh the live gold price."""
    try:
        await fetch_gold_price()
        return {"message": "Gold price updated", "current": str(LIVE_GOLD_DATA["current"]), "change": LIVE_GOLD_DATA["change"]}
    except Exception as e:
        print(f"Cron gold price error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cron/all")
async def cron_all(auth: str = Depends(verify_cron_secret)):
    """Combined cron endpoint — runs ALL tasks in one call.
    
    Use this with your single free Vercel cron slot (runs hourly).
    - Compounding: checks all loans, only acts if >= 365 days have passed (safe to run hourly)
    - Backup: saves a fresh snapshot every hour
    - Gold price: refreshes the live market price every hour
    """
    results = {}

    # 1. Compounding (idempotent — only fires if 365 days truly elapsed)
    try:
        compounded = await run_compounding_check()
        results["compounding"] = {"status": "ok", "compounded_loans": compounded, "count": len(compounded)}
    except Exception as e:
        results["compounding"] = {"status": "error", "detail": str(e)}

    # 2. Backup
    try:
        path = await run_backup_job()
        results["backup"] = {"status": "ok", "path": path}
    except Exception as e:
        results["backup"] = {"status": "error", "detail": str(e)}

    # 3. Gold price
    try:
        await fetch_gold_price()
        results["gold_price"] = {"status": "ok", "current": str(LIVE_GOLD_DATA["current"]), "change": LIVE_GOLD_DATA["change"]}
    except Exception as e:
        results["gold_price"] = {"status": "error", "detail": str(e)}

    return {"message": "All cron tasks executed", "results": results}


@app.post("/authenticate")
async def authenticate(auth: AuthRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    print(f"Auth attempt for: {auth.userName}")
    row = await conn.fetchrow("SELECT password, role FROM role WHERE LOWER(userName) = LOWER($1)", auth.userName)
    if row:
        print(f"Row found for {auth.userName}. Verifying password...")
        is_valid = verify_password(auth.password, row['password'])
        print(f"Password valid: {is_valid}")
        if is_valid:
            return {"message": "Authentication successful", "role": row['role']}
    else:
        print(f"No row found for user: {auth.userName}")
    raise HTTPException(status_code=401, detail="Invalid credentials. Authentication failed.")

@app.get("/all_loan_data")
async def get_all_loan_data(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    query = """
        WITH latest_statements AS (
            SELECT DISTINCT ON (loan_number) *
            FROM statement
            ORDER BY loan_number, date DESC, statementid DESC
        )
        SELECT ld.*, c.customername, c.phone, c.address, c.user_id,
               ls.currentPrincipal as latest_principle, 
               ls.currentInterest as latest_interest,
               ls.principleBalance as latest_p_balance,
               ls.interestBalance as latest_i_balance,
               ls.date as latest_s_date
        FROM loan_data ld
        JOIN customers c ON ld.customerid = c.customerid
        LEFT JOIN latest_statements ls ON ld.loan_number = ls.loan_number
        ORDER BY ld.date DESC
    """
    rows = await conn.fetch(query)
    grouped = {}
    for row in rows:
        cid = row['customerid']
        if cid not in grouped:
            grouped[cid] = {
                "customerid": cid, "customername": row['customername'], "phone": row['phone'], 
                "address": row['address'], "loanstatus": row['loanstatus'], "role": row['role'],
                "user_id": row['user_id'],
                "LoanDetails": []
            }
        loan_dict = dict(row)
        if loan_dict.get('loantype') == 'open':
            status = calculate_loan_status(loan_dict, {
                'date': loan_dict['latest_s_date'],
                'principlebalance': loan_dict['latest_p_balance'],
                'interestbalance': loan_dict['latest_i_balance']
            })
            loan_dict['refreshprincipleamount'] = status['current_principal']
            loan_dict['refreshinterest'] = status['current_interest']
        grouped[cid]["LoanDetails"].append(loan_dict)
    return {"customers": list(grouped.values())}

@app.post("/all_loan_data")
async def get_all_loan_data_by_customer(payload: dict, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    customer_id = payload.get("customerId")
    
    query = """
        WITH latest_statements AS (
            SELECT DISTINCT ON (loan_number) *
            FROM statement
            ORDER BY loan_number, date DESC, statementid DESC
        )
        SELECT ld.*, c.customername, c.phone, c.address, c.user_id,
               ls.currentPrincipal as latest_principle, 
               ls.currentInterest as latest_interest,
               ls.principleBalance as latest_p_balance,
               ls.interestBalance as latest_i_balance,
               ls.date as latest_s_date
        FROM loan_data ld
        JOIN customers c ON ld.customerid = c.customerid
        LEFT JOIN latest_statements ls ON ld.loan_number = ls.loan_number
    """
    
    if customer_id:
        rows = await conn.fetch(query + " WHERE ld.customerid = $1 ORDER BY ld.date DESC", int(customer_id))
    else:
        rows = await conn.fetch(query + " ORDER BY ld.date DESC")
        
    grouped = {}
    for row in rows:
        cid = row['customerid']
        if cid not in grouped:
            grouped[cid] = {
                "customerid": cid, "customername": row['customername'], "phone": row['phone'],
                "address": row['address'], "loanstatus": row['loanstatus'], "role": row['role'],
                "user_id": row['user_id'],
                "LoanDetails": []
            }
        
        loan_dict = dict(row)

        if loan_dict.get('loantype') == 'open':
            status = calculate_loan_status(loan_dict, {
                'date': loan_dict['latest_s_date'],
                'principlebalance': loan_dict['latest_p_balance'],
                'interestbalance': loan_dict['latest_i_balance']
            })
            loan_dict['refreshprincipleamount'] = status['current_principal']
            loan_dict['refreshinterest'] = status['current_interest']
            
        grouped[cid]["LoanDetails"].append(loan_dict)
    return {"customerLoanData": list(grouped.values())}

@app.post("/customers")
async def create_customer(c: CustomerCreate, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        row = await conn.fetchrow("""
            INSERT INTO customers (customerName, phone, address, loanStatus, role, user_id)
            VALUES ($1, $2, $3, $4, $5, $6) RETURNING *
        """, c.customerName, c.phone, c.address, c.loanStatus, c.role, c.user_id)
        
        await log_audit_action(conn, c.role, "CREATE_CUSTOMER", "CUSTOMER", str(row['customerid']), f"Created customer: {c.customerName}")
        
        return {"message": "Successfully completed", "customer": dict(row)}
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=400, detail="Phone number already exists. Please provide a unique phone number.")
    except Exception as e:
        print(f"Error in create_customer: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/loan_data")
async def create_loan_data(l: LoanDataCreate, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    check = await conn.fetchval("SELECT 1 FROM customers WHERE customerId = $1", l.customerId)
    if not check:
        raise HTTPException(status_code=400, detail="Invalid customerId. Customer does not exist.")

    # Pre-check duplicate loan number before starting a transaction
    existing = await conn.fetchval("SELECT 1 FROM loan_data WHERE loan_number = $1", l.loan_number)
    if existing:
        raise HTTPException(status_code=400, detail=f"Loan number {l.loan_number} already exists.")

    try:
        async with conn.transaction():
            row = await conn.fetchrow("""
                INSERT INTO loan_data (customerId, particulars, particulars_qty, number_of_items, weight,
                net_weight, principle_amount, interest, tenure, loan_number, loanStatus, role, date,
                loanType, refreshprincipleamount, refreshinterest, deduction)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) RETURNING *
            """, l.customerId, l.particulars, l.particulars_qty, l.number_of_items, l.weight, l.net_weight,
               l.principle_amount, l.interest, l.tenure, l.loan_number, l.loanStatus, l.role, l.date,
               l.loanType, l.refreshprincipleamount, l.refreshinterest, l.deduction)

            await conn.execute("""
                INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, row['loanid'], l.loan_number, Decimal("0.00"), l.date, Decimal("0.00"), Decimal("0.00"), l.principle_amount, Decimal("0.00"), 'newLoan')

            await conn.execute("UPDATE customers SET loanStatus = '1' WHERE customerId = $1", l.customerId)

            await log_audit_action(conn, l.role, "CREATE_LOAN", "LOAN", l.loan_number, f"Created loan for customerId: {l.customerId}, Amount: {l.principle_amount}")

            return {"message": "Successfully created loan", "loan": dict(row)}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in create_loan_data: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/loan_type")
async def update_loan_type(payload: dict, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    loan_type = payload.get("loanType")
    loan_number = payload.get("loan_number")
    row = await conn.fetchrow("UPDATE loan_data SET loanType = $1 WHERE loan_number = $2 RETURNING *", loan_type, loan_number)
    if not row:
        raise HTTPException(status_code=404, detail=f"No loan found with loan_number {loan_number}")
    
    # We don't have role in payload, but we can get it from the loan data or request header if we had auth
    # For now use 'System/API' as we don't want to break the contract if frontend doesn't send it
    await log_audit_action(conn, row['role'], "UPDATE_LOAN_TYPE", "LOAN", loan_number, f"Updated loanType to: {loan_type}")
    
    return {"message": "Successfully updated loanType", "loanData": dict(row)}

@app.get("/loan_data")
async def get_all_loan_data_list(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM loan_data ORDER BY date DESC")
    return [dict(r) for r in rows]

@app.get("/customers")
async def get_customers(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM customers")
    return [dict(r) for r in rows]

@app.get("/customers/{customer_id}")
async def get_customer_by_id(customer_id: int, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    row = await conn.fetchrow("SELECT * FROM customers WHERE customerId = $1", customer_id)
    if not row:
         raise HTTPException(status_code=404, detail="Customer not found")
    return dict(row)

@app.get("/loan_data/{customer_id}")
async def get_loan_data_by_customer(customer_id: int, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM loan_data WHERE customerId = $1 ORDER BY date DESC", customer_id)
    return [dict(r) for r in rows]

@app.post("/add_collection/{loan_number}")
async def add_collection(loan_number: str, request: CollectionRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        async with conn.transaction():
            paid = Decimal(str(request.amountPaid))  # already Decimal from model, str() is safe
            payment_date = datetime.fromisoformat(request.date.replace('Z', '+00:00')) if request.date else None
            stmt = await process_collection(conn, loan_number, paid, request.transactionType, payment_date, is_closing=request.is_closing)

            await log_audit_action(conn, request.role, "ADD_COLLECTION", "LOAN", loan_number, f"Type: {request.transactionType}, Amount: {paid}, Closing: {request.is_closing}")

            return {"message": "Collection added successfully", "statement": stmt}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in add_collection: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/import_history")
async def import_history(request: HistoryImportRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        async with conn.transaction():
            # 1. Handle Customer
            customer_id = request.selectedCustomerId
            if request.customerType == "new":
                c = request.customerData
                # Check uniqueness (phone)
                existing_c = await conn.fetchrow("SELECT customerid FROM customers WHERE phone = $1", c['phone'])
                if existing_c:
                    customer_id = existing_c['customerid']
                else:
                    customer_row = await conn.fetchrow("""
                        INSERT INTO customers (customerName, phone, address, loanStatus, role, user_id)
                        VALUES ($1, $2, $3, $4, $5, $6) RETURNING customerid
                    """, c['customerName'], c['phone'], c['address'], '1', request.role, c.get('user_id', 'admin'))
                    customer_id = customer_row['customerid']

            # 2. Create Loan
            l = request.loanData
            loan_number = l.get('loan_number')
            if not loan_number:
                # Auto-generate a loan number based on customer ID
                c_row = await conn.fetchrow("SELECT user_id FROM customers WHERE customerid = $1", customer_id)
                prefix = c_row['user_id'].replace("FIN", "").replace("-", "") if c_row and c_row['user_id'] else "HIS"

                existing_loans = await conn.fetch("SELECT loan_number FROM loan_data WHERE customerid = $1", customer_id)
                max_idx = 0
                for el in existing_loans:
                    ln = el['loan_number']
                    if ln and 'L' in ln:
                        try:
                            idx = int(ln.split('L')[-1])
                            if idx > max_idx: max_idx = idx
                        except Exception:
                            pass
                loan_number = f"{prefix}L{max_idx + 1}"

            # Check unique loan number — raise 400 here so it propagates correctly
            existing_l = await conn.fetchval("SELECT loanid FROM loan_data WHERE loan_number = $1", loan_number)
            if existing_l:
                raise HTTPException(status_code=400, detail=f"Loan number {loan_number} already exists.")

            # Ensure date is parsed correctly
            loan_date = datetime.fromisoformat(l['date'].replace('Z', '+00:00')) if isinstance(l['date'], str) else l['date']

            loan_row = await conn.fetchrow("""
                INSERT INTO loan_data (customerId, particulars, particulars_qty, number_of_items, weight,
                net_weight, principle_amount, interest, tenure, loan_number, loanStatus, role, date,
                loanType, refreshprincipleamount, refreshinterest, deduction)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) RETURNING *
            """, customer_id, l['particulars'], l.get('particulars_qty'), l['number_of_items'], Decimal(str(l['weight'])), Decimal(str(l['net_weight'])),
               Decimal(str(l['principle_amount'])), Decimal(str(l['interest'])), int(l['tenure']), loan_number, '1', request.role, loan_date,
               'open', Decimal(str(l['principle_amount'])), Decimal("0.00"), Decimal(str(l['deduction'])))

            # 3. Create 'newLoan' Statement
            await conn.execute("""
                INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, loan_row['loanid'], loan_number, Decimal("0.00"), loan_date, Decimal("0.00"), Decimal("0.00"), Decimal(str(l['principle_amount'])), Decimal("0.00"), 'newLoan')

            # 4. Process Collections Sequentially
            sorted_collections = sorted(request.collections, key=lambda x: x.date)
            for coll in sorted_collections:
                await process_collection(conn, loan_number, coll.amount, coll.type, coll.date)

            await log_audit_action(conn, request.role, "IMPORT_HISTORY", "LOAN", loan_number, f"Imported loan with {len(sorted_collections)} historical entries.")

            return {"message": "History imported successfully", "loan_number": loan_number}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in import_history: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/preview_import")
async def preview_import(request: HistoryImportRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    tx = conn.transaction()
    await tx.start()
    try:
        # 1. Handle Customer
        customer_id = request.selectedCustomerId
        if request.customerType == "new":
            c = request.customerData
            existing_c = await conn.fetchrow("SELECT customerid FROM customers WHERE phone = $1", c['phone'])
            if existing_c:
                customer_id = existing_c['customerid']
            else:
                customer_row = await conn.fetchrow("""
                    INSERT INTO customers (customerName, phone, address, loanStatus, role, user_id)
                    VALUES ($1, $2, $3, $4, $5, $6) RETURNING customerid
                """, c['customerName'], c['phone'], c['address'], '1', request.role, c.get('user_id', 'admin'))
                customer_id = customer_row['customerid']
        elif not customer_id:
            customer_id = 999999

        # 2. Create Loan
        l = request.loanData
        loan_number = l.get('loan_number') or "PREVIEW_LOAN_001"
        loan_date = datetime.fromisoformat(l['date'].replace('Z', '+00:00')) if isinstance(l['date'], str) else l['date']

        loan_row = await conn.fetchrow("""
            INSERT INTO loan_data (customerId, particulars, particulars_qty, number_of_items, weight,
            net_weight, principle_amount, interest, tenure, loan_number, loanStatus, role, date,
            loanType, refreshprincipleamount, refreshinterest, deduction)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17) RETURNING *
        """, customer_id, l['particulars'], l.get('particulars_qty'), l['number_of_items'], Decimal(str(l['weight'])), Decimal(str(l['net_weight'])),
           Decimal(str(l['principle_amount'])), Decimal(str(l['interest'])), int(l['tenure']), loan_number, '1', request.role, loan_date,
           'open', Decimal(str(l['principle_amount'])), Decimal("0.00"), Decimal(str(l['deduction'])))

        # 3. Create 'newLoan' Statement
        await conn.execute("""
            INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, loan_row['loanid'], loan_number, Decimal("0.00"), loan_date, Decimal("0.00"), Decimal("0.00"), Decimal(str(l['principle_amount'])), Decimal("0.00"), 'newLoan')

        # 4. Process Collections Sequentially
        sorted_collections = sorted(request.collections, key=lambda x: x.date)
        for coll in sorted_collections:
            await process_collection(conn, loan_number, coll.amount, coll.type, coll.date)

        # 5. Final automatic compounding up to today
        latest_stmt = await conn.fetchrow("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC LIMIT 1", loan_number)
        await check_and_apply_historical_compounding(conn, loan_row, latest_stmt, datetime.now().date())

        rows = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC", loan_number)
        statements = [dict(r) for r in rows]
        return statements
    except HTTPException:
        await tx.rollback()
        raise
    except Exception as e:
        print(f"Error in preview_import: {e}")
        await tx.rollback()
        raise HTTPException(status_code=500, detail="Internal Server Error")
    finally:
        # Rollback is idempotent if already rolled back above; ensures cleanup on success path
        try:
            await tx.rollback()
        except Exception:
            pass

@app.get("/statement")
async def get_all_statements(limit: int = 200, offset: int = 0, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    """Returns paginated statement records. Default limit=200."""
    rows = await conn.fetch("SELECT * FROM statement ORDER BY statementid DESC LIMIT $1 OFFSET $2", limit, offset)
    return [dict(r) for r in rows]

@app.get("/statement/{loan_number}")
async def get_statement_by_loan(loan_number: str, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC", loan_number)
    if not rows:
        raise HTTPException(status_code=404, detail=f"No statement data found for loan_number {loan_number}")
    return [dict(r) for r in rows]

@app.get("/single_loan/{loan_number}")
async def get_single_loan(loan_number: str, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM loan_data WHERE loan_number = $1", loan_number)
    if not rows:
         raise HTTPException(status_code=404, detail=f"No loan data found for loan_number {loan_number}")
    return [dict(r) for r in rows]

@app.put("/refresh_loan")
async def refresh_loan(payload: dict, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    principal = Decimal(str(payload.get("refreshprincipleamount") or 0))
    interest = Decimal(str(payload.get("refreshinterest") or 0))
    row = await conn.fetchrow("""
        UPDATE loan_data SET refreshprincipleamount = $1, refreshinterest = $2 WHERE loan_number = $3 RETURNING *
    """, principal, interest, payload.get("loan_number"))
    if not row:
        raise HTTPException(status_code=404, detail="Loan not found")
    return {"message": "Successfully updated loan refresh", "loanData": dict(row)}

@app.post("/update-particulars")
async def update_particulars(payload: dict, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    # Use RETURNING to safely check if a row was actually updated
    row = await conn.fetchrow(
        "UPDATE loan_data SET particulars = $1 WHERE loan_number = $2 RETURNING loan_number",
        payload.get("new_particulars"), payload.get("loan_number")
    )
    if not row:
        raise HTTPException(status_code=404, detail="Loan not found")
    return {"message": "Particulars updated successfully"}

@app.post("/edit_loan/{loan_number}")
async def edit_loan(loan_number: str, req: EditLoanRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        async with conn.transaction():
            statements = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC", loan_number)
            loan_data = await conn.fetchrow("SELECT * FROM loan_data WHERE loan_number = $1", loan_number)
            if not statements or not loan_data:
                 raise HTTPException(status_code=404, detail=f"No loan found with loan_number {loan_number}")
            
            status = calculate_loan_status(loan_data, statements[0])
            principle_to_add = Decimal(str(req.principleAmount or 0))
            updated_principal = status['current_principal'] + principle_to_add
            
            new_stmt = await conn.fetchrow("""
                INSERT INTO statement (loanId, loan_number, amountPaid, date, currentPrincipal, currentInterest, principleBalance, interestBalance, transactionType)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING *
            """, loan_data['loanid'], loan_number, principle_to_add, datetime.now(), Decimal("0.00"), Decimal("0.00"), updated_principal, status['current_interest'], req.transactionType)
            
            await log_audit_action(conn, req.role, "EDIT_LOAN", "LOAN", loan_number, f"Action: {req.transactionType}, Principal Change: {principle_to_add}")
            
            return {"message": "Loan details updated successfully", "loanData": dict(new_stmt)}
    except Exception as e:
        print(f"Error in edit_loan: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/audit_logs")
async def get_audit_logs(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    rows = await conn.fetch("SELECT * FROM audit_logs ORDER BY timestamp DESC")
    return [dict(r) for r in rows]

@app.get("/admin_summary")
async def get_admin_summary(force_refresh: bool = False, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    if force_refresh:
        # Full re-calculation — fetch all open loans AND their latest statements in 2 queries (not N+1)
        loans = await conn.fetch("SELECT * FROM loan_data WHERE loantype = 'open'")
        latest_stmts = await conn.fetch("""
            SELECT DISTINCT ON (loan_number) *
            FROM statement
            WHERE loan_number = ANY($1::varchar[])
            ORDER BY loan_number, date DESC, statementid DESC
        """, [loan['loan_number'] for loan in loans])
        stmt_map = {s['loan_number']: dict(s) for s in latest_stmts}

        total_principal = Decimal("0.00")
        total_interest = Decimal("0.00")
        updates = []
        for loan in loans:
            latest_stmt = stmt_map.get(loan['loan_number'])
            if not latest_stmt:
                continue
            status = calculate_loan_status(loan, latest_stmt)
            total_principal += status['current_principal']
            total_interest += status['current_interest']
            updates.append((status['current_principal'], status['current_interest'], loan['loan_number']))

        # Batch update using executemany instead of one UPDATE per loan
        if updates:
            await conn.executemany(
                "UPDATE loan_data SET refreshprincipleamount = $1, refreshinterest = $2 WHERE loan_number = $3",
                updates
            )
    else:
        # Fast aggregation using already synced columns
        res = await conn.fetchrow("""
            SELECT SUM(refreshprincipleamount) as total_p, SUM(refreshinterest) as total_i
            FROM loan_data WHERE loantype = 'open'
        """)
        total_principal = res['total_p'] or Decimal("0.00")
        total_interest = res['total_i'] or Decimal("0.00")

    return {"total_principal": total_principal, "total_interest": total_interest}


@app.get("/loan_summary/{loan_number}")
async def get_loan_summary(loan_number: str, is_closing: bool = False, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    statements = await conn.fetch("SELECT * FROM statement WHERE loan_number = $1 ORDER BY date DESC, statementid DESC", loan_number)
    loan_data = await conn.fetchrow("SELECT * FROM loan_data WHERE loan_number = $1", loan_number)
    if not statements:
        if not loan_data:
             raise HTTPException(status_code=404, detail="Loan not found")
        return {"loan_number": loan_number, "current_principal": loan_data['principle_amount'], "current_interest": Decimal("0.00"), "days_since_last_payment": 0, "total_outstanding": loan_data['principle_amount'], "statements": []}
    status = calculate_loan_status(loan_data, statements[0], is_closing=is_closing)
    return {"loan_number": loan_number, "current_principal": status['current_principal'], "current_interest": status['current_interest'], "days_since_last_payment": status['days_since_last_payment'], "total_outstanding": status['current_principal'] + status['current_interest'], "statements": [dict(s) for s in statements]}

@app.get("/overdue_loans")
async def get_overdue_loans(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        query = """
            SELECT 
                ld.loan_number, ld.date, ld.tenure, ld.refreshprincipleamount, ld.refreshinterest, ld.follow_up_date,
                c.customername, c.phone,
                CASE WHEN ld.follow_up_date > CURRENT_DATE THEN 1 ELSE 0 END as is_followed_up
            FROM loan_data ld
            JOIN customers c ON ld.customerid = c.customerid
            WHERE ld.loantype = 'open'
              AND CURRENT_DATE > (ld.date + (COALESCE(ld.tenure, 0) || ' months')::interval)
            ORDER BY is_followed_up ASC, ld.date ASC
        """
        rows = await conn.fetch(query)
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Overdue Loans Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.put("/update_follow_up/{loan_number}")
async def update_follow_up(loan_number: str, payload: dict, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    follow_up_date = payload.get("follow_up_date")
    try:
        date_obj = datetime.strptime(follow_up_date, "%Y-%m-%d").date() if follow_up_date else None
        
        row = await conn.fetchrow("""
            UPDATE loan_data SET follow_up_date = $1 WHERE loan_number = $2 RETURNING loan_number, follow_up_date
        """, date_obj, loan_number)
        
        if not row:
            raise HTTPException(status_code=404, detail="Loan not found")
        return {"message": "Follow-up date updated", "loan_number": row["loan_number"], "follow_up_date": row["follow_up_date"]}
    except Exception as e:
        print(f"Update Follow Up Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/analytics_data")
async def get_analytics_data(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        now_date = datetime.now().date()
        
        # Aggregate KPI data efficiently
        kpis_row = await conn.fetchrow("""
            SELECT 
                SUM(refreshprincipleamount) as total_portfolio,
                COUNT(*) as active_loans,
                SUM(weight) as total_weight
            FROM loan_data WHERE loantype = 'open'
        """)
        
        closed_count = await conn.fetchval("SELECT COUNT(*) FROM loan_data WHERE loantype = 'closed'")
        
        # Risk Aging - still need some date logic, but can be done in SQL
        risk_agg = await conn.fetchrow("""
            SELECT 
                SUM(CASE WHEN (CURRENT_DATE - latest_date) > 90 THEN refreshprincipleamount ELSE 0 END) as risk_90,
                SUM(CASE WHEN (CURRENT_DATE - latest_date) BETWEEN 31 AND 90 THEN refreshprincipleamount ELSE 0 END) as risk_31_90,
                SUM(CASE WHEN (CURRENT_DATE - latest_date) BETWEEN 1 AND 30 THEN refreshprincipleamount ELSE 0 END) as risk_1_30
            FROM (
                SELECT ld.refreshprincipleamount, COALESCE(MAX(s.date), ld.date)::date as latest_date
                FROM loan_data ld
                LEFT JOIN statement s ON ld.loan_number = s.loan_number
                WHERE ld.loantype = 'open'
                GROUP BY ld.loanid
            ) t
        """)
        
        aging_counts = await conn.fetch("""
            SELECT 
                CASE 
                    WHEN (CURRENT_DATE - latest_date) <= 30 THEN '0-30'
                    WHEN (CURRENT_DATE - latest_date) <= 60 THEN '31-60'
                    WHEN (CURRENT_DATE - latest_date) <= 90 THEN '61-90'
                    ELSE '90+'
                END as range,
                COUNT(*) as value
            FROM (
                SELECT COALESCE(MAX(s.date), ld.date)::date as latest_date
                FROM loan_data ld
                LEFT JOIN statement s ON ld.loan_number = s.loan_number
                WHERE ld.loantype = 'open'
                GROUP BY ld.loanid
            ) t
            GROUP BY range
        """)

        # Use live gold price from the scraper cron (falls back to default if scrape failed)
        GOLD_PRICE = LIVE_GOLD_DATA["current"]
        total_open_principal = kpis_row['total_portfolio'] or Decimal("0.00")
        total_weight = kpis_row['total_weight'] or Decimal("0.00")
        avg_ltv = (total_open_principal / (total_weight * GOLD_PRICE)) * 100 if total_weight > 0 else Decimal("0.00")

        # Today's stats — batched into a single query to avoid 7 sequential round-trips
        today_stats = await conn.fetchrow("""
            SELECT
                COALESCE((SELECT SUM(principle_amount) FROM loan_data WHERE DATE(date) = $1), 0) AS disbursed_today,
                COALESCE((SELECT COUNT(*) FROM loan_data WHERE DATE(date) = $1), 0) AS disbursed_today_count,
                COALESCE((SELECT SUM(amountPaid) FROM statement WHERE DATE(date) = $1 AND transactionType IN ('addColl', 'writeoff')), 0) AS collected_today,
                COALESCE((SELECT COUNT(*) FROM statement WHERE DATE(date) = $1 AND transactionType IN ('addColl', 'writeoff')), 0) AS collected_today_count,
                COALESCE((SELECT SUM(amountPaid) FROM statement WHERE DATE(date) = $1 AND transactionType = 'addColl' AND currentInterest > 0), 0) AS interest_today,
                COALESCE((SELECT COUNT(*) FROM loan_data WHERE loantype = 'closed' AND DATE(date) = $1), 0) AS closed_today,
                COALESCE((SELECT SUM(t.net_weight) FROM (
                    SELECT DISTINCT ON (ld.loan_number) ld.net_weight
                    FROM statement s
                    JOIN loan_data ld ON s.loan_number = ld.loan_number
                    WHERE ld.loantype = 'closed' AND DATE(s.date) = $1
                    AND s.transactiontype IN ('addColl','writeoff','closure')
                ) t), 0) AS gold_collected_today
        """, now_date)
        disbursed_today = today_stats['disbursed_today']
        disbursed_today_count = today_stats['disbursed_today_count']
        collected_today = today_stats['collected_today']
        collected_today_count = today_stats['collected_today_count']
        interest_today = today_stats['interest_today']
        closed_today = today_stats['closed_today']
        gold_collected_today = today_stats['gold_collected_today']

        # Recent Transactions
        recent_txs = await conn.fetch("""
            SELECT s.*, ld.particulars, c.customername 
            FROM statement s 
            JOIN loan_data ld ON s.loan_number = ld.loan_number 
            JOIN customers c ON ld.customerid = c.customerid 
            ORDER BY s.statementid DESC LIMIT 8
        """)

        # Branch Data
        branch_agg = await conn.fetch("""
            SELECT role, COUNT(*) as active, SUM(principle_amount) as disbursed 
            FROM loan_data 
            WHERE loantype = 'open' 
            GROUP BY role
        """)
        
        branch_map = {"Admin": "Main HQ (Admin)", "User1": "Santhwanam", "User2": "Swathantra"}
        real_branch_data = []
        for row in branch_agg:
            role = row['role'] or "Unknown"
            real_branch_data.append({
                "name": branch_map.get(role, role),
                "active": row['active'],
                "disbursed": float(row['disbursed'] or 0)
            })

        # Trends Data (Last 6 months)
        trends_rows = await conn.fetch("""
            WITH months AS (
                SELECT date_trunc('month', CURRENT_DATE - (i || ' months')::interval) as month_start
                FROM generate_series(0, 5) i
            ),
            disbursed_stats AS (
                SELECT date_trunc('month', date) as m, SUM(principle_amount) as total
                FROM loan_data
                WHERE date > CURRENT_DATE - INTERVAL '6 months'
                GROUP BY 1
            ),
            collected_stats AS (
                SELECT date_trunc('month', date) as m, SUM(amountPaid) as total
                FROM statement
                WHERE date > CURRENT_DATE - INTERVAL '6 months'
                AND transactionType IN ('addColl', 'writeoff')
                GROUP BY 1
            )
            SELECT 
                TO_CHAR(months.month_start, 'Mon') as month,
                COALESCE(disbursed_stats.total, 0) as disbursed,
                COALESCE(collected_stats.total, 0) as collected
            FROM months
            LEFT JOIN disbursed_stats ON months.month_start = disbursed_stats.m
            LEFT JOIN collected_stats ON months.month_start = collected_stats.m
            ORDER BY months.month_start ASC
        """)
        trends_data = [
            {
                "month": r['month'],
                "disbursed": float(r['disbursed']),
                "collected": float(r['collected'])
            } for r in trends_rows
        ]

        return {
            "kpis": {
                "total_portfolio": total_open_principal,
                "active_loans": kpis_row['active_loans'] or 0,
                "total_weight": total_weight,
                "closed_loans": closed_count,
                "risk_90": risk_agg['risk_90'] or Decimal("0.00"),
                "risk_31_90": risk_agg['risk_31_90'] or Decimal("0.00"),
                "risk_1_30": risk_agg['risk_1_30'] or Decimal("0.00"),
                "total_collected": await conn.fetchval("SELECT SUM(amountPaid) FROM statement WHERE transactionType IN ('addColl', 'writeoff')") or Decimal("0.00"),
                "avg_ltv": round_decimal(avg_ltv),
                "disbursed_today": disbursed_today,
                "disbursed_today_count": disbursed_today_count,
                "collected_today": collected_today,
                "collected_today_count": collected_today_count,
                "interest_today": interest_today,
                "closed_today": closed_today,
                "gold_collected_today": gold_collected_today
            },
            "aging": [dict(r) for r in aging_counts],
            "trends": trends_data,
            "recent_transactions": [dict(r) for r in recent_txs],
            "gold_price": {"current": GOLD_PRICE, "change": LIVE_GOLD_DATA["change"]},
            "branch_data": real_branch_data
        }
    except Exception as e:
        print(f"Analytics Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/performance_summary")
async def get_performance_summary(
    start_date: str = None,
    end_date: str = None,
    conn: asyncpg.Connection = Depends(get_db),
    api_key=Depends(verify_api_key)
):
    """Returns the 6 performance card values for a given date range."""
    try:
        now = datetime.now().date()
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else now
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else now

        # Dates stored as naive IST timestamps — use DATE() directly (no timezone conversion)
        disbursed = await conn.fetchval(
            "SELECT SUM(principle_amount) FROM loan_data WHERE DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0
        disbursed_count = await conn.fetchval(
            "SELECT COUNT(*) FROM loan_data WHERE DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0
        interest_collected = await conn.fetchval(
            "SELECT SUM(amountpaid) FROM statement WHERE DATE(date) BETWEEN $1 AND $2 AND transactiontype = 'addColl' AND currentinterest > 0",
            s_date, e_date
        ) or 0
        total_collected = await conn.fetchval(
            "SELECT SUM(amountpaid) FROM statement WHERE DATE(date) BETWEEN $1 AND $2 AND transactiontype IN ('addColl','writeoff')",
            s_date, e_date
        ) or 0
        collected_count = await conn.fetchval(
            "SELECT COUNT(*) FROM statement WHERE DATE(date) BETWEEN $1 AND $2 AND transactiontype IN ('addColl','writeoff')",
            s_date, e_date
        ) or 0
        principle_collected = max(0, float(total_collected) - float(interest_collected))

        # Closures: count loans closed where the closing statement falls in the date range
        closures_stmt = await conn.fetchval(
            """SELECT COUNT(DISTINCT ld.loan_number) FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                WHERE ld.loantype = 'closed' AND DATE(s.date) BETWEEN $1 AND $2
                AND s.transactiontype IN ('addColl','writeoff','closure')""",
            s_date, e_date
        ) or 0
        # Also count loans whose creation date falls in range and are now closed
        closures_loan = await conn.fetchval(
            "SELECT COUNT(DISTINCT loan_number) FROM loan_data WHERE loantype = 'closed' AND DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0
        closures = max(int(closures_loan), int(closures_stmt))

        # Gold weight disbursed in the period
        gold_disbursed = await conn.fetchval(
            "SELECT SUM(net_weight) FROM loan_data WHERE DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0

        # Gold weight collected in the period (released from closed loans)
        gold_collected = await conn.fetchval(
            """SELECT SUM(t.net_weight) FROM (
                SELECT DISTINCT ON (ld.loan_number) ld.net_weight 
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                WHERE ld.loantype = 'closed' AND DATE(s.date) BETWEEN $1 AND $2
                AND s.transactiontype IN ('addColl','writeoff','closure')
            ) t""",
            s_date, e_date
        ) or 0

        # Compounded Principal in the period
        compounded = await conn.fetchval(
            "SELECT SUM(currentPrincipal) FROM statement WHERE transactionType = 'compounding' AND DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0
        compounded_count = await conn.fetchval(
            "SELECT COUNT(DISTINCT loan_number) FROM statement WHERE transactionType = 'compounding' AND DATE(date) BETWEEN $1 AND $2",
            s_date, e_date
        ) or 0

        print(f"[PerfSummary] {s_date}->{e_date}: disbursed={disbursed}, total_collected={total_collected}, compounded={compounded}, closures={closures}, gold_d={gold_disbursed}g, gold_c={gold_collected}g")

        return {
            "disbursed": float(disbursed),
            "disbursed_count": int(disbursed_count),
            "interest_collected": float(interest_collected),
            "principle_collected": float(principle_collected),
            "total_collected": float(total_collected),
            "collected_count": int(collected_count),
            "new_loans": int(disbursed_count),
            "compounded": float(compounded),
            "compounded_count": int(compounded_count),
            "closures": int(closures),
            "gold_weight": float(gold_disbursed),
            "gold_disbursed": float(gold_disbursed),
            "gold_collected": float(gold_collected),
        }
    except Exception as e:
        print(f"Performance Summary Error: {e}")
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.get("/analytics_details/{detail_type}")
async def get_analytics_details(
    detail_type: str,
    start_date: str = None,
    end_date: str = None,
    conn: asyncpg.Connection = Depends(get_db),
    api_key=Depends(verify_api_key)
):
    """Returns drill-down data for each clickable card in the analytics dashboard."""
    try:
        now_date = datetime.now().date()
        s_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else now_date
        e_date = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else now_date
        period_label = f"{s_date} to {e_date}" if s_date != e_date else str(s_date)

        if detail_type == "disbursed_today":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.principle_amount, ld.date, ld.particulars, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(ld.date) BETWEEN $1 AND $2
                ORDER BY ld.date DESC
            """, s_date, e_date)
            return {
                "title": f"Amount Disbursed ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Amount", "Date", "Particulars", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["principle_amount"] or 0),
                        "date": str(r["date"])[:10],
                        "particulars": r["particulars"],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["principle_amount"] or 0) for r in rows)
            }

        elif detail_type == "interest_collected":
            rows = await conn.fetch("""
                SELECT s.loan_number, c.customername, c.phone, s.amountpaid, s.currentinterest, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(s.date) BETWEEN $1 AND $2 AND s.transactiontype = 'addColl' AND s.currentinterest > 0
                ORDER BY s.date DESC
            """, s_date, e_date)
            return {
                "title": f"Interest Collected ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Amount Paid", "Interest Portion", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["amountpaid"] or 0),
                        "interest_portion": float(r["currentinterest"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["amountpaid"] or 0) for r in rows)
            }

        elif detail_type == "principle_collected":
            rows = await conn.fetch("""
                SELECT s.loan_number, c.customername, c.phone, s.amountpaid, s.currentprincipal, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(s.date) BETWEEN $1 AND $2 AND s.transactiontype IN ('addColl', 'writeoff') AND s.currentprincipal > 0
                ORDER BY s.date DESC
            """, s_date, e_date)
            return {
                "title": f"Principal Collected ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Amount Paid", "Principal Portion", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["amountpaid"] or 0),
                        "principal_portion": float(r["currentprincipal"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["amountpaid"] or 0) for r in rows)
            }

        elif detail_type == "total_collected":
            rows = await conn.fetch("""
                SELECT s.loan_number, c.customername, c.phone, s.amountpaid, s.transactiontype, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(s.date) BETWEEN $1 AND $2 AND s.transactiontype IN ('addColl', 'writeoff')
                ORDER BY s.date DESC
            """, s_date, e_date)
            return {
                "title": f"Total Amount Collected ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Amount", "Type", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["amountpaid"] or 0),
                        "type": r["transactiontype"],
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["amountpaid"] or 0) for r in rows)
            }

        elif detail_type == "new_loans":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.principle_amount, ld.interest, ld.particulars, ld.date, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(ld.date) BETWEEN $1 AND $2
                ORDER BY ld.date DESC
            """, s_date, e_date)
            return {
                "title": f"New Loans ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Amount", "Interest %", "Particulars", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["principle_amount"] or 0),
                        "interest": float(r["interest"] or 0),
                        "particulars": r["particulars"],
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": len(rows)
            }

        elif detail_type == "closures":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.principle_amount, ld.date, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE ld.loantype = 'closed' AND DATE(ld.date) BETWEEN $1 AND $2
                ORDER BY ld.date DESC
            """, s_date, e_date)
            stmt_rows = await conn.fetch("""
                SELECT DISTINCT s.loan_number, c.customername, c.phone, ld.principle_amount, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE ld.loantype = 'closed' AND DATE(s.date) BETWEEN $1 AND $2
                AND s.transactiontype IN ('addColl', 'writeoff', 'closure')
                ORDER BY s.date DESC
            """, s_date, e_date)
            seen = set()
            result_rows = []
            for r in list(rows) + list(stmt_rows):
                if r["loan_number"] not in seen:
                    seen.add(r["loan_number"])
                    result_rows.append({
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["principle_amount"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    })
            return {
                "title": f"Closures ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Principal Amount", "Date", "Branch"],
                "rows": result_rows,
                "total": len(result_rows)
            }

        elif detail_type == "gold_collected":
            rows = await conn.fetch("""
                SELECT DISTINCT ON (ld.loan_number) ld.loan_number, c.customername, c.phone, ld.net_weight, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE ld.loantype = 'closed' AND DATE(s.date) BETWEEN $1 AND $2
                AND s.transactiontype IN ('addColl', 'writeoff', 'closure')
                ORDER BY ld.loan_number, s.date DESC
            """, s_date, e_date)
            return {
                "title": f"Gold Collected ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Gold Weight (g)", "Closed Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "weight": float(r["net_weight"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["net_weight"] or 0) for r in rows)
            }

        elif detail_type == "gold_disbursed" or detail_type == "gold_weight":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.net_weight, ld.date, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(ld.date) BETWEEN $1 AND $2
                ORDER BY ld.date DESC
            """, s_date, e_date)
            return {
                "title": f"Gold Disbursed ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Gold Weight (g)", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "weight": float(r["net_weight"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["net_weight"] or 0) for r in rows)
            }

        elif detail_type == "compounded":
            rows = await conn.fetch("""
                SELECT s.loan_number, c.customername, c.phone, s.currentprincipal, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE DATE(s.date) BETWEEN $1 AND $2 AND s.transactiontype = 'compounding'
                ORDER BY s.date DESC
            """, s_date, e_date)
            return {
                "title": f"Compounded Principal ({period_label})",
                "columns": ["Loan #", "Customer", "Phone", "Compounded Amount", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["currentprincipal"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["currentprincipal"] or 0) for r in rows)
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown detail type: {detail_type}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Analytics Details Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@app.post("/backup/manual")
async def manual_backup(api_key=Depends(verify_api_key)):
    """Triggers a manual database backup."""
    from services import create_json_backup
    try:
        os.makedirs("Backups", exist_ok=True)
        async with database.pool.acquire() as conn:
            backup_json = await create_json_backup(conn)
            backup_path = "Backups/finance_backup.json"
            with open(backup_path, "w") as f:
                f.write(backup_json)
            return {"message": "Backup created successfully.", "path": backup_path}
    except Exception as e:
        print(f"Manual Backup Error: {e}")
        raise HTTPException(status_code=500, detail="Backup generation failed.")

@app.get("/backup/status")
async def backup_status(api_key=Depends(verify_api_key)):
    """Returns the exact timestamp of the last backup file creation."""
    backup_path = "Backups/finance_backup.json"
    abs_path = os.path.abspath(backup_path)
    if os.path.exists(backup_path):
        mtime = os.path.getmtime(backup_path)
        last_dt = datetime.fromtimestamp(mtime).isoformat()
        return {"last_backup": last_dt, "path": abs_path}
    return {"last_backup": None, "path": abs_path}

@app.get("/backup/download")
async def download_backup(api_key=Depends(verify_api_key)):
    """Downloads the latest database backup."""
    backup_path = "Backups/finance_backup.json"
    if not os.path.exists(backup_path):
        raise HTTPException(status_code=404, detail="No backup file found.")
    return FileResponse(path=backup_path, filename="finance_backup.json", media_type="application/json")

@app.post("/backup/restore")
async def restore_backup(file: UploadFile = File(...), api_key=Depends(verify_api_key)):
    """Restores database from uploaded JSON backup file."""
    from services import restore_from_json
    try:
        content = await file.read()
        data = json.loads(content)
        async with database.pool.acquire() as conn:
            async with conn.transaction():
                await restore_from_json(conn, data)
        return {"message": "Database successfully restored from backup."}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file.")
    except Exception as e:
        print(f"Restore Error: {e}")
        raise HTTPException(status_code=500, detail=f"Database restore failed: {str(e)}")

@app.get("/admin_details/{detail_type}")
async def get_admin_details(detail_type: str, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    """Returns drill-down data for admin-specific KPI cards."""
    try:
        if detail_type == "principle_remaining":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.refreshprincipleamount as remaining, 
                       ld.principle_amount as original, ld.date, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE ld.loantype = 'open'
                ORDER BY ld.refreshprincipleamount DESC
            """)
            return {
                "title": "Principal Remaining (All Open Loans)",
                "columns": ["Loan #", "Customer", "Phone", "Remaining Principal", "Original Principal", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "remaining": float(r["remaining"] or 0),
                        "original": float(r["original"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["remaining"] or 0) for r in rows)
            }

        elif detail_type == "given_principle":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.principle_amount, ld.date, ld.role, ld.loantype
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                ORDER BY ld.date DESC
            """)
            return {
                "title": "Given Principal (All Loans Ever Disbursed)",
                "columns": ["Loan #", "Customer", "Phone", "Principal Given", "Date", "Branch", "Status"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "amount": float(r["principle_amount"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"],
                        "status": r["loantype"]
                    } for r in rows
                ],
                "total": sum(float(r["principle_amount"] or 0) for r in rows)
            }

        elif detail_type == "compounded_principle":
            rows = await conn.fetch("""
                SELECT s.loan_number, c.customername, c.phone, s.amountpaid as compounded_amount,
                       s.principlebalance as new_principal, s.date, ld.role
                FROM statement s
                JOIN loan_data ld ON s.loan_number = ld.loan_number
                JOIN customers c ON ld.customerid = c.customerid
                WHERE s.transactiontype = 'compounding'
                ORDER BY s.date DESC
            """)
            return {
                "title": "Compounded Principal Events",
                "columns": ["Loan #", "Customer", "Phone", "Compounded Amount", "New Principal Balance", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "compounded_amount": float(r["compounded_amount"] or 0),
                        "new_principal": float(r["new_principal"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["compounded_amount"] or 0) for r in rows)
            }

        elif detail_type == "interest_remaining":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.refreshinterest as interest_remaining, 
                       ld.refreshprincipleamount as principal, ld.interest as rate, ld.date, ld.role
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                WHERE ld.loantype = 'open' AND ld.refreshinterest > 0
                ORDER BY ld.refreshinterest DESC
            """)
            return {
                "title": "Interest Remaining (All Open Loans)",
                "columns": ["Loan #", "Customer", "Phone", "Interest Due", "Principal Balance", "Rate %", "Date", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "interest_remaining": float(r["interest_remaining"] or 0),
                        "principal": float(r["principal"] or 0),
                        "rate": float(r["rate"] or 0),
                        "date": str(r["date"])[:10],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": sum(float(r["interest_remaining"] or 0) for r in rows)
            }

        elif detail_type == "inactive_accounts":
            rows = await conn.fetch("""
                SELECT ld.loan_number, c.customername, c.phone, ld.refreshprincipleamount,
                       ld.refreshinterest, ld.date as loan_date, ld.role,
                       COALESCE(MAX(s.date), ld.date)::date as last_activity,
                       (CURRENT_DATE - COALESCE(MAX(s.date), ld.date)::date) as days_inactive
                FROM loan_data ld
                JOIN customers c ON ld.customerid = c.customerid
                LEFT JOIN statement s ON ld.loan_number = s.loan_number AND s.transactiontype IN ('addColl', 'writeoff')
                WHERE ld.loantype = 'open'
                GROUP BY ld.loan_number, c.customername, c.phone, ld.refreshprincipleamount, 
                         ld.refreshinterest, ld.date, ld.role
                HAVING (CURRENT_DATE - COALESCE(MAX(s.date), ld.date)::date) > 90
                ORDER BY days_inactive DESC
            """)
            return {
                "title": "Inactive Accounts (No payment > 90 days)",
                "columns": ["Loan #", "Customer", "Phone", "Principal Due", "Interest Due", "Last Activity", "Days Inactive", "Branch"],
                "rows": [
                    {
                        "loan_number": r["loan_number"],
                        "customername": r["customername"],
                        "phone": r["phone"],
                        "principal": float(r["refreshprincipleamount"] or 0),
                        "interest": float(r["refreshinterest"] or 0),
                        "last_activity": str(r["last_activity"]),
                        "days_inactive": r["days_inactive"],
                        "branch": r["role"]
                    } for r in rows
                ],
                "total": len(rows)
            }

        else:
            raise HTTPException(status_code=400, detail=f"Unknown detail type: {detail_type}")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Admin Details Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# ─────────────────────────────────────────────────────────
# SuperAdmin Endpoints
# ─────────────────────────────────────────────────────────

def require_superadmin(x_superadmin_key: str = Header(...)):
    """Validates a cryptographically-random session token issued at SuperAdmin login."""
    if x_superadmin_key not in _superadmin_sessions:
        raise HTTPException(status_code=403, detail="SuperAdmin access required.")

@app.post("/superadmin/authenticate")
async def superadmin_authenticate(auth: AuthRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    row = await conn.fetchrow("SELECT password, role FROM role WHERE LOWER(userName) = LOWER($1)", auth.userName)
    if row and row['role'] == 'SuperAdmin':
        is_valid = verify_password(auth.password, row['password'])
        if is_valid:
            # Issue a cryptographically-random session token
            token = secrets.token_urlsafe(32)
            _superadmin_sessions[token] = auth.userName
            return {"message": "SuperAdmin authentication successful", "role": "SuperAdmin", "session_token": token}
    raise HTTPException(status_code=401, detail="Invalid SuperAdmin credentials.")

@app.get("/superadmin/branches")
async def get_branches(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key), _=Depends(require_superadmin)):
    rows = await conn.fetch("""
        SELECT userName, role, display_name, logo, address, permissions FROM role
        WHERE role != 'SuperAdmin'
        ORDER BY userName
    """)
    return [dict(r) for r in rows]

@app.post("/superadmin/branches")
async def create_branch(branch: BranchCreate, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key), _=Depends(require_superadmin)):
    from security import get_password_hash
    existing = await conn.fetchval("SELECT 1 FROM role WHERE LOWER(userName) = LOWER($1)", branch.userName)
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{branch.userName}' already exists.")
    hashed = get_password_hash(branch.password)
    await conn.execute("""
        INSERT INTO role (userName, password, role, display_name, logo, address, permissions)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
    """, branch.userName, hashed, branch.userName, branch.display_name, branch.logo, branch.address, branch.permissions)
    return {"message": f"Branch '{branch.display_name}' created successfully."}

@app.put("/superadmin/branches/{username}")
async def update_branch(username: str, update: BranchUpdate, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key), _=Depends(require_superadmin)):
    row = await conn.fetchrow("SELECT 1 FROM role WHERE userName = $1", username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Branch '{username}' not found.")

    # Build a single UPDATE query with only the fields provided — avoids 4 round-trips
    fields = {}
    if update.display_name is not None:
        fields['display_name'] = update.display_name
    if update.logo is not None:
        fields['logo'] = update.logo
    if update.address is not None:
        fields['address'] = update.address
    if update.permissions is not None:
        fields['permissions'] = update.permissions

    if fields:
        set_clause = ", ".join(f"{col} = ${i+1}" for i, col in enumerate(fields))
        values = list(fields.values()) + [username]
        await conn.execute(
            f"UPDATE role SET {set_clause} WHERE userName = ${len(values)}",
            *values
        )
    return {"message": f"Branch '{username}' updated successfully."}

@app.post("/superadmin/reset_password/{username}")
async def reset_branch_password(username: str, req: ResetPasswordRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key), _=Depends(require_superadmin)):
    from security import get_password_hash
    row = await conn.fetchrow("SELECT 1 FROM role WHERE userName = $1", username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Branch '{username}' not found.")
    hashed = get_password_hash(req.new_password)
    await conn.execute("UPDATE role SET password = $1 WHERE userName = $2", hashed, username)
    return {"message": f"Password for '{username}' reset successfully."}

@app.delete("/superadmin/branches/{username}")
async def delete_branch(username: str, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key), _=Depends(require_superadmin)):
    row = await conn.fetchrow("SELECT role FROM role WHERE userName = $1", username)
    if not row:
        raise HTTPException(status_code=404, detail=f"Branch '{username}' not found.")
    if row['role'] in ('SuperAdmin', 'Admin'):
        raise HTTPException(status_code=403, detail="Cannot delete protected accounts.")
    await conn.execute("DELETE FROM role WHERE userName = $1", username)
    return {"message": f"Branch '{username}' deleted."}

@app.get("/branch-settings")
async def get_branch_settings(conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    """Public endpoint for main app to fetch branch display_name, logo, and permissions after login."""
    rows = await conn.fetch("SELECT userName, display_name, logo, address, permissions FROM role")
    result = {}
    for r in rows:
        result[r['username']] = {
            "display_name": r['display_name'],
            "logo": r['logo'],
            "address": r['address'],
            "permissions": (r['permissions'] or 'newcustomer,userlist,form1,analytics,report,history,backup').split(',')
        }
    return result

class FollowUpRequest(BaseModel):
    loan_number: str
    follow_up_date: str

# NOTE: The duplicate /overdue_loans GET route that was here has been removed.
# The canonical definition is at line ~610 above (with follow_up_date support).

@app.post("/set_follow_up")
async def set_follow_up(req: FollowUpRequest, conn: asyncpg.Connection = Depends(get_db), api_key=Depends(verify_api_key)):
    try:
        dt = datetime.strptime(req.follow_up_date, "%Y-%m-%d").date() if req.follow_up_date else None
        row = await conn.fetchrow(
            "UPDATE loan_data SET follow_up_date = $1 WHERE loan_number = $2 RETURNING loan_number",
            dt, req.loan_number
        )
        if not row:
            raise HTTPException(status_code=404, detail="Loan not found")
        return {"message": "Follow-up date updated"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error setting follow_up_date: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
