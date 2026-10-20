-- Accounts, sessions, branch ownership and referential integrity.
-- Runs in one transaction (scripts/migrate.py). Safe to re-run.

-- ── Accounts ───────────────────────────────────────────────────────────────────────
ALTER TABLE role ADD COLUMN IF NOT EXISTS account_type VARCHAR(20);
ALTER TABLE role ADD COLUMN IF NOT EXISTS branch_prefix VARCHAR(10);
ALTER TABLE role ADD COLUMN IF NOT EXISTS legal_name VARCHAR(255);
ALTER TABLE role ADD COLUMN IF NOT EXISTS phone VARCHAR(50);
ALTER TABLE role ADD COLUMN IF NOT EXISTS email VARCHAR(255);
ALTER TABLE role ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE role ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE role ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ;
ALTER TABLE role ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

UPDATE role SET account_type = CASE
        WHEN role = 'SuperAdmin' THEN 'superadmin'
        WHEN role = 'Admin' THEN 'hq'
        ELSE 'branch'
    END
WHERE account_type IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'role_account_type_check') THEN
        ALTER TABLE role ADD CONSTRAINT role_account_type_check
            CHECK (account_type IN ('superadmin', 'hq', 'branch'));
    END IF;
END $$;
ALTER TABLE role ALTER COLUMN account_type SET NOT NULL;

-- Head office must exist: unassigned customers belong to it. A missing row is created
-- without a password, so nobody can sign in to it until an operator sets one.
INSERT INTO role (username, password, role, display_name, account_type, permissions)
SELECT 'Admin', NULL, 'Admin', 'Head Office', 'hq', 'newcustomer,userlist,form1,analytics,report,history'
WHERE NOT EXISTS (SELECT 1 FROM role WHERE account_type = 'hq')
  AND NOT EXISTS (SELECT 1 FROM role WHERE username = 'Admin');

UPDATE role SET branch_prefix = CASE username
        WHEN 'Admin' THEN 'AD'
        WHEN 'User1' THEN 'SAN'
        WHEN 'User2' THEN 'SWA'
    END
WHERE branch_prefix IS NULL AND account_type <> 'superadmin';

UPDATE role SET branch_prefix = 'AD'
WHERE account_type = 'hq' AND branch_prefix IS NULL
  AND NOT EXISTS (SELECT 1 FROM role r2 WHERE r2.branch_prefix = 'AD');

-- Every branch needs a customer ID prefix to sign in. Other branch accounts get theirs from
-- `py scripts/migrate.py --branch-prefix <username>=<PREFIX>`; stop rather than lock them out.
DO $$
DECLARE
    missing TEXT;
BEGIN
    SELECT string_agg(username, ', ' ORDER BY username) INTO missing
    FROM role WHERE account_type <> 'superadmin' AND branch_prefix IS NULL;
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'These accounts need a customer ID prefix: %. Re-run: py scripts/migrate.py --branch-prefix <username>=<PREFIX>', missing;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'role_branch_prefix_key') THEN
        ALTER TABLE role ADD CONSTRAINT role_branch_prefix_key UNIQUE (branch_prefix);
    END IF;
END $$;

-- Letterheads previously hard-coded in seven print components.
UPDATE role SET
    legal_name = COALESCE(NULLIF(legal_name, ''), 'SANTHWANAM FINANCE PRIVATE LIMITED'),
    address = COALESCE(NULLIF(address, ''), 'PINKULAM JUNCTION URAMBU ROAD, UCHAKKADA PO. PIN - 695506'),
    email = COALESCE(NULLIF(email, ''), 'santhwanam72@gmail.com'),
    phone = COALESCE(NULLIF(phone, ''), '8089153752')
WHERE branch_prefix = 'SAN';

UPDATE role SET
    legal_name = COALESCE(NULLIF(legal_name, ''), 'SWATHANTRA FINANCE PRIVATE LIMITED'),
    address = COALESCE(NULLIF(address, ''), 'VALAMKULAM POZHIYOOR ROAD POZHIYOOR PO. PIN - 695513'),
    email = COALESCE(NULLIF(email, ''), 'swathantrafinance52@gmail.com'),
    phone = COALESCE(NULLIF(phone, ''), '8590678889')
WHERE branch_prefix = 'SWA';

-- "backup" is no longer a branch permission: exports contain every branch's data and are
-- restricted to head office and SuperAdmin.
-- Accounts that never had permissions set (NULL) had every feature in the old app; keep that.
-- An account deliberately left with none ('' or only 'backup') keeps none.
UPDATE role SET permissions = 'newcustomer,userlist,form1,analytics,report,history' WHERE permissions IS NULL;
UPDATE role SET permissions = array_to_string(array_remove(string_to_array(permissions, ','), 'backup'), ',');
ALTER TABLE role ALTER COLUMN permissions SET DEFAULT 'newcustomer,userlist,form1,analytics,report';

-- ── Sessions and login throttling ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    token_hash BYTEA PRIMARY KEY,
    username VARCHAR(255) NOT NULL REFERENCES role(username) ON UPDATE CASCADE ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    ip VARCHAR(64),
    user_agent VARCHAR(255)
);
CREATE INDEX IF NOT EXISTS sessions_username_idx ON sessions (username);
CREATE INDEX IF NOT EXISTS sessions_expires_idx ON sessions (expires_at);

CREATE TABLE IF NOT EXISTS login_throttle (
    username VARCHAR(255) NOT NULL,
    ip VARCHAR(64) NOT NULL,
    failures INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (username, ip)
);

-- ── Customer ownership and numbering ──────────────────────────────────────────────
ALTER TABLE customers ADD COLUMN IF NOT EXISTS branch_prefix VARCHAR(10);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_loan_no INTEGER NOT NULL DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE customers ALTER COLUMN created_at SET DEFAULT NOW();

