# Architecture

How Gold Loan Desk is built, and why. For setup and operations see [README](../README.md); for the
rules every change must follow see [CLAUDE.md](../CLAUDE.md).

## 1. System overview

```
Browser (React SPA)
   │  same origin, HttpOnly session cookie + X-CSRF-Token
   ▼
Vercel (one project, vercel.json)
   ├── /assets/*, /*.js, /*.css …  → static web app (Frontend/, built by Vite)
   ├── everything else             → Frontend/index.html (client-side routing)
   ├── /api/*                      → BackendPython/main.py → app.main:app (FastAPI, ASGI)
   ├── /health, /health/ready      → API
   └── /cron/daily  (00:00 IST)    → API  (Vercel Cron, Bearer CRON_SECRET)
                                        │ asyncpg pool (statement cache off: pooler-safe)
                                        ▼
                                   Supabase Postgres (RLS on, no Data API access)
```

There is one origin for the web app and the API, so there is no CORS, the cookie can be
`SameSite=Strict`, and the browser never holds a token that scripts can read.

## 2. Request lifecycle (API)

1. **`app/middleware.py`** (pure ASGI, outermost first):
   - `RequestContextMiddleware`: request id (`x-request-id`), security headers, `Cache-Control: no-store`,
     5 MB body limit, one JSON access-log line per request.
   - `OriginGuardMiddleware`: rejects POST/PUT/PATCH/DELETE whose `Origin` is another site.
   - `ApiPrefixMiddleware`: Vercel forwards `/api/...`; routes are mounted at `/`.
2. **FastAPI router** (`app/routers/*.py`): validates the body with Pydantic (`app/schemas.py`;
   unknown fields rejected, amounts as strings).
3. **Auth dependencies** (`app/auth.py`):
   - `require_session` reads the `__Host-sid` cookie, checks it with `auth_service.resolve_session`,
     and for unsafe methods checks `X-CSRF-Token`.
   - `require_actor` also blocks accounts that must change a temporary password.
4. **Service** (`app/services/*.py`): enforces permissions and branch scope, applies business rules,
   opens a transaction.
5. **Repositories** (`app/repositories/*.py`): the only SQL. Every statement passes through `Db`, which
   asserts that `$n` placeholders match the arguments.
6. **Errors** (`app/errors.py`, handlers in `app/main.py`): every failure is
   `{"error": {"code", "message", "details"}}`. Unexpected errors return 500 with the request id only.

## 3. Backend layers and dependency rules

| Layer | Folder | May import | Notes |
|---|---|---|---|
| Domain | `app/domain/` | standard library | Business rules as pure functions. Fully unit-tested. |
| Security | `app/security/` | standard library | Password hashing, session tokens, throttling. |
| Services | `app/services/` | domain, security, errors | One use case per function, one transaction per write. Never import FastAPI, asyncpg or `infra`. |
| Repositories | `app/repositories/` | domain (codec) | All SQL, parameterized; table/column names only from constants. |
| Infra | `app/infra/` | standard library, `pyzipper` (imported lazily) | Adapters to the outside world: `aeszip.py` (AES-256 ZIP) and `mailer.py` (SMTP, STARTTLS 587 or TLS 465, never plain text). The only place `smtplib` and `pyzipper` appear. |
| HTTP | `app/routers/`, `schemas.py`, `auth.py`, `main.py`, `db.py` | everything | Thin: parse, call a service, return. Routers build the mailer from settings and pass it to services. |

Because services receive repositories (and the mailer) as arguments, tests run every service against
in-memory fakes (`tests/fakes.py`, `tests/backup_fakes.py`) with no database and no network.

## 4. Business rules (authoritative)

Implemented in `app/domain/interest.py` and `app/domain/ledger.py`; the shared cases in
`test-vectors/interest.json` are checked by both the Python tests and the JavaScript calculator.

- **Rate**: annual (% p.a.). Interest = principal × rate × days ÷ 36500, rounded half-up to the paisa.
  A missing rate defaults to 18 % p.a.
- **Day count**: a period ending in a customer event (payment, top-up, closure, imported entry) counts
  `(end − start) + 1` days. A boundary day is therefore charged in both adjacent periods (agreed).
  One action (closing = payment + write-off) accrues once.
- **Compounding**: due on loan date + 365·k. That period counts exact days; interest due becomes principal.
  Applied lazily before any ledger write, by the daily cron, and virtually for on-screen quotes.
- **First 7 days ("peak principal")**: W = loan date + 6 (day 7, age counted inclusively).
  - Payments and top-ups on days 1–7 record no daily interest (`accrued_days` 0). A payment reduces principal
    by its full amount; one that would clear the principal is refused (`first_week_clears_principal`: use Close).
  - Days 1–7 are charged as 7 days' interest on the **window peak**, the highest principal reached in them.
  - Closing on days 1–7 charges exactly that. The first event after day 7 (payment, top-up, closing or
    compounding) charges it plus the days after day 7 on the current principal, **rounded once**; that row
    stores `accrued_days = 7 + extra days`, and inclusive counting resumes afterwards.
  - Quotes shown on days 1–7 give "interest so far" = peak × days elapsed, and carry `first_week`,
    `window_peak` and `first_week_interest`.
  - Loans already in their first week when the rule shipped subtract the interest their rows already charged,
    so nothing is charged twice. History import (`simulate`) follows the same rule.
  - Agreed example: ₹1,00,000 at 18 %; −₹30,000 on day 2; +₹50,000 on day 4; close on day 5 →
    1,20,000 × 18 × 7 ÷ 36500 = ₹414.25, payoff ₹1,20,414.25. `test-vectors/interest.json` is unchanged.
- **Payments** (after day 7): interest first, then principal. A payment of the whole amount due is not a
  collection: it must use **Close**.
