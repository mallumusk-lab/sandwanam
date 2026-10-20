# Gold Loan Desk

Gold-loan management for a group of branches. **Branch staff** register customers, record pledged gold,
issue loans, take payments, close loans and print receipts. **Head office** sees every branch, sets the
daily gold rate, reads reports and the audit log, and manages backups. A **SuperAdmin** creates branches
and accounts, decides which features each branch gets, and is the only one who can restore a backup.

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

Web app: none. It always calls `/api` on its own origin.

## Commands

| Where | Command | Does |
|---|---|---|
| `BackendPython/` | `py -m unittest discover -s tests -t .` | all backend tests (rules, security, services, SQL, middleware) |
| `Frontend/` | `npm test` | helpers, API client, components, every page per role, colour contrast |
| `Frontend/` | `npm run check` | bundles the app offline; fails on unexpected dependencies |
| `Frontend/` | `npm run lint` · `npm run build` | lint · production build into `Frontend/dist` |
| `BackendPython/` | `py scripts/migrate.py --preflight` | read-only report on the database before migrating |
| `BackendPython/` | `py scripts/migrate.py [--branch-prefix USER=PREFIX …]` | apply migrations 001–003 and the data steps |
| `BackendPython/` | `py scripts/migrate.py --post-cutover` | migration 004: drop the legacy trigger, validate constraints |
| `BackendPython/` | `py scripts/create_superadmin.py <username> "<name>"` | create a SuperAdmin (there are no default accounts) |
| `BackendPython/` | `py scripts/set_password.py <username> [--permanent] [--activate]` | set a password (temporary unless `--permanent`) |

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
   account. It applies 001–003, converts item lists, and **disables every account that still has a default
   or plaintext password**.
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

## Backups and recovery

- A compressed snapshot is stored in the database every night at 00:00 IST by the daily job. Each kind is
  kept separately: the last 14 nightly snapshots, the last 10 pre-restore safety snapshots, and the last 5
  manual snapshots (at most one every 10 minutes).
- *Backups* offers "Save a snapshot now" and JSON downloads. Store a downloaded backup off-site every week.
- Snapshots protect against mistakes, not against losing the database. **Keep Supabase's daily backups /
  point-in-time recovery switched on.**
- Restoring (SuperAdmin only, typed confirmation) replaces customers, loans and ledger entries. A safety
  snapshot is taken first. Accounts, passwords and the audit log are never changed.

## Business rules in brief

Full rules, with the reasons behind them, are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#4-business-rules-authoritative).

- Rates are annual (% p.a.): interest = principal × rate × days ÷ 36500, rounded half-up to the paisa.
- A period ending in a customer event counts both its first and last day: (end − start) + 1.
- Interest compounds yearly on the loan date + 365 days (then + 730, …).
- Closing within 7 days charges at least 7 days of interest. In the first 7 days a payment can cover interest only.
- Payments settle interest first, then principal. Paying everything owed is done with **Close loan**.
- Branches always record "now". Head office may record past dates (never before the latest entry).
  Past-dated loans from a branch come only through **History import**, a feature granted by the SuperAdmin.
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
