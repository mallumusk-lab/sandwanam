-- Preflight report. READ-ONLY: changes nothing.
-- Run with:  py scripts/migrate.py --preflight
-- Every check should return zero rows. Rows marked "blocking" stop migration 002/003;
-- the rest are informational and are handled automatically (see the "action" column).

SELECT 'blocking' AS severity, 'duplicate_customer_id' AS check_name, upper(user_id) AS item,
       'customer IDs must be unique; rename all but one' AS action
FROM customers WHERE user_id IS NOT NULL GROUP BY upper(user_id) HAVING COUNT(*) > 1

UNION ALL
SELECT 'blocking', 'account_needs_prefix', username,
       'pass --branch-prefix ' || username || '=<PREFIX> to migrate.py (2-5 letters, e.g. VZM)'
FROM role r WHERE COALESCE(r.role, '') <> 'SuperAdmin' AND r.username NOT IN ('Admin', 'User1', 'User2')
  AND (to_jsonb(r) ->> 'branch_prefix') IS NULL

UNION ALL
SELECT 'info', 'customer_id_without_branch_prefix', customerid::text || ' ' || COALESCE(user_id, '(none)'),
       'will be assigned to head office (AD)'
FROM customers WHERE user_id IS NULL OR upper(user_id) !~ '^(AD|SAN|SWA)[0-9]+$'

UNION ALL
SELECT 'info', 'orphan_statement', statementid::text || ' ' || COALESCE(loan_number, '(none)'),
       'statement has no matching loan; the new foreign key is added NOT VALID'
FROM statement s WHERE NOT EXISTS (SELECT 1 FROM loan_data l WHERE l.loan_number = s.loan_number)

UNION ALL
SELECT 'info', 'statement_loanid_mismatch', s.statementid::text,
       'loanid will be re-synced from loan_number'
FROM statement s JOIN loan_data l ON l.loan_number = s.loan_number
WHERE s.loanid IS DISTINCT FROM l.loanid

UNION ALL
SELECT 'info', 'loan_without_customer', loan_number, 'loan is hidden from customer views until fixed'
FROM loan_data l WHERE customerid IS NULL OR NOT EXISTS (SELECT 1 FROM customers c WHERE c.customerid = l.customerid)

UNION ALL
SELECT 'info', 'loan_number_format', loan_number, 'not <customer id>L<n>; kept as is'
FROM loan_data WHERE loan_number IS NULL OR upper(loan_number) !~ '^[A-Z]+[0-9]+L[0-9]+$'

UNION ALL
SELECT 'info', 'duplicate_opening_entry', loan_number, 'extra newLoan rows will be deleted (oldest kept)'
FROM statement WHERE transactiontype = 'newLoan' GROUP BY loan_number HAVING COUNT(*) > 1

UNION ALL
SELECT 'blocking', 'negative_balance_on_open_loan', s.loan_number,
       'the latest entry has a negative balance: correct it (or close the loan) before migrating'
FROM loan_data l
JOIN LATERAL (
    SELECT loan_number, principlebalance, interestbalance FROM statement
    WHERE loan_number = l.loan_number ORDER BY date DESC, statementid DESC LIMIT 1
) s ON TRUE
WHERE l.loantype = 'open' AND (s.principlebalance < 0 OR s.interestbalance < 0)

UNION ALL
SELECT 'info', 'negative_balance', statementid::text || ' ' || loan_number, 'older legacy entry; reported, not changed'
FROM statement WHERE principlebalance < 0 OR interestbalance < 0

UNION ALL
SELECT 'info', 'unknown_transaction_type', statementid::text || ' ' || COALESCE(transactiontype, '(null)'),
       'legacy data; excluded from metrics'
FROM statement
WHERE transactiontype IS NULL
   OR transactiontype NOT IN ('newLoan', 'addColl', 'disbursement', 'compounding', 'writeoff', 'modify')

UNION ALL
SELECT 'blocking', 'invalid_loan_values', loan_number,
       'correct the amount, weights or status: such loans cannot be updated (payments, closing) after migration'
FROM loan_data
WHERE principle_amount IS NULL OR principle_amount <= 0 OR weight < 0 OR net_weight < 0 OR deduction < 0
   OR loantype IS NULL OR loantype NOT IN ('open', 'closed')

UNION ALL
SELECT 'info', 'account_with_default_password', username, 'login disabled by migrate.py; set a new password with scripts/set_password.py'
FROM role
WHERE password IS NULL
   OR (password NOT LIKE 'pbkdf2%' AND password NOT LIKE 'sha256:%')
   OR password = 'sha256:' || encode(sha256(convert_to('1234' || 'salthere', 'UTF8')), 'hex')
   OR password = 'sha256:' || encode(sha256(convert_to('super1234' || 'salthere', 'UTF8')), 'hex')

ORDER BY 1, 2, 3;