- **Closing**: the cash actually received is recorded; any remainder is written off only when explicitly
  confirmed, with principal and interest written off stored separately.
- **Dates**: every daily entry (new loan, payment, top-up, closing) is dated today, for every role; the request
  bodies have no date field (an unknown field is a 422). Only History import (a SuperAdmin-granted feature)
  enters past-dated loans and entries.
- **History import** (`import_service`, `ledger.simulate`): the past entries are replayed through the same
  functions as live entries (`quote`, `collect`, `top_up`, `due_compoundings`), including the first-7-days
  rule. An entry of kind `close` (amount = cash received, may be 0; `write_off_remaining` to confirm a
  write-off) uses `quote(..., closing=True)` and `ledger.close`, exactly as **Close** does: the 7-day minimum,
  the write-off only when confirmed (`writeoff_not_confirmed` otherwise, same message as live), and
  overpayment refused. A close must be the last entry, by position and date (`close_not_last`), and there is at
  most one (`close_twice`). No compounding is added after a close; an open import compounds up to today.
  Commit stores the rows, then `mark_closed` with `closed_at` = the closing row's stored stamp and
  `refresh_loan_status`, the same repository calls as a live close.
  **Parity guarantee**: an imported loan is identical to the same loan recorded live, entry by entry, on its
  own dates: every ledger row, the statement calculations, the loan detail, the stored loan, today's quote
  and the customer's loan status. `tests/test_history_parity.py` checks 21 scenarios both ways.
- **Overdue and follow-ups** (`domain/reports.py`): a loan is overdue when today > loan date + 365
  (`OVERDUE_AFTER_DAYS`). An open loan's follow-up date is the date staff stored, else loan date + 364
  (`FOLLOW_UP_AFTER_DAYS`); closed loans have none. Nothing is backfilled.
- **Statement calculations** (`domain/statement_calc.py`): the "Show calculation" working for each ledger row
  is derived on the server from the stored rows only. Legacy rows say "Earlier system — not recalculated"; a
  row the rules cannot reproduce is shown "as recorded". It never raises and never changes stored data.
- **Legacy credit**: a negative interest balance from the earlier system is netted against principal.
- **Cash ledger** (`domain/cash.py`, `services/cash_service.py`): a per-branch drawer book, **independent of
  loans**. No loan, customer, ledger or settings table is read or written, and its figures appear on no other
  screen, report or dashboard. Every amount is typed by hand.
  - One day per branch per IST business day. **Carry forward** = the `closing_counted` of the branch's latest
    closed day before today (₹0.00 for the first day; a still-open earlier day carries its expected figure,
    which is what its automatic close will store). Starting a day stores the carry forward and the
    `opening_counted`; `opening_difference` = counted − carried (negative = shortage).
  - Entries are dated now and only go on today's open day: direction `in`/`out`, a category (in:
    `loan_collection`, `from_head_office`, `other_income`; out: `loan_disbursement`, `bill_payment`,
    `donation`, `expense`, `to_head_office`; either: `other`, which needs a description), optional
    description (≤ 255) and reference (≤ 40), amount > 0. Idempotent by `request_id`.
  - Mistakes are voided with a reason (3–255 characters) while the day is open, never deleted; voided entries
    stay listed and do not count.
  - Totals are computed on the server only: `cash_in`, `cash_out` (non-voided), `expected` = opening counted +
    in − out. Closing stores `closing_expected` and `closing_counted` (≥ 0) and locks the day; the client
    sends the expected figure it showed (`expected_total`) and gets 409 `cash_changed` if it moved.
  - Head office (account type `hq`) may reopen only the branch's latest day and only if it is today.
  - Days left open before today are closed automatically (counted = expected, `closed_automatically`) by the
    daily job and when the next day starts. Retention: today plus the previous 13 days; older days and their
    entries are deleted, except each branch's latest day (kept for the carry forward).

Ledger entry kinds (`statement.transactiontype`):

| Kind | Meaning | Amount field |
|---|---|---|
| `newLoan` | opening entry | `principlebalance` |
| `addColl` | payment | `amountpaid` (split: `currentinterest`, −`currentprincipal`) |
| `disbursement` | principal added | `currentprincipal` |
| `compounding` | annual compounding | `currentprincipal` |
| `writeoff` | written off at closing | `writeoff_principal` + `writeoff_interest`; legacy rows: `principlebalance` |
| `modify` | legacy top-up (earlier system only) | `amountpaid` |

## 5. Money, dates and ordering

- **Money**: `Decimal` on the server (`domain/money.py`), strings with two decimals in JSON
  (`services/serialize.py`), integer paise (`BigInt`) in the browser (`Frontend/src/lib/money.js`). Floats
  are never used for money or weight.
- **Dates**: business dates are IST calendar days (fixed +05:30, India has no DST):
  `domain/dates.py` and `Frontend/src/lib/dates.js`. Timestamps are stored as UTC `timestamptz`;
  reports filter on half-open UTC ranges of IST days (`dates.ist_day_bounds_utc`).
- **Ordering**: the latest ledger entry is `ORDER BY date DESC, statementid DESC`.
  `loans_service.stamps_for` guarantees strictly increasing stored timestamps (+1 µs when needed);
  a closing payment and its write-off are exactly 1 µs apart, which is how receipts pair them
  (`CLOSING_PAIR_GAP`, 1 ms). History import stores past same-day entries 1 µs apart at IST noon, so it
  starts an imported close's own rows more than `CLOSING_PAIR_GAP` after the entry before them.

## 6. Data model

