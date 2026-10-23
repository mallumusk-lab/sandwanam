# CLAUDE.md: rules for every change to Gold Loan Desk

The user usually asks for fixes by pasting a **screenshot** and describing the change. Each fix is
local, but the app handles money, so every fix must follow the same rules. Read this file fully before
editing. For deeper detail see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); for setup and operations see
[README.md](README.md).

## 1. The project in five lines

- Gold-loan desk for branch staff, head office (HQ) and a SuperAdmin: customers, pledged gold, loans,
  payments, closures, receipts, reports, history import, the branch cash ledger, backups, branch administration.
- `Frontend/`: React 18 + React Router, built with Vite. Its only runtime dependencies are `react`,
  `react-dom` and `react-router-dom`.
- `BackendPython/`: FastAPI + asyncpg + Pydantic v2, served under `/api` on the same domain (Vercel).
  `pyzipper` (AES-256 ZIP for the nightly backup email) is the only other dependency, used only in `app/infra/`.
- Database: Supabase Postgres. Schema changes go only through numbered files in `BackendPython/migrations/`.
- Interest rules are agreed with the business and pinned by `test-vectors/interest.json`.

### Hard limits (never cross without the user saying so in this conversation)

1. **Never connect to any database or URL.** No Supabase, no production, no network. Every check below runs offline.
2. **Never read or write `.env`, `.env.*` or `.env.example`** files.
3. **No git commands** (status, diff, commit, …) unless the user asks.
4. **Never change a business rule** without explicit approval. Business rules are interest, day counting,
   compounding, the 7-day minimum, payment allocation, backdating, permissions and branch scope. The same
   applies to `test-vectors/interest.json`, `app/domain/interest.py`, `app/domain/ledger.py` and
   `Frontend/src/lib/interest.js`. If a screenshot fix seems to need one, **stop and ask**.
5. **No new npm or pip dependencies** without approval. Never hand-edit `package-lock.json`.

## 2. Screenshot → code map

Identify the screen from its **page heading** (big title at the top) or the URL. All frontend paths are
under `Frontend/src/`, all backend paths are under `BackendPython/app/`. API wrappers are in
`api/endpoints.js` (grouped as `auth`, `branches`, `customers`, `loans`, `receipts`, `imports`, `dashboard`,
`reports`, `settings`, `backup`, `admin`, `cash`).

