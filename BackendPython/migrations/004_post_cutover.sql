-- Run only after the new application is deployed and the old one is gone:
--   py scripts/migrate.py --post-cutover
-- Fix anything the preflight report lists under "invalid_loan_values" / "orphan_statement"
-- / "loan_without_customer" first, or the VALIDATE statements will fail (nothing is
-- changed when they do: the whole file runs in one transaction).

-- The old trigger copied loan_data.loanStatus onto the customer on insert. The services
-- now maintain customers.loanstatus explicitly, including on closure.
DROP TRIGGER IF EXISTS update_customer_loan_status_trigger ON loan_data;
DROP FUNCTION IF EXISTS update_customer_loan_status();

ALTER TABLE loan_data VALIDATE CONSTRAINT loan_data_values_check;
ALTER TABLE loan_data VALIDATE CONSTRAINT loan_data_customerid_fkey;
ALTER TABLE statement VALIDATE CONSTRAINT statement_loanid_fkey;
ALTER TABLE statement VALIDATE CONSTRAINT statement_loan_number_fkey;
