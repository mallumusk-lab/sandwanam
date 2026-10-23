-- Branch cash ledger (the drawer book). Its own tables: no loan, customer, statement or
-- settings table is read or changed. Every amount is entered by hand; the services keep
-- 14 days (app/services/cash_service.py) and the backup includes both tables.
-- The last step drops the old backup_snapshots table (backups are emailed, never stored).
-- Runs in one transaction (scripts/migrate.py). Safe to re-run.

-- ── Days ───────────────────────────────────────────────────────────────────────────
-- One row per branch per IST business day. closing_* and closed_* are all NULL while
-- the day is open; an automatic close (the day was never counted) stores expected as
-- counted, which may be below zero when more cash out than in was recorded.
CREATE TABLE IF NOT EXISTS cash_days (
    id SERIAL PRIMARY KEY,
    branch_prefix VARCHAR(10) NOT NULL REFERENCES role(branch_prefix) ON UPDATE CASCADE ON DELETE RESTRICT,
    day DATE NOT NULL,
    carried_forward DECIMAL(15, 2) NOT NULL,
    opening_counted DECIMAL(15, 2) NOT NULL,
    opened_by VARCHAR(255) NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    client_request_id VARCHAR(64),
    closing_expected DECIMAL(15, 2),
    closing_counted DECIMAL(15, 2),
    closed_by VARCHAR(255),
    closed_at TIMESTAMPTZ,
    closed_automatically BOOLEAN NOT NULL DEFAULT FALSE
);

-- ── Entries ────────────────────────────────────────────────────────────────────────
-- Mistakes are voided (with a reason), never deleted; deleting a day deletes its entries.
CREATE TABLE IF NOT EXISTS cash_entries (
    id SERIAL PRIMARY KEY,
    day_id INTEGER NOT NULL REFERENCES cash_days(id) ON DELETE CASCADE,
    direction VARCHAR(3) NOT NULL,
    category VARCHAR(40) NOT NULL,
    description VARCHAR(255),
    reference VARCHAR(40),
    amount DECIMAL(15, 2) NOT NULL,
    client_request_id VARCHAR(64),
    created_by VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    voided_at TIMESTAMPTZ,
    voided_by VARCHAR(255),
    void_reason VARCHAR(255)
);

DO $$
BEGIN
    -- Its index also serves the newest-first lookups per branch (scanned backwards).
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cash_days_branch_day_key') THEN
        ALTER TABLE cash_days ADD CONSTRAINT cash_days_branch_day_key UNIQUE (branch_prefix, day);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cash_days_values_check') THEN
        ALTER TABLE cash_days ADD CONSTRAINT cash_days_values_check CHECK (
            opening_counted >= 0
            AND (closed_at IS NULL) = (closing_counted IS NULL)
            AND (closed_at IS NULL) = (closing_expected IS NULL)
            AND (closed_at IS NULL) = (closed_by IS NULL)
            AND (closed_automatically OR closing_counted IS NULL OR closing_counted >= 0)
            AND (closed_at IS NOT NULL OR NOT closed_automatically)
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cash_entries_client_request_id_key') THEN
        ALTER TABLE cash_entries ADD CONSTRAINT cash_entries_client_request_id_key UNIQUE (client_request_id);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'cash_entries_values_check') THEN
        ALTER TABLE cash_entries ADD CONSTRAINT cash_entries_values_check CHECK (
            direction IN ('in', 'out')
            AND amount > 0
            AND (voided_at IS NULL) = (voided_by IS NULL)
            AND (voided_at IS NULL) = (void_reason IS NULL)
        );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_cash_entries_day ON cash_entries (day_id, created_at, id);

-- ── Permission ─────────────────────────────────────────────────────────────────────
-- Every existing branch gets the cash ledger, and so does every new branch (the column
-- default mirrors DEFAULT_PERMISSIONS in app/services/context.py). A SuperAdmin can
-- still switch it off per branch.
UPDATE role
SET permissions = CASE WHEN btrim(COALESCE(permissions, '')) = '' THEN 'cashbook' ELSE permissions || ',cashbook' END
WHERE account_type = 'branch'
  AND NOT ('cashbook' = ANY (string_to_array(replace(COALESCE(permissions, ''), ' ', ''), ',')));
ALTER TABLE role ALTER COLUMN permissions SET DEFAULT 'newcustomer,userlist,form1,analytics,report,cashbook';

-- ── Row level security ─────────────────────────────────────────────────────────────
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['cash_days', 'cash_entries']
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

-- ── Stored backup snapshots are no longer used ─────────────────────────────────────
-- Backups are now emailed every night as a password-protected ZIP and nothing is stored
-- in the database (app/services/backup_email_service.py), so the snapshots table made by
-- migration 003 is removed to save space. Supabase's own backups remain the
-- disaster-recovery layer.
DROP TABLE IF EXISTS backup_snapshots;
