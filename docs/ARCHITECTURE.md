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
| Services | `app/services/` | domain, security, errors | One use case per function, one transaction per write. Never import FastAPI or asyncpg. |
| Repositories | `app/repositories/` | domain (codec) | All SQL, parameterized; table/column names only from constants. |
| HTTP | `app/routers/`, `schemas.py`, `auth.py`, `main.py`, `db.py` | everything | Thin: parse, call a service, return. |

Because services receive repositories as an argument, tests run every service against in-memory
fakes (`tests/fakes.py`) with no database.

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
- **Payments**: interest first, then principal. A payment of the whole amount due is not a collection:
  it must use **Close**. In a loan's first 7 days payments may cover interest only.
- **Closing**: within 7 days (inclusive age) at least 7 days of interest are charged in total. The cash
  actually received is recorded; any remainder is written off only when explicitly confirmed, with principal
  and interest written off stored separately.
- **Dates**: branches always record "now". Head office may enter a past date (never before the loan's
  latest entry, never in the future). History import (a SuperAdmin-granted feature) enters past-dated loans.
- **Legacy credit**: a negative interest balance from the earlier system is netted against principal.

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
  a closing payment and its write-off are exactly 1 µs apart, which is how receipts pair them.

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
| `app_settings` | settings | `gold_rate` → `{"per_gram": "…"}` |
| `backup_snapshots` | gzip JSON snapshots | `kind` (scheduled/manual/pre_restore), `sha256`, `payload` |
| `audit_logs` | who did what | `username`, `action`, `entity_id`, `details`, `ip`, `request_id` |
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
| `003_ledger_reporting.sql` | `closed_at`, `items`, ledger detail columns, checks, settings, snapshots |
| `004_post_cutover.sql` | drop the legacy trigger, validate constraints (run after go-live) |

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
  `branch` accounts only their own. Records of other branches return 404.

| Feature key | Grants | Enforced in |
|---|---|---|
| `analytics` | dashboard, performance, drill-downs | `reports_service._scope` |
| `userlist` | customer list and pages, loan statement, payments, closing, follow-ups, receipts | `customers_service`, `loans_service`, `receipts_service` |
| `newcustomer` | new customers, new loans, add principal, edit items (implies `userlist`) | `customers_service.create`, `loans_service.create/top_up/edit_items` |
| `report` | transaction report and CSV | `reports_service.transactions*` |
| `history` | history import (past-dated loans); opt-in for new branches | `import_service` |
| `form1` | application form, calculator (browser only) | route guards |
| head office | gold rate, backups (view/export/snapshot), audit log | `require_head_office` |
| SuperAdmin | branches and accounts, restore | `require_superadmin` |

- **Backups**: export never contains credentials, sessions or audit logs; restore is SuperAdmin-only, needs
  the typed word RESTORE, saves a `pre_restore` snapshot first, revalidates logos, never re-grants
  permissions, and relaxes the NOT VALID constraints only inside its transaction.
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
| GET | `/dashboard` | `reports_service.dashboard` | `analytics`, scope |
| GET | `/dashboard/performance` | `reports_service.performance` | `analytics`, scope |
| GET | `/dashboard/details/{metric}` | `reports_service.details` | `analytics`, scope |
| GET | `/dashboard/portfolio` | `reports_service.portfolio` | `analytics`, scope |
| GET | `/reports/transactions` | `reports_service.transactions` | `report`, scope |
| GET | `/reports/transactions.csv` | `reports_service.transactions_csv` | `report`, scope |
| GET | `/settings/gold-rate` | `reports_service.gold_rate` | signed in |
| PUT | `/settings/gold-rate` | `reports_service.set_gold_rate` | head office |
| GET | `/audit-logs` | `maintenance_service.audit_page` | head office |
| GET | `/admin/accounts` | `branches_service.list_accounts` | SuperAdmin |
| POST | `/admin/branches` | `branches_service.create_branch` | SuperAdmin |
| PATCH | `/admin/accounts/{username}` | `branches_service.update_branch` | SuperAdmin |
| POST | `/admin/accounts/{username}/reset-password` | `branches_service.reset_password` | SuperAdmin |
| POST | `/admin/accounts/{username}/active` | `branches_service.set_active` | SuperAdmin |
| POST | `/admin/accounts/{username}/unlock` | `branches_service.unlock` | SuperAdmin |
| DELETE | `/admin/accounts/{username}` | `branches_service.delete_branch` | SuperAdmin |
| GET | `/backup/snapshots` | `backup_service.list_snapshots` | head office |
| POST | `/backup/snapshots` | `backup_service.manual_snapshot` | head office (1 per 10 min) |
| GET | `/backup/snapshots/{snapshot_id}/download` | `backup_service.snapshot_json` | head office |
| GET | `/backup/export` | `backup_service.export_json` | head office |
| POST | `/backup/restore` | `backup_service.restore` | SuperAdmin + "RESTORE" |
| GET | `/health` | — | — |
| GET | `/health/ready` | database check | — |
| GET | `/cron/daily` | `maintenance_service.run_daily` | `Authorization: Bearer CRON_SECRET` |

Writes to loans take a client-generated `request_id` (replays return the original result) and, where an
amount was shown, `expected_total` (a changed amount returns 409 `outstanding_changed` with the new quote).

## 9. Reports and dashboard