| Table | Purpose | Key columns |
|---|---|---|
| `role` | accounts **and** branches (legacy name) | `username` PK, `password`, `account_type` (superadmin/hq/branch), `branch_prefix` UNIQUE, `permissions` (CSV), letterhead fields, `is_active`, `must_change_password` |
| `customers` | customers | `customerid`, `user_id` (e.g. SAN12, unique), `phone` unique, `branch_prefix` → role, `last_loan_no` |
| `loan_data` | loans | `loan_number` (e.g. SAN12L3) unique, `customerid`, `items` jsonb (truth), `particulars` (display), weights, `principle_amount`, `interest` (rate), `tenure`, `date`, `loantype` open/closed, `closed_at`, cached `refreshprincipleamount`/`refreshinterest` |
| `statement` | ledger | `statementid`, `loan_number`, `transactiontype`, `date`, amounts and balances, `accrued_days`, `writeoff_*`, `client_request_id` UNIQUE (idempotency), `created_at` (NULL = legacy row) |
| `sessions` | sign-in sessions | `token_hash` (SHA-256), `username`, `expires_at`, `last_seen_at` |
| `login_throttle` | sign-in throttling | (`username`, `ip`) where ip is an address, `*` (account), `trusted:<address>`, or `password-change` |
| `branch_counters` | next customer number per branch | `branch_prefix`, `next_customer_no` |
| `app_settings` | settings | `gold_rate` → `{"per_gram": "…"}`; local keys `backup_email` → `{"recipient", "enabled"}` and `backup_email_status` → `{"nightly", "manual"}` (an older `"test"` half is ignored and dropped), never exported or restored |
| `audit_logs` | who did what | `username`, `action`, `entity_id`, `details`, `ip`, `request_id` |
| ~~`backup_snapshots`~~ | removed by `005_cash_ledger.sql` (`DROP TABLE IF EXISTS`): backups are emailed, never stored | — |
| `cash_days` | cash ledger: one row per branch per IST day | `id`, `branch_prefix` → role (ON DELETE RESTRICT), `day`, UNIQUE (`branch_prefix`, `day`), `carried_forward`, `opening_counted`, `opened_by`/`opened_at`, `client_request_id`, `closing_expected`, `closing_counted`, `closed_by`/`closed_at` (all NULL while open), `closed_automatically` |
| `cash_entries` | cash ledger: one row per cash movement | `id`, `day_id` → cash_days (ON DELETE CASCADE), `direction` in/out, `category`, `description`, `reference`, `amount` > 0, `client_request_id` UNIQUE, `created_by`/`created_at`, `voided_at`/`voided_by`/`void_reason` |
| `schema_migrations` | applied migrations | `version` |

Constraints added to existing data use `NOT VALID` (enforced for new and updated rows; validated by
`004_post_cutover.sql`). The new-row check on `statement` applies only where `created_at IS NOT NULL`,
so legacy rows stay untouched. RLS is enabled on every table with no policies, and `anon`/`authenticated`
grants are revoked: the app connects as the table owner, the Supabase Data API sees nothing.

Migrations (`BackendPython/migrations/`, applied by `scripts/migrate.py`, each in one transaction):

| File | Does |
|---|---|
| `000_preflight.sql` | read-only report; *blocking* items stop `migrate.py` |
| `001_baseline.sql` | the previous schema, idempotent; dedupes opening entries |
| `002_auth_integrity.sql` | accounts, sessions, throttling, branch ownership, counters, FKs, RLS |
| `003_ledger_reporting.sql` | `closed_at`, `items`, ledger detail columns, checks, settings, snapshots (the snapshots table is dropped again by 005) |
| `004_post_cutover.sql` | drop the legacy trigger, validate constraints (run after go-live) |
| `005_cash_ledger.sql` | cash ledger tables, checks and index, RLS; `cashbook` for every existing branch and in the `role.permissions` default; drops the unused `backup_snapshots` table (part of the main steps; once applied it must never be edited) |

`migrate.py` also runs data steps: structured items backfill, and disabling every default or plaintext password.

## 7. Security model

- **Sessions**: random 256-bit token in `__Host-sid` (HttpOnly, Secure, SameSite=Strict); only its hash is
  stored. 8 h absolute, 60 min idle. Logout, password change, reset and deactivation revoke sessions.
- **CSRF**: `X-CSRF-Token` = HMAC(session token, "csrf"), returned by `/auth/login` and `/auth/me`, required
  on every unsafe request; plus the Origin guard.
- **Passwords**: PBKDF2-SHA256, 600 000 iterations. Older formats verify once and are upgraded; plaintext
  and published defaults never work. Policy: ≥ 10 characters, not common, not containing the username.
- **Throttling** (`security/throttle.py`, `auth_service._claim`): each attempt is claimed under a row lock
  *before* the password check. Per address: 3 free attempts, then 30 s doubling to 15 min. Per account:
  20 free, capped at 5 min, skipped for addresses that signed in successfully in the last 30 days. IPv6 is
  grouped by /64. Lock starts are audited.
- **Roles and branch scope** (`services/context.py`): `superadmin` and `hq` (head office) see every branch;
  `branch` accounts only their own. Records of other branches return 404. Head office has every feature. A
  SuperAdmin has only `SUPERADMIN_FEATURES` = `newcustomer`, `userlist` (customers and loans of any branch);
  anything else is refused with "A SuperAdmin account cannot use this feature." `/auth/me` reports exactly
  these permissions, and the UI mirrors them.

