# Gold Loan Desk

Gold-loan management for a group of branches. **Branch staff** register customers, record pledged gold,
issue loans, take payments, close loans, print or share receipts, and keep the branch's daily **cash ledger**
(the drawer book). **Head office** (HQ) sees every branch,
sets the daily gold rate, reads the dashboard, reports and the audit log, and manages backups. A
**SuperAdmin** creates branches and accounts, decides which features each branch gets, and is the only one
who can restore a backup or set the backup email address.

| Role | Sees | Can use |
|---|---|---|
| Branch | its own branch only | the features the SuperAdmin grants it (dashboard, customers, new customers and loans, reports, history import, loan calculator, cash ledger) |
| Head office (HQ) | every branch; the picker's **Admin – all branches** shows them together, or pick one | every branch feature, gold rate, audit log, backups ("Email backup now", backup email status, Check a backup file). The cash ledger is always one branch at a time (chosen on the page); there is no combined drawer. Only head office can reopen a closed cash day. |
| SuperAdmin | every branch | customers and loans of any branch (find, add, payments, add principal, close, edit items, follow-ups, receipts), backups including "Email backup now", Import (restore) and the backup email address, Branches & Users. **Not** the dashboard, reports, history import, cash ledger, gold rate or audit log; the server refuses them. |

Branch features are switched on or off per branch by the SuperAdmin on *Branches & Users*. The server checks
the same keys on every request.

| Feature (as shown) | Key | New branches get it |
|---|---|---|
| Dashboard | `analytics` | yes |
| Customers | `userlist` | yes |
| New customers and loans (needs Customers too) | `newcustomer` | yes |
| Reports | `report` | yes |
| Loan calculator | `form1` | yes |
| Cash ledger | `cashbook` | yes (migration 005 also grants it to every existing branch) |
| History import (enters past-dated loans) | `history` | no, only when the SuperAdmin grants it |

| Part | Technology | Location |
|---|---|---|
| Web app | React 18, React Router, Vite (no other runtime dependencies) | `Frontend/` |
| API | Python 3.12, FastAPI, asyncpg, Pydantic v2 | `BackendPython/` |
| Database | PostgreSQL on Supabase | `BackendPython/migrations/` |
| Hosting | One Vercel project; the API is served under `/api` on the same domain, plus a daily cron | `vercel.json` |

**Documentation**
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): how it is built: layers, business rules, data model,
  security, API catalogue, frontend, deployment, tests.
- [CLAUDE.md](CLAUDE.md): the rules every change follows (screen → code map, invariants, checks). Claude
  Code loads it automatically; human contributors should read it too.
- [docs/INTEGRITY.md](docs/INTEGRITY.md): every test and what it protects, the grep gates and the manual checks.

## Quick start (local development)

Requirements: Python 3.12, Node 20, and a **development** Postgres database (never production).

```bash
# API, on http://127.0.0.1:8000
cd BackendPython
py -m pip install -r requirements-dev.txt
set DATABASE_URL=postgresql://…              # development database
set COOKIE_SECURE=false                      # only if your browser refuses Secure cookies on http://localhost
py -m uvicorn app.main:app --port 8000 --reload

# Web app, on http://localhost:5173 (proxies /api to :8000)
cd Frontend
npm ci
npm run dev
```