Definitions live in `app/domain/reports.py` (docstring) and the SQL in `app/repositories/reports.py`:
interest collected = Σ `currentinterest` of payments; principal collected = Σ −`currentprincipal`;
disbursed = new-loan principal + top-ups (`disbursement`, legacy `modify`); compounded = Σ compounding
`currentprincipal`; written off = new split columns or legacy `principlebalance`; closures and gold released
by `closed_at`. Every metric is branch-scoped and uses IST day ranges.

The portfolio (`reports_service.portfolio`) quotes every open loan as of today with the same ledger
functions used for payments, so the dashboard equals what customers would actually owe. Loan-to-value
uses net weight × the manually entered gold rate.

## 10. Backups and the daily job

`maintenance_service.run_daily` (Vercel Cron, 18:30 UTC = 00:00 IST): applies due compounding loan by loan
(each in its own locked transaction; one failure does not stop the rest), stores a `scheduled` snapshot,
purges expired sessions and stale throttle rows. Snapshots are pruned per kind: 14 scheduled, 10
pre-restore, 5 manual. Snapshots protect against mistakes; Supabase backups/PITR protect against losing
the database.

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
  print/              letterhead, receipts, print.css
```

Routes (`app/routes.jsx`; every page is lazy-loaded):

| Path | Page | Guard |
|---|---|---|
| `/login` | `features/auth/LoginPage.jsx` | public |
| `/` | `features/dashboard/DashboardPage.jsx` | `analytics` (else redirect to the first allowed page) |
| `/account` | `features/auth/AccountPage.jsx` | signed in (also the forced password change) |
| `/customers` | `features/customers/CustomerListPage.jsx` | `userlist` |
| `/customers/new` | `features/customers/NewCustomerPage.jsx` | `newcustomer` + `userlist` |
| `/customers/:customerId` | `features/customers/CustomerPage.jsx` | `userlist` |
| `/customers/:customerId/loans/new` | `features/loans/NewLoanPage.jsx` | `newcustomer` + `userlist` |
| `/loans/:loanNumber` | `features/loans/StatementPage.jsx` | `userlist` |
| `/reports` | `features/reports/ReportPage.jsx` | `report` |
| `/history` | `features/history/HistoryImportPage.jsx` | `history` |
| `/tools/application-form` | `features/tools/ApplicationFormPage.jsx` | `form1` |
| `/tools/calculator` | `features/tools/CalculatorPage.jsx` | `form1` |
| `/settings` | `features/admin/SettingsPage.jsx` (gold rate) | head office |
| `/backup` | `features/backup/BackupPage.jsx` | head office |
| `/audit` | `features/admin/AuditLogPage.jsx` | head office |
| `/admin/branches` | `features/admin/BranchesPage.jsx` | SuperAdmin |
| `/print/loan/:loanNumber` | `print/LoanReceiptPage.jsx` (no app shell) | `userlist` |
| `/print/entry/:statementId` | `print/EntryReceiptPage.jsx` (no app shell) | `userlist` |
| `/superadmin/*` | redirect to `/login` (old bookmarks) | — |
| `*` | `features/NotFoundPage.jsx` | — |

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
(`print/printing.jsx`); `printOnly()` prints one sheet; printing is always light.

## 12. Deployment

- `vercel.json`: legacy `builds` (Python function + static build) and `routes` (headers, API, static files,
  SPA fallback), daily cron. `.vercelignore` keeps tests, scripts and migrations out of the deployment.
- `.github/workflows/ci.yml`: backend compile, import, unit tests, `pip-audit`; frontend `npm ci`, lint,
  tests, bundle check, build, `npm audit`.
- Environment variables: see the [README](../README.md#environment-variables).

## 13. Testing strategy

| Where | What |
|---|---|
| `BackendPython/tests/test_interest_vectors.py`, `test_ledger.py`, `test_dates.py` | business rules |
| `test_particulars_validation.py`, `test_reports_codec.py` | items, validation, reports maths, CSV, backup codec |
| `test_security.py` | passwords, sessions, CSRF, throttling |
| `test_services.py` (with `tests/fakes.py`) | every service end to end: auth, customers, loans, closing, import, reports, admin, receipts |
| `test_repositories.py` | every SQL statement: placeholders, no user input in SQL text |
| `test_middleware_config.py` | middleware and configuration |
| `Frontend/tests/lib.test.js` | money, dates, interest parity, items, validation, permissions |
| `Frontend/tests/client.test.js` | API client |
| `Frontend/tests/ui.test.jsx` | component accessibility markup |
| `Frontend/tests/pages.test.jsx` | every page renders for each role; gating |
| `Frontend/tests/contrast.test.js` | colour contrast in both themes |

Offline checks: `scripts/run-tests.mjs` bundles each test with esbuild and runs `node --test`;
`scripts/check-bundle.mjs` bundles the app and fails on unexpected dependencies.

## 14. Known limitations

- The API and migrations have not yet been run against real FastAPI/Postgres; no end-to-end tests yet.
- Dev tooling is behind (vite 4, eslint 8); the lockfile was pruned rather than regenerated.
- Python dependencies use version ranges, not a lock file.
- Legacy `sha256:` passwords work until each user's next sign-in, then are upgraded.
- `scripts/migrate.py` assumes the previous schema exists: on an empty database the prefix assignment
  and preflight query `customers`/`role` before `001_baseline.sql` creates them, and fail.