| Feature key | Grants | Enforced in |
|---|---|---|
| `analytics` | dashboard, performance, drill-downs | `reports_service._scope` |
| `userlist` | customer list and pages, loan statement, payments, closing, follow-ups, receipts | `customers_service`, `loans_service`, `receipts_service` |
| `newcustomer` | new customers, new loans, add principal, edit items (implies `userlist`) | `customers_service.create`, `loans_service.create/top_up/edit_items` |
| `report` | transaction report and CSV | `reports_service.transactions*` |
| `history` | history import (past-dated loans); opt-in for new branches | `import_service` |
| `form1` | loan calculator (browser only) | route guards |
| `cashbook` | cash ledger (one branch's drawer at a time; head office must name the branch, `branch_required`); on by default for new branches | `cash_service` |
| HQ only | gold rate, audit log, reopening a closed cash day | `require_head_office` (account type `hq`; SuperAdmin refused) |
| head office incl. SuperAdmin | backups: Check a file, "Email backup now", backup email status | `backup_service`, `backup_email_service` (`is_head_office`) |
| SuperAdmin | branches and accounts, Import (restore), backup email address | `require_superadmin` |

| Role | `analytics` | `userlist` | `newcustomer` | `report` | `history` | `form1` | `cashbook` | gold rate, audit, cash reopen | backups | restore, email, branches |
|---|---|---|---|---|---|---|---|---|---|---|
| branch | if granted | if granted | if granted | if granted | if granted | if granted | if granted (own drawer) | — | — | — |
| hq | yes | yes | yes | yes | yes | yes | yes (one branch at a time) | yes | yes | — |
| superadmin | — | yes | yes | — | — | — | — | — | yes | yes |

- **Backups**: backups are emailed, never stored; a backup never contains credentials, sessions, audit logs
  or the backup email settings; files are read strictly (size caps, no NaN, no duplicate JSON keys, no trailing
  data, unique-key checks); restore is SuperAdmin-only, needs the typed word RESTORE, keeps no copy of the old
  data (by the user's decision; the page warns), revalidates logos, never re-grants permissions, and relaxes
  the NOT VALID constraints only inside its transaction. The emailed ZIP is AES-256 encrypted; its password
  (`BACKUP_ZIP_PASSWORD`) is never sent. For Import backup the browser sends the ZIP and a password over HTTPS;
  the server checks access and RESTORE first, decrypts in memory, and never stores, logs or audits the password.
- **Headers**: strict CSP (`default-src 'self'`, no inline scripts or styles), HSTS, nosniff, frame-ancestors none.

## 8. API catalogue

All paths are under `/api` in the browser. "Visible" means the record must belong to the user's branch
(head office and SuperAdmin: any branch).

| Method | Path | Service | Requires |
|---|---|---|---|
| POST | `/auth/login` | `auth_service.login` | — (throttled) |
| GET | `/auth/me` | session | signed in |
| POST | `/auth/logout` | `auth_service.logout` | signed in |
| POST | `/auth/change-password` | `auth_service.change_password` | signed in (throttled) |
| GET | `/branches` | `branches_service.directory` | signed in |
| GET | `/customers` | `customers_service.search` | `userlist`, scope |
| POST | `/customers` | `customers_service.create` | `newcustomer` |
| GET | `/customers/{customer_id}` | `customers_service.detail` | `userlist`, visible |
| POST | `/loans` | `loans_service.create` | `newcustomer`, visible |
| GET | `/loans/{loan_number}` | `loans_service.detail` | `userlist`, visible |
| GET | `/loans/{loan_number}/closing-quote` | `loans_service.closing_quote` | `userlist`, visible |
| POST | `/loans/{loan_number}/collections` | `loans_service.collect` | `userlist`, visible |
| POST | `/loans/{loan_number}/top-ups` | `loans_service.top_up` | `newcustomer`, visible |
| POST | `/loans/{loan_number}/close` | `loans_service.close` | `userlist`, visible |
| PUT | `/loans/{loan_number}/items` | `loans_service.edit_items` | `newcustomer`, visible |
| PUT | `/loans/{loan_number}/follow-up` | `loans_service.set_follow_up` | `userlist`, visible |
| GET | `/receipts/loans/{loan_number}` | `receipts_service.for_loan` | `userlist`, visible |
| GET | `/receipts/statements/{statement_id}` | `receipts_service.for_statement` | `userlist`, visible |
| POST | `/imports/preview` | `import_service.preview` | `history` |
| POST | `/imports` | `import_service.commit` | `history`, visible |
| GET | `/cash?branch=` | `cash_service.overview` | `cashbook`, visible (head office must pass `branch`) |
| POST | `/cash/days` | `cash_service.start_day` (201) | `cashbook`, visible |
| POST | `/cash/days/{day_id}/entries` | `cash_service.add_entry` (201) | `cashbook`, visible, today's open day |
| POST | `/cash/entries/{entry_id}/void` | `cash_service.void_entry` | `cashbook`, visible, today's open day |
| POST | `/cash/days/{day_id}/close` | `cash_service.close_day` | `cashbook`, visible, today's open day |
| POST | `/cash/days/{day_id}/reopen` | `cash_service.reopen_day` | HQ; the branch's latest day, today only |
| GET | `/dashboard` | `reports_service.dashboard` | `analytics`, scope |
| GET | `/dashboard/performance` | `reports_service.performance` | `analytics`, scope |
| GET | `/dashboard/details/{metric}` | `reports_service.details` | `analytics`, scope |
| GET | `/dashboard/portfolio` | `reports_service.portfolio` | `analytics`, scope |
| GET | `/reports/transactions` | `reports_service.transactions` | `report`, scope |
| GET | `/reports/transactions.csv` | `reports_service.transactions_csv` | `report`, scope |
| GET | `/settings/gold-rate` | `reports_service.gold_rate` | signed in |
| PUT | `/settings/gold-rate` | `reports_service.set_gold_rate` | HQ |
| GET | `/audit-logs` | `maintenance_service.audit_page` | HQ |
| GET | `/admin/accounts` | `branches_service.list_accounts` | SuperAdmin |
| POST | `/admin/branches` | `branches_service.create_branch` | SuperAdmin |
| PATCH | `/admin/accounts/{username}` | `branches_service.update_branch` | SuperAdmin |
| POST | `/admin/accounts/{username}/reset-password` | `branches_service.reset_password` | SuperAdmin |
| POST | `/admin/accounts/{username}/active` | `branches_service.set_active` | SuperAdmin |
| POST | `/admin/accounts/{username}/unlock` | `branches_service.unlock` | SuperAdmin |
| DELETE | `/admin/accounts/{username}` | `branches_service.delete_branch` | SuperAdmin; refused (`branch_in_use`) while the branch has customers or cash days |
| POST | `/backup/check` | `backup_service.check` | head office incl. SuperAdmin |
| POST | `/backup/restore` | `backup_service.restore` | SuperAdmin + "RESTORE" |
| GET | `/backup/email` | `backup_email_service.email_settings` | head office incl. SuperAdmin |
| PUT | `/backup/email` | `backup_email_service.set_email_settings` | SuperAdmin |
| POST | `/backup/email/send` | `backup_email_service.send_now` ("Email backup now") | head office incl. SuperAdmin (1 per 10 min, `email_backup_too_soon`) |
| GET | `/health` | — | — |
| GET | `/health/ready` | database check | — |
| GET | `/cron/daily` | `maintenance_service.run_daily` | `Authorization: Bearer CRON_SECRET` |

Writes to loans take a client-generated `request_id` (replays return the original result) and, where an
amount was shown, `expected_total` (a changed amount returns 409 `outstanding_changed` with the new quote).
`POST /loans`, `/collections` and `/top-ups` take no date: an unknown field returns 422 `invalid_request`.

Response fields worth knowing (money is always a two-decimal string):
- **Quote** (`loan.outstanding` and `GET …/closing-quote`): `as_of`, `principal`, `interest`, `total`,
  `period_days`, `compoundings_due`, `first_week` (bool), `window_peak` (money or null) and
  `first_week_interest` (money, non-null only while `first_week`).
- **Loan**: also `follow_up_date` (stored date, else loan date + 364 for open loans, null for closed) and
  `follow_up_set` (true only when staff stored a date).
- **Statement row**: also `in_first_week` (a new-system row, not the opening, dated in days 1–7, that
  charged nothing: `accrued_days` 0 and no interest; rows posted under the earlier rule are not flagged). Rows from
  `GET /loans/{loan_number}` (not receipts) add `calculation`: `method` (`opening`, `first_week`,
  `first_week_settlement`, `inclusive`, `compounding`, `writeoff`, `legacy`, `as_recorded`), `period_from`,
  `period_to`, `days`, `principal_charged`, `rate`, `interest_accrued`, `peak_principal`, `first_week_days`,
  `extra_days`, `extra_principal`, `interest_paid`, `principal_paid`, `principal_balance`, `interest_balance`
  and a plain-English `note`.
- **Portfolio** (`/dashboard`, `/dashboard/portfolio`): `overdue` entries (today > loan date + 365) carry
  `due_date`, `days_overdue` and `followed_up`; `follow_ups` lists open loans that are not overdue and whose
  follow-up date is at most `follow_up_notice_days` (10) days away or has passed, by date then loan number. Both carry
  `follow_up_date`, `follow_up_set` and `follow_up_days` (follow-up date minus today, negative once passed), which the
  dashboard shows as "Due in N days", "Due today" or "Overdue by N days".
- **History import**: each entry is `{date, kind: "addColl"|"disbursement"|"close", amount, write_off_remaining?}`
  (`write_off_remaining` only matters on the close). The preview adds `closes_on` (ISO date or null) and
  `remaining_after_close` (the amount that would be written off, or null when the cash received covers
  everything); each preview row also carries `writeoff_principal` / `writeoff_interest` (null except on a
  write-off row). The preview shows the write-off rows even when it is not yet confirmed; commit then refuses
  with `writeoff_not_confirmed` until `write_off_remaining` is true.
- **Cash ledger**: every write returns the fresh overview for that branch. Overview = `branch`, `branch_name`,
  `today`, `carry_forward` {`amount`, `from_day`}, `today_day` (Day or null), `history` (earlier days in the
  14-day window, newest first), `categories` [{`key`, `label`, `direction` in/out/any}], `suggestions` (custom
  "Other" descriptions, most used first, at most 20) and `can_reopen`. Day = `id`, `day`, `status`
  (open/closed), `carried_forward`, `opening_counted`, `opening_difference`, `cash_in`, `cash_out`, `expected`,
  `closing_counted`, `closing_difference`, `closed_automatically`, `opened_by`, `opened_at`, `closed_by`,
  `closed_at`, `entries` (oldest first). Entry = `id`, `at`, `direction`, `category`, `category_label`,
  `description`, `reference`, `amount`, `recorded_by`, `voided`, `voided_at`, `voided_by`, `void_reason`.
  Bodies: start `{branch?, opening_counted, request_id}`; entry `{direction, category, description?,
  reference?, amount, request_id}`; void `{reason}`; close `{closing_counted, expected_total}`. Codes include
  `branch_required`, `day_already_started`, `no_open_day`, `day_closed`, `entry_voided`, `request_id_reused`,
  `cash_changed` (409, `details.expected`), `reopen_not_allowed`, and field errors with `details.field`.
- **Backups**: there are no snapshot, export or download endpoints. `/backup/check` and `/backup/restore`
  take exactly one of `backup` (a parsed `.json`), `backup_gzip` (a `.json.gz`, base64) or `backup_zip` (the
  emailed ZIP, base64, at most 4.7 M characters) with `zip_password` (12–128 characters; only with
  `backup_zip`); restore also takes `confirmation: "RESTORE"`. Uploads stay under Vercel's 4.5 MB request
  limit. The router passes `app.infra.aeszip.read_backup_zip` to the service, which calls it only after the
  access and RESTORE checks; it takes the single top-level `backup_*.json`, capping the ZIP and the unpacked
  entry at 48 MiB. Codes: `invalid_restore` (zero or several sources), `zip_password` (missing or wrong
  password, `details.field`), `invalid_backup`, `unknown_branches`, `confirmation_required`, `zip_unavailable`
  (503, pyzipper missing). Check returns `format_version`, `created_at`, `created_by`, `kind`, `checksum`
  (`verified` or, for v2 files, `absent`), `counts`, `branch_prefixes`, `warnings`, `missing_branches` and
  `restorable`; restore returns `customers`, `loans`, `entries` and `taken_at`. The email endpoints (including
  `/backup/email/send`) return `configured`, `missing`, `recipient`, `enabled` and `status.nightly` /
  `status.manual` (each `{at, ok, result, message, size_bytes, sha256?, by?}`).

## 9. Reports and dashboard

Definitions live in `app/domain/reports.py` (docstring) and the SQL in `app/repositories/reports.py`:
interest collected = Σ `currentinterest` of payments; principal collected = Σ −`currentprincipal`;
disbursed = new-loan principal + top-ups (`disbursement`, legacy `modify`); compounded = Σ compounding
`currentprincipal`; written off = new split columns or legacy `principlebalance`; closures and gold released
by `closed_at`. Every metric is branch-scoped and uses IST day ranges.

The portfolio (`reports_service.portfolio`) quotes every open loan as of today with the same ledger
functions used for payments, so the dashboard equals what customers would actually owe. Loan-to-value
uses net weight × the manually entered gold rate. "Overdue loans" are those open for more than 365 days;
"Follow-ups due" are the other open loans whose follow-up date (stored, else day 364) is within the next 10 days or has passed.

## 10. Backups and the daily job

`maintenance_service.run_daily` (Vercel Cron, 18:30 UTC = 00:00 IST): applies due compounding loan by loan
(each in its own locked transaction; one failure does not stop the rest), then the cash ledger step
(`cash_service.auto_close_and_purge`: closes days left open before today at their expected figure and deletes
days past the 14-day window, keeping each branch's latest day; results `cash_days_closed` and
`cash_days_purged`, both null if the step failed, which never stops the rest of the job; automatic closes are
audited as user `system`), purges expired sessions and stale throttle rows, then sends the nightly backup
email (`result["backup_email"]`; it never fails the job). Order: compounding → cash auto-close/purge →
session/throttle purges → nightly email. The result has no `snapshot_id`: the backup is built in memory
(`backup_service.backup_bytes`, kind `scheduled`, by `system`) and only emailed. Nothing is stored in the
database; Supabase backups/PITR remain the disaster-recovery layer.

**Format v3** (`domain/backup_codec.py`, standard library only): canonical JSON (`allow_nan=False`) with
`format_version`, `app`, a schema fingerprint, `created_at`/`created_by`, `kind`, a `manifest` (rows and
sha256 per table) and a whole-document `checksum`, gzip-compressed. Reading accepts `.json` and `.json.gz`,
caps the unpacked size (48 MiB), and rejects NaN, duplicate JSON
keys, trailing data and duplicate business keys (customer id, phone, customer number, loan id, loan number,
entry id, request id, one opening entry per loan, cash day id, one cash day per branch and date, cash entry
id and request id; a cash entry whose day is missing is refused). `TABLES` includes `cash_days` and
`cash_entries` (after `app_settings`); restore truncates and reinserts them (days before entries) and resets
their id sequences. Check lists the branches of customers and cash days in `branch_prefixes` (counters are left
out: every sign-in has one, the head office's `AD` too). Check (`missing_branches`) and restore (`unknown_branches`)
also count branch counters, so a file whose customers, cash days or counters name a branch that does not exist here is refused. v2 files still decode (with an
empty cash ledger); a v3 file without a checksum is
refused. The checksum detects damage, not forgery. `inspect()` gives the dry-run report behind
`/backup/check`. New files have kind `scheduled` (nightly) or `manual` ("Email backup now"); files from
before backups were email-only (kinds `pre_restore`, `export`) still check and restore.

**Backup email** (`services/backup_email_service.py`): the SuperAdmin stores one recipient and an on/off
flag (`app_settings.backup_email`, audited). `send_nightly` never raises. Its results are `sent`, `failed`,
`too_large` (over 15 MiB: a notice without the file), `skipped_*` (off or not set up) and
`already_sent_today`; each is stored in `app_settings.backup_email_status` (`nightly` and `manual` halves,
written separately) and audited (`EMAIL_BACKUP`, `EMAIL_BACKUP_NOW`, with the file name and sha256). The ZIP
(`infra/aeszip.py`, AES-256) holds `backup_<IST stamp>.json` (canonical v3 JSON built in memory) and
`README.txt` (how to import it). `send_now` ("Email backup now": HQ and SuperAdmin, once per 10 minutes)
sends the same ZIP at once (kind `manual`, made by the user); failures are shown, not raised. The mailer (`infra/mailer.py`) uses `SMTP_*` settings, a 20 s timeout and exactly one
recipient; when settings or pyzipper are missing, the Backups page lists what is missing.

## 11. Frontend

```
Frontend/src/
  main.jsx            theme, global CSS, <App/>
  app/                App (providers, error boundary), routes (lazy pages + guards), guards
  auth/AuthContext    session (me/login/logout/change-password), CSRF token, head-office branch filter
  api/                client.js (fetch wrapper), endpoints.js (one function per endpoint)
  hooks/useAsync.js   useAsync (load, abort, resetKey), useSubmit (no double submit), useDocumentTitle, useFocusOnChange
  lib/                money, dates (IST), interest (calculator only), items, validation, permissions, ledger labels
  ui/                 design system (see below)
  features/<area>/    pages and their dialogs
  print/              letterhead, receipts, print.css, Share as PDF (pdf.js, receiptCanvas.js, ShareReceipt.jsx)
```

Routes (`app/routes.jsx`; every page is lazy-loaded):

| Path | Page | Guard |
|---|---|---|
| `/login` | `features/auth/LoginPage.jsx` | public |
| `/` | `features/dashboard/DashboardPage.jsx` | `analytics` (else redirect to the first allowed page: `/customers`, `/reports`, `/tools/calculator`, `/cash`, `/history`, then `/account`; SuperAdmin → `/customers`) |
| `/account` | `features/auth/AccountPage.jsx` | signed in (also the forced password change) |
| `/customers` | `features/customers/CustomerListPage.jsx` | `userlist` |
| `/customers/new` | `features/customers/NewCustomerPage.jsx` | `newcustomer` + `userlist` |
| `/customers/:customerId` | `features/customers/CustomerPage.jsx` | `userlist` |
| `/customers/:customerId/loans/new` | `features/loans/NewLoanPage.jsx` | `newcustomer` + `userlist` |
| `/loans/:loanNumber` | `features/loans/StatementPage.jsx` | `userlist` |
| `/reports` | `features/reports/ReportPage.jsx` | `report` |
| `/history` | `features/history/HistoryImportPage.jsx` | `history` |
| `/cash` | `features/cash/CashLedgerPage.jsx` (dialogs in `CashDialogs.jsx`, pieces in `CashParts.jsx`) | `cashbook` |
| `/tools/calculator` | `features/tools/CalculatorPage.jsx` | `form1` |
| `/settings` | `features/admin/SettingsPage.jsx` (gold rate) | HQ only (`hq`) |
| `/backup` | `features/backup/BackupPage.jsx` | head office incl. SuperAdmin (`headOffice`) |
| `/audit` | `features/admin/AuditLogPage.jsx` | HQ only (`hq`) |
| `/admin/branches` | `features/admin/BranchesPage.jsx` | SuperAdmin |
| `/print/loan/:loanNumber` | `print/LoanReceiptPage.jsx` (no app shell) | `userlist` |
| `/print/entry/:statementId` | `print/EntryReceiptPage.jsx` (no app shell) | `userlist` |
| `/superadmin/*` | redirect to `/admin/branches` (old bookmarks) | — |
| `*` | `features/NotFoundPage.jsx` (also the removed `/tools/application-form`) | — |

Navigation (`ui/AppShell.jsx`) has two groups. **Branch operations**: Dashboard, Customers, New customer
(hidden for SuperAdmin, who adds customers from the list), Reports, Cash ledger (`cashbook`), History import,
Loan calculator.
**Head office**: Gold rate and Audit log (HQ), Backups (HQ and SuperAdmin), Branches & Users (SuperAdmin). The
head-office branch picker starts with "Admin – all branches" (`ALL_BRANCHES_LABEL`, value `""`) and leaves
out the head-office branch itself.

**Data flow**: pages call `api/endpoints.js` through `useAsync`. The client sends cookies same-origin, adds
`X-CSRF-Token` on writes, times out after 30 s, turns error envelopes into `ApiError` (with `fieldErrors()`),
and broadcasts session expiry so `AuthContext` returns to sign-in. Changing a page's inputs clears its data;
`resetKey` keeps rows while only the page number changes.

**Design system** (`ui/`):
- `tokens.css`: colours (light, dark via `prefers-color-scheme` or `data-theme`, and forced-light print),
  spacing `--space-1…8`, type `--text-xs…2xl`, radii, shadows, z-index. `tests/contrast.test.js` enforces
  WCAG AA for every colour pair in both themes.
- `base.css` (reset, focus ring, `.visually-hidden`, skip link, reduced motion) and `components.css`.
- Components: `controls.jsx` (`Button`, `IconButton`, `Segmented`, `Pagination`, `ThemeToggle`, `Spinner`),
  `fields.jsx` (`TextField`, `AmountField`, `WeightField`, `DateField`, `SelectField`, `TextareaField`,
  `CheckboxField`, `focusFirstError`), `surfaces.jsx` (`Card`, `PageHeader`, `Banner`, `Pill`, `LoanStatus`,
  `Details`, `SummaryList`, `Stepper`), `feedback.jsx` (`EmptyState`, `ErrorState`, `Skeleton(Rows)`,
  `PageLoading`, `ToastProvider`/`useToast`), `Modal.jsx` (`Modal` with `focusKey`, `ConfirmDialog`),
  `DataTable.jsx`, `charts.jsx` (`ColumnChart`, `BarList`), `Icon.jsx`, `AppShell.jsx`, `ErrorBoundary.jsx`.

**Accessibility patterns**: every field has a visible label, hint and error wired with `aria-describedby`;
failed submits focus the first invalid field; dialogs trap focus, close on Escape, restore focus; status
uses text, not colour alone; toasts and result counts use persistent live regions; Malayalam is marked
`lang="ml"`; targets are at least 24 px; the drawer makes the page inert while open.

**Printing**: receipts load everything from `/receipts/*` and use the loan's branch letterhead
(`print/printing.jsx`); printing is always light. `loanSheet()` / `entrySheet()` describe each copy once, and
`Sheet` renders it on screen. **Share** (`print/ShareReceipt.jsx`, beside Print in `PrintToolbar`) draws the
Customer copy from the same description on a 200-dpi canvas (`receiptCanvas.js`, live colours and fonts,
Malayalam drawn by the browser) and wraps the JPEG in a one-page A4 PDF (`pdf.js`, no dependency). It uses
`navigator.share` with the file when the device can; otherwise it saves the PDF and offers WhatsApp
(`wa.me`, valid mobile numbers only) and `mailto:` links with a short fixed message. No receipt data goes
into a URL.

**Cash ledger page**: branch staff see their own drawer; head office picks one branch in a `SelectField` (default
the picker's branch, else its own). Every figure shown comes from the server's overview; the browser only
previews the difference while typing a count (`lib/money.js`, display only). Earlier days are disclosure
buttons (`aria-expanded`/`aria-controls`); voided entries are struck through and labelled "Voided". Closing
sends the shown `expected`; on 409 `cash_changed` the page reloads the overview.

**History import page**: entry types Payment received, Additional principal and Loan closed (settled), the
last offered only on the last entry; after a close "Add an entry" is disabled. The review shows the server's
closing rows, "imported as closed on …" and, when `remaining_after_close` is set, a "Write off the remaining
₹…" checkbox that sets `write_off_remaining` on the close entry.

**Statement**: "Show calculation" (`LedgerCard` in `StatementPage.jsx`, `aria-pressed`) adds a `DataTable`
`detail` row under each entry. `LedgerCalculation.jsx` only formats the server's `calculation`; labels come
from `lib/ledger.js`.

## 12. Deployment

- `vercel.json`: legacy `builds` (Python function + static build) and `routes` (headers, API, static files,
  SPA fallback), daily cron. `.vercelignore` keeps tests, scripts and migrations out of the deployment.
- `.github/workflows/ci.yml`: backend compile, import, unit tests, `pip-audit`; frontend `npm ci`, lint,
  tests, bundle check, build, `npm audit`.
- `BackendPython/requirements.txt` includes `pyzipper` for the encrypted backup ZIP; the API still starts
  without it (email then reports "pyzipper is not installed").
- Environment variables: see the [README](../README.md#environment-variables), including the optional
  `SMTP_*` / `BACKUP_ZIP_PASSWORD` settings. If the nightly email step times out, raise the function's Max Duration.

## 13. Testing strategy

| Where | What |
|---|---|
| `BackendPython/tests/test_interest_vectors.py`, `test_ledger.py`, `test_dates.py` | business rules, including the first-7-days rule |
| `test_statement_calc.py` | "Show calculation" working, legacy and as-recorded rows |
| `test_follow_up.py` | day-364 follow-ups, overdue after 365 days |
| `test_particulars_validation.py`, `test_reports_codec.py` | items, validation, reports maths, CSV, backup codec v2/v3 |
| `test_security.py` | passwords, sessions, CSRF, throttling |
| `test_services.py` (with `tests/fakes.py`) | every service end to end: auth, customers, loans, closing, import, reports, admin, receipts, role matrix |
| `test_history_parity.py` | history import equals the same loan recorded live (21 scenarios, including every kind of close), and the import close rules |
| `test_cash.py` | cash ledger rules, the day flow (carry forward, entries, voids, close, reopen, auto-close, purge), access per role, request bodies |
| `test_backup_service.py`, `test_backup_email.py` (with `tests/backup_fakes.py`) | backups built in memory (nothing stored), Check, restore (including the cash ledger and the emailed ZIP), the backup routes, the daily job, the nightly email and "Email backup now" |
| `test_aeszip.py` | AES-256 ZIP round trip, wrong password, `read_backup_zip` (one backup entry, size caps) |
| `test_repositories.py` | every SQL statement: placeholders, no user input in SQL text |
| `test_middleware_config.py` | middleware, configuration, the SMTP mailer (fake SMTP) |
| `test_integrity_doc.py` | every test is listed in [INTEGRITY.md](INTEGRITY.md) |
| `Frontend/tests/lib.test.js` | money, dates, interest parity, items, validation, permissions, calculation labels |
| `Frontend/tests/client.test.js` | API client, downloads |
| `Frontend/tests/ui.test.jsx` | component accessibility markup |
| `Frontend/tests/pages.test.jsx` | every page renders for each role; gating, navigation, statement toggle, dialogs |
| `Frontend/tests/print.test.jsx` | receipts, Share, the Backups page (Backup email, Import backup with the ZIP password) |
| `Frontend/tests/cash.test.jsx` | the Cash ledger page: start card, today's summary, voided entries, closed and reopen states, history disclosures, no browser arithmetic |
| `Frontend/tests/history.test.jsx` | History import: the close entry, the review's closing rows and write-off confirmation, the payload |
| `Frontend/tests/pdf.test.js`, `backup.test.js` | PDF writer, receipt canvas, backup upload helpers (ZIP, gzip, ZIP password) |
| `Frontend/tests/contrast.test.js` | colour contrast in both themes |

The full list, one line per test, is [INTEGRITY.md](INTEGRITY.md).

Offline checks: `scripts/run-tests.mjs` bundles each test with esbuild and runs `node --test`;
`scripts/check-bundle.mjs` bundles the app and fails on unexpected dependencies.

## 14. Known limitations

- The API and migrations have not yet been run against real FastAPI/Postgres; no end-to-end tests yet.
- Dev tooling is behind (vite 4, eslint 8); the lockfile was pruned rather than regenerated.
- Python dependencies use version ranges, not a lock file.
- Legacy `sha256:` passwords work until each user's next sign-in, then are upgraded.
- The backup email is tested with a fake SMTP server only; the first real send is the manual check in
  [INTEGRITY.md](INTEGRITY.md#4-manual-checks).
- `scripts/migrate.py` assumes the previous schema exists: on an empty database the prefix assignment
  and preflight query `customers`/`role` before `001_baseline.sql` creates them, and fail.