Use a **copy of the existing database** for development, migrated with the going-live steps below, then
`py scripts/create_superadmin.py <username> "<name>"`. An empty database is not supported yet, because
`migrate.py` runs its preflight checks before the baseline creates the tables (see
[known limitations](docs/ARCHITECTURE.md#14-known-limitations)).

## Environment variables

API (`BackendPython`; set them in Vercel → Project → Settings → Environment Variables):

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string. The Supabase **transaction pooler** URL (port 6543) is fine for the app. |
| `CRON_SECRET` | yes | At least 32 random characters. Vercel Cron sends it as `Authorization: Bearer …`. |
| `APP_ENV` | no | `production`, `preview` or `development`. Derived from `VERCEL_ENV` when unset. |
| `TRUSTED_ORIGINS` | no | Extra origins allowed to send changes (comma-separated). Not needed on a single domain. |
| `COOKIE_SECURE` | no | `false` only for plain-http local development. |
| `DOCS_ENABLED` | no | `true` serves the interactive API docs at `/docs` outside production. |
| `TRUST_PROXY_HEADERS` | no | Use `x-real-ip` / `x-forwarded-for` for client addresses. Default: on for Vercel (which sets them), off elsewhere. |
| `MIGRATION_DATABASE_URL` | scripts only | **Direct** connection (port 5432) for the scripts below. Falls back to `DATABASE_URL`. |
| `SMTP_HOST` | for backup email | Mail server, for example `smtp.gmail.com`. |
| `SMTP_PORT` | no | `587` (STARTTLS, the default) or `465` (TLS from the start). Mail is never sent unencrypted. |
| `SMTP_USERNAME` | for backup email | Login for the mail server. Set it together with `SMTP_PASSWORD`. |
| `SMTP_PASSWORD` | for backup email | Password for `SMTP_USERNAME`. For Gmail, use an **app password** (Google account → Security → 2-Step Verification → App passwords), not the account password. |
| `SMTP_FROM` | no | Sender address. Defaults to `SMTP_USERNAME` when that is an address. |
| `BACKUP_ZIP_PASSWORD` | for backup email | 12–128 characters. The emailed ZIP is AES-256 encrypted with it. Keep it somewhere other than the mailbox. |

The six mail settings are optional for the API, but **every backup email needs them**: without them the API runs
normally, no backup is emailed (nightly or "Email backup now"), and the Backups page lists what is missing. If the nightly job's email step times out, raise the function's **Max Duration** in Vercel → Project →
Settings → Functions.

Web app: none. It always calls `/api` on its own origin.

## Commands

| Where | Command | Does |
|---|---|---|
| `BackendPython/` | `py -m unittest discover -s tests -t .` | all backend tests (rules, security, services, SQL, middleware, backups, email, the integrity list) |
| `Frontend/` | `npm test` | helpers, API client, components, every page per role, colour contrast |
| `Frontend/` | `npm run check` | bundles the app offline; fails on unexpected dependencies |
| `Frontend/` | `npm run lint` · `npm run build` | lint · production build into `Frontend/dist` |
| `BackendPython/` | `py scripts/migrate.py --preflight` | read-only report on the database before migrating |
| `BackendPython/` | `py scripts/migrate.py [--branch-prefix USER=PREFIX …]` | apply migrations 001–003 and 005 (cash ledger) and the data steps; already-applied files are skipped |
| `BackendPython/` | `py scripts/migrate.py --post-cutover` | migration 004: drop the legacy trigger, validate constraints |
| `BackendPython/` | `py scripts/create_superadmin.py <username> "<name>"` | create a SuperAdmin (there are no default accounts) |
| `BackendPython/` | `py scripts/set_password.py <username> [--permanent] [--activate]` | set a password (temporary unless `--permanent`) |
| `BackendPython/` | `py scripts/reset_all_passwords.py [--password PWD] [--random] [--permanent] [--activate]` | reset passwords for all accounts in the database |

The scripts show the target database and ask you to type its name before changing anything.
CI (`.github/workflows/ci.yml`) runs the tests, lint, bundle check and build, plus `pip-audit` and `npm audit`.

## Going live (one-time migration from the previous version)

Run every step against a **staging copy** of the database first.

1. **Preflight:** `py scripts/migrate.py --preflight`. It changes nothing. Fix everything marked *blocking*:
   - duplicate customer numbers
   - branch accounts other than Admin/User1/User2 that need a customer-number prefix (given in step 3)
   - open loans whose latest entry has a negative balance
   - loans with invalid amounts, weights or status

   Review the rest. `migrate.py` refuses to run while blocking items remain.
2. **Stop the old deployment.** It accepts the public key `12345`, so it must not run against the migrated database.
3. **Migrate:** `py scripts/migrate.py`, adding `--branch-prefix <username>=<PREFIX>` for each extra branch
   account. It applies 001–003 and 005, converts item lists, and **disables every account that still has a
   default or plaintext password**.
4. **Accounts:** `py scripts/create_superadmin.py <username> "<name>"`, then
   `py scripts/set_password.py <username>` for each branch account. Temporary passwords must be changed at
   first sign-in. A deactivated account stays deactivated unless you add `--activate`.
5. **Deploy** this version and set the environment variables above.
6. **Rotate the Supabase database password**, update `DATABASE_URL`, and delete old Preview deployments.
   This cuts off any old deployment still holding the previous password.
7. In *Branches*, check each branch's letterhead and upload its logo. Set today's rate under *Gold rate*.
8. When everything works: `py scripts/migrate.py --post-cutover`.

Ledger rows from the previous version are kept unchanged and are labelled "Earlier system" where their
meaning differs. (For example, their write-offs were stored as the balance at closing.)

### Updating a database that is already live: migration 005 (cash ledger)

This version adds `migrations/005_cash_ledger.sql`: two new tables (`cash_days`, `cash_entries`), the
`cashbook` permission for every existing branch, and `cashbook` in the default for new branches. It does not
read or change any loan, customer, ledger or settings table. Its last step drops the old `backup_snapshots`
table: backups are now emailed and never stored in the database, so any snapshots still in it are deleted.

1. Make sure you have a recent backup outside the app: press *Backups → Email backup now* (with the mail
   settings set) or keep Supabase's own backup, and check that the ZIP opens.
2. Against a staging copy first, then production: `py scripts/migrate.py`. It skips 001–003 (already
   applied, so no preflight runs), applies 005 in one transaction, and repeats the closing data steps: item
   lists already converted are left alone, and any account that still has a default or plaintext password is
   disabled again. Re-running it is safe.
3. Deploy this version **after** the migration: the new code expects the cash tables.
4. Once 005 has run on production it is an applied migration and must never be edited; later schema changes
   go in a new numbered file.

## Backups and recovery

Backups are **emailed, never stored in the app**, so they use no database space.

- **Every night at 00:00 IST** the daily job (which first closes forgotten cash days and deletes old ones; see
  [Cash ledger](#cash-ledger)) builds a full backup in memory and emails it to the address the SuperAdmin set
  on *Backups → Backup email*, as a password-protected ZIP named with the IST date and time, for example
  `backup_2026-10-20_0001IST.zip`. Nothing is kept on the server. The Backups page and the audit log
  (`EMAIL_BACKUP`) show whether it was sent or why it failed.
- **Email backup now** (head office: HQ and SuperAdmin) sends the same ZIP to the same address at once, at most
  once every 10 minutes. The page shows the result (Sent / Failed and the IST time); it is audited as
  `EMAIL_BACKUP_NOW`.
- The mail settings in [Environment variables](#environment-variables) (`SMTP_*` and `BACKUP_ZIP_PASSWORD`) are
  required for **any** backup email.
- About the ZIP:
  - It is AES-256 encrypted with `BACKUP_ZIP_PASSWORD`. The password is never in the email; keep it separate
    from the mailbox.
  - It holds `backup_<date>_<time>IST.json` (format v3: customers, loans, ledger entries, the cash ledger,
    branch letterheads and business settings) and a `README.txt`.
  - To open it yourself use **7-Zip** or **WinZip**; Windows Explorer cannot open AES-encrypted ZIP files.
  - Backups over 15 MB are not attached; the email says so.
- Keep the emailed files somewhere safe; they contain customer names, phone numbers and loans. **Keep
  Supabase's daily backups / point-in-time recovery switched on**: they remain the disaster-recovery layer.
- The checksum detects damage (a broken download, a truncated file). It does **not** prove who made the file,
  because anyone can recompute it. Keep backups where only you can change them.
- Migration 005 drops the old `backup_snapshots` table; there is no snapshot list, download or retention any more.

### If something goes wrong: import the emailed backup

*Backups → Import backup* brings a backup back. No 7-Zip is needed.

1. **Keep your own copy of the current data first.** Restoring replaces all data, and the app saves no copy
   before it does (press **Email backup now** first if the current data is worth keeping).
2. Sign in as the **SuperAdmin**, open **Backups**, and under **Import backup** press **Choose a backup file**.
   Pick the emailed `.zip` as it is. You can also pick the `.json` inside it (taken out with 7-Zip or WinZip)
   or an older `.json.gz`.
3. For a ZIP, type the **ZIP password** (`BACKUP_ZIP_PASSWORD`). It is sent over HTTPS only to open the file
   in memory, and is never stored, logged or audited. A wrong password says "The ZIP password is wrong."
4. Press **Check**. It changes nothing and shows when the backup was taken, "Checksum verified", the counts
   (branches, customers, loans, ledger entries, settings), warnings, and whether it can be restored here.
   Head office (HQ) can Check; only the SuperAdmin can import.
5. Press **Import**, read the warning ("Restoring replaces all data. Keep your own copy of the current data
   first."), type `RESTORE` and confirm. The page shows how many customers, loans and entries were restored.

Notes:
- Files up to about 3 MB compressed can be uploaded (the hosting limit is about 4.5 MB per request). For a
  larger backup, restore from Supabase's backups.
- A restore replaces customers, loans, ledger entries and the cash ledger, and updates branch letterheads and
  business settings. Accounts, passwords, feature permissions, the audit log and the backup email settings are
  never changed. A file whose customers, cash days or branch counters belong to a branch that does not exist here is reported by
  Check as not restorable, and restore refuses it.
- Older v2 `.json` backups can still be checked and restored; they hold no cash ledger, so restoring one
  leaves the cash ledger empty. Files downloaded before backups became email-only still import.

## Receipts

Loan vouchers and entry receipts print from the server's receipt data (`/receipts/*`). **Share**, next to
Print, makes a one-page PDF of the customer copy. On phones (and Chrome on Windows) it opens the system share
sheet, so you can pick WhatsApp, Mail and so on. Elsewhere it saves the PDF and offers WhatsApp and email
links: attach the saved file yourself. The links carry a short fixed message only, never receipt details.

## Cash ledger

*Branch operations → Cash ledger* (`/cash`) is the branch's drawer book: every rupee that goes in or out of
the cash drawer, entered by hand. It is **independent**: it never reads or changes loans, and its figures
appear nowhere else (not on the dashboard, reports, receipts or customer pages). Each branch has its own
drawer. The permission is **Cash ledger** (`cashbook`), set per branch; the SuperAdmin has no access.

**A day, step by step**
1. **Start the day.** The page shows the **carry forward**: the counted closing cash of the branch's last
   closed day (₹0.00 for a branch's first day). Staff count the drawer and enter **Cash in hand now
   (counted)**. Any difference from the carry forward is shown in words (Shortage ₹… / Excess ₹… / Matches)
   and saved with the day.
2. **Entries.** Choose **Cash in** or **Cash out**, a category, the amount, and optionally a description and
   a reference (bill or loan number). Entries are always dated today (IST).
   - Cash in: Loan collection, Cash from head office, Other income.
   - Cash out: Loan disbursement, Bill payment, Donation, Expense, Cash to head office / bank.
   - Either way: **Other (type a description)**, which needs a description. Descriptions typed for "Other"
     in the last 14 days are offered as suggestions.

   "Cash in drawer now" (opening counted + cash in − cash out) is worked out by the server after every save.
3. **Mistakes are voided, never deleted.** **Void** asks for a reason (at least 3 characters). The line stays
   listed, struck through and labelled "Voided" with its reason, and no longer counts.
4. **Count and close.** **Close the day** shows the expected cash; staff enter the counted cash and the
   difference is saved. A closed day is locked: no entries, voids or second close. If the figures changed
   while the dialog was open, closing is refused and the page refreshes.
5. **Reopen (head office only).** Head office can reopen a branch's day only if it is that branch's latest
   day and it is today, so the next day's carry forward stays right.

**Automatic close at midnight.** The daily job (00:00 IST) closes any day left open before today, storing
the expected cash as counted, and marks it "Closed automatically (not counted)". Starting a new day does the
same for a forgotten earlier day.

**14-day retention.** The ledger keeps today and the previous 13 days. The daily job **deletes** older days and
their entries completely, except each branch's latest day, which is kept for the carry forward. *Last 14 days*
lists the earlier days, one collapsed row per day; open a row to see that day's entries.

Every cash write is also recorded in the audit log, as security logging only.

## History import

*History import* (`/history`, feature `history`) enters a loan that was given **before** this system went
live, with its past entries: payments, additional principal and, if the loan was already settled, its
**closing**.

- Entry types: **Payment received**, **Additional principal** and **Loan closed (settled)**. A closing must
  be the last entry (nothing may be dated after it) and a loan closes only once. Its amount is the cash
  received at closing and may be ₹0.
- **Preview** replays the loan through the same engine as live entries and shows every row the import will
  store: interest, compounding on each anniversary, the first-7-days rule and the closing rows.
- If the cash received at closing is less than what was owed, the preview shows **Write off the remaining ₹…**
  with the server's amount. Without that tick the import is refused, exactly as **Close loan** refuses an
  unconfirmed write-off.
- A closed import is stored as closed on its closing date, with no follow-up and no compounding after the
  closing. An open import is compounded up to today.

**Live-vs-import parity.** An imported loan ends up exactly as if every entry had been recorded live on its own
date: the same ledger rows, statement calculations, balances, status and closing quote.
`BackendPython/tests/test_history_parity.py` runs each of these both ways and compares them:
- interest-only payments, part principal payments, and top-ups;
- a day 1–7 payment, then nothing until after the first anniversary;
- payments the day before, on, and the day after an anniversary;
- two years of compounding with part payments and a top-up; a loan dated 29 February;
- a payment and a top-up on the same day; an open loan compounded up to today;
- the agreed example (pay day 2, add day 4, close day 5: ₹414.25);
- closing on day 3 with no entries, and on days 7, 8 and 10; a closing after compounding;
- a closing with a confirmed write-off, with nothing received, and with full payment;
- a short closing without confirmation, which is refused the same way as live.

## Business rules in brief

Full rules, with the reasons behind them, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#4-business-rules-authoritative).

- Rates are annual (% p.a.): interest = principal × rate × days ÷ 36500, rounded half-up to the paisa.
- A period ending in a customer event counts both its first and last day: (end − start) + 1.
- Interest compounds yearly on the loan date + 365 days (then + 730, …).
- **First 7 days (peak principal).** Days 1–7 are charged as 7 days' interest on the highest principal reached
  in those days. A payment in those days reduces principal by its full amount, and no daily interest is
  recorded. The 7 days are charged at closing, or on the first entry after day 7 together with the days after
  day 7 on the current principal, rounded once. A payment that would clear the principal must use **Close loan**.
  Example: ₹1,00,000 at 18 % on day 1; pays ₹30,000 on day 2 (principal ₹70,000); adds ₹50,000 on day 4
  (₹1,20,000, the peak); closes on day 5. Interest = 1,20,000 × 18 × 7 ÷ 36500 = **₹414.25**, payoff
  **₹1,20,414.25**.
- After day 7, payments settle interest first, then principal. Paying everything owed is done with **Close loan**.
- Every daily entry (new loan, payment, add principal, closing) is dated **today**, for every role. Past dates
  come only through **History import**, a feature granted by the SuperAdmin.
- A loan is **overdue** once it has been open for more than 365 days. It is due for a **follow-up** from day 364
  automatically. Staff can set their own follow-up date on the dashboard or the customer page; clearing it
  brings back the automatic date. The dashboard lists a follow-up from 10 days before its date ("Due in N days",
  "Due today", then "Overdue by N days" until it is changed), and both its cards list every loan, 50 to a page.
- Customer numbers are `<branch prefix><n>` (e.g. `SAN12`); loan numbers are `<customer number>L<n>` (e.g. `SAN12L3`).

## Security in brief

- Server-side sessions in an HttpOnly, Secure, SameSite=Strict cookie, plus a CSRF token on every change.
  A session lasts 8 hours, or ends after 60 minutes idle.
- Sign-in attempts are throttled per address and per account; usual counters are exempt from the account-wide
  limit, so strangers can't lock staff out. Lockouts appear in the audit log.
- Passwords use PBKDF2-SHA256 (600,000 iterations); default and plaintext passwords never work.
- Branch accounts see only their own branch; **the server enforces this on every request.**

Details: [docs/ARCHITECTURE.md § Security model](docs/ARCHITECTURE.md#7-security-model).

## Making changes

Read [CLAUDE.md](CLAUDE.md) first. It maps each screen to its code, lists the invariants (money, dates,
access, design system, accessibility) and the checks to run. When asking Claude for a fix, paste a
screenshot and describe the change; it follows those rules automatically.

[docs/INTEGRITY.md](docs/INTEGRITY.md) lists every test with the rule it protects, the grep gates and the
manual checks. Add a line there for each new test; `tests/test_integrity_doc.py` fails until you do.
