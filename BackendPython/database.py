import asyncpg
from typing import Optional
from config import DATABASE_URI, DB_USER, DB_PASS, DB_HOST, DB_PORT

pool: Optional[asyncpg.Pool] = None

async def init_db():
    global pool
    # Connect to the default postgres db first to create the 'myfin' database only in local dev
    if DB_USER and DB_HOST in ("localhost", "127.0.0.1"):
        try:
            sys_pool = await asyncpg.create_pool(
                user=DB_USER, password=DB_PASS, host=DB_HOST, port=DB_PORT, database="postgres"
            )
            async with sys_pool.acquire() as conn:
                try:
                    await conn.execute("CREATE DATABASE myfin")
                    print("Database created successfully")
                except asyncpg.exceptions.DuplicateDatabaseError:
                    print("Database already exists")
            await sys_pool.close()
        except Exception as e:
            print(f"Notice: Local database check/creation skipped: {e}")

    try:
        # Create pool for 'myfin' / Supabase (statement_cache_size=0 is required for pgbouncer)
        statement_cache = 0 if ("supabase" in DATABASE_URI or "pooler" in DATABASE_URI or ":6543" in DATABASE_URI) else None
        if statement_cache is not None:
            pool = await asyncpg.create_pool(DATABASE_URI, min_size=1, max_size=10, statement_cache_size=0)
        else:
            pool = await asyncpg.create_pool(DATABASE_URI, min_size=1, max_size=10)
        async with pool.acquire() as conn:
            # Create Tables matching Node.js exactly
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS customers (
                    customerId SERIAL PRIMARY KEY,
                    customerName VARCHAR(255),
                    phone VARCHAR(50) UNIQUE,
                    address VARCHAR(255),
                    loanStatus VARCHAR(20),
                    role VARCHAR(20) DEFAULT 'user',
                    user_id VARCHAR(100),
                    UNIQUE(customerId)
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS loan_data (
                    loanId SERIAL PRIMARY KEY,
                    customerId INTEGER REFERENCES customers(customerId) ON UPDATE CASCADE,
                    loanStatus VARCHAR(1) DEFAULT '0' CHECK (loanStatus IN ('0', '1', '2')),
                    particulars VARCHAR(255),
                    particulars_qty VARCHAR(255),
                    loan_number VARCHAR(255) UNIQUE,
                    number_of_items VARCHAR(255),
                    weight DECIMAL(15, 2),  
                    net_weight DECIMAL(15, 2),  
                    principle_amount DECIMAL(15, 2),
                    interest DECIMAL(15, 2),
                    tenure INTEGER,
                    deduction DECIMAL(15, 2),
                    role VARCHAR(20) DEFAULT 'user',
                    date TIMESTAMPTZ,
                    loanType VARCHAR(10),
                    refreshprincipleamount DECIMAL(15, 2),
                    refreshinterest DECIMAL(15, 2)
                );
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS statement (
                    statementId SERIAL PRIMARY KEY,
                    loanId INTEGER REFERENCES loan_data(loanId) ON UPDATE CASCADE,
                    loan_number VARCHAR(255),
                    amountPaid DECIMAL(15, 2) DEFAULT 0,
                    date TIMESTAMPTZ,
                    currentPrincipal DECIMAL(15, 2),
                    currentInterest DECIMAL(15, 2),
                    principleBalance DECIMAL(15, 2),
                    interestBalance DECIMAL(15, 2),
                    transactionType VARCHAR(30)
                );
            """)

            # Add UNIQUE constraint to loan_number if missing (defensive)
            await conn.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'loan_data_loan_number_key') THEN
                        ALTER TABLE loan_data ADD CONSTRAINT loan_data_loan_number_key UNIQUE (loan_number);
                    END IF;
                END $$;
            """)

            # Add unique index on statement to prevent duplicate initial statements per loanId
            await conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS unique_initial_statement_pct 
                ON statement (loan_number) 
                WHERE transactionType = 'newLoan';
            """)

            # Performance indexes for frequently queried columns
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_statement_loan_number ON statement(loan_number);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_statement_date ON statement(date);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_statement_transaction_type ON statement(transactionType);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_loan_data_loantype ON loan_data(loantype);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_loan_data_customerid ON loan_data(customerid);
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_loan_data_date ON loan_data(date);
            """)

            # Trigger logic
            trigger_check = await conn.fetchval("""
                SELECT 1 FROM pg_trigger
                WHERE tgname = 'update_customer_loan_status_trigger'
            """)
            if not trigger_check:
                await conn.execute("""
                    CREATE OR REPLACE FUNCTION update_customer_loan_status()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        UPDATE customers
                        SET loanStatus = NEW.loanStatus
                        WHERE customerId = NEW.customerId;
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    
                    CREATE TRIGGER update_customer_loan_status_trigger
                    AFTER INSERT ON loan_data
                    FOR EACH ROW
                    EXECUTE FUNCTION update_customer_loan_status();
                """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS role (
                    userName VARCHAR(255) PRIMARY KEY,
                    password VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'user',
                    display_name VARCHAR(255),
                    logo TEXT
                );
            """)

            # Add new columns defensively if they don't exist yet
            await conn.execute("""
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='role' AND column_name='display_name') THEN
                        ALTER TABLE role ADD COLUMN display_name VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='role' AND column_name='logo') THEN
                        ALTER TABLE role ADD COLUMN logo TEXT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='role' AND column_name='address') THEN
                        ALTER TABLE role ADD COLUMN address TEXT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='role' AND column_name='permissions') THEN
                        ALTER TABLE role ADD COLUMN permissions TEXT DEFAULT 'newcustomer,userlist,form1,analytics,report,history,backup';
                    END IF;
                    
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='loan_data' AND column_name='follow_up_date') THEN
                        ALTER TABLE loan_data ADD COLUMN follow_up_date DATE;
                    END IF;
                END $$;
            """)

            from security import get_password_hash
            hashed_pwd = get_password_hash("1234")
            hashed_super = get_password_hash("super1234")

            await conn.execute("""
                INSERT INTO role (userName, password, role, display_name)
                VALUES 
                    ('Admin', $1, 'Admin', 'Admin Branch'),
                    ('User1', $1, 'User1', 'Santhwanam'),
                    ('User2', $1, 'User2', 'Swathantra')
                ON CONFLICT (userName) DO UPDATE SET display_name = EXCLUDED.display_name;
            """, hashed_pwd)

            # Backfill display_name for existing rows where it was never set
            await conn.execute("""
                UPDATE role SET display_name = CASE
                    WHEN userName = 'Admin' THEN 'Admin Branch'
                    WHEN userName = 'User1' THEN 'Santhwanam'
                    WHEN userName = 'User2' THEN 'Swathantra'
                    WHEN userName = 'SuperAdmin' THEN 'Super Administrator'
                    ELSE userName
                END
                WHERE display_name IS NULL OR display_name = '';
            """)

            # Backfill permissions for existing rows where it was never set
            await conn.execute("""
                UPDATE role SET permissions = 'newcustomer,userlist,form1,analytics,report,history,backup'
                WHERE permissions IS NULL OR permissions = '';
            """)

            await conn.execute("""
                INSERT INTO role (userName, password, role, display_name)
                VALUES ('SuperAdmin', $1, 'SuperAdmin', 'Super Administrator')
                ON CONFLICT (userName) DO UPDATE SET display_name = EXCLUDED.display_name;
            """, hashed_super)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id SERIAL PRIMARY KEY,
                    username VARCHAR(255),
                    action VARCHAR(100),
                    entity_type VARCHAR(50),
                    entity_id VARCHAR(100),
                    details TEXT,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                );
            """)

            print("Tables created successfully.")
    except Exception as e:
        print(f"Error initializing DB schema: {e}")

async def get_db():
    async with pool.acquire() as conn:
        yield conn
