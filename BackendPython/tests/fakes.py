"""In-memory repositories with the same interface as app.repositories.Repos.

Transactions snapshot the whole state and restore it on error, like Postgres would,
so tests also prove that failed operations leave nothing behind.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from decimal import Decimal

from app.security import passwords


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


class State:
    def __init__(self):
        self.users: dict[str, dict] = {}
        self.sessions: dict[bytes, dict] = {}
        self.throttle: dict[tuple[str, str], dict] = {}
        self.counters: dict[str, int] = {}
        self.customers: dict[int, dict] = {}
        self.loans: dict[str, dict] = {}
        self.statements: list[dict] = []
        self.audit: list[dict] = []
        self.settings: dict[str, dict] = {}
        self.snapshots: list[dict] = []
        self.next_ids = {"customer": 1, "loan": 1, "statement": 1, "snapshot": 1}


class Transaction:
    def __init__(self, repos: "MemoryRepos"):
        self.repos = repos

    async def __aenter__(self):
        self.saved = copy.deepcopy(self.repos.state)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self.repos.state.__dict__.update(self.saved.__dict__)
        return False


class _Part:
    def __init__(self, repos: "MemoryRepos"):
        self.repos = repos

    @property
    def s(self) -> State:
        return self.repos.state


class Users(_Part):
    async def get(self, username):
        for name, row in self.s.users.items():
            if name.lower() == username.lower():
                return dict(row)
        return None

    async def list_accounts(self):
        return [dict(r, has_password=bool(r.get("password"))) for r in self.s.users.values()]

    async def branches(self):
        return [dict(r) for r in self.s.users.values() if r.get("branch_prefix")]

    async def branch(self, prefix):
        return next((dict(r) for r in self.s.users.values() if r.get("branch_prefix") == prefix), None)

    async def branch_prefixes(self):
        return {r["branch_prefix"] for r in self.s.users.values() if r.get("branch_prefix")}

    async def create(self, *, username, password_hash, account_type, branch_prefix, display_name, legal_name,
                     address, phone, email, logo, permissions):
        self.s.users[username] = dict(
            username=username, password=password_hash, account_type=account_type, branch_prefix=branch_prefix,
            display_name=display_name, legal_name=legal_name, address=address, phone=phone, email=email, logo=logo,
            permissions=permissions, is_active=True, must_change_password=True,
        )

    async def update_settings(self, username, fields):
        self.s.users[username].update(fields)

    async def set_password(self, username, password_hash, *, must_change):
        self.s.users[username].update(password=password_hash, must_change_password=must_change)

    async def upgrade_hash(self, username, password_hash):
        self.s.users[username]["password"] = password_hash

    async def set_active(self, username, active):
        self.s.users[username]["is_active"] = active

    async def delete(self, username):
        del self.s.users[username]

    async def customer_count(self, prefix):
        return sum(1 for c in self.s.customers.values() if c["branch_prefix"] == prefix)

    async def ensure_counter(self, prefix):
        self.s.counters.setdefault(prefix, 1)


class Sessions(_Part):
    async def create(self, token_hash, username, now, expires_at, ip, user_agent):
        self.s.sessions[token_hash] = dict(username=username, last_seen_at=now, expires_at=expires_at)

    async def get(self, token_hash):
        session = self.s.sessions.get(token_hash)
        if session is None or session["username"] not in self.s.users:
            return None
        return {**self.s.users[session["username"]], **session}

    async def touch(self, token_hash, now):
        self.s.sessions[token_hash]["last_seen_at"] = now

    async def delete(self, token_hash):
        self.s.sessions.pop(token_hash, None)

    async def delete_for_user(self, username, keep=None):
        for key in [k for k, v in self.s.sessions.items() if v["username"] == username and k != keep]:
            del self.s.sessions[key]

    async def purge_expired(self, now, idle_cutoff):
        for key in [k for k, v in self.s.sessions.items() if v["expires_at"] <= now or v["last_seen_at"] <= idle_cutoff]:
            del self.s.sessions[key]


class Throttle(_Part):
    async def get(self, username, key):
        row = self.s.throttle.get((username.lower(), key))
        return dict(row) if row else None

    async def purge(self, stale_before, now, trusted_before):
        for key, row in list(self.s.throttle.items()):
            trusted = key[1].startswith("trusted:")
            if (trusted and row["updated_at"] < trusted_before) or (
                not trusted and row["updated_at"] < stale_before and (row["locked_until"] is None or row["locked_until"] < now)
            ):
                del self.s.throttle[key]

    async def lock_row(self, username, key, now):
        row = self.s.throttle.setdefault((username.lower(), key), dict(failures=0, locked_until=None, updated_at=now))
        return dict(row)

    async def save(self, username, ip, failures, locked_until, now):
        self.s.throttle[(username.lower(), ip)] = dict(failures=failures, locked_until=locked_until, updated_at=now)

    async def clear(self, username, ip):
        self.s.throttle.pop((username.lower(), ip), None)

    async def clear_user(self, username):
        for key in [k for k in self.s.throttle if k[0] == username.lower()]:
            del self.s.throttle[key]


class Customers(_Part):
    async def search(self, branch, term, limit, offset):
        rows = [c for c in self.s.customers.values() if branch is None or c["branch_prefix"] == branch]
        if term:
            rows = [c for c in rows if term.lower() in c["customername"].lower() or term in c["phone"]]
        rows.sort(key=lambda c: -c["customerid"])
        return [dict(r) for r in rows[offset:offset + limit]], len(rows)

    async def get(self, customer_id):
        row = self.s.customers.get(customer_id)
        return dict(row) if row else None

    async def by_phone(self, phone):
        return next((dict(c) for c in self.s.customers.values() if c["phone"] == phone), None)

    lock = get

    async def next_customer_number(self, branch):
        if branch not in self.s.counters:
            return None
        number = self.s.counters[branch]
        self.s.counters[branch] = number + 1
        return number

    async def user_id_taken(self, user_id):
        return any(c["user_id"].upper() == user_id.upper() for c in self.s.customers.values())

    async def insert(self, *, name, phone, address, user_id, branch):
        cid = self.s.next_ids["customer"]
        self.s.next_ids["customer"] += 1
        self.s.customers[cid] = dict(customerid=cid, customername=name, phone=phone, address=address, user_id=user_id,
                                     branch_prefix=branch, loanstatus="0", last_loan_no=0, created_at=utc(2025, 1, 1))
        return dict(self.s.customers[cid])

    async def next_loan_number(self, customer_id):
        self.s.customers[customer_id]["last_loan_no"] += 1
        return self.s.customers[customer_id]["last_loan_no"]

    async def refresh_loan_status(self, customer_id):
        open_ = any(l["customerid"] == customer_id and l["loantype"] == "open" for l in self.s.loans.values())
        self.s.customers[customer_id]["loanstatus"] = "1" if open_ else "0"


class Loans(_Part):
    def _with_customer(self, loan):
        customer = self.s.customers.get(loan["customerid"], {})
        row = dict(loan)
        for key in ("branch_prefix", "customername", "phone", "user_id", "address"):
            row[key] = customer.get(key)
        entries = sorted((s for s in self.s.statements if s["loan_number"] == loan["loan_number"]),
                         key=lambda s: (s["date"], s["statementid"]))
        if entries:
            row.update(last_entry_at=entries[-1]["date"], last_principal=entries[-1]["principlebalance"],
                       last_interest=entries[-1]["interestbalance"])
        else:
            row.update(last_entry_at=None, last_principal=None, last_interest=None)
        row["compoundings"] = sum(1 for s in entries if s["transactiontype"] == "compounding")
        payments = [s["date"] for s in entries if s["transactiontype"] == "addColl" and s["amountpaid"] > 0]
        row["last_payment_at"] = max(payments) if payments else None
        return row

    async def get(self, loan_number):
        loan = self.s.loans.get(loan_number)
        return self._with_customer(loan) if loan else None

    lock = get

    async def exists(self, loan_number):
        return any(k.upper() == loan_number.upper() for k in self.s.loans)

    async def for_customer(self, customer_id):
        return [self._with_customer(l) for l in self.s.loans.values() if l["customerid"] == customer_id]

    async def open_with_position(self, branch):
        rows = [self._with_customer(l) for l in self.s.loans.values() if l["loantype"] == "open"]
        return [r for r in rows if branch is None or r["branch_prefix"] == branch]

    async def insert(self, *, customer_id, loan_number, items_json, particulars, number_of_items, weight, deduction,
                     net_weight, principal, rate, tenure, branch, loan_date, created_by):
        lid = self.s.next_ids["loan"]
        self.s.next_ids["loan"] += 1
        self.s.loans[loan_number] = dict(
            loanid=lid, customerid=customer_id, loan_number=loan_number, items=json.loads(items_json),
            particulars=particulars, number_of_items=str(number_of_items), weight=weight, deduction=deduction,
            net_weight=net_weight, principle_amount=principal, interest=rate, tenure=tenure, date=loan_date,
            loantype="open", refreshprincipleamount=principal, refreshinterest=Decimal("0"), follow_up_date=None,
            closed_at=None, created_by=created_by,
        )
        return {"loanid": lid, "loan_number": loan_number}

    async def set_items(self, loan_number, items_json, particulars, number_of_items):
        self.s.loans[loan_number].update(items=json.loads(items_json), particulars=particulars,
                                         number_of_items=str(number_of_items))

    async def update_cache(self, loan_number, principal, interest):
        self.s.loans[loan_number].update(refreshprincipleamount=principal, refreshinterest=interest)

    async def mark_closed(self, loan_number, closed_at):
        self.s.loans[loan_number].update(loantype="closed", closed_at=closed_at, refreshprincipleamount=Decimal("0"),
                                         refreshinterest=Decimal("0"), follow_up_date=None)

    async def set_follow_up(self, loan_number, follow_up):
        self.s.loans[loan_number]["follow_up_date"] = follow_up


class Statements(_Part):
    def _for(self, loan_number):
        return sorted((s for s in self.s.statements if s["loan_number"] == loan_number),
                      key=lambda s: (s["date"], s["statementid"]))

    async def latest(self, loan_number):
        rows = self._for(loan_number)
        return dict(rows[-1]) if rows else None

    async def history(self, loan_number):
        return [dict(date=s["date"], transactiontype=s["transactiontype"], accrued_days=s["accrued_days"])
                for s in self._for(loan_number)]

    async def compounding_count(self, loan_number):
        return sum(1 for s in self._for(loan_number) if s["transactiontype"] == "compounding")

    async def by_request_id(self, request_id):
        return next(({"statementid": s["statementid"], "loan_number": s["loan_number"]}
                     for s in self.s.statements if s.get("client_request_id") == request_id), None)

    async def insert(self, *, loan_id, loan_number, kind, at, amount_paid, current_principal, current_interest,
                     principal_balance, interest_balance, accrued_days, writeoff_principal, writeoff_interest,
                     created_by, request_id):
        if request_id and any(s.get("client_request_id") == request_id for s in self.s.statements):
            raise AssertionError("duplicate client_request_id")
        sid = self.s.next_ids["statement"]
        self.s.next_ids["statement"] += 1
        self.s.statements.append(dict(
            statementid=sid, loanid=loan_id, loan_number=loan_number, transactiontype=kind, date=at,
            amountpaid=amount_paid, currentprincipal=current_principal, currentinterest=current_interest,
            principlebalance=principal_balance, interestbalance=interest_balance, accrued_days=accrued_days,
            writeoff_principal=writeoff_principal, writeoff_interest=writeoff_interest, created_by=created_by,
            client_request_id=request_id, created_at=at,
        ))
        return sid

    async def for_loan(self, loan_number):
        return [dict(s) for s in reversed(self._for(loan_number))]

    async def get(self, statement_id):
        return next((dict(s) for s in self.s.statements if s["statementid"] == statement_id), None)


class Audit(_Part):
    async def log(self, **entry):
        self.s.audit.append(entry)


class Settings(_Part):
    async def get(self, key):
        return copy.deepcopy(self.s.settings.get(key))

    async def put(self, key, value, updated_by):
        self.s.settings[key] = {"value": value, "updated_at": utc(2025, 1, 1), "updated_by": updated_by}


class MemoryRepos:
    def __init__(self):
        self.state = State()
        self.users = Users(self)
        self.sessions = Sessions(self)
        self.throttle = Throttle(self)
        self.customers = Customers(self)
        self.loans = Loans(self)
        self.statements = Statements(self)
        self.audit = Audit(self)
        self.settings = Settings(self)

    def transaction(self):
        return Transaction(self)

    # ── fixtures ────────────────────────────────────────────────────────────────
    def add_account(self, username, password, account_type, prefix=None, permissions="newcustomer,userlist,form1,analytics,report,history",
                    **extra):
        self.state.users[username] = dict(
            username=username, password=passwords.hash_password(password, iterations=1000) if password else None,
            account_type=account_type, branch_prefix=prefix, display_name=extra.pop("display_name", username),
            legal_name=None, address=None, phone=None, email=None, logo=None, permissions=permissions,
            is_active=extra.pop("is_active", True), must_change_password=extra.pop("must_change_password", False),
            **extra,
        )
        if prefix:
            self.state.counters.setdefault(prefix, 1)


def standard_repos() -> MemoryRepos:
    repos = MemoryRepos()
    repos.add_account("Admin", "Head-office-2026", "hq", "AD")
    repos.add_account("User1", "Santhwanam-2026", "branch", "SAN")
    repos.add_account("User2", "Swathantra-2026", "branch", "SWA")
    repos.add_account("root", "Super-admin-2026", "superadmin")
    return repos
