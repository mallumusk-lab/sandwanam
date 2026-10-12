-- ==============================================================================
-- FINAPP: SUPABASE DATABASE INITIALIZATION SCHEMA
-- Run this script in your Supabase project's SQL Editor (supabase.com -> SQL Editor)
-- ==============================================================================

-- 1. Customers Table
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

-- 2. Loan Data Table
CREATE TABLE IF NOT EXISTS loan_data (
    loanId SERIAL PRIMARY KEY,
    customerId INTEGER REFERENCES customers(customerId) ON UPDATE CASCADE ON DELETE CASCADE,
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
    refreshinterest DECIMAL(15, 2),
    follow_up_date DATE
);

-- Defensive check for loan_number unique constraint
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'loan_data_loan_number_key') THEN
        ALTER TABLE loan_data ADD CONSTRAINT loan_data_loan_number_key UNIQUE (loan_number);
    END IF;
END $$;

-- 3. Statement Table
CREATE TABLE IF NOT EXISTS statement (
    statementId SERIAL PRIMARY KEY,
    loanId INTEGER REFERENCES loan_data(loanId) ON UPDATE CASCADE ON DELETE CASCADE,
    loan_number VARCHAR(255),
    amountPaid DECIMAL(15, 2) DEFAULT 0,
    date TIMESTAMPTZ,
    currentPrincipal DECIMAL(15, 2),
    currentInterest DECIMAL(15, 2),
    principleBalance DECIMAL(15, 2),
    interestBalance DECIMAL(15, 2),
    transactionType VARCHAR(30)
);

-- Unique index to prevent duplicate initial statements per loan_number
CREATE UNIQUE INDEX IF NOT EXISTS unique_initial_statement_pct 
ON statement (loan_number) 
WHERE transactionType = 'newLoan';

-- 4. Customer Loan Status Trigger
CREATE OR REPLACE FUNCTION update_customer_loan_status()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE customers
    SET loanStatus = NEW.loanStatus
    WHERE customerId = NEW.customerId;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_customer_loan_status_trigger ON loan_data;
CREATE TRIGGER update_customer_loan_status_trigger
AFTER INSERT ON loan_data
FOR EACH ROW
EXECUTE FUNCTION update_customer_loan_status();

-- 5. Role & Authentication Table
CREATE TABLE IF NOT EXISTS role (
    userName VARCHAR(255) PRIMARY KEY,
    password VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',
    display_name VARCHAR(255),
    logo TEXT,
    address TEXT,
    permissions TEXT DEFAULT 'newcustomer,userlist,form1,analytics,report,history,backup'
);

-- 6. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    username VARCHAR(255),
    action VARCHAR(100),
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    details TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 7. Default System Users (Admin, Branches, SuperAdmin)
-- Passwords hashed using sha256 + salt ("salthere") matching security.py
-- Default passwords:
-- Admin: 1234
-- User1: 1234
-- User2: 1234
-- SuperAdmin: super1234
INSERT INTO role (userName, password, role, display_name, permissions)
VALUES 
    ('Admin', 'sha256:690569c39a3177066973d831624d880ba0686be82c8d103557be1d66edb7d81f', 'Admin', 'Admin Branch', 'newcustomer,userlist,form1,analytics,report,history,backup'),
    ('User1', 'sha256:690569c39a3177066973d831624d880ba0686be82c8d103557be1d66edb7d81f', 'User1', 'Santhwanam', 'newcustomer,userlist,form1,analytics,report,history,backup'),
    ('User2', 'sha256:690569c39a3177066973d831624d880ba0686be82c8d103557be1d66edb7d81f', 'User2', 'Swathantra', 'newcustomer,userlist,form1,analytics,report,history,backup'),
    ('SuperAdmin', 'sha256:6c4cfcca9c5d43a0721b27a895d173d3c5eb09b5eb9b93ac8c4ed55bcadb03ee', 'SuperAdmin', 'Super Administrator', 'newcustomer,userlist,form1,analytics,report,history,backup')
ON CONFLICT (userName) DO UPDATE SET 
    display_name = EXCLUDED.display_name,
    permissions = COALESCE(role.permissions, EXCLUDED.permissions);
