-- Branch receipt counters: each branch has its own receipt series starting from 1 (Option B).
-- Adds next_receipt_no to branch_counters and receipt_no to statement table.
-- Safe to re-run.

ALTER TABLE branch_counters ADD COLUMN IF NOT EXISTS next_receipt_no INTEGER NOT NULL DEFAULT 1 CHECK (next_receipt_no > 0);
ALTER TABLE statement ADD COLUMN IF NOT EXISTS receipt_no INTEGER;

-- Initialize next_receipt_no for existing branches based on any existing receipts, or default 1
INSERT INTO branch_counters (branch_prefix, next_customer_no, next_receipt_no)
SELECT r.branch_prefix, 1,
       COALESCE(MAX(s.receipt_no), 0) + 1
FROM role r
LEFT JOIN customers c ON c.branch_prefix = r.branch_prefix
LEFT JOIN loan_data l ON l.customerid = c.customerid
LEFT JOIN statement s ON s.loan_number = l.loan_number AND s.receipt_no IS NOT NULL
WHERE r.branch_prefix IS NOT NULL
GROUP BY r.branch_prefix
ON CONFLICT (branch_prefix) DO UPDATE
    SET next_receipt_no = GREATEST(branch_counters.next_receipt_no, EXCLUDED.next_receipt_no);
