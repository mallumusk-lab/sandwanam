"""In-memory backups repository and a recording mailer, attached to a tests.fakes
MemoryRepos (`with_backups(standard_repos())`). Like the real BackupsRepo it only exports
and replaces business data: backups are never stored."""
from __future__ import annotations

import copy
import json

from app.domain import backup_codec
from tests.fakes import MemoryRepos


class Backups:
    def __init__(self, repos: MemoryRepos):
        self.repos = repos

    @property
    def s(self):
        return self.repos.state

    async def export_rows(self):
        s = self.s
        branches = [dict(u) for u in s.users.values() if u["account_type"] != "superadmin"]
        return {
            "branches": sorted(branches, key=lambda u: u["username"]),
            "branch_counters": [{"branch_prefix": p, "next_customer_no": n, "next_receipt_no": s.receipt_counters.get(p, 1)} for p, n in sorted(s.counters.items())],
            "customers": [dict(c) for _, c in sorted(s.customers.items())],
            "loan_data": sorted((dict(l) for l in s.loans.values()), key=lambda l: l["loanid"]),
            "statement": sorted((dict(e) for e in s.statements), key=lambda e: e["statementid"]),
            "app_settings": [dict(v, key=k) for k, v in sorted(s.settings.items())],
            "cash_days": [dict(d) for _, d in sorted(s.cash_days.items())],
            "cash_entries": sorted((dict(e) for e in s.cash_entries), key=lambda e: e["id"]),
        }

    async def missing_branches(self, prefixes):
        known = {u["branch_prefix"] for u in self.s.users.values() if u.get("branch_prefix")}
        return sorted(set(prefixes) - known)

    async def replace_business_data(self, tables):
        s = self.s
        rows = {t: [dict(zip(backup_codec.columns(t), row)) for row in tables.get(t, [])] for t in backup_codec.TABLES}
        s.customers = {c["customerid"]: c for c in rows["customers"]}
        s.loans = {}
        for loan in rows["loan_data"]:
            loan["items"] = json.loads(loan["items"]) if loan["items"] else None
            s.loans[loan["loan_number"]] = loan
        s.statements = rows["statement"]
        s.cash_days = {d["id"]: d for d in rows["cash_days"]}
        s.cash_entries = rows["cash_entries"]
        for name, ids in (("customer", s.customers), ("loan", [l["loanid"] for l in s.loans.values()]),
                          ("statement", [e["statementid"] for e in s.statements]),
                          ("cash_day", s.cash_days), ("cash_entry", [e["id"] for e in s.cash_entries])):
            s.next_ids[name] = max(ids, default=0) + 1
        for branch in rows["branches"]:
            user = s.users.get(branch["username"])
            if user is not None and user.get("branch_prefix") == branch["branch_prefix"]:
                user.update({k: branch[k] for k in ("display_name", "address", "phone", "email", "logo")})
        for counter in rows["branch_counters"]:
            s.counters[counter["branch_prefix"]] = counter["next_customer_no"]
            if "next_receipt_no" in counter:
                s.receipt_counters[counter["branch_prefix"]] = counter["next_receipt_no"]
        for setting in rows["app_settings"]:
            s.settings[setting["key"]] = {"value": json.loads(setting["value"]), "updated_at": setting["updated_at"],
                                          "updated_by": setting["updated_by"]}


def with_backups(repos: MemoryRepos) -> MemoryRepos:
    repos.backups = Backups(repos)
    return repos


class MailFailure(Exception):
    """What app.infra.mailer.MailError looks like to a service."""

    def __init__(self, public_message="The mail server could not be reached (TimeoutError)."):
        super().__init__(public_message)
        self.public_message = public_message


class FakeMailer:
    """Records what would be sent. `fail` makes send raise; `zip_size` pads the ZIP."""

    def __init__(self, *, fail: Exception | None = None, zip_size: int | None = None):
        self.fail = fail
        self.zip_size = zip_size
        self.sent: list[dict] = []
        self.zipped: list[list[tuple[str, bytes]]] = []

    def encrypt_zip(self, entries, *, modified):
        entries = [(name, bytes(data)) for name, data in entries]
        self.zipped.append(entries)
        body = b"PK-fake:" + b"|".join(name.encode() for name, _ in entries)
        return body if self.zip_size is None else body.ljust(self.zip_size, b"\0")

    async def send(self, *, to, subject, text, attachment=None):
        if self.fail is not None:
            raise self.fail
        self.sent.append({"to": to, "subject": subject, "text": text, "attachment": copy.copy(attachment)})
