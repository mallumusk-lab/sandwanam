-- Ledger detail, reporting columns, settings and in-database backup snapshots.

-- ── Loans ──────────────────────────────────────────────────────────────────────────
ALTER TABLE loan_data ADD COLUMN IF NOT EXISTS closed_at TIMESTAMPTZ;
ALTER TABLE loan_data ADD COLUMN IF NOT EXISTS items JSONB;
ALTER TABLE loan_data ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);
ALTER TABLE loan_data ALTER COLUMN particulars TYPE TEXT;

-- Closing date for loans closed before this column existed: their last ledger entry.
UPDATE loan_data ld SET closed_at = s.last_date
FROM (SELECT loan_number, MAX(date) AS last_date FROM statement GROUP BY loan_number) s
WHERE ld.loan_number = s.loan_number AND ld.loantype = 'closed' AND ld.closed_at IS NULL;
UPDATE loan_data SET closed_at = date WHERE loantype = 'closed' AND closed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_loan_data_closed_at ON loan_data (closed_at);
CREATE INDEX IF NOT EXISTS idx_loan_data_open ON loan_data (customerid) WHERE loantype = 'open';

-- ── Ledger ─────────────────────────────────────────────────────────────────────────
-- created_at stays NULL on legacy rows; constraints below only apply to new rows.
ALTER TABLE statement ADD COLUMN IF NOT EXISTS accrued_days INTEGER;
ALTER TABLE statement ADD COLUMN IF NOT EXISTS writeoff_principal DECIMAL(15, 2);
ALTER TABLE statement ADD COLUMN IF NOT EXISTS writeoff_interest DECIMAL(15, 2);
ALTER TABLE statement ADD COLUMN IF NOT EXISTS client_request_id VARCHAR(64);
ALTER TABLE statement ADD COLUMN IF NOT EXISTS created_by VARCHAR(255);
ALTER TABLE statement ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ;
ALTER TABLE statement ALTER COLUMN created_at SET DEFAULT NOW();

CREATE UNIQUE INDEX IF NOT EXISTS statement_client_request_id_key
    ON statement (client_request_id) WHERE client_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_statement_loan_latest
    ON statement (loan_number, date DESC, statementid DESC);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'statement_new_rows_check') THEN
        ALTER TABLE statement ADD CONSTRAINT statement_new_rows_check CHECK (
            created_at IS NULL OR (
                transactiontype IN ('newLoan', 'addColl', 'disbursement', 'compounding', 'writeoff')
                AND amountpaid >= 0
                AND (transactiontype <> 'addColl' OR amountpaid > 0)
                AND accrued_days IS NOT NULL AND accrued_days >= 0
                AND COALESCE(writeoff_principal, 0) >= 0
                AND COALESCE(writeoff_interest, 0) >= 0
            )
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'loan_data_values_check') THEN
        ALTER TABLE loan_data ADD CONSTRAINT loan_data_values_check CHECK (
            principle_amount > 0
            AND COALESCE(weight, 0) >= 0
            AND COALESCE(net_weight, 0) >= 0
            AND COALESCE(deduction, 0) >= 0
            AND loantype IN ('open', 'closed')
        ) NOT VALID;
    END IF;
END $$;

-- ── Settings, snapshots, audit ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_settings (
    key VARCHAR(64) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS backup_snapshots (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255) NOT NULL,
    kind VARCHAR(20) NOT NULL CHECK (kind IN ('scheduled', 'manual', 'pre_restore')),
    size_bytes INTEGER NOT NULL,
    sha256 CHAR(64) NOT NULL,
    payload BYTEA NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backup_snapshots_created ON backup_snapshots (created_at DESC);

ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip VARCHAR(64);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(64);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs (timestamp DESC);

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['app_settings', 'backup_snapshots']
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
