-- Baseline: the schema as the previous application left it. Idempotent, so it is safe on
-- the existing Supabase database and creates everything on a fresh one.
-- This file replaces supabase_schema.sql and the DDL that database.py ran on every start.

CREATE TABLE IF NOT EXISTS customers (
    customerId SERIAL PRIMARY KEY,
    customerName VARCHAR(255),
    phone VARCHAR(50) UNIQUE,
    address VARCHAR(255),
    loanStatus VARCHAR(20),
    role VARCHAR(20) DEFAULT 'user',
    user_id VARCHAR(100)
);

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
    refreshinterest DECIMAL(15, 2),
    follow_up_date DATE
);

ALTER TABLE loan_data ADD COLUMN IF NOT EXISTS follow_up_date DATE;

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

CREATE TABLE IF NOT EXISTS role (
    userName VARCHAR(255) PRIMARY KEY,
    password VARCHAR(255),
    role VARCHAR(20) DEFAULT 'user',
    display_name VARCHAR(255),
    logo TEXT,
    address TEXT,
    permissions TEXT DEFAULT 'newcustomer,userlist,form1,analytics,report,history'
);

ALTER TABLE role ADD COLUMN IF NOT EXISTS display_name VARCHAR(255);
ALTER TABLE role ADD COLUMN IF NOT EXISTS logo TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE role ADD COLUMN IF NOT EXISTS permissions TEXT;

CREATE TABLE IF NOT EXISTS audit_logs (
    log_id SERIAL PRIMARY KEY,
    username VARCHAR(255),
    action VARCHAR(100),
    entity_type VARCHAR(50),
    entity_id VARCHAR(100),
    details TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Older databases may hold duplicate opening entries; keep the oldest before indexing.
DELETE FROM statement
WHERE statementid IN (
    SELECT statementid FROM (
        SELECT statementid, ROW_NUMBER() OVER (PARTITION BY loan_number ORDER BY statementid) AS rn
        FROM statement WHERE transactionType = 'newLoan'
    ) ranked
    WHERE rn > 1
);
CREATE UNIQUE INDEX IF NOT EXISTS unique_initial_statement_pct
    ON statement (loan_number) WHERE transactionType = 'newLoan';
CREATE INDEX IF NOT EXISTS idx_statement_loan_number ON statement (loan_number);
CREATE INDEX IF NOT EXISTS idx_statement_date ON statement (date);
CREATE INDEX IF NOT EXISTS idx_statement_transaction_type ON statement (transactionType);
CREATE INDEX IF NOT EXISTS idx_loan_data_loantype ON loan_data (loantype);
CREATE INDEX IF NOT EXISTS idx_loan_data_customerid ON loan_data (customerid);
CREATE INDEX IF NOT EXISTS idx_loan_data_date ON loan_data (date);