| Screen (heading · URL) | Page file | Pieces on it | API group → service | Tests |
|---|---|---|---|---|
| **Sign in** · `/login` | `features/auth/LoginPage.jsx` | form, throttle message | `auth` → `services/auth_service.py` (`login`) | `tests/test_services.py`, `tests/test_security.py` |
| **Your account / Set your password** · `/account` | `features/auth/AccountPage.jsx` | profile, password form (also the forced first-sign-in change) | `auth` → `auth_service.change_password` | same |
| **Dashboard** · `/` | `features/dashboard/DashboardPage.jsx` | KPI tiles (`Kpi`), "Disbursed and collected" chart, "Follow-ups due" and "Overdue loans" cards, `features/shared/FollowUpDialog.jsx`, gold-rate banner | `dashboard`, `loans` → `reports_service.dashboard/portfolio`, `loans_service.set_follow_up`; rules in `domain/reports.py` | `tests/test_services.py`, `tests/test_follow_up.py`, `tests/test_reports_codec.py` |
| ↳ **Performance** panel | `features/dashboard/PerformancePanel.jsx` | period picker, `KpiButton` | `dashboard` → `reports_service.performance` | same |
| ↳ drill-down dialog | `features/dashboard/DetailDialog.jsx` | table in a `Modal` | `dashboard` → `reports_service.details` | same |
| **Customers** · `/customers` | `features/customers/CustomerListPage.jsx` | search, branch filter, `DataTable`, `Pagination` | `customers` → `customers_service.search` | `Frontend/tests/pages.test.jsx` |
| **New customer** · `/customers/new` | `features/customers/NewCustomerPage.jsx` | form, duplicate-phone banner | `customers`, `branches` → `customers_service.create` | `test_services.py` |
| **Customer name** · `/customers/:customerId` | `features/customers/CustomerPage.jsx` | `LoanCard` per loan (follow-up date, "(automatic)", Follow-up button → `FollowUpDialog`) | `customers`, `loans` → `customers_service.detail`, `loans_service.set_follow_up` | `test_services.py`, `test_follow_up.py`, `pages.test.jsx` |
| ↳ **Record payment / Add principal** dialog | `features/customers/LoanDialogs.jsx` → `PostingDialog` | `OutstandingSummary`, `FirstWeekBanner` (server's `first_week`), `SuccessPanel` | `loans` → `loans_service.collect` / `top_up` | `test_services.py`, `tests/test_ledger.py` |
| ↳ **Close loan …** dialog | `LoanDialogs.jsx` → `CloseLoanDialog` | quote, first-week banner (`window_peak`), write-off confirmation | `loans` → `loans_service.closing_quote` / `close` | same |
| ↳ **Edit items** dialog | `LoanDialogs.jsx` → `EditItemsDialog` | `features/loans/ItemsEditor.jsx` | `loans` → `loans_service.edit_items` | `tests/test_particulars_validation.py` |
| **New loan** · `/customers/:id/loans/new` | `features/loans/NewLoanPage.jsx` | "Pledged gold" (`ItemsEditor`), "Loan terms" | `customers`, `loans` → `loans_service.create` | `test_services.py` |
| **Statement · LOAN** · `/loans/:loanNumber` | `features/loans/StatementPage.jsx` | "Loan details", "Ledger" table (`LedgerCard`) with the "Show calculation" toggle (`LedgerCalculation.jsx`, `DataTable` `detail` row), labels from `lib/ledger.js` | `loans` → `loans_service.detail`; working from `domain/statement_calc.py` | `test_services.py`, `tests/test_statement_calc.py`, `Frontend/tests/lib.test.js`, `pages.test.jsx` |
| **Reports** · `/reports` | `features/reports/ReportPage.jsx` | period presets, transaction table, CSV, print | `reports` → `reports_service.transactions` / `transactions_csv` | `test_reports_codec.py`, `tests/test_repositories.py` |
| **History import** · `/history` | `features/history/HistoryImportPage.jsx` | `Stepper`: `CustomerStep`, `LoanStep` (entries: Payment received, Additional principal, Loan closed (settled) on the last entry only), `ReviewStep` (server's closing rows, "imported as closed on …", "Write off the remaining ₹…" checkbox → `write_off_remaining`) | `imports`, `customers`, `branches` → `services/import_service.py`; replay in `domain/ledger.py` `simulate` | `test_services.py`, `tests/test_history_parity.py`, `tests/test_ledger.py`, `Frontend/tests/history.test.jsx` |
| **Cash ledger** · `/cash` | `features/cash/CashLedgerPage.jsx` | branch select (head office), "Start the day", "Today · …" summary + entries table, "Add entry", "Last 14 days" disclosures; dialogs in `features/cash/CashDialogs.jsx` (`VoidEntryDialog`, `CloseDayDialog`, `ReopenDayDialog`); pills and tables in `features/cash/CashParts.jsx` | `cash` → `services/cash_service.py`; rules in `domain/cash.py`; SQL in `repositories/cash.py` | `tests/test_cash.py`, `test_repositories.py`, `test_backup_service.py`, `Frontend/tests/cash.test.jsx`, `pages.test.jsx` |
| **Loan calculator** · `/tools/calculator` | `features/tools/CalculatorPage.jsx` | estimate, uses `lib/interest.js` (browser only) | none | `lib.test.js` (shared vectors) |
| **Gold rate** · `/settings` (HQ only) | `features/admin/SettingsPage.jsx` | current rate, "Set today's rate" | `settings` → `reports_service.gold_rate` / `set_gold_rate` | `test_services.py` |
| **Backups** · `/backup` (HQ and SuperAdmin) | `features/backup/BackupPage.jsx` | "Backup email" card (`EmailDetails`: address form for the SuperAdmin, last nightly / Email backup now status, **Email backup now**), "Import backup" card (`ImportBackup`: choose a `.zip` + "ZIP password" `PasswordField`, `.json` or `.json.gz`; Check → `CheckReport`; SuperAdmin Import → `RestoreDialog`; helpers in `features/backup/backupFile.js`). No snapshot list, no download button | `backup` → `services/backup_service.py`, `services/backup_email_service.py`; codec `domain/backup_codec.py`; ZIP and mail `infra/aeszip.py`, `infra/mailer.py` | `test_backup_service.py`, `test_backup_email.py`, `test_reports_codec.py` (codec), `test_aeszip.py`, `Frontend/tests/print.test.jsx`, `backup.test.js` |
| **Audit log** · `/audit` (HQ only) | `features/admin/AuditLogPage.jsx` | filtered table | `settings` → `maintenance_service.audit_page` | `test_services.py` |
| **Branches** · `/admin/branches` | `features/admin/BranchesPage.jsx` | `BranchDialog`, `PasswordDialog`, `ConfirmDialog` | `admin` → `services/branches_service.py` | `test_services.py` |
| **Loan voucher** (print) · `/print/loan/:loanNumber` | `print/LoanReceiptPage.jsx` (`loanSheet`) | `print/printing.jsx` (`Sheet`, `Letterhead`, `Terms`, `Signatures`, `CutLine`, `PrintToolbar`), Share beside Print (`print/ShareReceipt.jsx`, `receiptCanvas.js`, `pdf.js`) | `receipts` → `receipts_service.for_loan` | `test_services.py`, `Frontend/tests/print.test.jsx`, `pdf.test.js` |
| **Entry receipt** (print) · `/print/entry/:statementId` | `print/EntryReceiptPage.jsx` (`entrySheet`, first-7-days line) | same print pieces | `receipts` → `receipts_service.for_statement` | same |
| **This page doesn't exist** · any other URL | `features/NotFoundPage.jsx` | | | `pages.test.jsx` |
| (old bookmark) · `/superadmin/*` | redirect in `app/routes.jsx` | goes to `/admin/branches` | | |
| (removed) · `/tools/application-form` | none: falls through to `NotFoundPage.jsx` | | | `pages.test.jsx` |

Shared pieces seen on many screens:

| You see | It lives in |
|---|---|
| Sidebar, top bar, mobile drawer, branch picker (head office; first option "Admin – all branches", `branchOptions`), theme toggle, nav items in two groups, **Branch operations** and **Head office** | `ui/AppShell.jsx` (`NAV` at the top of the file; `hq`, `headOffice`, `superadmin`, `notSuperadmin` flags) |
| "You don't have access" / redirects | `app/guards.jsx` (`RequireAuth`, `RequirePermission` with `permission`, `hq`, `headOffice`, `superadmin`), routes in `app/routes.jsx` |
| "Admin – all branches", feature names, `can`, `isHeadOfficeStaff`, `homePath` | `lib/permissions.js` |
| Follow-up dialog (dashboard and customer page) | `features/shared/FollowUpDialog.jsx` |
| Buttons, segmented controls, pager, spinner | `ui/controls.jsx` |
| Inputs, amount/weight/date fields, errors under fields | `ui/fields.jsx` |
| Cards, page header, banners, status pills, stepper | `ui/surfaces.jsx` |
| Empty/error/loading states, toasts | `ui/feedback.jsx` |
| Dialogs and confirmations | `ui/Modal.jsx` |
| Tables (stacked on mobile; optional `detail(row)` full-width row) | `ui/DataTable.jsx` |
| Charts | `ui/charts.jsx` |
| Icons (including `calculator`, `share`, `mail`) | `ui/Icon.jsx` |
| Colours, spacing, fonts, dark mode | `ui/tokens.css`, `ui/base.css`, `ui/components.css`, `ui/theme.js` |
| Print layout | `print/print.css`, `print/printing.jsx` |
| Loan/customer links | `features/shared/links.jsx` |
| Server error messages shown in the UI | the service that raised them (`raise Invalid("…")`) |

If the screenshot does not match a row, search for its visible text: `Grep` the exact words under
`Frontend/src` first, then under `BackendPython/app` (server messages).

## 3. Workflow for every fix

1. **Locate.** Use the map above to find the screen. Grep the visible text to find the exact component.
2. **Read before editing.** Read the page, the components it uses, the API wrapper, the service function
   if data is involved, and the related tests.
3. **Classify the change.**
   - *Display only* (text, layout, spacing, colour, order): frontend only.
   - *Frontend behaviour* (validation message, focus, a new button): frontend, and keep it in line with the server.
   - *Server rule or data* (what is allowed, what is computed, what is stored): the service or domain layer.
     **If it touches money, interest, dates, permissions or branch scope, stop and ask the user first.**
4. **Make the smallest change in the layer that owns the behaviour.** Don't refactor neighbours, rename
   shared components or "tidy up" unrelated code. If a shared `ui/` component must change, check
   every user of it (`Grep` the component name).
5. **Add or update a test** that would have caught the problem, and give it a line in
   [docs/INTEGRITY.md](docs/INTEGRITY.md). Never weaken an existing assertion to make it pass.
6. **Run the checks** in section 6 that apply.
7. **Report** using the template in section 7.

## 4. Invariants: never break these

**Money**
- Never use floats for money or weight. Client: `lib/money.js` (integer paise as `BigInt`; `toPaise`,
  `add`, `subtract`, `compare`, `formatINR`, `normaliseAmount`). Server: `domain/money.py` (`Decimal`).
  JSON carries amounts as strings with two decimals.
- The UI never computes what a customer owes. Amounts due come from the server (`closing_quote`,
  loan detail, including `first_week`, `window_peak` and `first_week_interest`). The calculator
  (`lib/interest.js`) is the only exception and must keep matching `test-vectors/interest.json`.
- Statement calculations come from the server: `calculation` on each row of `GET /loans/{n}`, built by
  `domain/statement_calc.py` from stored rows. `LedgerCalculation.jsx` only formats it, never recalculates.

**Dates**
- Business dates are IST days. Use `lib/dates.js` (`todayIST`, `addDays`, `formatDay`, …) and
  `domain/dates.py` (`business_date`, `ist_day_bounds_utc`). Never `new Date().toISOString().slice(0, 10)`
  outside `lib/dates.js`.

**Ledger**
- Ledger rows are written only by `loans_service` (`create`, `_post` via `collect`/`top_up`/`close`,
  `apply_due_compounding`) and `import_service.commit`. Writes lock the loan row, take a `request_id`
  (idempotency) and, where an amount was shown, `expected_total` (409 `outstanding_changed` if it moved).
- Legacy rows (`created_at` NULL) are never rewritten or "fixed".
- Daily entries (`create`, `collect`, `top_up`, `close`) are always dated today; their request bodies have no
  date field. Past dates come only through `import_service`.
- History import replays through the same ledger functions as live entries (`ledger.simulate`), including a
  `close` entry (last, at most once) that uses `quote(..., closing=True)` and `ledger.close`. An imported loan
  must stay identical to the same loan recorded live: `tests/test_history_parity.py` pins this. Never give
  the import its own interest or closing maths.

**Cash ledger**
- Independent of loans: `cash_service` and `repositories/cash.py` never read or write loan, customer, ledger
  or settings tables, and no other screen, report or dashboard shows cash ledger figures.
- Totals (`cash_in`, `cash_out`, `expected`, differences, carry forward) are computed on the server only
  (`domain/cash.py`); the page shows them as sent. The only browser arithmetic is the display-only difference
  preview while typing a count (`lib/money.js`).
- Entries go only on today's open day, are idempotent by `request_id`, and are voided with a reason, never
  deleted. Closing checks `expected_total` (409 `cash_changed`). Reopen is HQ only, latest day, today only.
- `cash_days` and `cash_entries` are business data in `backup_codec.TABLES`; restore checks their branches.
  The daily job auto-closes old open days and deletes days past 14, keeping each branch's latest day.

**Backend layering**
- `domain/` and `security/`: standard library only. `services/`: never import FastAPI, asyncpg or `infra/`.
- `infra/` (AES ZIP, SMTP) is the only place for `smtplib` and `pyzipper`; routers build the mailer and pass
  it to services, so tests use `FakeMailer` (`tests/backup_fakes.py`) and never touch the network. Likewise the
  backup router passes `aeszip.read_backup_zip` to `backup_service.check`/`restore`, which call it only after
  the access and RESTORE checks.
- SQL only in `repositories/`, always `$1…$n` parameters, never user input in SQL text (f-strings only with
  constant column/table names). `tests/test_repositories.py` checks every statement.
- Routers stay thin: parse, call one service, return.
- Errors: raise `AppError` subclasses from `app/errors.py` (`Invalid`, `NotFound`, `Conflict`, `Forbidden`,
  `Unauthorized`, `TooManyRequests`, `ServiceUnavailable`) with a plain-English message and a `code`.
  A user mistake must never become a 500.

**Access**
- Every service function that reads or writes branch data starts with `actor.require("<feature>")` (or
  `actor.require_head_office()` / `actor.require_superadmin()`), then `resolve_scope(...)` for lists or
  `ensure_visible(...)` for single records (`services/context.py`). Another branch's record is a 404.
- Feature keys (`PERMISSIONS` in `services/context.py`, `FEATURES` in `lib/permissions.js`): `analytics`
  (Dashboard), `userlist` (Customers), `newcustomer` (New customers and loans), `report` (Reports), `history`
  (History import, opt-in for new branches), `form1` (Loan calculator), `cashbook` (Cash ledger). New branches
  get all but `history` (`DEFAULT_PERMISSIONS`, mirrored by the `role.permissions` default in migration 005).
  Head office has every key; the cash ledger is one branch at a time (head office must pass `branch`).
- A SuperAdmin has only `SUPERADMIN_FEATURES` (`newcustomer`, `userlist`): customers and loans of any branch,
  no cash ledger.
  `require_head_office()` is **HQ only** (gold rate, audit log). Backups check `actor.is_head_office`, which
  includes the SuperAdmin (Check a file, "Email backup now"). Restore (Import) and the backup email address
  are `require_superadmin()`.
- UI gating (`can()` from `lib/permissions.js`, `RequirePermission`, nav `permission:` keys) mirrors the
  server and never replaces it. `newcustomer` implies `userlist` (`CREATE`). For a SuperAdmin `can()` follows
  the server's `permissions` list; `hq: true` guards HQ-only pages.

**Database**
- Schema changes only as a **new** numbered migration (next: `006_….sql`, idempotent: `IF NOT EXISTS`, one
  transaction). Never edit an applied migration (000–004). `005_cash_ledger.sql` is new in this version;
  once it has been applied to production it is frozen like the others. Its last step drops the unused
  `backup_snapshots` table (made by 003). Add new constraints on existing tables as `NOT VALID`.
- **Backups are emailed, never stored.** The nightly job and "Email backup now" build the v3 backup in memory
  and email it as an AES-256 ZIP; there is no snapshot table, list, download or retention. Don't add one back
  without the user's approval. Import backup accepts the emailed ZIP (+ password, never stored, logged or
  audited), the `.json` inside it, or a `.json.gz`; a restore keeps no copy of the old data (the page warns).
- A new column that must survive backup/restore goes in `domain/backup_codec.py` `TABLES`; secrets never do.
  `app_settings` keys that belong to this server only (`backup_email`, `backup_email_status`) go in
  `LOCAL_SETTINGS`, so they are never exported or restored.
- The app connects as the table owner; RLS stays enabled with no policies.

**Design system and UI**
- Build with `ui/` components: `Button` / `IconButton` (always with `label`), fields from `ui/fields.jsx`,
  `Modal` / `ConfirmDialog`, `useToast`, `DataTable`, `EmptyState` / `ErrorState` / `PageLoading`,
  `PageHeader`, `Card`, `Banner`, `Pill`.
- Colours only through `tokens.css` variables (`var(--color-…)`), spacing `var(--space-1…8)`, type
  `var(--text-xs…2xl)`. Add a new colour as a token in **both** themes and keep `tests/contrast.test.js` passing.
  No hex colours in components (the logo in `AppShell.jsx` is the only exception).
- CSP forbids inline `<style>`/`<script>` and `style="…"` strings. A computed value may use React's `style={{ … }}`
  prop (as `charts.jsx` does); everything else goes in CSS classes.
- No `alert`, `confirm`, `prompt`, `dangerouslySetInnerHTML`, `console.log`. Only the theme preference
  is kept in `localStorage`.
- Data loading: `useAsync(loader, deps, resetKey)`. Submitting: `useSubmit(action)` (prevents double submits).
  Page titles: `useDocumentTitle`.

**Accessibility**
- Every field has a visible label. Errors go through the field's `error` prop (wired by `aria-describedby`),
  and after a failed submit call `focusFirstError(form)`. Hints go through `hint`.
- Dialogs: `Modal` with a `title`; pass `focusKey` when content changes (for example, form → success).
- Status is never shown by colour alone (text or icon too). Touch targets ≥ 24 px. Malayalam text gets `lang="ml"`.

**Printing**
- Receipt data always comes from `/receipts/*`, never from page state or the URL. Nothing sensitive goes in URLs.

## 5. Recipes

**Change wording or a label.** Grep the text. If it comes from the server (a service's `raise …("…")`), change
it there, plus any test asserting it. Keep the tone plain and short; say what to do next.

**Add a field to a form.**
1. Use the right `ui/fields.jsx` field with `label`, `hint` and `error`.
2. Validate in the browser with `lib/validation.js` (mirroring the server).
3. Add it to the API wrapper's body.
4. Add it to the Pydantic model in `app/schemas.py`. Unknown fields are rejected, so this is required.
5. Validate and store it in the service, and add the SQL in the repository.
6. If a new column is needed, follow the database recipe below.
7. Add tests in `test_services.py` and, if it's new markup, in `Frontend/tests/pages.test.jsx`.

**Add a column to a table or report.**
1. Add it to the repository's `SELECT`.
2. Expose it in the service's serializer (`services/serialize.py` or the service). Money goes out as a string.
3. Add it to the `DataTable` `columns` (`numeric: true` for amounts).
4. For the CSV, update `domain/reports.py` and its test.

**Add an API endpoint.**
1. Add the route in the right `routers/*.py`, with `ActorDep` (signed in) and a schema for the body.
2. Add a service function that calls `actor.require(...)` plus `resolve_scope`/`ensure_visible`.
3. Put the SQL in the repository.
4. Add the wrapper to `api/endpoints.js`.
5. Add tests (service with `tests/fakes.py`; SQL in `test_repositories.py`) and list them in `docs/INTEGRITY.md`.
6. Add the row to the API catalogue in `docs/ARCHITECTURE.md`.

**Add a database column.**
1. Write a new migration `migrations/006_<name>.sql` (`ADD COLUMN IF NOT EXISTS`), and add it to the steps in
   `scripts/migrate.py`.
2. Update the repository SQL, `tests/fakes.py`, `backup_codec.TABLES` if it is business data, and the
   data model table in `docs/ARCHITECTURE.md`.
3. Never backfill legacy ledger rows.

**Add a page or route.**
1. Create a lazy page in `features/<area>/`.
2. Add the route in `app/routes.jsx`, wrapped in `RequirePermission` with the same rule the server uses.
3. Add the nav entry in `ui/AppShell.jsx` if needed.
4. Add the row to the map in section 2 of this file and the route table in `docs/ARCHITECTURE.md`.
5. Add a render test per role in `pages.test.jsx`.

**Add a permission-gated button.** Show it with `can(user, "<feature>")`. The server must already refuse the
action without that feature; if it doesn't, that is a server change: ask first.

**Change a colour, spacing or size.** Change or add a token in `ui/tokens.css` (light **and** dark), or a class
in `ui/components.css`. Run the contrast test. Check print (`print/print.css`) if receipts are affected.

## 6. Checks (all offline)

Run from the folder shown. Use `py` on this machine.

```bash
# BackendPython/
py -m unittest discover -s tests -t .        # all backend tests (domain, security, services, SQL, middleware, docs/INTEGRITY.md)
py -m compileall -q app scripts tests        # syntax check

# Frontend/
node scripts/run-tests.mjs                   # = npm test: lib, client, UI, pages, contrast
node scripts/check-bundle.mjs                # = npm run check: bundles offline, rejects unexpected imports
node node_modules/vite/bin/vite.js build     # = npm run build
npm run lint                                 # if node_modules has eslint
```

Run the backend checks if you touched `BackendPython/`, and the frontend checks if you touched `Frontend/`.
A business-rule change (only with approval) runs both, because `test-vectors/interest.json` is shared.

**Grep gates.** Each pattern must find nothing new under `Frontend/src`, apart from the existing exceptions in brackets:

| Pattern | Why |
|---|---|
| `parseFloat`, `toFixed(`, `Number(` on amounts | float money |
| `toISOString().slice` | non-IST dates (only inside `lib/dates.js`) |
| `#[0-9a-fA-F]{3,6}` in `.jsx` | hard-coded colour (logo in `AppShell.jsx`) |
| `dangerouslySetInnerHTML`, `alert(`, `confirm(`, `console.log` | security, UX |
| `fetch(` outside `api/client.js` | bypasses CSRF, timeouts and errors |
| `localStorage` | only the theme (`ui/theme.js`) and the cleanup in `AuthContext.jsx` |

Under `BackendPython/app`:

| Pattern | Why |
|---|---|
| `float(` | float money |
| `from fastapi` / `import asyncpg` in `services/`, `domain/`, `security/` | layering |
| `infra` imported from `services/`, `domain/`, `security/` | layering: services get the mailer as a parameter |
| `smtplib`, `pyzipper` anywhere except `app/infra/` | network and encryption code stays in one place |
| `f"SELECT` / `f"UPDATE` / `.format(` with SQL anywhere | SQL injection risk |
| `print(` | use `app/logs.py` |

## 7. Definition of done, and the reply

Done means:
- [ ] The change is in the layer that owns the behaviour, and is as small as it can be.
- [ ] No invariant in section 4 is broken; the grep gates are clean.
- [ ] A test covers the change and is listed in [docs/INTEGRITY.md](docs/INTEGRITY.md); all relevant checks
  pass (paste the counts).
- [ ] Shared components changed? Every user was checked.
- [ ] Docs updated if a route, endpoint, table or rule changed (`docs/ARCHITECTURE.md`, this map,
  `docs/INTEGRITY.md` for tests and gates).
- [ ] Nothing was run against a database or the network; no `.env` file was touched.

Reply to the user in this shape:

```
What was wrong: <one or two sentences, in the user's terms>
What I changed: <file:line links, one line each>
Checks: backend <n> tests OK · frontend <n> tests OK · bundle/build OK   (or what failed, with output)
Not done / needs you: <anything skipped, any question>
```

## 8. Don'ts

- Don't rewrite a page or component to fix one detail.
- Don't rename or move shared files (`ui/*`, `lib/*`, `api/*`, services, repositories).
- Don't duplicate logic that already exists (money, dates, validation, permissions, ledger labels): import it.
- Don't add a dependency, a CSS framework, an icon pack or a font.
- Don't compute balances, interest or totals in the browser for anything that is saved or shown as owed.
- Don't loosen a permission check or a validation to "make it work". Find out why it refuses.
- Don't skip or weaken tests; don't delete a failing test.
- Don't touch migrations 000–004 (or 005 once it is applied to production), `test-vectors/interest.json`,
  `.env*` files, or `package-lock.json` by hand.
- Don't guess what a screenshot means when two readings change money or access differently: ask.