UPDATE customers c SET branch_prefix = m.branch_prefix
FROM (
    SELECT DISTINCT ON (c2.customerid) c2.customerid, r.branch_prefix
    FROM customers c2
    JOIN role r ON r.branch_prefix IS NOT NULL
               AND upper(c2.user_id) ~ ('^' || r.branch_prefix || '[0-9]+$')
    ORDER BY c2.customerid, length(r.branch_prefix) DESC
) m
WHERE c.customerid = m.customerid AND c.branch_prefix IS NULL;

DO $$
DECLARE
    unassigned INTEGER;
BEGIN
    SELECT COUNT(*) INTO unassigned FROM customers WHERE branch_prefix IS NULL;
    IF unassigned > 0 THEN
        RAISE NOTICE '% customer(s) had no branch prefix and were assigned to head office (AD).', unassigned;
        UPDATE customers SET branch_prefix = (SELECT branch_prefix FROM role WHERE account_type = 'hq' ORDER BY username LIMIT 1)
        WHERE branch_prefix IS NULL;
    END IF;
END $$;
ALTER TABLE customers ALTER COLUMN branch_prefix SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'customers_branch_prefix_fkey') THEN
        ALTER TABLE customers ADD CONSTRAINT customers_branch_prefix_fkey
            FOREIGN KEY (branch_prefix) REFERENCES role(branch_prefix) ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_customers_branch ON customers (branch_prefix);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM customers WHERE user_id IS NOT NULL GROUP BY upper(user_id) HAVING COUNT(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate customer IDs exist. Run the preflight report and rename duplicates first.';
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS customers_user_id_key ON customers (upper(user_id));

CREATE TABLE IF NOT EXISTS branch_counters (
    branch_prefix VARCHAR(10) PRIMARY KEY REFERENCES role(branch_prefix) ON UPDATE CASCADE ON DELETE CASCADE,
    next_customer_no INTEGER NOT NULL DEFAULT 1 CHECK (next_customer_no > 0)
);

INSERT INTO branch_counters (branch_prefix, next_customer_no)
SELECT r.branch_prefix,
       COALESCE(MAX(substring(upper(c.user_id) FROM '^' || r.branch_prefix || '([0-9]+)$')::INTEGER), 0) + 1
FROM role r
LEFT JOIN customers c ON c.branch_prefix = r.branch_prefix
WHERE r.branch_prefix IS NOT NULL
GROUP BY r.branch_prefix
ON CONFLICT (branch_prefix) DO UPDATE
    SET next_customer_no = GREATEST(branch_counters.next_customer_no, EXCLUDED.next_customer_no);

UPDATE customers c SET last_loan_no = GREATEST(c.last_loan_no, sub.max_no)
FROM (
    SELECT customerid, MAX(substring(upper(loan_number) FROM 'L([0-9]+)$')::INTEGER) AS max_no
    FROM loan_data
    GROUP BY customerid
) sub
WHERE c.customerid = sub.customerid AND sub.max_no IS NOT NULL;

-- ── Ledger integrity ──────────────────────────────────────────────────────────────
UPDATE statement s SET loanid = l.loanid
FROM loan_data l
WHERE s.loan_number = l.loan_number AND s.loanid IS DISTINCT FROM l.loanid;

DELETE FROM statement
WHERE statementid IN (
    SELECT statementid FROM (
        SELECT statementid, ROW_NUMBER() OVER (PARTITION BY loan_number ORDER BY statementid) AS rn
        FROM statement WHERE transactiontype = 'newLoan'
    ) ranked
    WHERE rn > 1
);

-- Deleting a customer or loan must never silently delete ledger history.
DO $$
DECLARE
    fk RECORD;
BEGIN
    FOR fk IN
        SELECT conname, conrelid::regclass::text AS tbl
        FROM pg_constraint
        WHERE contype = 'f' AND confdeltype = 'c'
          AND conrelid IN ('loan_data'::regclass, 'statement'::regclass)
          AND confrelid IN ('customers'::regclass, 'loan_data'::regclass)
    LOOP
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', fk.tbl, fk.conname);
    END LOOP;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.conrelid = 'loan_data'::regclass AND c.contype = 'f' AND a.attname = 'customerid'
    ) THEN
        ALTER TABLE loan_data ADD CONSTRAINT loan_data_customerid_fkey
            FOREIGN KEY (customerid) REFERENCES customers(customerid)
            ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
        WHERE c.conrelid = 'statement'::regclass AND c.contype = 'f' AND a.attname = 'loanid'
    ) THEN
        ALTER TABLE statement ADD CONSTRAINT statement_loanid_fkey
            FOREIGN KEY (loanid) REFERENCES loan_data(loanid)
            ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'statement_loan_number_fkey') THEN
        ALTER TABLE statement ADD CONSTRAINT statement_loan_number_fkey
            FOREIGN KEY (loan_number) REFERENCES loan_data(loan_number)
            ON UPDATE CASCADE ON DELETE RESTRICT NOT VALID;
    END IF;
END $$;

-- ── Supabase Data API ─────────────────────────────────────────────────────────────
-- The application connects as the table owner, which bypasses RLS. Enabling RLS with no
-- policies (and revoking grants) keeps these tables unreachable through PostgREST.
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['customers', 'loan_data', 'statement', 'role', 'audit_logs',
                             'sessions', 'login_throttle', 'branch_counters']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
            EXECUTE format('REVOKE ALL ON TABLE %I FROM anon', t);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
            EXECUTE format('REVOKE ALL ON TABLE %I FROM authenticated', t);
        END IF;
    END LOOP;
END $$;
